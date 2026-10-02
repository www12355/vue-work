#!/usr/bin/env python
"""
Claude AI 标书自动生成 Pipeline — 通用型多方案模式（1中标+N参考文件）
========================================================

11 阶段流水线（Stage 0→10，按逻辑顺序排列）：

  Stage 0: 文档解析         → .cache/01_parsed/
  Stage 1: 标书总结         → .cache/02_summary/
  Stage 2: 需求提取         → .cache/03_requirements/
  Stage 3: 技术章节定位     → .cache/04_template/       (regex 定位技术方案标号)
  Stage 4: 默认格式准备     → .cache/05_format/         (不解析标书格式)
  Stage 5: 投标策略生成     → .cache/06_strategies/
  Stage 6: 标书内容生成     → .cache/07_bids/           (中标+参考文件)
  Stage 7: 模板内容填充     → .cache/08_filled/         (插入到模板对应位置)
  Stage 8: DOCX导出         → .cache/08_exported/       (格式化导出)
  Stage 9: 应答表生成       → .cache/09_response_tables/
  Stage 10: 最终整合导出    → .cache/10_final/

用法:
    python bid_pipeline.py                      # 完整运行（1中标+2参考文件）
    python bid_pipeline.py --task 3             # 指定第三包，生成三份方案
    python bid_pipeline.py --task 3 --mode winning_only    # 仅中标方案
    python bid_pipeline.py --task 3 --mode accompany_only  # 仅参考文件方案
    python bid_pipeline.py --count 3            # 生成3个参考文件
    python bid_pipeline.py --bid 2              # 仅处理第2个参考文件
    python bid_pipeline.py --docx ./xxx.docx    # 指定标书文件
    python bid_pipeline.py --resume             # 断点续跑
    python bid_pipeline.py --status             # 查看进度
    python bid_pipeline.py --from-stage N       # 从指定阶段开始
    python bid_pipeline.py --only-stage N       # 仅执行单个阶段（调试）
    python bid_pipeline.py --init               # 生成默认配置
"""

from __future__ import annotations

import sys
import os
import json
import re
import time
import argparse
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保项目根目录在 Python 路径中
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from lib.config_loader import BidPipelineConfig
from lib.state_manager import PipelineState
from lib.claude_runner import ClaudeRunner
from lib.docx_parser import BidDocumentParser, ParsedDocument
from lib.degrade_engine import DegradeEngine, DegradeStrategy, save_strategies
from lib.skill_manager import SkillManager
from lib.docx_exporter import DocxExporter
from lib.format_adapter import FormatAdapter, FormatSpec, load_format_spec, save_format_spec
from lib.template_filler import TemplateFiller, TemplateDocument
from lib.response_table import ResponseTableGenerator, RequirementItem, ResponseTable
from lib.word_composer import WordComposer, compose_bid_document
from lib.document_output_guard import DocumentOutputGuard, export_basename

TECHNICAL_SECTION_TITLES = [
    "项目背景与需求分析",
    "总体技术架构设计",
    "核心功能模块技术方案",
    "AI模型与智能化能力",
    "项目重点难点与应对",
    "人员配置方案",
    "项目进度安排",
    "服务质量保证与验收",
]

TECHNICAL_SECTION_ALIASES = {
    "项目背景与需求分析": ["项目背景", "需求分析", "项目概述", "需求理解"],
    "总体技术架构设计": ["总体架构设计", "总体技术架构", "技术架构设计", "总体架构", "技术路线"],
    "核心功能模块技术方案": ["核心功能模块方案", "核心功能模块", "功能模块技术方案", "功能模块方案", "业务功能方案"],
    "AI模型与智能化能力": ["AI能力", "智能化能力", "AI模型", "人工智能能力", "智能化方案"],
    "项目重点难点与应对": ["重点难点", "难点应对", "重点难点分析", "风险与应对"],
    "人员配置方案": ["人员配置", "团队配置", "项目团队", "人员安排"],
    "项目进度安排": ["进度安排", "实施进度", "项目计划", "进度计划"],
    "服务质量保证与验收": ["服务质量保证", "质量保证与验收", "验收方案", "服务保障", "质量保障"],
}


# ═══════════════════════════════════════════════════════════════
# 路径常量
# ═══════════════════════════════════════════════════════════════

SKILLS_DIR = ROOT / "skills"

# Cache dirs — stages 0-10 map to directories (keeping original numbering for compatibility)
CACHE_DIRS = {
    0: "01_parsed",
    1: "02_summary",
    2: "03_requirements",
    3: "04_template",
    4: "05_format",
    5: "06_strategies",
    6: "07_bids",
    7: "08_filled",
    8: "09_exported",
    9: "10_response_tables",
    10: "11_final",
}

# Legacy cache directory names (for backward compatibility)
# Maps stage_id -> old directory name; empty when no migrations needed
_OLD_CACHE_DIRS: Dict[int, str] = {}

# Profile reference analysis cache dir (pre-stage)
PROFILE_CACHE = "00_profile"


# ═══════════════════════════════════════════════════════════════
# 主编排器
# ═══════════════════════════════════════════════════════════════

