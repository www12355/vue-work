"""
配置加载器 — 加载 YAML 配置，深度合并默认值。

用法:
    from lib.config_loader import BidPipelineConfig
    cfg = BidPipelineConfig("pipeline_config.yaml")
    print(cfg.get_num_accompanying())
"""

from __future__ import annotations

import sys
import os
import copy
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# 注册项目根目录
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml


class BidPipelineConfig:
    """标书 Pipeline 配置管理器。"""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = Path(config_path) if config_path else Path("pipeline_config.yaml")
        self._data: Dict[str, Any] = {}
        self.load()

    # ── 加载 ──────────────────────────────────────────────

    def load(self) -> Dict[str, Any]:
        """加载 YAML 配置文件，深度合并默认值。"""
        base = self._default_config()

        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            self._data = self._deep_merge(base, user)
            if "proposal_set" not in user and isinstance(user.get("solution"), dict):
                legacy = user["solution"]
                winning = self._data["proposal_set"]["winning"]
                winning.update({
                    "name": legacy.get("strategy_name") or winning["name"],
                    "tech_stack_id": legacy.get("tech_stack_id") or winning["tech_stack_id"],
                    "team_profile_id": legacy.get("team_profile_id") or winning["team_profile_id"],
                    "delivery_days": legacy.get("delivery_days") or winning["delivery_days"],
                    "writing_rules": legacy.get("writing_rules") or winning["writing_rules"],
                })
        else:
            self._data = base

        return self._data

    def save(self, path: Optional[Path] = None) -> None:
        """保存当前配置到 YAML 文件。"""
        target = Path(path) if path else self._config_path
        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # ── 默认配置 ──────────────────────────────────────────

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        return {
            "input": {
                "bid_docx": "标书文件.docx",
            },
            "output": {
                "dir": "./.cache",
            },
            "task": {
                "package_id": None,   # None=全部标包, 整数=指定标包编号
                "technical_only": True,  # 仅生成技术章节
            },
            "proposal_set": {
                "winning": {
                    "id": "bid_00_winning", "name": "中标方案", "tech_stack_id": "modern_ai",
                    "team_profile_id": "medium_ai", "delivery_days": 180, "writing_rules": [],
                },
                "reference_1": {
                    "id": "bid_01", "name": "参考方案 1", "tech_stack_id": "java_enterprise",
                    "team_profile_id": "medium_research_dev", "delivery_days": 210, "writing_rules": [],
                },
                "reference_2": {
                    "id": "bid_02", "name": "参考方案 2", "tech_stack_id": "modern_ai",
                    "team_profile_id": "small_ai", "delivery_days": 240, "writing_rules": [],
                },
            },
            "claude": {
                "timeout": 600,
                "max_retries": 3,
                "min_output_size": 200,
                "allowed_tools": ["Read", "Write", "Bash", "Glob", "Grep"],
            },
            "stages": [
                {"id": 0, "name": "文档解析", "description": "解析标书 .docx 文件", "cache_dir": "01_parsed", "enabled": True},
                {"id": 1, "name": "标书总结", "description": "生成标书总结", "cache_dir": "02_summary", "enabled": True},
                {"id": 2, "name": "需求提取", "description": "提取结构化需求清单", "cache_dir": "03_requirements", "enabled": True},
                {"id": 3, "name": "技术章节定位", "description": "用 regex 定位技术方案标号并生成章节编号映射", "cache_dir": "04_template", "enabled": True},
                {"id": 4, "name": "默认格式准备", "description": "直接使用默认 DOCX 格式，不解析标书格式", "cache_dir": "05_format", "enabled": True},
                {"id": 5, "name": "投标策略生成", "description": "生成中标+参考文件策略", "cache_dir": "06_strategies", "enabled": True},
                {"id": 6, "name": "标书内容生成", "description": "AI生成技术方案内容", "cache_dir": "07_bids", "enabled": True},
                {"id": 7, "name": "模板拼接跳过", "description": "已禁用格式模板拼接，仅保留独立文档导出", "cache_dir": "08_filled", "enabled": True},
                {"id": 8, "name": "DOCX导出", "description": "使用默认格式导出Word文档", "cache_dir": "09_exported", "enabled": True},
                {"id": 9, "name": "应答表生成", "description": "生成技术一对一应答表", "cache_dir": "10_response_tables", "enabled": True},
                {"id": 10, "name": "最终整合导出", "description": "合并应答表并最终检查", "cache_dir": "11_final", "enabled": True},
            ],
            "format": {
                "image_placeholders": True,
                "reference_docx": "标书/系统性能设计方案评价.docx",
                "reference_txt": "标书/项目服务方案_01.txt",
                "default_format_template": None,
                "generate_toc": True,
                "generate_response_table": True,
                "company_info": {
                    "name": "",
                    "address": "",
                    "contact_name": "",
                    "contact_phone": "",
                    "contact_email": "",
                },
            },
            "team_profiles": {},
            "tech_stacks": {},
        }

    # ── 深度合并 ──────────────────────────────────────────

    @staticmethod
    def _deep_merge(base: Dict, override: Dict) -> Dict:
        """递归合并两个字典，override 的值覆盖 base。"""
        result = copy.deepcopy(base)
        for key, val in override.items():
            # 方案集合是可变长度列表式映射，不能由默认值补回用户删除的参考方案。
            if key == "proposal_set":
                result[key] = copy.deepcopy(val)
                continue
            if key in result and isinstance(result[key], dict) and isinstance(val, dict):
                result[key] = BidPipelineConfig._deep_merge(result[key], val)
            else:
                result[key] = copy.deepcopy(val)
        return result

    # ── 便捷访问 ──────────────────────────────────────────

    def get_input_docx(self) -> Path:
        """返回主标书 .docx 的绝对路径。"""
        p = Path(self._data["input"]["bid_docx"])
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()

    def get_output_dir(self) -> Path:
        """返回 .cache 输出目录的绝对路径。"""
        p = Path(self._data["output"]["dir"])
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()

    def get_num_accompanying(self) -> int:
        """返回当前配置中可变数量的参考方案。"""
        return sum(1 for slot in self.get_proposal_set() if re.fullmatch(r"reference_[1-9]\d*", slot))

    def get_main_team_size(self) -> int:
        return self.get_selected_team_total()

    def get_main_timeline_months(self) -> int:
        return max(1, round(self.get_solution_delivery_days() / 30))

    def get_strategy_templates(self) -> List[Dict]:
        return list(self._data.get("accompany", {}).get("strategy_templates", []))

    def get_tech_stack(self, stack_id: str) -> Dict[str, Any]:
        """根据 ID 获取完整技术栈定义。"""
        stacks = self._data.get("tech_stacks", {})
        stack = dict(stacks.get(stack_id, {}))
        rows = stack.get("rows", [])
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("key"):
                    stack.setdefault(str(row["key"]), row.get("value", ""))
        stack.setdefault("id", stack_id)
        return stack

    def get_tech_stacks(self) -> Dict[str, Any]:
        """返回全部技术栈配置。"""
        return dict(self._data.get("tech_stacks", {}))

    def get_team_profiles(self) -> Dict[str, Any]:
        """返回全部团队配置。"""
        return dict(self._data.get("team_profiles", {}))

    def get_proposal_set(self) -> Dict[str, Dict[str, Any]]:
        """返回固定的中标、参考一、参考二三份方案配置。"""
        proposal_set = self._data.get("proposal_set", {})
        return {slot: dict(value) for slot, value in proposal_set.items() if isinstance(value, dict)}

    def get_proposal_config(self, slot: str) -> Dict[str, Any]:
        proposal = self.get_proposal_set().get(slot, {})
        if not proposal:
            raise ValueError(f"缺少方案配置: {slot}")
        return proposal

    def get_solution_config(self) -> Dict[str, Any]:
        """兼容旧调用方：返回中标方案配置。"""
        return self.get_proposal_config("winning")

    def get_solution_tech_stack_id(self) -> str:
        return str(self.get_solution_config().get("tech_stack_id") or "modern_ai")

    def get_solution_team_profile_id(self) -> str:
        return str(self.get_solution_config().get("team_profile_id") or "medium_ai")

    def get_solution_delivery_days(self) -> int:
        try:
            days = int(self.get_solution_config().get("delivery_days", 180))
        except (TypeError, ValueError):
            days = 180
        return max(1, days)

    def get_proposal_team_profile(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = str(proposal.get("team_profile_id") or "")
        profiles = self.get_team_profiles()
        profile = dict(profiles.get(profile_id, {}))
        if profile:
            return profile
        # Last-resort fallback keeps generation usable if the YAML was edited badly.
        return {
            "id": profile_id,
            "name": "默认研发团队",
            "summary": "默认 6 人研发团队。",
            "total": 6,
            "roles": [
                {"role": "项目经理", "count": 1, "focus": "统筹交付"},
                {"role": "后端开发工程师", "count": 2, "focus": "服务开发"},
                {"role": "前端开发工程师", "count": 1, "focus": "页面开发"},
                {"role": "测试工程师", "count": 1, "focus": "质量验证"},
                {"role": "运维工程师", "count": 1, "focus": "部署运维"},
            ],
        }

    def get_selected_team_profile(self) -> Dict[str, Any]:
        return self.get_proposal_team_profile(self.get_solution_config())

    def get_selected_team_total(self) -> int:
        profile = self.get_selected_team_profile()
        roles = profile.get("roles", [])
        if isinstance(roles, list):
            total = sum(int(r.get("count", 0) or 0) for r in roles if isinstance(r, dict))
        else:
            total = int(profile.get("total", 0) or 0)
        return min(max(total, 1), 20)

    def get_claude_config(self) -> Dict[str, Any]:
        return dict(self._data["claude"])

    def get_stages(self) -> List[Dict]:
        return list(self._data["stages"])

    def is_stage_enabled(self, stage_id: int) -> bool:
        for s in self._data["stages"]:
            if s["id"] == stage_id:
                return bool(s.get("enabled", True))
        return True

    def get_target_bid(self) -> Optional[int]:
        """固定三方案生成不再支持单独筛选参考方案。"""
        return None

    def set_target_bid(self, bid: Optional[int]) -> None:
        """设置目标参考文件编号，None 表示所有参考文件。"""
        del bid

    def set_num_accompanying(self, count: int) -> None:
        del count

    def set_input_docx(self, path: str) -> None:
        self._data["input"]["bid_docx"] = path

    # ── 任务配置 ──────────────────────────────────────────

    def get_task_package_id(self) -> Optional[int]:
        """返回要处理的目标标包编号，None=全部。"""
        val = self._data.get("task", {}).get("package_id")
        if val is None:
            return None
        return int(val)

    def set_task_package_id(self, package_id: Optional[int]) -> None:
        """设置目标标包编号。"""
        if "task" not in self._data:
            self._data["task"] = {}
        self._data["task"]["package_id"] = package_id

    def is_technical_only(self) -> bool:
        """是否仅生成技术章节。"""
        return bool(self._data.get("task", {}).get("technical_only", True))

    # ── 中标方案配置 ──────────────────────────────────────

    def is_winning_enabled(self) -> bool:
        """是否生成中标方案。"""
        return bool(self.get_solution_config().get("enabled", True))

    def get_winning_config(self) -> Dict[str, Any]:
        """返回中标方案完整配置。"""
        return self.get_solution_config()

    def get_winning_tech_stack(self) -> Dict[str, Any]:
        """返回中标方案技术栈定义。"""
        stack_id = self.get_solution_tech_stack_id()
        return self.get_tech_stack(stack_id)

    def get_winning_team_size(self) -> int:
        """返回中标方案团队人数。"""
        return self.get_selected_team_total()

    def get_winning_timeline_months(self) -> int:
        """返回中标方案项目周期（月）。"""
        return max(1, round(self.get_solution_delivery_days() / 30))

    # ── 格式配置（Stage 6-10） ────────────────────────────

    def get_format_config(self) -> Dict[str, Any]:
        """返回完整的 format 配置节。"""
        return dict(self._data.get("format", {}))

    def get_reference_docx_path(self) -> Optional[Path]:
        """返回参考 DOCX 的绝对路径（用于样式捕获）。"""
        p = self._data.get("format", {}).get("reference_docx")
        if p:
            path = Path(p)
            return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
        return None

    def get_reference_txt_path(self) -> Optional[Path]:
        """返回参考 TXT 的绝对路径（用于叙述模式提取）。"""
        p = self._data.get("format", {}).get("reference_txt")
        if p:
            path = Path(p)
            return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
        return None

    def get_default_format_template(self) -> Optional[Path]:
        """返回默认格式模板路径（当招标文件中无格式章节时使用的后备）。"""
        p = self._data.get("format", {}).get("default_format_template")
        if p:
            path = Path(p)
            return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
        return None

    def is_image_placeholders_enabled(self) -> bool:
        """是否在技术方案中保留图片占位符和题注。"""
        return bool(self._data.get("format", {}).get("image_placeholders", True))

    def is_toc_enabled(self) -> bool:
        """是否生成目录。"""
        return bool(self._data.get("format", {}).get("generate_toc", True))

    def is_response_table_enabled(self) -> bool:
        """是否生成一对一应答表。"""
        return bool(self._data.get("format", {}).get("generate_response_table", True))

    def get_company_info(self) -> Dict[str, str]:
        """返回公司信息配置。"""
        return dict(self._data.get("format", {}).get("company_info", {}))

    # ── 原始数据 ──────────────────────────────────────────

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def __repr__(self) -> str:
        return f"BidPipelineConfig({self._config_path})"
