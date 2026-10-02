"""
Contract Adapter v3.0 — 5-stage pipeline orchestrator.

New pipeline: 文件收集 → 合同生成 → 质量审查 ∥ 工作量统计 → 文档导出

Bridges the synchronous contract generation workflow with the async FastAPI server
by running in a thread pool executor and sending progress updates via WebSocket.

输出3个文件:
  1. {contract_id}.docx         — 格式化合同文档
  2. {contract_id}_审查报告.md   — 质量审查报告
  3. {contract_id}_工作量统计.md — 工作量统计报告
  4. {contract_id}_工作量统计.json — 工作量统计数据 (JSON)
"""

from __future__ import annotations

import sys
import asyncio
import os
import json
import time
import logging
import traceback
import concurrent.futures
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure the project root is on sys.path
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.loader import ConfigLoader
from src.llm.deepseek_client import DeepSeekClient, LLMError
from src.llm.prompt_builder import PromptBuilder
from src.llm.prompts import SECTION_DISPLAY_NAMES
from src.document.reader import read_file_auto
from src.document.generator import (
    generate_contract_docx,
    generate_review_report_docx,
    _generate_simple_docx,
)
from src.utils.date_utils import format_duration, compute_end_date, format_date, today_str

from .ws_manager import ConnectionManager, ws_manager as global_ws
from .session_manager import SessionManager, session_manager as global_sm
from .models import STAGE_DEFINITIONS, TOTAL_STAGES

logger = logging.getLogger(__name__)