class BidPipeline:
    """标书自动生成与技术方案 Pipeline — 11 阶段（先参考后核心，模板条件分支）。"""

    def __init__(self, args: argparse.Namespace, progress_callback=None, log_callback=None):
        self.args = args
        self.config = BidPipelineConfig(Path(args.config) if args.config else None)

        # Server-mode callbacks (None in CLI mode)
        self.progress_callback = progress_callback  # callable(stage_id, status, message)
        self.log_callback = log_callback            # callable(message)

        # 命令行覆盖
        if args.count is not None:
            print("  [COMPAT] --count 已废弃，请在 pipeline_config.yaml 的 proposal_set 中调整参考方案数量")
            self.config.set_num_accompanying(args.count)
        if args.bid is not None:
            print("  [COMPAT] --bid 已废弃，固定生成全部三份方案")
            self.config.set_target_bid(args.bid)
        if args.docx is not None:
            self.config.set_input_docx(args.docx)
        if args.task is not None:
            self.config.set_task_package_id(args.task)
        if args.mode and args.mode not in ("mixed", "proposal_set"):
            print(f"  [COMPAT] --mode {args.mode} 已废弃，改为按 proposal_set 生成全部方案")
        self.run_mode = "proposal_set"

        # 运行时变量
        self.task_content: str = ""
        self.format_spec: Optional[FormatSpec] = None
        self._chapter_number_map: Dict[str, str] = {}
        self.templates: Dict[str, TemplateDocument] = {}
        self.response_tables: Dict[str, ResponseTable] = {}

        # 输出目录
        self.cache_dir = self.config.get_output_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Workspace root (parent of .cache/)
        self.workspace = self.cache_dir.parent

        # Template discovery flag
        self.has_template: Optional[bool] = None  # 格式模板拼接已禁用，默认按 False 处理

        # 组件初始化
        self.state = PipelineState(self.cache_dir)
        if self.args.resume:
            self.state.load()
        else:
            self.state.reset()

        # Skill 管理器 — 传入 cache_dir 以支持自动加载 .cache
        self.skills = SkillManager(SKILLS_DIR, self.cache_dir)
        self.runner = ClaudeRunner(self.config.get_claude_config(), SKILLS_DIR, log_callback=self.log_callback, working_dir=self.workspace)
        self.exporter = DocxExporter()

        # 运行时变量
        self.parsed_doc: Optional[ParsedDocument] = None
        self.requirements: List[Dict[str, Any]] = []
        self.strategies: List[DegradeStrategy] = []

    # ── 进度通知辅助（服务器模式）──────────────────────────

    def _notify_progress(self, stage_id: int, status: str, message: str) -> None:
        """Thread-safe progress notification (no-op in CLI mode)."""
        if self.progress_callback:
            try:
                self.progress_callback(stage_id, status, message)
            except Exception:
                pass

    def _notify_log(self, message: str) -> None:
        """Thread-safe log notification (no-op in CLI mode)."""
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass

    # ── 缓存路径辅助 ──────────────────────────────────────

    def _cache(self, stage_id: int, *subpath: str) -> Path:
        """获取某个阶段的缓存目录路径（向后兼容旧目录名）。"""
        base = self.cache_dir / CACHE_DIRS.get(stage_id, f"stage_{stage_id}")
        if subpath:
            base = base.joinpath(*subpath)
        # 向后兼容：如果新路径不存在但旧路径存在（stage 8-10 曾改名），回退到旧路径
        if not base.exists() and stage_id in _OLD_CACHE_DIRS:
            old_base = self.cache_dir / _OLD_CACHE_DIRS[stage_id]
            if subpath:
                old_base = old_base.joinpath(*subpath)
            if old_base.exists():
                print(f"    [COMPAT] 使用旧缓存目录: {old_base.relative_to(self.cache_dir)}（建议清理后重新运行）")
                return old_base
        return base

    def _configured_proposals(self) -> List[Dict[str, Any]]:
        """Return only proposals declared by the current session configuration."""
        proposal_set = self.config.get_proposal_set()
        slots = ["winning"] + sorted(
            (slot for slot in proposal_set if re.fullmatch(r"reference_[1-9]\d*", slot)),
            key=lambda slot: int(slot.split("_")[1]),
        )
        proposals: List[Dict[str, Any]] = []
        for slot in slots:
            proposal = proposal_set.get(slot, {})
            proposal_id = str(proposal.get("id") or ("bid_00_winning" if slot == "winning" else ""))
            if not proposal_id:
                continue
            team_profile = self.config.get_proposal_team_profile(proposal)
            proposals.append({
                "slot": slot,
                "id": proposal_id,
                "name": str(proposal.get("name") or proposal_id),
                "export_basename": export_basename(proposal.get("name") or proposal_id),
                "bid_dir": "bid_00_winning" if slot == "winning" else proposal_id,
                "tech_stack_id": str(proposal.get("tech_stack_id") or ""),
                "team_profile_id": str(proposal.get("team_profile_id") or ""),
                "delivery_days": str(proposal.get("delivery_days") or ""),
                "writing_rules": list(proposal.get("writing_rules") or []),
                "tech_stack": self.config.get_tech_stack(str(proposal.get("tech_stack_id") or "")),
                "team_profile": team_profile,
            })
        return proposals

    # ── 任务内容提取 ──────────────────────────────────────

    def _extract_task_content(self, task_id: int) -> str:
        """从 full_text.md 中提取指定标包的技术要求内容。"""
        full_text_path = self._cache(0) / "full_text.md"
        if not full_text_path.exists():
            return ""

        text = full_text_path.read_text(encoding="utf-8")

        task_labels = {
            1: "第一包", 2: "第二包", 3: "第三包", 4: "第四包", 5: "第五包",
        }
        label = task_labels.get(task_id, f"第{task_id}包")
        next_labels = [task_labels.get(task_id + i, "") for i in range(1, 4) if task_id + i <= 5]

        pattern = rf"{label}[：:]"
        matches = list(re.finditer(pattern, text))
        if not matches:
            return f"未找到第{task_id}包的专项内容"

        content_parts = []
        for match in matches:
            start = match.start()
            end = len(text)
            for nl in next_labels:
                next_pattern = rf"{nl}[：:]"
                nm = re.search(next_pattern, text[start + len(match.group()):])
                if nm:
                    candidate_end = start + len(match.group()) + nm.start()
                    if candidate_end < end:
                        end = candidate_end
                        break
            chunk = text[start:min(end, start + 5000)]
            content_parts.append(chunk)

        return "\n\n---\n\n".join(content_parts) if content_parts else f"未找到第{task_id}包的专项内容"

    # ── 需求提取结果规范化 ──────────────────────────────────

    CATEGORY_LABELS = {
        "TECH": "技术需求",
        "FUNC": "功能需求",
        "DATA": "数据需求",
        "SEC": "安全需求",
        "DEPLOY": "部署需求",
        "PERSON": "人员需求",
        "TIMELINE": "进度需求",
        "SERVICE": "服务需求",
        "COMPLIANCE": "合规需求",
        "OTHER": "其他需求",
    }

    @staticmethod
    def _extract_json_payload(text: str) -> Optional[Any]:
        """从模型输出中提取 JSON 对象或数组，兼容 ```json 代码块。"""
        cleaned = (text or "").strip()
        if not cleaned:
            return None

        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if fenced:
            cleaned = fenced.group(1).strip()

        for candidate in (cleaned,):
            try:
                return json.loads(candidate)
            except Exception:
                pass

        obj_start = cleaned.find("{")
        obj_end = cleaned.rfind("}")
        if 0 <= obj_start < obj_end:
            try:
                return json.loads(cleaned[obj_start:obj_end + 1])
            except Exception:
                pass

        arr_start = cleaned.find("[")
        arr_end = cleaned.rfind("]")
        if 0 <= arr_start < arr_end:
            try:
                return json.loads(cleaned[arr_start:arr_end + 1])
            except Exception:
                pass

        return None

    @staticmethod
    def _classify_requirement_text(text: str) -> str:
        """启发式分类，用于 AI JSON 不可用时兜底。"""
        if re.search(r"安全|加密|权限|审计|等保|保密|访问控制", text):
            return "SEC"
        if re.search(r"部署|环境|服务器|国产化|容器|数据库|操作系统", text):
            return "DEPLOY"
        if re.search(r"人员|团队|项目经理|工程师|资质|证书", text):
            return "PERSON"
        if re.search(r"工期|进度|交付|里程碑|完成时间|服务期", text):
            return "TIMELINE"
        if re.search(r"售后|运维|培训|响应|服务|质保|验收", text):
            return "SERVICE"
        if re.search(r"法律|标准|规范|合规|资格|声明函|证件|政策", text):
            return "COMPLIANCE"
        if re.search(r"数据|数据库|导入|导出|采集|治理|存储|备份", text):
            return "DATA"
        if re.search(r"功能|模块|查询|统计|管理|接口|上传|下载", text):
            return "FUNC"
        if re.search(r"技术|架构|性能|算法|模型|系统", text):
            return "TECH"
        return "OTHER"

    @staticmethod
    def _normalize_requirement_item(item: Dict[str, Any], index: int) -> Dict[str, Any]:
        """补齐并规整单条需求字段。"""
        text = str(item.get("text") or item.get("requirement") or item.get("content") or "").strip()
        category = str(item.get("category") or "").upper().strip()
        if category not in BidPipeline.CATEGORY_LABELS:
            category = BidPipeline._classify_requirement_text(text)

        mandatory = item.get("mandatory")
        if mandatory is None:
            mandatory = bool(re.search(r"必须|须|应当|应满足|不得|★", text))

        priority = str(item.get("priority") or "").upper().strip()
        if priority not in ("HIGH", "MEDIUM", "NORMAL", "LOW"):
            if "★" in text:
                priority = "HIGH"
            elif "▲" in text:
                priority = "MEDIUM"
            else:
                priority = "NORMAL"

        keywords = item.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = [str(keywords)]
        if not keywords:
            keywords = [kw for kw in ["必须", "须", "应", "要求", "功能", "安全", "服务", "验收"] if kw in text]

        return {
            "req_id": str(item.get("req_id") or f"REQ-{index:03d}"),
            "category": category,
            "text": text,
            "mandatory": bool(mandatory),
            "priority": priority,
            "source_section": str(item.get("source_section") or ""),
            "source_paragraph": item.get("source_paragraph", item.get("paragraph_index", None)),
            "satisfaction_criteria": str(
                item.get("satisfaction_criteria")
                or item.get("criteria")
                or "投标技术方案中需明确响应该要求，并给出可验证的实现措施。"
            ),
            "keywords": [str(k) for k in keywords if str(k).strip()],
        }

    def _build_requirements_payload(
        self,
        parsed_ai_text: str,
        task_id: Optional[int],
        fallback_requirements: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """将 AI 输出或启发式结果规范成 requirements.json 结构。"""
        parsed = self._extract_json_payload(parsed_ai_text)
        if isinstance(parsed, dict):
            raw_requirements = parsed.get("requirements", [])
            project_name = parsed.get("project_name", "")
            package_id = parsed.get("package_id", task_id)
        elif isinstance(parsed, list):
            raw_requirements = parsed
            project_name = ""
            package_id = task_id
        else:
            raw_requirements = fallback_requirements or []
            project_name = ""
            package_id = task_id

        if not isinstance(raw_requirements, list):
            raw_requirements = []
        if not raw_requirements and fallback_requirements:
            raw_requirements = fallback_requirements

        requirements = []
        seen = set()
        for item in raw_requirements:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_requirement_item(item, len(requirements) + 1)
            if not normalized["text"]:
                continue
            dedupe_key = re.sub(r"\s+", "", normalized["text"])[:120]
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized["req_id"] = f"REQ-{len(requirements) + 1:03d}"
            requirements.append(normalized)

        category_counts = {
            code: sum(1 for req in requirements if req["category"] == code)
            for code in self.CATEGORY_LABELS
        }
        category_counts = {k: v for k, v in category_counts.items() if v}

        return {
            "project_name": project_name,
            "package_id": package_id,
            "total_requirements": len(requirements),
            "category_counts": category_counts,
            "mandatory_count": sum(1 for req in requirements if req["mandatory"]),
            "optional_count": sum(1 for req in requirements if not req["mandatory"]),
            "high_priority_count": sum(1 for req in requirements if req["priority"] == "HIGH"),
            "requirements": requirements,
            "generated_at": datetime.datetime.now().isoformat(),
            "source": "ai_json" if parsed is not None else "heuristic_fallback",
        }

    def _requirements_to_markdown(self, payload: Dict[str, Any]) -> str:
        """把结构化需求转换为人类可读 requirements.md。"""
        lines = [
            "# 需求规格说明书",
            "",
            f"- 项目名称：{payload.get('project_name') or '未识别'}",
            f"- 标包：{payload.get('package_id') if payload.get('package_id') is not None else '全部'}",
            f"- 需求总数：{payload.get('total_requirements', 0)}",
            f"- 强制性需求：{payload.get('mandatory_count', 0)}",
            f"- 高优先级需求：{payload.get('high_priority_count', 0)}",
            "",
            "## 分类统计",
            "",
            "| 分类 | 名称 | 数量 |",
            "| --- | --- | --- |",
        ]
        counts = payload.get("category_counts", {})
        for code, label in self.CATEGORY_LABELS.items():
            if counts.get(code):
                lines.append(f"| {code} | {label} | {counts[code]} |")

        requirements = payload.get("requirements", [])
        for code, label in self.CATEGORY_LABELS.items():
            group = [req for req in requirements if req.get("category") == code]
            if not group:
                continue
            lines.extend(["", f"## {code} {label}", ""])
            for req in group:
                mandatory = "强制" if req.get("mandatory") else "非强制"
                lines.extend([
                    f"### {req.get('req_id')} {mandatory} / {req.get('priority', 'NORMAL')}",
                    "",
                    f"- 需求内容：{req.get('text', '')}",
                    f"- 满足标准：{req.get('satisfaction_criteria', '')}",
                    f"- 来源章节：{req.get('source_section') or '未识别'}",
                    f"- 来源段落：{req.get('source_paragraph') if req.get('source_paragraph') is not None else '未识别'}",
                    f"- 关键词：{', '.join(req.get('keywords', [])) or '无'}",
                    "",
                ])

        return "\n".join(lines).rstrip() + "\n"

    def _requirements_to_checklist(self, payload: Dict[str, Any]) -> str:
        """生成可勾选的需求检查清单。"""
        lines = [
            "# 需求检查清单",
            "",
            "| 勾选 | 编号 | 分类 | 优先级 | 需求内容 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for req in payload.get("requirements", []):
            text = str(req.get("text", "")).replace("|", "｜")
            if len(text) > 180:
                text = text[:180] + "..."
            lines.append(
                f"| [ ] | {req.get('req_id')} | {req.get('category')} | {req.get('priority')} | {text} |"
            )
        return "\n".join(lines).rstrip() + "\n"

    # ── 章节编号重映射 ──────────────────────────────────────

    # ── 中文数字 → 阿拉伯数字映射 ──
    _CHINESE_DIGIT_MAP = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }

    @staticmethod
    def _renumber_chapters(md_text: str, chapter_map: Dict[str, str]) -> str:
        """
        后处理：将 AI 生成的标题编号重映射为模板要求的数字编号。

        规则（按用户指定）：
        1. 阿拉伯数字 → 直接在最前面添加大节序号前缀
           例：`### 1.1 xxx` → `### 13.1.1 xxx`
           例：`#### 1.2.3 xxx` → `#### 13.1.2.3 xxx`
        2. 中文汉字 → 转成对应数字，再加上大节序号前缀
           例：`## 一、xxx` → `## 13.1 xxx`（通过 chapter_map）
           例：`### 三、xxx` → `### 13.1.3 xxx`（中文→数字 + 前缀）
        3. 移除顶层标题 `# 投标技术方案`
        4. 已含前缀的编号（如 13.1.1）不再重复处理
        5. 保留非标题行不变
        """
        lines = md_text.split("\n")
        result = []
        chapter_prefix = chapter_map.get("_prefix", "")

        # 中文数字 → 完整编号映射（如 "一" → "13.1"）
        cn_to_num = {}
        chinese_nums = chapter_map.get("_chinese_numerals", ["一", "二", "三", "四", "五", "六", "七", "八"])
        for cn in chinese_nums:
            if cn in chapter_map:
                cn_to_num[cn] = chapter_map[cn]

        # 中文数字 → 阿拉伯数字映射（如 "三" → 3）
        cn_digit_map = BidPipeline._CHINESE_DIGIT_MAP

        # 跟踪当前所属的大节序号（如 "1", "2"），用于 H3 中文数字继承父节
        current_section_num = "1"

        for line in lines:
            stripped = line.strip()

            # ── 移除顶层标题 ──
            if re.match(r'^#\s+投标技术方案', stripped):
                continue

            # ── H2：中文数字 → chapter_map 映射 ──
            # "## 一、项目概述" → "## 13.1 项目概述"
            h2_match = re.match(
                r'^(##\s+)([一二三四五六七八九十]+)[、，．。\s]+(.+)', stripped
            )
            if h2_match:
                prefix = h2_match.group(1)    # "## "
                cn = h2_match.group(2)         # "一"
                rest = h2_match.group(3).strip()  # "项目概述"
                if cn in cn_to_num:
                    new_num = cn_to_num[cn]       # e.g. "13.1"
                    # 提取末位数字作为当前大节序号
                    current_section_num = new_num.split(".")[-1]  # "1"
                    new_line = f"{prefix}{new_num} {rest}"
                else:
                    new_line = line
                result.append(new_line)
                continue

            # ── 如果 chapter_prefix 为空，跳过阿拉伯数字重编号 ──
            if not chapter_prefix:
                result.append(line)
                continue

            # ── H3：阿拉伯数字 → 前缀 + 原数字 ──
            # "### 1.1 背景" → "### 13.1.1 背景"
            h3_match = re.match(
                r'^(###\s+)(\d+\.\d+)([、，．。\s]+)(.+)', stripped
            )
            if h3_match:
                prefix = h3_match.group(1)     # "### "
                num = h3_match.group(2)         # "1.1"
                rest = h3_match.group(4).strip()  # "背景"
                # 避免重复前缀（如已为 13.1.1）
                if not num.startswith(chapter_prefix + "."):
                    new_num = f"{chapter_prefix}.{num}"
                    new_line = f"{prefix}{new_num} {rest}"
                    result.append(new_line)
                    continue

            # ── H3：中文数字 → 前缀.当前大节.数字 ──
            # "### 三、需求分析" → "### 13.2.3 需求分析"（继承最近的 H2 节号）
            h3_cn_match = re.match(
                r'^(###\s+)([一二三四五六七八九十]+)[、，．。\s]+(.+)', stripped
            )
            if h3_cn_match:
                prefix = h3_cn_match.group(1)
                cn = h3_cn_match.group(2)
                rest = h3_cn_match.group(3).strip()
                digit = cn_digit_map.get(cn, 0)
                if digit > 0:
                    new_num = f"{chapter_prefix}.{current_section_num}.{digit}"
                    new_line = f"{prefix}{new_num} {rest}"
                    result.append(new_line)
                    continue

            # ── H4：阿拉伯数字 → 前缀 + 原数字 ──
            # "#### 1.1.1 详细" → "#### 13.1.1.1 详细"
            h4_match = re.match(
                r'^(####\s+)(\d+\.\d+\.\d+)([、，．。\s]+)(.+)', stripped
            )
            if h4_match:
                prefix = h4_match.group(1)      # "#### "
                num = h4_match.group(2)          # "1.1.1"
                rest = h4_match.group(4).strip()  # "详细"
                if not num.startswith(chapter_prefix + "."):
                    new_num = f"{chapter_prefix}.{num}"
                    new_line = f"{prefix}{new_num} {rest}"
                    result.append(new_line)
                    continue

            # ── H5：更深层级的阿拉伯数字 ──
            # "##### 1.1.1.1 xxx" → "##### 13.1.1.1.1 xxx"
            h5_match = re.match(
                r'^(#{5}\s+)(\d+(?:\.\d+)+)([、，．。\s]+)(.+)', stripped
            )
            if h5_match:
                prefix = h5_match.group(1)
                num = h5_match.group(2)
                rest = h5_match.group(4).strip()
                if not num.startswith(chapter_prefix + "."):
                    new_num = f"{chapter_prefix}.{num}"
                    new_line = f"{prefix}{new_num} {rest}"
                    result.append(new_line)
                    continue

            result.append(line)

        return "\n".join(result)

    @staticmethod
    def _normalize_title(text: str) -> str:
        """用于章节标题匹配的轻量归一化。"""
        text = re.sub(r'^[#\s]+', '', text or "")
        text = re.sub(r'^\d+(?:\.\d+)*\s*', '', text)
        text = re.sub(r'^[一二三四五六七八九十]+[、，．。\s]+', '', text)
        return re.sub(r'[\s:：、，,。.．（）()【】\[\]<>《》"-]+', '', text).lower()

    @staticmethod
    def _build_technical_section_map(prefix: str) -> Dict[str, str]:
        """按确定性算法生成技术方案一级章节编号映射。"""
        prefix = str(prefix or "11").strip()
        return {title: f"{prefix}.{idx}" for idx, title in enumerate(TECHNICAL_SECTION_TITLES, start=1)}

    @staticmethod
    def _build_chapter_number_map_from_section_map(section_map: Dict[str, str]) -> Dict[str, Any]:
        """将 technical_section_map 转为兼容旧 prompt/后处理的 chapter_number_map。"""
        chinese_numerals = ["一", "二", "三", "四", "五", "六", "七", "八"]
        ordered_sections = [section_map[title] for title in TECHNICAL_SECTION_TITLES if title in section_map]
        first_num = ordered_sections[0] if ordered_sections else "11.1"
        prefix = first_num.split(".")[0]
        result: Dict[str, Any] = {
            "_prefix": prefix,
            "_ordered_sections": ordered_sections,
            "_chinese_numerals": chinese_numerals[:len(ordered_sections)],
            "technical_section_map": section_map,
        }
        for idx, cn in enumerate(chinese_numerals):
            if idx < len(ordered_sections):
                result[cn] = ordered_sections[idx]
        return result

    @staticmethod
    def _attachment_prefix(marker: str) -> Optional[str]:
        """从“附件11”“第十一部分”“11 技术方案”等标号中提取一级编号。"""
        if not marker:
            return None
        digit = re.search(r'附件\s*(\d+)', marker)
        if digit:
            return digit.group(1)
        zh = re.search(r'附件\s*([一二三四五六七八九十]+)', marker)
        if zh:
            value = BidPipeline._chinese_number_to_int(zh.group(1))
            return str(value) if value else None
        zh_part = re.search(r'第\s*([一二三四五六七八九十]+)\s*(?:部分|章|节)', marker)
        if zh_part:
            value = BidPipeline._chinese_number_to_int(zh_part.group(1))
            return str(value) if value else None
        digit_part = re.search(r'第\s*(\d+)\s*(?:部分|章|节)', marker)
        if digit_part:
            return digit_part.group(1)
        heading = re.search(r'(?<!\d)(\d{1,2})(?:\.\d+)*\s*(?:[、.．。\s]|$)', marker)
        if heading:
            return heading.group(1)
        return None

    @staticmethod
    def _chinese_number_to_int(text: str) -> Optional[int]:
        """支持一到十九的中文数字转整数，足够覆盖常见附件号。"""
        if not text:
            return None
        mapping = BidPipeline._CHINESE_DIGIT_MAP
        if text in mapping:
            return mapping[text]
        if text == "十":
            return 10
        if text.startswith("十"):
            return 10 + mapping.get(text[1:], 0)
        if "十" in text:
            left, right = text.split("十", 1)
            return mapping.get(left, 0) * 10 + (mapping.get(right, 0) if right else 0)
        return None

    @staticmethod
    def _locate_technical_section_by_regex(text: str) -> Dict[str, Any]:
        """
        用 regex 定位技术方案所在附件/章节。

        不依赖 LLM 判断“投标文件格式”，只在解析后的全文中查找带技术语义的标号。
        """
        keywords = [
            "技术方案", "技术路线", "实施方案", "服务方案", "设计方案",
            "系统方案", "总体方案", "建设方案", "证明材料及方案", "方案",
        ]
        exclude_keywords = ["应答表", "响应表", "点对点", "一对一", "商务", "报价"]
        candidates: List[Dict[str, Any]] = []

        lines = text.splitlines()
        scan_entries: List[tuple[int, str]] = []
        for idx, line in enumerate(lines):
            clean_line = line.strip()
            if clean_line:
                scan_entries.append((idx, clean_line))
            if idx + 1 < len(lines):
                nxt = lines[idx + 1].strip()
                if clean_line and nxt and len(clean_line) <= 60 and len(nxt) <= 80:
                    scan_entries.append((idx, f"{clean_line} {nxt}"))

        for idx, clean in scan_entries:
            if not clean or len(clean) > 120:
                continue
            if not any(kw in clean for kw in keywords):
                continue
            if any(kw in clean for kw in exclude_keywords):
                continue

            marker_match = re.search(
                r'(附件\s*(?:\d+|[一二三四五六七八九十]+)(?:[-−]\d+)?)|'
                r'(第\s*(?:\d+|[一二三四五六七八九十]+)\s*(?:部分|章|节))|'
                r'(?<!\d)(\d{1,2})(?:\.\d+)*\s*[、.．。\s]',
                clean,
            )
            if not marker_match:
                continue

            marker = marker_match.group(0).strip()
            prefix = BidPipeline._attachment_prefix(marker)
            if not prefix:
                continue

            score = 0
            if "技术方案" in clean:
                score += 50
            if "技术路线" in clean:
                score += 45
            if "证明材料及方案" in clean:
                score += 40
            if "方案" in clean:
                score += 20
            if re.search(r'附件\s*(?:\d+|[一二三四五六七八九十]+)', clean):
                score += 10

            candidates.append({
                "line_index": idx,
                "line_text": clean,
                "marker": marker,
                "prefix": prefix,
                "score": score,
            })

        if candidates:
            candidates.sort(key=lambda item: (-item["score"], item["line_index"]))
            selected = candidates[0]
        else:
            selected = {
                "line_index": -1,
                "line_text": "",
                "marker": "附件11",
                "prefix": "11",
                "score": 0,
            }

        section_map = BidPipeline._build_technical_section_map(selected["prefix"])
        chapter_map = BidPipeline._build_chapter_number_map_from_section_map(section_map)
        return {
            "selected": selected,
            "candidates": candidates[:20],
            "technical_section_map": section_map,
            "chapter_number_map": chapter_map,
            "algorithm": "regex_keywords_marker_prefix_v1",
            "keywords": keywords,
            "generated_at": datetime.datetime.now().isoformat(),
        }

    @staticmethod
    def _enforce_technical_section_numbering(md_text: str, section_map: Dict[str, str]) -> str:
        """生成后确定性修正技术方案一级章节及其子章节编号。"""
        if not section_map:
            return md_text

        normalized_to_title = {
            BidPipeline._normalize_title(title): title
            for title in section_map
        }
        for canonical, aliases in TECHNICAL_SECTION_ALIASES.items():
            if canonical in section_map:
                for alias in aliases:
                    normalized_to_title[BidPipeline._normalize_title(alias)] = canonical
        lines = md_text.splitlines()
        result: List[str] = []
        current_main_num = ""
        child_counters: Dict[str, int] = {}

        for line in lines:
            match = re.match(r'^(#{2,6})\s+(.+?)\s*$', line)
            if not match:
                result.append(line)
                continue

            hashes, raw_title = match.groups()
            level = len(hashes)
            title_without_num = re.sub(r'^\d+(?:\.\d+)*[、，．。\s]+', '', raw_title).strip()
            title_without_num = re.sub(r'^[一二三四五六七八九十]+[、，．。\s]+', '', title_without_num).strip()
            norm = BidPipeline._normalize_title(title_without_num)

            matched_title = normalized_to_title.get(norm)
            if not matched_title:
                for n_title, canonical in normalized_to_title.items():
                    if n_title and (n_title in norm or norm in n_title):
                        matched_title = canonical
                        break

            if level == 2 and matched_title:
                current_main_num = section_map[matched_title]
                child_counters[current_main_num] = 0
                result.append(f"## {current_main_num} {matched_title}")
                continue

            if level > 2 and current_main_num:
                child_title = title_without_num
                old_num_match = re.match(r'^(\d+(?:\.\d+)+)', raw_title.strip())
                if old_num_match:
                    old_parts = old_num_match.group(1).split(".")
                    suffix = old_parts[-(level - 2):]
                    if suffix:
                        new_num = ".".join([current_main_num] + suffix)
                    else:
                        child_counters[current_main_num] = child_counters.get(current_main_num, 0) + 1
                        new_num = f"{current_main_num}.{child_counters[current_main_num]}"
                else:
                    child_counters[current_main_num] = child_counters.get(current_main_num, 0) + 1
                    new_num = f"{current_main_num}.{child_counters[current_main_num]}"
                result.append(f"{hashes} {new_num} {child_title}")
                continue

            result.append(line)

        return "\n".join(result)

    def _load_technical_section_map(self) -> Dict[str, str]:
        """从缓存加载 pipeline 生成的 technical_section_map。"""
        candidate_paths = [
            self._cache(3) / "technical_section_map.json",
            self._cache(4) / "technical_section_map.json",
            self._cache(4) / "chapter_number_map.json",
        ]
        for path in candidate_paths:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if "technical_section_map" in data:
                    return dict(data["technical_section_map"])
                if all(title in data for title in TECHNICAL_SECTION_TITLES):
                    return {title: data[title] for title in TECHNICAL_SECTION_TITLES}
            except Exception:
                continue
        return {}

    def _build_chapter_numbering_context(self) -> str:
        """构建章节编号指令文本，追加到 AI prompt 中。"""
        section_map = self._load_technical_section_map()
        chapter_map = self._chapter_number_map
        if not chapter_map:
            map_path = self._cache(4) / "chapter_number_map.json"
            if map_path.exists():
                try:
                    chapter_map = json.loads(map_path.read_text(encoding="utf-8"))
                    self._chapter_number_map = chapter_map
                except Exception:
                    pass

        if not chapter_map:
            return ""

        prefix = chapter_map.get("_prefix", "")
        if not section_map:
            section_map = chapter_map.get("technical_section_map", {})

        section_lines = [
            f"  ## {section_map[title]} {title}"
            for title in TECHNICAL_SECTION_TITLES
            if title in section_map
        ]

        return f"""---
## ⚠️ 章节编号要求（重要）

pipeline 已通过 regex 定位技术方案所在标号，并用算法生成 `technical_section_map`。
**模型不得自行生成、猜测或改写右侧编号；必须逐字使用以下映射：**

technical_section_map:
{json.dumps(section_map, ensure_ascii=False, indent=2)}

章节标题必须按以下形式输出：
{chr(10).join(section_lines)}

编号规则：
- 一级章节只能使用 technical_section_map 中给定的编号，例如 ## {prefix}.1 章节名
- 二级子章节在对应一级章节下顺延，例如 ### {prefix}.1.1 子章节名
- 三级子章节继续顺延，例如 #### {prefix}.1.1.1 子章节名

**注意：必须以 `# 投标技术方案` 开头，但章节标题使用上述编号，不要使用中文数字。**"""

    # ── 主入口 ──────────────────────────────────────────────

    def run(self) -> int:
        """执行 Pipeline。返回 0 成功，1 失败。"""
        stages = self.config.get_stages()
        start_stage = self.args.from_stage or 0
        only_stage = self.args.only_stage

        if only_stage is not None:
            return self._run_single_stage(only_stage)

        self.state.set_started()
        target_bid = self.config.get_target_bid()
        task_id = self.config.get_task_package_id()
        print("=" * 60)
        print("  标书与技术方案自动生成 Pipeline v2")
        print(f"  输入: {self.config.get_input_docx()}")
        if task_id is not None:
            print(f"  目标任务: 第{task_id}包")
        print(f"  生成模式: {self.run_mode}")
        if self.run_mode in ("mixed", "accompany_only"):
            print(f"  参考文件数量: {self.config.get_num_accompanying()}")
        if self.config.is_winning_enabled() and self.run_mode != "accompany_only":
            print(f"  中标方案: 已启用")
        if self.config.is_technical_only():
            print(f"  内容范围: 仅技术章节")
        if target_bid is not None:
            print(f"  目标参考文件: 仅处理第 {target_bid} 个参考文件")
        print(f"  输出: {self.cache_dir}")
        print("=" * 60)

        completed = self.state.get_completed_stages() if not self.args.force else 0
        actual_start = max(start_stage, completed)

        # ── Pre-stage: 参考文件分析（先分析 profile/ 再解析核心标书）──
        if actual_start <= 0 and not self.args.force:
            print("\n  ▶ 先分析参考文件（profile/），再解析核心标书...")
            ok = self._execute_prestage_profile()
            if not ok:
                print("  [WARN] 参考文件分析失败，继续执行...")

        if actual_start > 0 and not self.args.force:
            print(f"\n  从 Stage {actual_start} 继续 (已完成 {completed} 个阶段)")

        for stage in stages:
            sid = stage["id"]
            if sid < actual_start:
                print(f"\n  [SKIP] Stage {sid}: {stage['name']} (已完成)")
                continue
            if not stage.get("enabled", True):
                print(f"\n  [SKIP] Stage {sid}: {stage['name']} (已禁用)")
                continue

            ok = self._execute_stage(sid)
            if not ok:
                print(f"\n  [FAIL] Stage {sid}: {stage['name']} 执行失败")
                return 1

            self.state.mark_stage_complete(sid, {"name": stage["name"]})
            self.state.save()

        print("\n" + "=" * 60)
        print("  Pipeline 完成！")
        self._print_summary()
        print("=" * 60)
        return 0

    def _run_single_stage(self, stage_id: int) -> int:
        """仅执行单个阶段（调试用）。"""
        stages = self.config.get_stages()
        stage_info = next((s for s in stages if s["id"] == stage_id), None)
        if not stage_info:
            print(f"无效的阶段 ID: {stage_id}")
            return 1
        print(f"\n  [ONLY] Stage {stage_id}: {stage_info['name']}")
        ok = self._execute_stage(stage_id)
        return 0 if ok else 1

    # ── Stage 0: 文档解析 ───────────────────────────────────

    def _execute_stage_0(self) -> bool:
        """解析标书 .docx 文件（从 uploads/）→ .cache/01_parsed/"""
        print("\n  [Stage 0] 文档解析（核心标书）...")
        # Read from session uploads/ directory
        docx_path = self.config.get_input_docx()
        # If uploads/bid_document.docx exists, use it
        upload_docx = self.workspace / "uploads" / "bid_document.docx"
        if upload_docx.exists():
            docx_path = upload_docx
        elif not docx_path.exists():
            # Fallback: search uploads/ for any .docx
            uploads_dir = self.workspace / "uploads"
            if uploads_dir.exists():
                docx_files = list(uploads_dir.glob("*.docx"))
                if docx_files:
                    docx_path = docx_files[0]
        print(f"    标书文件: {docx_path}")
        output_dir = self._cache(0)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            parser = BidDocumentParser(docx_path, output_dir)
            self.parsed_doc = parser.parse()
            print(f"    段落: {self.parsed_doc.total_paragraphs}")
            print(f"    表格: {self.parsed_doc.total_tables}")
            print(f"    图片: {self.parsed_doc.total_images}")
            print(f"    一级章节: {len(self.parsed_doc.sections)}")
            self._notify_progress(0, "progress", f"解析完成: {self.parsed_doc.total_paragraphs}段落, {self.parsed_doc.total_tables}表格, {self.parsed_doc.total_images}图片, {len(self.parsed_doc.sections)}章节")
            return True
        except FileNotFoundError as e:
            print(f"    [ERROR] {e}")
            return False
        except Exception as e:
            print(f"    [ERROR] 解析失败: {e}")
            return False

    # ── Stage 1: 标书总结 ───────────────────────────────────

    def _execute_stage_1(self) -> bool:
        """使用 Claude 生成标书总结 → .cache/02_summary/"""
        print("\n  [Stage 1] 标书总结...")

        output_dir = self._cache(1)
        output_dir.mkdir(parents=True, exist_ok=True)

        full_text_path = self._cache(0) / "full_text.md"
        if not full_text_path.exists():
            print("    [ERROR] 未找到解析结果，请先执行 Stage 0")
            return False

        parsed_text = full_text_path.read_text(encoding="utf-8")

        # 使用通用型 prompt 构建（从 .cache 加载）
        prompt = self.skills.build_prompt(
            "summarize-bid",
            context=parsed_text[:30000],  # 增大上下文以覆盖完整标书结构
        )

        # ── 追加最终输出约束（必须在 prompt 最末尾，覆盖其他指令）──
        prompt += """

---
## ⚠️ 最终输出指令（最高优先级）

**你必须直接输出完整的标书总结正文。以下行为将导致生成失败：**

1. ❌ 禁止输出"标书总结已生成并写入以下文件""总结已生成""以下是对XX的分析"等过程报告
2. ❌ 禁止输出文件路径列表或"共覆盖XX章节""总计XX字"等统计信息
3. ❌ 禁止输出元描述、自检清单结果、验证报告
4. ❌ 禁止使用占位符（除 `[待确认]` 外，最多5处）
5. ✅ 必须以 `# 标书总结` 开头，直接开始正文
6. ✅ 必须包含全部 7 个章节，每个章节有实质性内容
7. ✅ 总字数 ≥ 1850 字

**现在直接输出标书总结正文（从 `# 标书总结` 开始）：**"""

        out_file = output_dir / "bid_summary.md"
        ok = self.runner.run(prompt, out_file, stage_name="01_标书总结")
        if not ok:
            return False

        json_out = output_dir / "bid_summary.json"
        json_out.write_text(
            json.dumps(
                {
                    "generated_at": datetime.datetime.now().isoformat(),
                    "source": str(out_file),
                    "note": "完整总结请参阅 bid_summary.md",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        prompt_file = output_dir / "summary_prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        return True

    # ── Stage 2: 需求提取 ───────────────────────────────────

    def _execute_stage_2(self) -> bool:
        """使用 Claude 提取标书需求清单 → .cache/03_requirements/"""
        print("\n  [Stage 2] 需求提取...")

        output_dir = self._cache(2)
        output_dir.mkdir(parents=True, exist_ok=True)

        full_text_path = self._cache(0) / "full_text.md"
        summary_path = self._cache(1) / "bid_summary.md"

        if not full_text_path.exists():
            print("    [ERROR] 未找到解析结果")
            return False

        task_id = self.config.get_task_package_id()
        if task_id is not None:
            self.task_content = self._extract_task_content(task_id)
            print(f"    已筛选第{task_id}包内容 ({len(self.task_content)} 字符)")
            parsed_text = self.task_content[:12000]
        else:
            parsed_text = full_text_path.read_text(encoding="utf-8")[:15000]

        summary_text = ""
        if summary_path.exists():
            summary_text = summary_path.read_text(encoding="utf-8")[:3000]

        tables_text = ""
        tables_path = self._cache(0) / "tables.json"
        if tables_path.exists():
            tables_text = tables_path.read_text(encoding="utf-8")[:5000]

        heuristic_text = ""
        heuristic_path = self._cache(0) / "heuristic_requirements.json"
        if heuristic_path.exists():
            heuristic_text = heuristic_path.read_text(encoding="utf-8")[:5000]

        context = f"""## 标书全文（节选）
{parsed_text}

## 标书总结
{summary_text}

## 表格内容（节选，需求常出现在表格中）
{tables_text}

## 启发式需求候选
{heuristic_text}"""

        extra_instructions = f"""
请只输出一个 JSON 对象，不要输出说明文字、Markdown 代码块、文件生成报告或上下文回显。
JSON 顶层必须包含 `project_name`、`package_id`、`requirements`。
`requirements` 必须是数组，每个元素包含 req_id/category/text/mandatory/priority/source_section/source_paragraph/satisfaction_criteria/keywords。
当前目标标包: {task_id if task_id is not None else "全部"}。
"""
        prompt = self.skills.build_prompt(
            "extract-requirements",
            context=context,
            extra_instructions=extra_instructions,
        )

        raw_file = output_dir / "requirements_raw.json"
        ok = self.runner.run(prompt, raw_file, stage_name="02_需求提取")
        if not ok:
            return False

        heuristic_reqs: List[Dict[str, Any]] = []
        heuristic_path = self._cache(0) / "heuristic_requirements.json"
        if heuristic_path.exists():
            try:
                heuristic_reqs = json.loads(heuristic_path.read_text(encoding="utf-8"))
            except Exception:
                heuristic_reqs = []

        raw_text = raw_file.read_text(encoding="utf-8")
        payload = self._build_requirements_payload(raw_text, task_id, heuristic_reqs)
        if payload.get("source") == "heuristic_fallback":
            print("    [WARN] AI 需求 JSON 解析失败，已使用启发式需求兜底")

        json_out = output_dir / "requirements.json"
        json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        out_file = output_dir / "requirements.md"
        out_file.write_text(self._requirements_to_markdown(payload), encoding="utf-8")

        checklist_file = output_dir / "requirements_checklist.md"
        checklist_file.write_text(self._requirements_to_checklist(payload), encoding="utf-8")

        prompt_file = output_dir / "extract_prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        self.requirements = payload.get("requirements", [])
        print(f"    需求清单: {len(self.requirements)} 条 → requirements.md / requirements.json / requirements_checklist.md")

        return True

    # ── Stage 3: 技术章节定位 ───────────────────────────────

    def _execute_stage_3(self) -> bool:
        """用 regex 定位技术方案所在标号，不再解析投标文件格式模板。"""
        print("\n  [Stage 3] 技术章节定位（regex）...")

        output_dir = self._cache(3)
        output_dir.mkdir(parents=True, exist_ok=True)

        full_text_path = self._cache(0) / "full_text.md"
        full_text = full_text_path.read_text(encoding="utf-8") if full_text_path.exists() else ""
        location = self._locate_technical_section_by_regex(full_text)
        selected = location["selected"]
        technical_section_map = location["technical_section_map"]
        chapter_map = location["chapter_number_map"]

        self.has_template = False
        self._chapter_number_map = chapter_map

        technical_section = {
            "marker": selected.get("marker") or f"附件{selected.get('prefix', '11')}",
            "title": selected.get("line_text") or "附件11 证明材料及方案",
            "description": "技术方案正文（regex定位）",
            "type": "technical",
            "prefix": selected.get("prefix", "11"),
        }

        template_map = {
            "template_found": False,
            "template_source": None,
            "format_parsing_disabled": True,
            "total_attachments": 1,
            "sections": [technical_section],
            "insertion_plan": [],
            "technical_section": technical_section,
            "technical_section_map": technical_section_map,
            "chapter_number_map": chapter_map,
            "regex_location": location,
            "analysis_notes": [
                "已禁用投标文件格式解析，不再裁切或学习标书格式。",
                "技术方案位置由 regex 关键词和标号算法定位。",
                "后续仅导出默认格式的独立技术方案和应答表。",
            ],
            "analysis_timestamp": datetime.datetime.now().isoformat(),
        }

        map_path = output_dir / "template_map.json"
        map_path.write_text(
            json.dumps(template_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "technical_section_map.json").write_text(
            json.dumps(technical_section_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "chapter_number_map.json").write_text(
            json.dumps(chapter_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        no_template_path = output_dir / "format_parsing_disabled.txt"
        no_template_path.write_text(
            "投标文件格式解析已禁用。\n"
            "pipeline 将直接使用默认 DOCX 格式，并通过 regex 定位技术方案编号。\n"
            f"定位标号: {technical_section['marker']}\n"
            f"编号前缀: {technical_section['prefix']}\n"
            f"时间: {datetime.datetime.now().isoformat()}\n",
            encoding="utf-8",
        )

        print(f"    技术章节定位: {technical_section['marker']} → 前缀 {technical_section['prefix']}")
        print(f"    技术章节映射 → technical_section_map.json")

        report_path = output_dir / "template_analysis.md"
        self._write_template_analysis_report(template_map, report_path)
        print(f"    定位报告 → template_analysis.md")

        self._notify_progress(3, "progress", f"技术章节定位完成: {technical_section['marker']}")
        return True

    def _analyze_template_structure(self, templates_docx: Path) -> Dict[str, Any]:
        """
        动态分析模板 DOCX 结构，输出插入映射。

        不硬编码附件编号——从文档内容自动推断每个附件的类型。
        """
        from docx import Document as DocxDoc
        doc = DocxDoc(str(templates_docx))

        # ── 识别所有章节标记 ──
        sections = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # 识别附件标记
            att_match = re.match(r'(附件\d+(?:[-−]\d+)?)\s*[：:]?\s*(.*)', text)
            if att_match:
                att_id = att_match.group(1)
                att_title = text
                att_desc = att_match.group(2) if att_match.group(2) else ""

                # 动态判断类型
                sec_type = self._classify_attachment(att_id, att_title, att_desc)
                sections.append({
                    "marker": att_id,
                    "title": att_title,
                    "description": att_desc,
                    "type": sec_type,
                })

            # 识别章节编号标题（如 "13.2.1 平台功能要求"）
            chapter_match = re.match(r'(\d+(?:\.\d+)+)\s+(.+)', text)
            if chapter_match:
                chapter_num = chapter_match.group(1)
                chapter_title = chapter_match.group(2)
                # 判断是否与技术相关
                sec_type = self._classify_attachment(chapter_num, text, "")
                if sec_type != "business":
                    sections.append({
                        "marker": chapter_num,
                        "title": text,
                        "type": sec_type,
                    })

        # ── 构建插入计划 ──
        insertion_plan = []
        step = 0
        for s in sections:
            if s["type"] == "response_table":
                step += 1
                insertion_plan.append({
                    "step": step,
                    "target": s["marker"],
                    "content": "response_table",
                    "description": f"{s['marker']} — 技术应答表",
                })
            elif s["type"] == "technical":
                step += 1
                insertion_plan.append({
                    "step": step,
                    "target": s["marker"],
                    "content": "technical_chapters",
                    "description": f"{s['marker']} — 技术方案正文",
                })

        # ── 构建章节编号映射 ──
        # 找到技术方案插入附件，尝试提取编号前缀
        tech_section = next((s for s in sections if s["type"] == "technical"), None)
        chapter_map = {}
        if tech_section:
            # 尝试从附件标题中提取编号信息
            # 常见模式：附件11（在13.x之前）→ 编号前缀为 "13"
            chapter_map = self._build_chapter_map_from_template(sections, tech_section)

        return {
            "sections": sections,
            "insertion_plan": insertion_plan,
            "chapter_number_map": chapter_map,
            "analysis_timestamp": datetime.datetime.now().isoformat(),
        }

    @staticmethod
    def _classify_attachment(att_id: str, title: str, description: str) -> str:
        """
        根据附件内容特征动态判断类型。

        判断优先级: response_table > technical > business
        """
        full_text = f"{title} {description}".lower()

        # 应答表特征
        response_keywords = [
            "应答表", "点对点", "技术要求响应",
            "功能参数要求", "需求响应表", "一对一应答",
        ]
        if any(kw in full_text for kw in response_keywords):
            return "response_table"

        # 技术方案特征
        technical_keywords = [
            "技术方案", "实施方案", "服务方案", "证明材料及方案",
            "设计方案", "技术架构", "系统方案", "项目服务方案",
        ]
        if any(kw in full_text for kw in technical_keywords):
            return "technical"

        # 默认商务附件
        return "business"

    @staticmethod
    def _build_chapter_map_from_template(
        sections: List[Dict[str, Any]],
        tech_section: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        从模板结构中构建章节编号映射。

        尝试从技术方案插入点附近的编号推断编号体系。
        如果无法推断，使用默认的阿拉伯数字编号。
        """
        # 查找技术附件之前的章节编号
        tech_marker = tech_section.get("marker", "")
        tech_idx = next((i for i, s in enumerate(sections) if s["marker"] == tech_marker), -1)

        # 尝试从附近章节推断编号前缀
        prefix = None
        if tech_idx > 0:
            # 查找前面最近的数字编号章节
            for i in range(tech_idx - 1, -1, -1):
                prev = sections[i]
                # 尝试匹配 "XX.XX.XX" 格式
                match = re.match(r'(\d+)\.\d+', prev.get("marker", ""))
                if match:
                    prefix = match.group(1)
                    break

        if prefix is None:
            # 从附件编号推断：附件11 → 可能在13章节附近
            att_num_match = re.search(r'附件(\d+)', tech_marker)
            if att_num_match:
                att_num = int(att_num_match.group(1))
                # 附件号与章节号的常见偏移
                prefix = str(att_num + 2)  # 如 附件11 → 13

        if prefix is None:
            prefix = "1"

        chinese_numerals = ["一", "二", "三", "四", "五", "六", "七", "八"]
        ordered_sections = [f"{prefix}.{i}" for i in range(1, 9)]
        chapter_map = {
            "_prefix": prefix,
            "_ordered_sections": ordered_sections,
            "_chinese_numerals": chinese_numerals,
        }
        for i, cn in enumerate(chinese_numerals):
            chapter_map[cn] = f"{prefix}.{i + 1}"

        return chapter_map

    def _write_template_analysis_report(self, template_map: Dict[str, Any], report_path: Path) -> None:
        """生成人类可读的模板分析报告。"""
        sections = template_map.get("sections", [])
        insertion_plan = template_map.get("insertion_plan", [])
        chapter_map = template_map.get("chapter_number_map", {})
        technical_section_map = template_map.get("technical_section_map", {})
        format_disabled = template_map.get("format_parsing_disabled", False)

        lines = [
            "# 技术章节定位报告" if format_disabled else "# 投标模板结构分析报告",
            "",
            f"生成时间: {template_map.get('analysis_timestamp', 'N/A')}",
            "",
            "## 定位结果" if format_disabled else "## 附件识别结果",
            "",
        ]

        type_labels = {"business": "📋 商务附件", "technical": "🔧 技术方案", "response_table": "📊 应答表"}
        for s in sections:
            label = type_labels.get(s["type"], "❓ 未知")
            lines.append(f"- **{s['marker']}** ({label}): {s.get('title', '')}")

        if insertion_plan:
            lines.extend([
                "",
                "## 插入计划",
                "",
            ])
            for step in insertion_plan:
                lines.append(f"{step['step']}. **{step['target']}** ← 插入 `{step['content']}` ({step['description']})")

        if chapter_map:
            prefix = chapter_map.get("_prefix", "?")
            lines.extend([
                "",
                "## 章节编号映射",
                "",
                f"编号前缀: `{prefix}`",
                f"章节数: {len(chapter_map.get('_ordered_sections', []))}",
                "",
            ])
            for cn in chapter_map.get("_chinese_numerals", []):
                if cn in chapter_map:
                    lines.append(f"- {cn} → {chapter_map[cn]}")

        if technical_section_map:
            lines.extend([
                "",
                "## technical_section_map",
                "",
            ])
            for title in TECHNICAL_SECTION_TITLES:
                if title in technical_section_map:
                    lines.append(f"- {title}: `{technical_section_map[title]}`")

        lines.extend([
            "",
            "## 注意事项",
            "",
            "- 投标文件格式解析已禁用，后续直接使用默认 DOCX 格式",
            "- 技术方案一级章节编号由 pipeline 算法生成，不交给模型自由生成",
            "- 应答表基于最终技术方案生成",
            "- 如果定位结果有误，请手动编辑 `technical_section_map.json` 后重新运行后续阶段",
        ])

        report_path.write_text("\n".join(lines), encoding="utf-8")

    # ── Stage 4: 默认格式准备 ───────────────────────────────

    def _execute_stage_4(self) -> bool:
        """直接使用默认格式规格，并继承 regex 生成的技术章节编号。"""
        print("\n  [Stage 4] 默认格式准备（不解析标书格式）...")

        output_dir = self._cache(4)
        output_dir.mkdir(parents=True, exist_ok=True)

        template_map_path = self._cache(3) / "template_map.json"
        if template_map_path.exists():
            template_map = json.loads(template_map_path.read_text(encoding="utf-8"))
            print("    已加载 regex 技术章节定位结果")
        else:
            template_map = {}
            print("    [WARN] 未找到技术章节定位结果，将使用默认附件11")

        technical_section_map = template_map.get("technical_section_map") or self._build_technical_section_map("11")
        chapter_map = (
            template_map.get("chapter_number_map")
            or self._build_chapter_number_map_from_section_map(technical_section_map)
        )

        adapter = FormatAdapter(self.config)
        self.format_spec = adapter.get_default_format_spec()
        self.format_spec.technical_section_map = dict(technical_section_map)
        self.format_spec.source_section = "(默认格式；未解析标书格式)"
        self.format_spec.source_found = False
        self.format_spec.narrative_patterns = {}

        spec_path = output_dir / "format_spec.json"
        save_format_spec(self.format_spec, spec_path)
        (output_dir / "technical_section_map.json").write_text(
            json.dumps(technical_section_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "narrative_patterns.json").write_text(
            json.dumps({}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        map_path = output_dir / "chapter_number_map.json"
        map_path.write_text(
            json.dumps(chapter_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._chapter_number_map = chapter_map

        print("    默认格式规格已保存: format_spec.json")
        print(f"    技术章节编号前缀: {chapter_map.get('_prefix', '11')}.x")
        print(f"    技术章节映射: {len(technical_section_map)} 个")

        return True

    # ── Stage 5: 投标策略生成 ───────────────────────────────

    def _execute_stage_5(self) -> bool:
        """按 pipeline_config.yaml 生成中标方案和可变数量参考方案策略 → .cache/06_strategies/"""
        print("\n  [Stage 5] 投标策略生成...")

        task_id = self.config.get_task_package_id() or 0

        # 加载需求
        if not self.requirements:
            heuristic_path = self._cache(0) / "heuristic_requirements.json"
            if heuristic_path.exists():
                self.requirements = json.loads(heuristic_path.read_text(encoding="utf-8"))
            else:
                self.requirements = []
                print("    [WARN] 未找到需求数据，将使用空列表")

        # 生成中标方案和配置中所有独立参考方案。
        engine = DegradeEngine(self.requirements, self.config)
        self.strategies = engine.generate_strategies(task_package_id=task_id)

        output_dir = self._cache(5)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._notify_progress(5, "progress", f"正在生成 {len(self.strategies)} 份方案策略...")
        for strategy in self.strategies:
            print(f"    {strategy.strategy_name}: {strategy.tech_stack.name} / {strategy.team_plan.total}人 / {strategy.timeline.total_days}天")

        # 保存策略到 06_strategies/
        strategy_paths = save_strategies(self.strategies, output_dir)

        print(f"\n    共生成 {len(self.strategies)} 个策略 → .cache/06_strategies/")
        return True

    # ── Stage 6: 标书内容生成 ───────────────────────────────

    def _execute_stage_6(self) -> bool:
        """使用 Claude 生成中标+参考文件技术方案内容 → .cache/07_bids/"""
        print("\n  [Stage 6] 标书内容生成...")

        if not self.strategies:
            # 尝试从缓存加载
            degrade_dir = self._cache(5)
            if degrade_dir.exists():
                self.strategies = []
                for f in sorted(degrade_dir.glob("bid_*_strategy.json")):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        from lib.degrade_engine import DegradeStrategy, TechStackConfig, TeamPlan, Timeline
                        s = DegradeStrategy(
                            strategy_id=data.get("strategy_id", ""),
                            bid_index=data.get("bid_index", 0),
                            strategy_name=data.get("strategy_name", ""),
                            satisfaction_rate=data.get("satisfaction_rate", 0.75),
                            is_winning=data.get("is_winning", False),
                            task_package_id=data.get("task_package_id", 0),
                        )
                        self.strategies.append(s)
                    except Exception:
                        pass

            if not self.strategies:
                print("    [ERROR] 未找到投标策略，请先执行 Stage 5")
                return False

        # 读取解析内容
        full_text_path = self._cache(0) / "full_text.md"
        task_id = self.config.get_task_package_id()
        if task_id is not None and self.task_content:
            parsed_text = self.task_content[:10000]
        elif full_text_path.exists():
            parsed_text = full_text_path.read_text(encoding="utf-8")[:10000]
        else:
            parsed_text = ""

        # 读取需求
        reqs_text = ""
        reqs_path = self._cache(2) / "requirements.md"
        if reqs_path.exists():
            reqs_text = reqs_path.read_text(encoding="utf-8")[:8000]

        # 构建任务信息文本
        task_info = ""
        if task_id is not None:
            task_labels = {1: "第一包", 2: "第二包", 3: "第三包", 4: "第四包", 5: "第五包"}
            task_info = f"目标标包：{task_labels.get(task_id, f'第{task_id}包')}\n\n{self.task_content[:3000]}"

        all_ok = True
        bids_dir = self._cache(6)
        bids_dir.mkdir(parents=True, exist_ok=True)

        for s in self.strategies:
            idx = s.bid_index
            is_winning = getattr(s, 'is_winning', False)

            # 方案目录
            if is_winning:
                bid_dir = bids_dir / "bid_00_winning"
            else:
                bid_dir = bids_dir / f"bid_{idx:02d}"

            bid_dir.mkdir(parents=True, exist_ok=True)

            draft_file = bid_dir / "bid_draft.md"
            if draft_file.exists() and self.args.resume:
                bid_type = "中标方案" if is_winning else f"参考文件 {idx}"
                print(f"    {bid_type}: 已存在，跳过 (--resume 模式)")
                self.state.set_bid_status(idx if not is_winning else 0, "completed", str(draft_file))
                continue

            bid_type = "中标方案" if is_winning else f"参考文件 {idx}"
            print(f"    生成 {bid_type}: {s.strategy_name}...")
            self._notify_progress(6, "progress", f"正在生成 {bid_type}: {s.strategy_name}")

            # 加载完整策略
            strategy_path = self._cache(5) / f"{s.strategy_id}_strategy.json"
            strategy_dict = {}
            if strategy_path.exists():
                strategy_dict = json.loads(strategy_path.read_text(encoding="utf-8"))
            else:
                strategy_dict = s.to_dict() if hasattr(s, 'to_dict') else {}

            prompt = self.skills.build_solution_prompt(
                strategy_dict,
                reqs_text,
                parsed_text,
                task_info,
            )

            # ── 追加章节编号指令 ──
            chapter_context = self._build_chapter_numbering_context()
            if chapter_context:
                prompt = prompt + "\n\n" + chapter_context

            # 保存 prompt
            prompt_file = bid_dir / "bid_prompt.txt"
            prompt_file.write_text(prompt, encoding="utf-8")

            # 调用 Claude 生成
            ok = self.runner.run(
                prompt,
                draft_file,
                stage_name=f"06_{bid_type}",
                output_validator=DocumentOutputGuard.validator("proposal"),
            )
            if ok:
                technical_section_map = self._load_technical_section_map()
                if technical_section_map:
                    try:
                        raw_text = draft_file.read_text(encoding="utf-8")
                        raw_file = bid_dir / "bid_draft_raw.md"
                        if not raw_file.exists():
                            raw_file.write_text(raw_text, encoding="utf-8")
                        numbered = self._enforce_technical_section_numbering(raw_text, technical_section_map)
                        draft_file.write_text(numbered, encoding="utf-8")
                        (bid_dir / "technical_section_map.json").write_text(
                            json.dumps(technical_section_map, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        print(f"    章节编号已按 technical_section_map 校正: {bid_dir.name}")
                    except Exception as e:
                        print(f"    [WARN] 章节编号校正失败: {e}")
                self.state.set_bid_status(idx if not is_winning else 0, "completed", str(draft_file))
                self.state.save()
            else:
                print(f"    [FAIL] {bid_type} 生成失败")
                self.state.set_bid_status(idx if not is_winning else 0, "failed")
                all_ok = False

        return all_ok

    # ── Stage 7: 模板内容填充 ───────────────────────────────

    def _execute_stage_7(self) -> bool:
        """【条件】使用 Word COM 将 AI 生成的技术内容插入模板 → .cache/08_filled/

        格式模板拼接已禁用，默认跳过。
        技术方案和应答表仍会在 Stage 10 独立导出。
        """
        print("\n  [Stage 7] 模板内容填充（Word COM）...")

        # ── 条件检查：是否有模板 ──
        if not self.has_template:
            print("    ⏭ 未检测到投标模板，跳过模板填充")
            print("    → 技术方案和应答表将在 Stage 10 独立导出")
            self._notify_progress(7, "progress", "跳过: 无模板可填充")
            # Create empty output marker
            output_dir = self._cache(7)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "_template_skipped.txt").write_text(
                "模板填充已跳过：未检测到投标文件格式模板。\n"
                "技术方案和应答表将在 Stage 10 独立导出为 output/ 下的文件。\n",
                encoding="utf-8",
            )
            return True

        # Session-scoped template path
        templates_docx = self.workspace / "templates" / "template.docx"
        if not templates_docx.exists():
            # Fallback to global
            templates_docx = ROOT / "templates" / "templates.docx"
        if not templates_docx.exists():
            print("    [ERROR] 模板文件不存在")
            return False

        output_dir = self._cache(7)
        output_dir.mkdir(parents=True, exist_ok=True)

        bids_dir = self._cache(6)
        response_dir = self._cache(9)
        target_bid = self.config.get_target_bid()

        # ── 兼容旧缓存：如果手动开启模板拼接，可继续读取 insertion_plan ──
        insertion_plan = None
        template_map_path = self._cache(3) / "template_map.json"
        if template_map_path.exists():
            try:
                template_map = json.loads(template_map_path.read_text(encoding="utf-8"))
                insertion_plan = template_map.get("insertion_plan", None)
                if insertion_plan:
                    print(f"    已加载插入计划 ({len(insertion_plan)} 个步骤)")
                else:
                    print(f"    [INFO] template_map.json 中无 insertion_plan，将使用默认插入位置")
            except Exception as e:
                print(f"    [WARN] 加载 insertion_plan 失败: {e}")

        # ── 初始化 COM ──
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()

        word = None
        filled_count = 0

        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            word.ScreenUpdating = False

            for bid_dir in sorted(bids_dir.iterdir()):
                if not bid_dir.is_dir():
                    continue

                is_winning = bid_dir.name == "bid_00_winning"
                if target_bid is not None and not is_winning:
                    try:
                        if int(bid_dir.name.replace("bid_", "")) != target_bid:
                            continue
                    except ValueError:
                        pass

                # 优先使用格式化 DOCX，其次 MD
                draft_docx = bid_dir / "bid_output.docx"
                if not draft_docx.exists():
                    docx_files = list(bid_dir.glob("*.docx"))
                    if docx_files:
                        draft_docx = docx_files[0]
                draft_md = bid_dir / "bid_draft_renumbered.md"
                if not draft_md.exists():
                    draft_md = bid_dir / "bid_draft.md"

                if not draft_docx.exists() and not draft_md.exists():
                    continue

                bid_label = "中标方案" if is_winning else f"参考文件{bid_dir.name}"
                filled_path = output_dir / f"{bid_dir.name}_filled.docx"

                print(f"    填充 {bid_label}...")
                self._notify_progress(7, "progress", f"正在填充 {bid_label} 到模板...")

                response_table = response_dir / f"{bid_dir.name}_response_table.docx"
                if not response_table.exists():
                    response_table = None

                try:
                    composer = WordComposer(templates_docx, filled_path)
                    composer.word = word
                    composer.compose(
                        response_table_path=response_table,
                        technical_draft_path=draft_docx if draft_docx.exists() else draft_md,
                        strategy_name=bid_label,
                        insertion_plan=insertion_plan,
                    )
                    filled_count += 1
                    print(f"    [OK] {bid_dir.name}_filled.docx")
                except Exception as e:
                    print(f"    [FAIL] {bid_label}: {e}")

        finally:
            if word is not None:
                try:
                    word.ScreenUpdating = True
                    word.Quit()
                except Exception:
                    pass
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

        print(f"    共填充 {filled_count} 个文档")
        return filled_count > 0

    # ── Stage 8: DOCX 导出 ──────────────────────────────────

    def _execute_stage_8(self) -> bool:
        """将 Markdown 标书导出为格式化 .docx 文件 → .cache/09_exported/"""
        print("\n  [Stage 8] DOCX 导出...")

        bids_dir = self._cache(6)
        if not bids_dir.exists():
            print("    [ERROR] 未找到标书生成结果")
            return False

        task_id = self.config.get_task_package_id()
        task_labels = {1: "第一包", 2: "第二包", 3: "第三包", 4: "第四包", 5: "第五包"}
        task_suffix = f"_{task_labels.get(task_id, f'第{task_id}包')}" if task_id else ""

        exported = 0
        target_bid = self.config.get_target_bid()
        for bid_dir in sorted(bids_dir.iterdir()):
            if not bid_dir.is_dir():
                continue

            draft_file = bid_dir / "bid_draft.md"
            if not draft_file.exists():
                print(f"    [SKIP] {bid_dir.name}: 无草稿文件")
                continue

            # ── 章节编号后处理已在 Stage 6 完成，这里仅保留旧逻辑注释作兼容说明 ──
            # if not self._chapter_number_map:
            #     map_path = self._cache(4) / "chapter_number_map.json"
            #     if map_path.exists():
            #         try:
            #             self._chapter_number_map = json.loads(map_path.read_text(encoding="utf-8"))
            #         except Exception:
            #             pass
            # if self._chapter_number_map:
            #     md_text = draft_file.read_text(encoding="utf-8")
            #     renumbered = self._renumber_chapters(md_text, self._chapter_number_map)
            #     renumbered_file = bid_dir / "bid_draft_renumbered.md"
            #     renumbered_file.write_text(renumbered, encoding="utf-8")
            #     draft_file = renumbered_file
            #     print(f"    章节编号已重映射: {bid_dir.name}")

            is_winning_dir = bid_dir.name == "bid_00_winning"

            if target_bid is not None and not is_winning_dir:
                try:
                    dir_idx = int(bid_dir.name.replace("bid_", ""))
                    if dir_idx != target_bid:
                        continue
                except ValueError:
                    pass

            # 读取策略文件获取方案名称
            strategy_file = self._cache(5) / f"{bid_dir.name}_strategy.json"
            strategy_name = ""
            tech_stack_name = ""
            if strategy_file.exists():
                try:
                    sd = json.loads(strategy_file.read_text(encoding="utf-8"))
                    strategy_name = sd.get("strategy_name", "")
                    ts = sd.get("tech_stack", {})
                    tech_stack_name = ts.get("name", "")
                except Exception:
                    pass

            if is_winning_dir:
                output_filename = f"中标方案{task_suffix}_{tech_stack_name or '现代AI技术方案'}.docx"
            else:
                try:
                    bid_num = int(bid_dir.name.replace("bid_", ""))
                except ValueError:
                    bid_num = bid_dir.name
                strategy_short = strategy_name.replace("技术栈", "").replace("技术方案", "") if strategy_name else f"方案{bid_num}"
                output_filename = f"参考文件方案{strategy_short}{task_suffix}.docx"

            output_file = bid_dir / output_filename

            if output_file.exists() and self.args.resume:
                print(f"    [SKIP] {output_filename}: 已存在 (--resume 模式)")
                exported += 1
                continue

            generic_output = bid_dir / "bid_output.docx"

            try:
                print(f"    导出 {output_filename}...")
                self._notify_progress(8, "progress", f"正在导出: {output_filename}")
                self.exporter.export_from_markdown(draft_file, output_file)
                import shutil
                try:
                    shutil.copy2(str(output_file), str(generic_output))
                except (PermissionError, OSError):
                    pass
                exported += 1
            except Exception as e:
                print(f"    [ERROR] {bid_dir.name} 导出失败: {e}")

        print(f"    共导出 {exported} 个 DOCX 文件")
        return exported > 0

    # ── Stage 9: 应答表生成 ──────────────────────────────────

    def _execute_stage_9(self) -> bool:
        """基于技术方案和原始需求生成技术一对一应答表 → .cache/10_response_tables/"""
        print("\n  [Stage 9] 应答表生成（AI Skill — 通用型）...")

        output_dir = self._cache(9)
        output_dir.mkdir(parents=True, exist_ok=True)

        bids_dir = self._cache(6)
        task_id = self.config.get_task_package_id()
        task_labels = {1: "第一包", 2: "第二包", 3: "第三包", 4: "第四包", 5: "第五包"}
        company_info = self.config.get_company_info()
        generated = 0

        for proposal in self._configured_proposals():
            bid_dir = bids_dir / proposal["bid_dir"]
            draft_file = bid_dir / "bid_draft.md"
            if not draft_file.exists():
                print(f"    [WARN] 未找到技术方案，跳过应答表: {proposal['name']}")
                continue

            bid_label = proposal["name"]
            print(f"    生成应答表: {bid_label}...")
            self._notify_progress(9, "progress", f"正在生成应答表: {bid_label}")

            draft_text = draft_file.read_text(encoding="utf-8")
            package_id = task_labels.get(task_id, f"第{task_id}包") if task_id else ""

            # 使用通用型 Skill 构建 prompt（自动从 .cache 加载需求清单和模板分析）
            try:
                prompt = self.skills.build_response_table_prompt(
                    technical_draft_text=draft_text,
                    project_name=company_info.get("name", ""),
                    package_id=package_id,
                    proposal_metadata=proposal,
                )
            except ValueError as e:
                print(f"    [ERROR] {e}")
                return self._execute_stage_9_fallback()

            cache_stem = f"{proposal['id']}_{proposal['export_basename']}_response_table"
            prompt_file = output_dir / f"{cache_stem}_prompt.txt"
            prompt_file.write_text(prompt, encoding="utf-8")

            response_md = output_dir / f"{cache_stem}.md"
            ok = self.runner.run(
                prompt,
                response_md,
                stage_name=f"09_{proposal['id']}",
                output_validator=DocumentOutputGuard.validator("response_table"),
            )
            if not ok:
                print(f"    [FAIL] {bid_label} AI 生成失败，尝试回退...")
                continue

            docx_path = output_dir / f"{cache_stem}.docx"
            try:
                self._convert_response_md_to_docx(response_md, docx_path, f"{proposal['name']}技术一对一应答表")
                generated += 1
            except Exception as e:
                print(f"    [WARN] DOCX 转换失败: {e}，保留 Markdown 版本")

        print(f"    共生成 {generated} 个应答表")
        return generated > 0

    def _execute_stage_9_fallback(self) -> bool:
        """回退方案：使用原有 ResponseTableGenerator 库代码。"""
        print("    [FALLBACK] 使用库代码生成应答表...")
        output_dir = self._cache(9)
        output_dir.mkdir(parents=True, exist_ok=True)

        format_spec = self.format_spec
        if format_spec is None:
            spec_path = self._cache(4) / "format_spec.json"
            if spec_path.exists():
                try:
                    format_spec = load_format_spec(spec_path)
                except Exception:
                    pass
        if format_spec is None:
            format_spec = FormatAdapter(self.config).get_default_format_spec()

        tables_json = self._cache(0) / "tables.json"
        full_text_path = self._cache(0) / "full_text.md"
        generator = ResponseTableGenerator(format_spec, self.config)
        requirements = generator.extract_platform_requirements(tables_json, full_text_path)
        print(f"    提取需求: {len(requirements)} 条")

        bids_dir = self._cache(6)
        task_id = self.config.get_task_package_id()
        task_labels = {1: "第一包", 2: "第二包", 3: "第三包", 4: "第四包", 5: "第五包"}
        company_info = self.config.get_company_info()
        generated = 0

        for proposal in self._configured_proposals():
            bid_dir = bids_dir / proposal["bid_dir"]
            draft_file = bid_dir / "bid_draft.md"
            if not draft_file.exists():
                continue

            matched_reqs = generator.match_responses(requirements, draft_file)
            cache_stem = f"{proposal['id']}_{proposal['export_basename']}_response_table"
            output_path = output_dir / f"{cache_stem}.docx"
            meta = {
                "project_name": company_info.get("name", "") or self.config.get_input_docx().stem,
                "project_id": company_info.get("id", "") or "",
                "package_id": task_labels.get(task_id, f"第{task_id}包") if task_id else "",
                "response_table_title": f"{proposal['name']}技术一对一应答表",
            }
            try:
                generator.generate_response_docx(matched_reqs, output_path, meta)
                generated += 1
            except Exception as e:
                print(f"    [ERROR] 应答表生成失败: {e}")

        print(f"    共生成 {generated} 个应答表")
        return generated > 0

    @staticmethod
    def _convert_response_md_to_docx(
        md_path: Path,
        docx_path: Path,
        title: str = "技术一对一应答表",
    ) -> None:
        """将 AI 生成的 Markdown 应答表转换为 A4竖排 4列 DOCX（1:2:7:2 列宽比）。"""
        md_text = DocumentOutputGuard.clean_and_validate(
            md_path.read_text(encoding="utf-8"), "response_table"
        )

        from docx import Document
        from docx.shared import Cm, Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        import re

        doc = Document()

        # ── A4 竖排页面设置 ──
        section = doc.sections[0]
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

        lines = md_text.split("\n")
        table_started = False
        table_rows = []

        def is_markdown_separator_row(cells: List[str]) -> bool:
            if not cells:
                return False
            return all(re.fullmatch(r":?-{3,}:?", c.strip()) for c in cells if c.strip())

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                if is_markdown_separator_row(cells):
                    continue
                if not table_started:
                    table_started = True
                table_rows.append(cells)
            elif table_started and not stripped:
                break

        if not table_rows:
            raise ValueError("应答表 Markdown 中未找到有效表格")

        # ── 标题：技术一对一应答表（黑体 16pt 加粗居中）──
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_para.add_run(title)
        title_run.font.size = Pt(16)
        title_run.bold = True
        title_run.font.name = "Times New Roman"
        title_run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        doc.add_paragraph()

        # ── 4列表格：序号 | 模块 | 功能参数要求 | 应答章节 ──
        num_cols = 4
        # 只取前4列（忽略可能的额外列）
        num_rows = len(table_rows)
        table = doc.add_table(rows=num_rows, cols=num_cols)
        table.autofit = False
        table.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # ── 列宽按 1:2:7:2 比例分配 ──
        # 可用宽度 = 21.0 - 2.5*2 = 16.0cm, total_ratio = 12
        # 序号: 16.0 * 1/12 ≈ 1.33cm, 模块: ≈2.67cm, 功能参数要求: ≈9.33cm, 应答章节: ≈2.67cm
        usable_width_cm = 16.0
        total_ratio = 12
        col_widths = [
            Cm(usable_width_cm * r / total_ratio)
            for r in (1, 2, 7, 2)
        ]
        for j, width in enumerate(col_widths):
            for row in table.rows:
                try:
                    row.cells[j].width = width
                except Exception:
                    pass

        for i, row_data in enumerate(table_rows):
            row = table.rows[i]
            for j, cell_text in enumerate(row_data):
                if j >= num_cols:
                    break
                cell = row.cells[j]
                cell.text = ""
                para = cell.paragraphs[0]

                is_header = (i == 0)

                if is_header:
                    run = para.add_run(cell_text)
                    run.bold = True
                    run.font.size = Pt(10)
                    run.font.name = "Times New Roman"
                    run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    run = para.add_run(cell_text)
                    run.font.size = Pt(9)
                    run.font.name = "Times New Roman"
                    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

                    # 序号列居中，其余左对齐
                    if j == 0:
                        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    else:
                        para.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # ── 三线表边框 ──
        tbl = table._tbl
        tbl_pr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
        borders = OxmlElement('w:tblBorders')

        for border_name, sz in [('top', '12'), ('bottom', '12'), ('insideH', '4')]:
            el = OxmlElement(f'w:{border_name}')
            el.set(qn('w:val'), 'single')
            el.set(qn('w:sz'), sz)
            el.set(qn('w:space'), '0')
            el.set(qn('w:color'), '000000')
            borders.append(el)
        for border_name in ['insideV', 'left', 'right']:
            el = OxmlElement(f'w:{border_name}')
            el.set(qn('w:val'), 'none')
            el.set(qn('w:sz'), '0')
            el.set(qn('w:space'), '0')
            el.set(qn('w:color'), 'auto')
            borders.append(el)

        tbl_pr.append(borders)

        doc.save(str(docx_path))
        print(f"    [应答表 DOCX] {docx_path.name} ({docx_path.stat().st_size} 字节)")

    # ── Stage 10: 最终整合导出 ───────────────────────────────

    def _execute_stage_10_legacy(self) -> bool:
        """独立文档导出 → output/ 文件夹。

        无条件导出（不管有无模板）：
        - output/技术方案.docx （从中标方案 Markdown 生成）
        - output/技术一对一应答表.docx （从应答表 DOCX 复制）

        条件导出（模板存在时）：
        - output/标书文件_完整版.docx （拼接应答表到填充后的标书）
        """
        print("\n  [Stage 10] 独立文档导出（output/）...")

        import shutil

        output_dir = self.workspace / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        winning_bid_dir = self._cache(6) / "bid_00_winning"
        response_dir = self._cache(9)
        filled_dir = self._cache(7)

        exported_files = []

        # ══════════════════════════════════════════════════════
        # 1. 技术方案.docx（始终生成 — 从中标方案 Markdown）
        # ══════════════════════════════════════════════════════
        tech_solution_path = output_dir / "技术方案.docx"
        draft_md = winning_bid_dir / "bid_draft.md"
        if draft_md.exists():
            print("    导出技术方案.docx...")
            try:
                self.exporter.export_from_markdown(draft_md, tech_solution_path)
                size_kb = tech_solution_path.stat().st_size / 1024
                print(f"    [OK] 技术方案.docx ({size_kb:.1f} KB)")
                exported_files.append("技术方案.docx")
            except Exception as e:
                print(f"    [WARN] 技术方案导出失败: {e}")
        else:
            # Fallback: try existing bid_output.docx
            draft_docx = winning_bid_dir / "bid_output.docx"
            if draft_docx.exists():
                shutil.copy2(str(draft_docx), str(tech_solution_path))
                print(f"    [OK] 技术方案.docx (从 bid_output.docx 复制)")
                exported_files.append("技术方案.docx")
            else:
                print("    [WARN] 未找到中标方案内容，无法导出技术方案")

        # 全部参考方案与中标方案一同保存在会话 output/，便于直接核对输出。
        for proposal_dir in sorted(self._cache(6).glob("bid_[0-9][0-9]")):
            try:
                reference_index = int(proposal_dir.name.replace("bid_", ""))
            except ValueError:
                continue
            output_name = f"参考方案{reference_index}.docx"
            proposal_md = proposal_dir / "bid_draft.md"
            proposal_output = output_dir / output_name
            if proposal_md.exists():
                try:
                    self.exporter.export_from_markdown(proposal_md, proposal_output)
                    exported_files.append(output_name)
                    print(f"    [OK] {output_name}")
                except Exception as e:
                    print(f"    [WARN] {output_name} 导出失败: {e}")

        # ══════════════════════════════════════════════════════
        # 2. 技术一对一应答表.docx（始终生成）
        # ══════════════════════════════════════════════════════
        resp_output_path = output_dir / "技术一对一应答表.docx"
        # Try response table docx files
        resp_candidates = list(response_dir.glob("*winning*response*.docx")) if response_dir.exists() else []
        if not resp_candidates and response_dir.exists():
            resp_candidates = list(response_dir.glob("*.docx"))

        if resp_candidates:
            resp_file = resp_candidates[0]
            shutil.copy2(str(resp_file), str(resp_output_path))
            size_kb = resp_output_path.stat().st_size / 1024
            print(f"    [OK] 技术一对一应答表.docx ({size_kb:.1f} KB)")
            exported_files.append("技术一对一应答表.docx")
        else:
            # Generate from markdown if available
            resp_md = response_dir / "bid_00_winning_response_table.md" if response_dir.exists() else None
            if not resp_md or not resp_md.exists():
                # Try alternate location
                alt_md = self._cache(9) / "bid_00_winning_response_table.md"
                if alt_md.exists():
                    resp_md = alt_md
            if resp_md and resp_md.exists():
                print("    从 Markdown 生成应答表 DOCX...")
                try:
                    self.exporter.export_from_markdown(resp_md, resp_output_path)
                    print(f"    [OK] 技术一对一应答表.docx")
                    exported_files.append("技术一对一应答表.docx")
                except Exception as e:
                    print(f"    [WARN] 应答表 DOCX 生成失败: {e}")
            else:
                print("    [WARN] 未找到应答表内容，无法导出")

        # ══════════════════════════════════════════════════════
        # 3. 标书文件_完整版.docx（条件：需模板存在 + 填充完成）
        # ══════════════════════════════════════════════════════
        if self.has_template:
            bid_output_path = output_dir / "标书文件_完整版.docx"
            if filled_dir.exists():
                filled_files = list(filled_dir.glob("bid_*_filled.docx"))
                if filled_files:
                    filled_file = filled_files[0]
                    # Check for response table
                    resp_for_merge = resp_candidates[0] if resp_candidates else None

                    if resp_for_merge and resp_for_merge.exists():
                        try:
                            from lib.response_table_inserter import ResponseTableInserter
                            inserter = ResponseTableInserter()
                            inserter.insert(filled_file, resp_for_merge, bid_output_path)
                        except Exception as e:
                            print(f"    [WARN] 应答表插入失败: {e}，使用简单复制")
                            shutil.copy2(str(filled_file), str(bid_output_path))
                    else:
                        shutil.copy2(str(filled_file), str(bid_output_path))

                    size_kb = bid_output_path.stat().st_size / 1024
                    print(f"    [OK] 标书文件_完整版.docx ({size_kb:.1f} KB)")
                    exported_files.append("标书文件_完整版.docx")
                else:
                    print("    [WARN] 模板存在但未找到填充后的文件")
            else:
                print("    [WARN] 模板存在但填充目录不存在")
        else:
            print("    ⏭ 无模板 → 跳过标书文件_完整版.docx")

        # ── 汇总 ──
        print(f"\n    输出目录: {output_dir}")
        print(f"    已导出: {', '.join(exported_files) if exported_files else '(无)'}")
        return len(exported_files) > 0

    def _execute_stage_10(self) -> bool:
        """Export the configured proposal set and its paired response tables."""
        print("\n  [Stage 10] 导出全部技术方案和技术一对一应答表...")

        import shutil

        output_dir = self.workspace / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        bids_dir = self._cache(6)
        response_dir = self._cache(9)
        exported_files: List[str] = []

        for proposal in self._configured_proposals():
            label = proposal["name"]
            base_name = proposal["export_basename"]
            bid_dir = bids_dir / proposal["bid_dir"]
            technical_output = output_dir / f"{base_name}技术方案.docx"
            draft_md = bid_dir / "bid_draft.md"

            if draft_md.exists():
                try:
                    self.exporter.export_from_markdown(draft_md, technical_output)
                    exported_files.append(technical_output.name)
                    print(f"    [OK] {technical_output.name}")
                except Exception as exc:
                    print(f"    [WARN] {label}技术方案导出失败: {exc}")
            else:
                draft_docx = bid_dir / "bid_output.docx"
                if draft_docx.exists():
                    shutil.copy2(str(draft_docx), str(technical_output))
                    exported_files.append(technical_output.name)
                    print(f"    [OK] {technical_output.name} (从缓存复制)")
                else:
                    print(f"    [WARN] 未找到技术方案: {label}")

            response_output = output_dir / f"{base_name}技术一对一应答表.docx"
            cache_stem = f"{proposal['id']}_{base_name}_response_table"
            response_docx_candidates = [
                response_dir / f"{cache_stem}.docx",
                response_dir / f"{proposal['bid_dir']}_response_table.docx",
            ]
            response_md_candidates = [
                response_dir / f"{cache_stem}.md",
                response_dir / f"{proposal['bid_dir']}_response_table.md",
            ]
            response_docx = next((path for path in response_docx_candidates if path.exists()), None)
            response_md = next((path for path in response_md_candidates if path.exists()), None)

            if response_docx:
                shutil.copy2(str(response_docx), str(response_output))
                exported_files.append(response_output.name)
                print(f"    [OK] {response_output.name}")
            elif response_md:
                try:
                    self._convert_response_md_to_docx(
                        response_md, response_output, f"{label}技术一对一应答表"
                    )
                    exported_files.append(response_output.name)
                    print(f"    [OK] {response_output.name}")
                except Exception as exc:
                    print(f"    [WARN] {label}应答表导出失败: {exc}")
            else:
                print(f"    [WARN] 未找到应答表: {label}")

        print(f"\n    输出目录: {output_dir}")
        print(f"    已导出: {', '.join(exported_files) if exported_files else '(无)'}")
        return bool(exported_files)

    # ── 阶段调度（按逻辑顺序 0→10）─────────────────────────

    def _execute_stage(self, stage_id: int) -> bool:
        """执行指定阶段（v2: 保持原编号，新增条件分支和纯净导出）。"""
        # Pre-stage: reference file analysis (runs before stage 0)
        if stage_id == -1:
            return self._execute_prestage_profile()

        handlers = {
            0: self._execute_stage_0,   # 文档解析（从 uploads/）
            1: self._execute_stage_1,   # 标书总结
            2: self._execute_stage_2,   # 需求提取
            3: self._execute_stage_3,   # 模板搜索与结构分析
            4: self._execute_stage_4,   # 默认格式准备
            5: self._execute_stage_5,   # 投标策略生成
            6: self._execute_stage_6,   # 标书内容生成
            7: self._execute_stage_7,   # 模板内容填充【条件】
            8: self._execute_stage_8,   # DOCX 导出
            9: self._execute_stage_9,   # 应答表生成
            10: self._execute_stage_10, # 独立文档导出（output/）
        }
        handler = handlers.get(stage_id)
        if handler is None:
            print(f"    [ERROR] 未知阶段: {stage_id}")
            return False

        stage_info = next((s for s in self.config.get_stages() if s.get("id") == stage_id), {})
        stage_name = stage_info.get("name", f"Stage {stage_id}")

        # Notify: stage starting
        self._notify_progress(stage_id, "running", f"开始: {stage_name}")

        ok = handler()

        if ok:
            self._notify_progress(stage_id, "completed", f"完成: {stage_name}")
        else:
            self._notify_progress(stage_id, "failed", f"失败: {stage_name}")
        return ok

    # ── Pre-stage: 参考文件分析 ─────────────────────────────

    def _execute_prestage_profile(self) -> bool:
        """解析 profile/ 下所有参考文件 → .cache/00_profile/（无 AI，纯库解析）。

        在 Stage 0 之前执行，分析参考文档的内容/格式/风格信息，
        为后续核心标书解析提供参考。
        """
        print("\n  [Pre-Stage] 参考文件分析（profile/）...")
        self._notify_progress(-1, "running", "开始: 参考文件分析")

        output_dir = self.workspace / ".cache" / PROFILE_CACHE
        output_dir.mkdir(parents=True, exist_ok=True)

        profile_dir = self.workspace / "profile"
        if not profile_dir.exists() or not any(profile_dir.iterdir()):
            print("    [INFO] profile/ 目录为空，跳过参考文件分析")
            (output_dir / "_empty.txt").write_text("(无参考文件)", encoding="utf-8")
            self._notify_progress(-1, "completed", "完成: 参考文件分析（无文件）")
            return True

        parsed_count = 0
        all_texts = []

        for ref_file in sorted(profile_dir.iterdir()):
            if ref_file.is_file() and not ref_file.name.startswith("."):
                ext = ref_file.suffix.lower()
                try:
                    if ext in (".docx", ".doc"):
                        # Parse DOCX reference files
                        from docx import Document as DocxDoc
                        doc = DocxDoc(str(ref_file))
                        text_parts = []
                        for para in doc.paragraphs:
                            if para.text.strip():
                                text_parts.append(para.text)
                        content = "\n".join(text_parts)
                        if not content:
                            content = "(空文档或仅含图片/表格)"
                    elif ext == ".pdf":
                        content = f"[PDF 参考文件: {ref_file.name}] (需 PDF 解析器)"
                    elif ext in (".txt", ".md"):
                        content = ref_file.read_text(encoding="utf-8", errors="replace")
                    elif ext in (".pptx", ".ppt"):
                        content = f"[PPTX 参考文件: {ref_file.name}] (需 PPTX 解析器)"
                    elif ext in (".xlsx", ".xls"):
                        content = f"[XLSX 参考文件: {ref_file.name}] (需 Excel 解析器)"
                    else:
                        content = f"[参考文件: {ref_file.name}]"

                    # Save parsed content
                    out_name = ref_file.stem + ".txt"
                    out_path = output_dir / out_name
                    out_path.write_text(content, encoding="utf-8")
                    all_texts.append(f"=== {ref_file.name} ===\n{content}")
                    parsed_count += 1
                    print(f"    解析参考文件: {ref_file.name} ({len(content)} 字符)")

                except Exception as e:
                    print(f"    [WARN] 参考文件解析失败: {ref_file.name} — {e}")
                    out_path = output_dir / (ref_file.stem + "_error.txt")
                    out_path.write_text(f"解析失败: {e}", encoding="utf-8")

        # Write combined reference text
        if all_texts:
            combined_path = output_dir / "profile_combined.txt"
            combined_path.write_text("\n\n".join(all_texts), encoding="utf-8")
            print(f"    参考文件解析完成: {parsed_count} 个文件")

        self._notify_progress(-1, "completed", f"完成: 参考文件分析（{parsed_count} 个文件）")
        return True

    # ── 输出摘要 ────────────────────────────────────────────

    def _print_summary(self) -> None:
        """打印输出文件摘要。"""
        print()
        files = []
        for root, dirs, filenames in os.walk(str(self.cache_dir)):
            for fn in filenames:
                fp = Path(root) / fn
                size_kb = fp.stat().st_size / 1024
                rel = fp.relative_to(self.cache_dir)
                files.append((rel, size_kb))

        if files:
            print("  缓存文件:")
            for rel, size_kb in files:
                print(f"    .cache/{rel} ({size_kb:.1f} KB)")

        final_files = list(ROOT.glob("*_完整.docx"))
        if final_files:
            print("\n  最终导出文件:")
            for fp in sorted(final_files):
                size_kb = fp.stat().st_size / 1024
                print(f"    {fp.name} ({size_kb:.1f} KB)")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Claude AI 标书自动生成与参考文件制作 Pipeline（通用型 11 阶段）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python bid_pipeline.py                      # 完整运行（1中标+2参考文件）
  python bid_pipeline.py --task 3             # 指定第三包，生成三份方案
  python bid_pipeline.py --task 3 --mode winning_only    # 仅生成中标方案
  python bid_pipeline.py --task 3 --mode accompany_only  # 仅生成参考文件方案
  python bid_pipeline.py --count 3            # 生成3个参考文件
  python bid_pipeline.py --bid 2              # 仅处理第2个参考文件
  python bid_pipeline.py --docx ./xxx.docx    # 指定标书文件
  python bid_pipeline.py --resume             # 断点续跑
  python bid_pipeline.py --status             # 查看进度
  python bid_pipeline.py --from-stage 6       # 从Stage 6开始
  python bid_pipeline.py --only-stage 5       # 仅执行Stage 5（调试）
  python bid_pipeline.py --init               # 生成默认配置
        """,
    )

    parser.add_argument("--resume", action="store_true", help="断点续跑")
    parser.add_argument("--status", action="store_true", help="查看进度")
    parser.add_argument("--docx", type=str, help="标书 .docx 文件路径")
    parser.add_argument("--config", type=str, default="pipeline_config.yaml", help="配置文件路径")
    parser.add_argument("--from-stage", type=int, help="从指定Stage开始")
    parser.add_argument("--only-stage", type=int, help="仅执行单个Stage（调试）")
    parser.add_argument("--init", action="store_true", help="生成默认配置文件")
    parser.add_argument("--force", action="store_true", help="强制覆盖/重新生成")
    parser.add_argument("--count", type=int, help="参考文件数量（覆盖配置文件）")
    parser.add_argument("--bid", type=int, help="仅处理指定编号的参考文件（覆盖配置文件 target_bid）")
    parser.add_argument("--task", type=int, help="指定处理的标包编号（1-5），仅处理该标包的技术方案")
    parser.add_argument("--mode", type=str, default="mixed",
                        choices=["mixed", "winning_only", "accompany_only"],
                        help="生成模式：mixed=1中标+N参考文件, winning_only=仅中标, accompany_only=仅参考文件")

    return parser


def cmd_status(config_path: str) -> None:
    """显示 Pipeline 进度状态。"""
    cfg = BidPipelineConfig(Path(config_path))
    cache_dir = cfg.get_output_dir()
    state = PipelineState(cache_dir)
    state.load()

    print("Pipeline 状态")
    print("=" * 40)
    total_stages = len(cfg.get_stages())
    print(f"  已完成阶段: {state.get_completed_stages()}/{total_stages}")
    print(f"  开始时间: {state.state.get('started_at', '未开始')}")
    print(f"  最后更新: {state.state.get('last_updated', 'N/A')}")
    print()

    stages = cfg.get_stages()
    for s in stages:
        sid = s["id"]
        done = state.is_stage_complete(sid)
        mark = "[OK]" if done else "[  ]"
        enabled = "[ON]" if s.get("enabled", True) else "[OFF]"
        print(f"  {mark} Stage {sid}: {s['name']} {enabled}")

    print()
    bids = state.get_all_bid_statuses()
    if bids:
        print("方案进度:")
        for bid_idx, info in sorted(bids.items()):
            status = info.get("status", "unknown")
            path = info.get("output_path", "")
            label = "中标方案" if bid_idx == "0" else f"参考文件 #{bid_idx}"
            print(f"  {label}: {status}  {path}")
    else:
        print("方案: 未开始")

    target_bid = cfg.get_target_bid()
    target_info = f", 目标参考文件=#{target_bid}" if target_bid is not None else ""
    task_id = cfg.get_task_package_id()
    task_info = f", 目标标包=第{task_id}包" if task_id else ""
    tech_info = ", 仅技术章节" if cfg.is_technical_only() else ""
    print(f"\n配置: 输入={cfg.get_input_docx()}, 参考文件数={cfg.get_num_accompanying()}{target_info}{task_info}{tech_info}, 输出={cache_dir}")


def cmd_init(config_path: str, force: bool = False) -> None:
    """生成默认配置文件。"""
    path = Path(config_path)
    if path.exists() and not force:
        print(f"配置文件已存在: {path}")
        print("使用 --force 强制覆盖")
        return

    cfg = BidPipelineConfig(path)
    cfg.save()
    print(f"默认配置已生成: {path}")
    print()
    print("请编辑此文件后运行:")
    print(f"  python bid_pipeline.py")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.init:
        cmd_init(args.config, args.force)
        return 0

    if args.status:
        cmd_status(args.config)
        return 0

    if args.resume:
        cfg = BidPipelineConfig(Path(args.config))
        cache_dir = cfg.get_output_dir()
        state = PipelineState(cache_dir)
        state.load()
        args.from_stage = state.get_completed_stages()
        print(f"断点续跑：从 Stage {args.from_stage} 开始")

    pipeline = BidPipeline(args)
    return pipeline.run()


if __name__ == "__main__":
    sys.exit(main())
