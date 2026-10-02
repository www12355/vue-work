"""
Pipeline Adapter — wraps the existing BidPipeline for async server use.

Bridges the synchronous, blocking BidPipeline with the async FastAPI server
by running the pipeline in a thread pool executor and sending progress
updates via WebSocket.
"""

from __future__ import annotations

import sys
import argparse
import asyncio
import copy
import traceback
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Ensure the project root is on sys.path so bid_pipeline imports work
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent  # 标书自动生成/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from .ws_manager import ConnectionManager, ws_manager as global_ws
from .session_manager import SessionManager, session_manager as global_sm
from .models import STAGE_DEFINITIONS


# Total pipeline stages
TOTAL_STAGES = 11

class PipelineAdapter:
    """Wraps BidPipeline to run asynchronously with WebSocket progress reporting.

    Usage:
        adapter = PipelineAdapter(session_id, workspace_path, config_path, ws_manager)
        await adapter.run()
    """

    def __init__(
        self,
        session_id: str,
        workspace: Path,
        user_config: Dict[str, Any],
        ws_mgr: Optional[ConnectionManager] = None,
        sm: Optional[SessionManager] = None,
    ):
        self.session_id = session_id
        self.workspace = Path(workspace)
        self.user_config = user_config
        self.ws = ws_mgr or global_ws
        self.sm = sm or global_sm
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def run(self) -> bool:
        """Run the 11-stage pipeline in a thread pool, sending progress via WS.

        Returns True on success, False on failure.
        """
        self._loop = asyncio.get_running_loop()

        try:
            # ── Build pipeline args ──
            args = self._build_pipeline_args()

            # ── Run in thread pool ──
            await self.ws.send_echo(
                self.session_id,
                "🚀 标书生成流水线启动中...",
                "info",
            )

            result = await self._loop.run_in_executor(
                None,
                self._run_pipeline_sync,
                args,
            )

            if result == 0:
                # Success — send file list
                files = self.sm.list_output_files(self.session_id)
                await self.ws.send_pipeline_complete(self.session_id, files)
                self.sm.update_session(self.session_id, status="completed")
                return True
            else:
                await self.ws.send_pipeline_failed(
                    self.session_id,
                    f"流水线返回非零退出码: {result}",
                )
                self.sm.update_session(self.session_id, status="failed")
                return False

        except Exception as e:
            tb = traceback.format_exc()
            await self.ws.send_pipeline_failed(self.session_id, f"{e}\n{tb}")
            self.sm.update_session(self.session_id, status="failed", error=str(e))
            return False

    def _build_pipeline_args(self) -> argparse.Namespace:
        """Build argparse.Namespace mimicking CLI invocation for BidPipeline."""
        config_path = self.workspace / "pipeline_config.yaml"

        # Write a session-specific pipeline config
        self._write_session_config(config_path)

        return argparse.Namespace(
            config=str(config_path),
            docx=None,
            resume=False,
            status=False,
            from_stage=None,
            only_stage=None,
            count=None,
            bid=None,
            task=self.user_config.get("task_package_id"),
            mode="proposal_set",
            force=False,
            init=False,
        )

    def _write_session_config(self, config_path: Path) -> None:
        """Write a session-specific pipeline_config.yaml.

        Points the input DOCX to the uploaded file and output to the workspace.
        """
        uploaded_docx = self.workspace / "uploads" / "bid_document.docx"

        config = self._load_pipeline_config_base()

        input_cfg = self._ensure_section(config, "input")
        input_cfg["bid_docx"] = uploaded_docx.as_posix()

        output_cfg = self._ensure_section(config, "output")
        output_cfg["dir"] = (self.workspace / ".cache").as_posix()
        output_cfg["clean_dir"] = (self.workspace / "output").as_posix()

        template_cfg = self._ensure_section(config, "template")
        template_cfg.setdefault("search", True)
        template_cfg["extract_to"] = (self.workspace / "templates" / "template.docx").as_posix()

        task_cfg = self._ensure_section(config, "task")
        task_cfg["package_id"] = self.user_config.get("task_package_id")
        task_cfg.setdefault("technical_only", True)

        proposal_set = config.get("proposal_set")
        if not isinstance(proposal_set, dict):
            raise ValueError("pipeline_config.yaml 缺少 proposal_set 三方案配置")
        proposal_slots = ["winning"] + sorted(
            (slot for slot in proposal_set if re.fullmatch(r"reference_[1-9]\d*", slot)),
            key=lambda slot: int(slot.split("_")[1]),
        )
        for slot in proposal_slots:
            proposal_id = "bid_00_winning" if slot == "winning" else f"bid_{int(slot.split('_')[1]):02d}"
            proposal = proposal_set.get(slot)
            if not isinstance(proposal, dict):
                raise ValueError(f"pipeline_config.yaml 缺少 {slot} 方案配置")
            if proposal.get("id") != proposal_id:
                raise ValueError(f"{slot}.id 必须为 {proposal_id}")

        config.pop("solution", None)
        config.pop("accompany", None)

        claude_cfg = self._ensure_section(config, "claude")
        claude_cfg.setdefault("timeout", 600)
        claude_cfg.setdefault("max_retries", 3)
        claude_cfg.setdefault("min_output_size", 200)
        claude_cfg.setdefault("allowed_tools", ["Read", "Write", "Bash", "Glob", "Grep"])

        if not isinstance(config.get("stages"), list) or not config["stages"]:
            config["stages"] = self._default_stage_config()

        format_cfg = self._ensure_section(config, "format")
        format_cfg.setdefault("image_placeholders", True)
        format_cfg.setdefault("generate_toc", True)
        format_cfg.setdefault("generate_response_table", True)
        company_info = format_cfg.get("company_info")
        if not isinstance(company_info, dict):
            company_info = {}
            format_cfg["company_info"] = company_info
        company_info.update({
            "name": self.user_config.get("company", ""),
            "address": self.user_config.get("address", ""),
            "contact_name": self.user_config.get("contact_name", ""),
            "contact_phone": self.user_config.get("contact_phone", ""),
            "contact_email": self.user_config.get("contact_email", ""),
        })

        defaults = self._load_project_pipeline_defaults()
        if not isinstance(config.get("tech_stacks"), dict) or not config["tech_stacks"]:
            config["tech_stacks"] = copy.deepcopy(defaults.get("tech_stacks", {}))
        if not isinstance(config.get("team_profiles"), dict) or not config["team_profiles"]:
            config["team_profiles"] = copy.deepcopy(defaults.get("team_profiles", {}))

        proposal_slots = ["winning"] + sorted(
            (slot for slot in config["proposal_set"] if re.fullmatch(r"reference_[1-9]\d*", slot)),
            key=lambda slot: int(slot.split("_")[1]),
        )
        for slot in proposal_slots:
            proposal = config["proposal_set"][slot]
            if proposal.get("tech_stack_id") not in config["tech_stacks"]:
                raise ValueError(f"{slot} 引用了不存在的技术栈")
            profile = config["team_profiles"].get(proposal.get("team_profile_id"))
            if not isinstance(profile, dict):
                raise ValueError(f"{slot} 引用了不存在的团队配置")
            roles = profile.get("roles", [])
            if not isinstance(roles, list) or not roles:
                raise ValueError(f"{slot} 团队至少需要一个角色")
            total = 0
            for role in roles:
                if not isinstance(role, dict) or not str(role.get("role", "")).strip():
                    raise ValueError(f"{slot} 团队角色名称不能为空")
                count = int(role.get("count", 0) or 0)
                if count < 0:
                    raise ValueError(f"{slot} 团队角色人数不能为负数")
                total += count
            if total < 1 or total > 20:
                raise ValueError(f"{slot} 团队人数必须在 1 到 20 人之间")

        header = (
            f"# Session-specific pipeline config for {self.session_id}\n"
            "# Auto-generated by PipelineAdapter from frontend pipeline_config.yaml\n\n"
        )
        config_path.write_text(
            header + yaml.safe_dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        return

    @staticmethod
    def _ensure_section(config: Dict[str, Any], key: str) -> Dict[str, Any]:
        section = config.get(key)
        if not isinstance(section, dict):
            section = {}
            config[key] = section
        return section

    def _load_project_pipeline_defaults(self) -> Dict[str, Any]:
        path = PROJECT_ROOT / "pipeline_config.yaml"
        if not path.exists():
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}

    def _load_pipeline_config_base(self) -> Dict[str, Any]:
        submitted = str(self.user_config.get("pipeline_config_yaml") or "").strip()
        if submitted:
            try:
                data = yaml.safe_load(submitted) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"前端提交的 pipeline_config.yaml 解析失败: {e}") from e
            if not isinstance(data, dict):
                raise ValueError("前端提交的 pipeline_config.yaml 顶层必须是 YAML 对象")
            return copy.deepcopy(data)
        return copy.deepcopy(self._load_project_pipeline_defaults())

    @staticmethod
    def _default_stage_config() -> List[Dict[str, Any]]:
        cache_dirs = [
            "01_parsed",
            "02_summary",
            "03_requirements",
            "04_template",
            "05_format",
            "06_strategies",
            "07_bids",
            "08_filled",
            "09_exported",
            "10_response_tables",
            "11_final",
        ]
        return [
            {
                "id": stage["id"],
                "name": stage["name"],
                "description": stage["description"],
                "cache_dir": cache_dirs[idx],
                "enabled": True,
            }
            for idx, stage in enumerate(STAGE_DEFINITIONS)
        ]

    # ── Synchronous pipeline runner (executed in thread pool) ──

    def _run_pipeline_sync(self, args: argparse.Namespace) -> int:
        """Run the BidPipeline synchronously. Called from thread pool."""
        import threading

        # ── Keepalive: send periodic pings while pipeline runs ──
        # Prevents proxy/router idle-timeout during long Claude calls
        _keepalive_stop = threading.Event()
        _keepalive_interval = 30  # seconds

        def _keepalive_loop():
            """Send 'still working...' pings every 30s from this thread."""
            while not _keepalive_stop.is_set():
                _keepalive_stop.wait(_keepalive_interval)
                if _keepalive_stop.is_set():
                    break
                if self._loop is None:
                    continue
                async def send_ka():
                    await self.ws.send_keepalive(
                        self.session_id,
                        "流水线正在运行中...",
                    )
                try:
                    asyncio.run_coroutine_threadsafe(send_ka(), self._loop)
                except Exception:
                    pass

        keepalive_thread = threading.Thread(target=_keepalive_loop, daemon=True)
        keepalive_thread.start()

        try:
            from bid_pipeline import BidPipeline

            # Create progress callback adapter (thread-safe)
            def progress_cb(stage_id: int, status: str, message: str) -> None:
                """Called by BidPipeline at stage transitions."""
                if self._loop is None:
                    return
                if stage_id < 0:
                    progress_pct = 0  # pre-stage is before stage 0
                else:
                    progress_pct = int((stage_id / TOTAL_STAGES) * 100) if status == "completed" else \
                                   int(((stage_id + 0.5) / TOTAL_STAGES) * 100)

                async def send():
                    if stage_id < 0:
                        # Pre-stage: send as echo only, no stage card on frontend
                        level = "error" if status == "failed" else "info"
                        await self.ws.send_echo(self.session_id, f"[预分析] {message}", level)
                    else:
                        stage_def = STAGE_DEFINITIONS[stage_id] if 0 <= stage_id < len(STAGE_DEFINITIONS) else {}
                        if status == "running":
                            await self.ws.send_stage_start(self.session_id, stage_id, message, progress_pct)
                        elif status == "completed":
                            await self.ws.send_stage_complete(self.session_id, stage_id, message, progress_pct)
                        elif status == "failed":
                            await self.ws.send_stage_failed(self.session_id, stage_id, message, progress_pct)
                        else:
                            await self.ws.send_echo(self.session_id, f"[Stage {stage_id}] {status}: {message}")

                    # Update session registry
                    self.sm.update_session(
                        self.session_id,
                        current_stage=max(stage_id, 0),
                        status="running" if status != "completed" else "running",
                    )

                try:
                    asyncio.run_coroutine_threadsafe(send(), self._loop)
                except Exception:
                    pass

            def log_cb(message: str) -> None:
                """ClaudeRunner verbose logs are intentionally disabled."""
                return

            # Create pipeline with callbacks
            pipeline = BidPipeline(
                args,
                progress_callback=progress_cb,
                log_callback=log_cb,
            )

            result = pipeline.run()
            _keepalive_stop.set()
            return result

        except ImportError as e:
            _keepalive_stop.set()
            if self._loop:
                async def send_err():
                    await self.ws.send_echo(
                        self.session_id,
                        f"无法导入 bid_pipeline: {e}",
                        "error",
                    )
                asyncio.run_coroutine_threadsafe(send_err(), self._loop)
            _keepalive_stop.set()
            return 1
        except Exception as e:
            _keepalive_stop.set()
            if self._loop:
                async def send_err():
                    await self.ws.send_echo(
                        self.session_id,
                        f"流水线异常: {e}",
                        "error",
                    )
                asyncio.run_coroutine_threadsafe(send_err(), self._loop)
            return 1