class ContractAdapter:
    """Wraps the 5-stage contract generation pipeline for async execution.

    Usage:
        adapter = ContractAdapter(session_id, workspace, form_data)
        await adapter.run()
    """

    def __init__(
        self,
        session_id: str,
        workspace: Path,
        form_data: Dict[str, Any],
        ws_mgr: Optional[ConnectionManager] = None,
        sm: Optional[SessionManager] = None,
    ):
        self.session_id = session_id
        self.workspace = Path(workspace)
        self.form_data = form_data
        self.ws = ws_mgr or global_ws
        self.sm = sm or global_sm
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def run(self) -> bool:
        """Run the contract generation pipeline in a thread pool.

        Returns True on success, False on failure.
        """
        self._loop = asyncio.get_running_loop()

        try:
            await self.ws.send_echo(
                self.session_id,
                "🚀 合同生成流水线启动中...",
                "info",
            )

            result = await self._loop.run_in_executor(
                None,
                self._run_generation_sync,
            )

            if result:
                files = self.sm.list_output_files(self.session_id)
                await self.ws.send_pipeline_complete(self.session_id, files)
                self.sm.update_session(self.session_id, status="completed")
                return True
            else:
                await self.ws.send_pipeline_failed(
                    self.session_id,
                    "合同生成失败，请检查日志",
                )
                self.sm.update_session(self.session_id, status="failed")
                return False

        except Exception as e:
            tb = traceback.format_exc()
            await self.ws.send_pipeline_failed(self.session_id, f"{e}\n{tb}")
            self.sm.update_session(self.session_id, status="failed", error=str(e))
            return False

    # ── Synchronous generation (executed in thread pool) ──

    def _run_generation_sync(self) -> bool:
        """Run the 5-stage contract generation pipeline."""
        import threading

        _keepalive_stop = threading.Event()
        _keepalive_interval = 30

        def _keepalive_loop():
            while not _keepalive_stop.is_set():
                _keepalive_stop.wait(_keepalive_interval)
                if _keepalive_stop.is_set():
                    break
                if self._loop is None:
                    continue
                async def send_ka():
                    await self.ws.send_keepalive(self.session_id, "合同生成进行中...")
                try:
                    asyncio.run_coroutine_threadsafe(send_ka(), self._loop)
                except Exception:
                    pass

        keepalive_thread = threading.Thread(target=_keepalive_loop, daemon=True)
        keepalive_thread.start()

        try:
            # ── Load config ──
            config_path = PROJECT_ROOT / "config.yaml"
            config = ConfigLoader(str(config_path)).get_all()

            # ── Resolve paths ──
            examples_dir = PROJECT_ROOT / config.get("paths", {}).get("examples", "合同案例")
            if not examples_dir.exists():
                examples_dir = PROJECT_ROOT / "合同案例"

            source_dir = PROJECT_ROOT / "source"
            if not source_dir.exists():
                source_dir = PROJECT_ROOT / config.get("paths", {}).get("source", "source")

            profile_dir = PROJECT_ROOT / config.get("paths", {}).get("profile", "profile")

            # ── Create clients ──
            ds_config = config.get("deepseek", {})
            client = DeepSeekClient(ds_config)

            # ── Stage 0: 文件收集 ──
            self._emit_stage_start(0, "正在收集所有参考文件...")

            # ── 读取会话级上传文件 ──
            def _read_dir(dir_path: Path, label: str) -> List[tuple]:
                """Read all readable files from a directory, return [(label, filename), ...]."""
                results = []
                if not dir_path.exists():
                    return results
                for f in sorted(dir_path.iterdir()):
                    if not f.is_file() or f.name.startswith(".") or f.name.startswith("~$"):
                        continue
                    try:
                        ext = f.suffix.lower()
                        if ext in ('.txt', '.md', '.docx', '.doc', '.pdf', '.pptx', '.ppt', '.xlsx', '.xls'):
                            text = read_file_auto(str(f))
                            if text and not text.startswith("["):
                                results.append((f"【{label}：{f.name}】\n{text}", f.name))
                            else:
                                self._emit_echo(f"[警告] {label} 文件读取失败: {f.name}", "warn")
                    except Exception as e:
                        self._emit_echo(f"[警告] 无法读取 {label} 文件 {f.name}: {e}", "warn")
                return results

            # 核心文件（本次生成主要输入）
            core_items = _read_dir(self.workspace / "uploads", "核心文件")
            core_texts = [t for t, _ in core_items]

            # 参考文件（辅助参考）
            profile_items = _read_dir(self.workspace / "profile", "参考文件")
            profile_texts = [t for t, _ in profile_items]

            # 模板文件（合同模板参考）
            template_items = _read_dir(self.workspace / "templates", "模板")
            template_texts = [t for t, _ in template_items]

            self._emit_echo(
                f"[文件收集] 核心 {len(core_items)} + 参考 {len(profile_items)} + 模板 {len(template_items)}",
                "info"
            )

            # 缓存文件文本到 02_examples/
            stage1_dir = self.workspace / "02_examples"
            stage1_dir.mkdir(parents=True, exist_ok=True)

            # 缓存核心文件
            if core_items:
                cache_uploads = stage1_dir / "uploads"
                cache_uploads.mkdir(parents=True, exist_ok=True)
                src_dir = self.workspace / "uploads"
                for _, fname in core_items:
                    try:
                        src = src_dir / fname
                        if src.suffix.lower() in ('.txt', '.md'):
                            (cache_uploads / fname).write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
                        else:
                            (cache_uploads / (Path(fname).stem + '.txt')).write_text(read_file_auto(str(src)), encoding='utf-8')
                    except Exception as e:
                        self._emit_echo(f"[警告] 缓存失败 {fname}: {e}", "warn")

            # 缓存参考文件
            if profile_items:
                cache_profile = stage1_dir / "profile"
                cache_profile.mkdir(parents=True, exist_ok=True)
                src_dir = self.workspace / "profile"
                for _, fname in profile_items:
                    try:
                        src = src_dir / fname
                        if src.suffix.lower() in ('.txt', '.md'):
                            (cache_profile / fname).write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
                        else:
                            (cache_profile / (Path(fname).stem + '.txt')).write_text(read_file_auto(str(src)), encoding='utf-8')
                    except Exception as e:
                        self._emit_echo(f"[警告] 缓存失败 {fname}: {e}", "warn")

            self._emit_stage_complete(
                0,
                f"核心 {len(core_texts)} + 参考 {len(profile_texts)} + 模板 {len(template_texts)}"
            )

            # ── Build context ──
            prompt_builder = PromptBuilder(
                examples_dir=str(examples_dir),
                source_dir=str(source_dir),
                profile_texts=profile_texts,
                upload_texts=core_texts,
                template_texts=template_texts,
            )
            prompt_builder.load_contexts()

            user_inputs = self._build_user_inputs()
            llm_ctx = {
                "contract_id": self.form_data.get("contract_id", ""),
                "project_name": self.form_data.get("project_name", ""),
                "party_a": self.form_data.get("party_a", ""),
                "party_b": self.form_data.get("party_b", ""),
                "duration": user_inputs.get("aicc_service_timedelta", ""),
                "signing_place": self.form_data.get("signing_place", ""),
                "signing_date": self.form_data.get("signing_date", ""),
                "start_date": self.form_data.get("start_date", ""),
                "end_date": user_inputs.get("aicc_time_end", ""),
            }

            # ── Stage 1: 合同内容生成 ──
            self._emit_stage_start(1, "正在使用 AI 生成完整合同（13章）...")
            stage2_cache = self.workspace / "03_contract"
            stage2_cache.mkdir(parents=True, exist_ok=True)

            contract_md = ""
            try:
                system_prompt, user_prompt = prompt_builder.build_generation_prompt(llm_ctx)
                contract_md = client.generate(
                    section_name="完整合同生成",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                # 保存到缓存
                (stage2_cache / "contract_full.md").write_text(contract_md, encoding="utf-8")
                self._emit_stage_complete(1, f"合同生成完成 ({len(contract_md)} 字符)")
            except LLMError as e:
                self._emit_stage_failed(1, f"合同生成失败: {e}")
                self._emit_echo(f"[错误] 合同生成失败: {e}", "error")
                _keepalive_stop.set()
                return False
            except Exception as e:
                self._emit_stage_failed(1, f"合同生成异常: {e}")
                self._emit_echo(f"[错误] 合同生成异常: {e}", "error")
                _keepalive_stop.set()
                return False

            if not contract_md or len(contract_md.strip()) < 500:
                self._emit_stage_failed(1, "合同生成内容过短（<500字符），可能是API返回异常")
                _keepalive_stop.set()
                return False

            # ── 保存合同配置到 01_config/ ──
            stage0_dir = self.workspace / "01_config"
            stage0_dir.mkdir(parents=True, exist_ok=True)
            config_data = {
                "form_data": self.form_data,
                "user_inputs": user_inputs,
            }
            (stage0_dir / "contract_config.json").write_text(
                json.dumps(config_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # ── Stage 2 & 3: 并行执行审查和统计 ──
            review_result = [None]
            stats_md_result = [None]
            stats_json_result = [None]

            def run_review():
                """Stage 2: 合同质量审查"""
                self._emit_stage_start(2, "正在进行合同质量审查...")
                try:
                    sys_prompt, usr_prompt = prompt_builder.build_review_prompt(contract_md, llm_ctx)
                    review_text = client.generate(
                        section_name="合同质量审查",
                        system_prompt=sys_prompt,
                        user_prompt=usr_prompt,
                    )
                    (stage2_cache / "review_report.md").write_text(review_text, encoding="utf-8")
                    self._emit_stage_complete(2, f"质量审查完成 ({len(review_text)} 字符)")
                    return review_text
                except Exception as e:
                    error_msg = f"质量审查失败: {e}"
                    self._emit_stage_failed(2, error_msg)
                    self._emit_echo(f"[错误] {error_msg}", "error")
                    review_result[0] = f"# 审查报告生成失败\n\n错误: {e}"
                    return None

            def run_statistics():
                """Stage 3: 工作量统计"""
                self._emit_stage_start(3, "正在生成工作量统计...")
                try:
                    sys_prompt, usr_prompt = prompt_builder.build_statistics_prompt(contract_md, llm_ctx)
                    stats_text = client.generate(
                        section_name="工作量统计",
                        system_prompt=sys_prompt,
                        user_prompt=usr_prompt,
                    )
                    (stage2_cache / "statistics.md").write_text(stats_text, encoding="utf-8")
                    self._emit_stage_complete(3, f"工作量统计完成 ({len(stats_text)} 字符)")
                    return stats_text
                except Exception as e:
                    error_msg = f"工作量统计失败: {e}"
                    self._emit_stage_failed(3, error_msg)
                    self._emit_echo(f"[错误] {error_msg}", "error")
                    return None

            # 并行执行审查和统计
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_review = executor.submit(run_review)
                future_stats = executor.submit(run_statistics)

                review_text = future_review.result()
                stats_text = future_stats.result()

            # ── Stage 4: 文档导出 ──
            self._emit_stage_start(4, "正在生成文档文件...")

            contract_id = user_inputs.get("aicc_service_id") or \
                datetime.now().strftime("HT-%Y%m%d-%H%M%S")

            stage4_dir = self.workspace / "04_output"
            stage4_dir.mkdir(parents=True, exist_ok=True)

            output_files = []

            # 文件1: 合同 DOCX
            try:
                contract_docx_path = generate_contract_docx(
                    contract_md, str(stage4_dir), contract_id, self.form_data
                )
                output_files.append(Path(contract_docx_path).name)
                self._emit_echo(f"[文档] 合同 DOCX: {Path(contract_docx_path).name}", "info")
            except Exception as e:
                self._emit_echo(f"[错误] 合同 DOCX 生成失败: {e}", "error")

            # 文件2: 审查报告 (Markdown)
            if review_text:
                review_path = stage4_dir / f"{contract_id}_审查报告.md"
                review_path.write_text(review_text, encoding="utf-8")
                output_files.append(review_path.name)
                # 同时也生成 DOCX 版审查报告
                try:
                    generate_review_report_docx(review_text, str(stage4_dir), contract_id)
                except Exception:
                    pass

            # 文件3: 工作量统计 (Markdown + JSON)
            if stats_text:
                stats_path = stage4_dir / f"{contract_id}_工作量统计.md"
                stats_path.write_text(stats_text, encoding="utf-8")
                output_files.append(stats_path.name)

                # 提取 JSON 并单独保存
                json_match = __import__('re').search(r'```json\s*\n(.*?)\n```', stats_text, __import__('re').DOTALL)
                if json_match:
                    try:
                        stats_json = json.loads(json_match.group(1))
                        json_path = stage4_dir / f"{contract_id}_工作量统计.json"
                        json_path.write_text(
                            json.dumps(stats_json, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        output_files.append(json_path.name)
                    except json.JSONDecodeError:
                        pass

            # 复制合同DOCX到workspace根目录以兼容下载API
            import shutil
            docx_files = list(stage4_dir.glob(f"{contract_id}.docx"))
            for f in docx_files:
                root_copy = self.workspace / f.name
                if not root_copy.exists():
                    shutil.copy2(str(f), str(root_copy))

            self._emit_stage_complete(4, f"文档导出完成 ({len(output_files)} 个文件)")
            self._emit_echo(f"[成功] 合同生成完成！共生成 {len(output_files)} 个文件", "info")

            _keepalive_stop.set()
            return True

        except Exception as e:
            _keepalive_stop.set()
            if self._loop:
                async def send_err():
                    await self.ws.send_echo(
                        self.session_id,
                        f"合同生成异常: {e}",
                        "error",
                    )
                try:
                    asyncio.run_coroutine_threadsafe(send_err(), self._loop)
                except Exception:
                    pass
            return False

    def _build_user_inputs(self) -> Dict[str, str]:
        """Build the user input values dict."""
        fd = self.form_data

        # Parse start date
        start_str = fd.get("start_date", "")
        try:
            start_date = datetime.strptime(start_str, "%Y年%m月%d日").date()
        except (ValueError, TypeError):
            start_date = datetime.now().date()

        years = fd.get("duration_years", 0)
        months = fd.get("duration_months", 0)
        days = fd.get("duration_days", 0)
        end_date = compute_end_date(start_date, years, months, days)

        duration_text = format_duration(years, months, days)

        # Generate default contract ID if empty: HT-YYYYMMDD-XXXXXX
        import uuid
        contract_id = fd.get("contract_id", "").strip()
        if not contract_id:
            contract_id = f"HT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
            # Save back to form_data so DOCX generator can use it
            self.form_data["contract_id"] = contract_id

        return {
            "aicc_service_id": contract_id,
            "aicc_project_name": fd.get("project_name", "").strip(),
            "user_searcher": fd.get("party_a", "").strip(),
            "user_provider": fd.get("party_b", "").strip(),
            "aicc_apply_place": fd.get("signing_place", "").strip(),
            "aicc_write_date": fd.get("signing_date", today_str()),
            "aicc_time_start": format_date(start_date),
            "aicc_service_timedelta": duration_text,
            "aicc_time_end": format_date(end_date),
        }

    # ── Thread-safe emit helpers ──

    def _emit_stage_start(self, stage_id: int, message: str):
        progress_pct = int((stage_id / TOTAL_STAGES) * 100)
        if self._loop:
            async def send():
                await self.ws.send_stage_start(self.session_id, stage_id, message, progress_pct)
            try:
                asyncio.run_coroutine_threadsafe(send(), self._loop)
            except Exception:
                pass
        self.sm.update_session(self.session_id, current_stage=stage_id, status="running")

    def _emit_stage_complete(self, stage_id: int, detail: str):
        progress_pct = int(((stage_id + 1) / TOTAL_STAGES) * 100)
        if self._loop:
            async def send():
                await self.ws.send_stage_complete(self.session_id, stage_id, detail, progress_pct)
            try:
                asyncio.run_coroutine_threadsafe(send(), self._loop)
            except Exception:
                pass

    def _emit_stage_failed(self, stage_id: int, error: str):
        progress_pct = int(((stage_id + 1) / TOTAL_STAGES) * 100)
        if self._loop:
            async def send():
                await self.ws.send_stage_failed(self.session_id, stage_id, error, progress_pct)
            try:
                asyncio.run_coroutine_threadsafe(send(), self._loop)
            except Exception:
                pass

    def _emit_echo(self, message: str, level: str = "info"):
        if self._loop:
            async def send():
                await self.ws.send_echo(self.session_id, message, level)
            try:
                asyncio.run_coroutine_threadsafe(send(), self._loop)
            except Exception:
                pass
