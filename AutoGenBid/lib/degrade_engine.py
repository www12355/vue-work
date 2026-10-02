"""
主方案策略生成引擎。

标书生成链路现在以 pipeline_config.yaml 为唯一可变配置来源：
技术栈、团队配置、交付天数和写作规则都由 YAML 中的 solution 配置决定。
旧的参考/陪标降级策略入口保留空实现，便于老调用方平滑过渡。
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from lib.document_output_guard import export_basename

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class TechStackConfig:
    """技术栈配置。"""

    stack_id: str = ""
    id: str = ""
    name: str = ""
    summary: str = ""
    rows: List[Dict[str, Any]] = field(default_factory=list)
    backend_lang: str = ""
    backend_framework: str = ""
    web_server: str = ""
    orm: str = ""
    database: str = ""
    build_tool: str = ""
    data_processing: str = ""
    ai_ml: str = ""
    frontend: str = ""
    deployment: str = ""
    containerization: str = "无"
    mood_adjectives: List[str] = field(default_factory=list)


@dataclass
class RequirementDegradation:
    """单条需求的满足方案。"""

    req_id: str = ""
    original_text: str = ""
    degradation_type: str = "full_satisfy"
    partial_description: str = ""
    degraded_response_hint: str = ""


@dataclass
class TeamPlan:
    """团队配置方案。"""

    total: int = 0
    roles: List[Dict[str, Any]] = field(default_factory=list)
    missing_roles: List[str] = field(default_factory=list)


@dataclass
class Timeline:
    """项目时间线。"""

    total_months: int = 0
    total_days: int = 0
    phases: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""


@dataclass
class DegradeStrategy:
    """完整的方案策略。

    类名保留为 DegradeStrategy 是为了兼容已有缓存和调用方；运行链路只生成主方案。
    """

    strategy_id: str = ""
    bid_index: int = 0
    strategy_name: str = ""
    satisfaction_rate: float = 1.0
    tech_stack: TechStackConfig = field(default_factory=TechStackConfig)
    team_plan: TeamPlan = field(default_factory=TeamPlan)
    timeline: Timeline = field(default_factory=Timeline)
    is_winning: bool = False
    proposal_slot: str = "winning"
    task_package_id: int = 0
    strategy_prompt: str = ""
    requirement_degradations: List[RequirementDegradation] = field(default_factory=list)
    content_deletion_sections: List[str] = field(default_factory=list)
    writing_rules: List[str] = field(default_factory=list)
    export_basename: str = ""
    proposal_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return asdict(self)


class SolutionStrategyEngine:
    """基于 pipeline_config.yaml 生成中标方案和可变数量参考方案策略。"""

    def __init__(
        self,
        requirements: List[Dict[str, Any]],
        config: Any,
        main_team_size: int = 16,
        main_timeline_months: int = 8,
    ):
        self.requirements = requirements
        self.config = config
        self.main_team_size = main_team_size
        self.main_timeline_months = main_timeline_months

    def generate_strategies(self, num_bids: int = 2, task_package_id: int = 0) -> List[DegradeStrategy]:
        """生成中标方案和配置中所有独立参考方案，num_bids 仅为旧调用方兼容参数。"""
        del num_bids
        proposal_set = self.config.get_proposal_set()
        slots = ["winning"] + sorted(
            (slot for slot in proposal_set if re.fullmatch(r"reference_[1-9]\d*", slot)),
            key=lambda slot: int(slot.split("_")[1]),
        )
        return [self.generate_proposal_strategy(slot, task_package_id) for slot in slots]

    def generate_winning_strategy(self, task_package_id: int = 0) -> DegradeStrategy:
        """兼容旧调用方：生成中标方案策略。"""
        return self.generate_proposal_strategy("winning", task_package_id)

    def generate_proposal_strategy(self, slot: str, task_package_id: int = 0) -> DegradeStrategy:
        """生成单个方案的展开策略，配置只来自 proposal_set。"""
        proposal = self.config.get_proposal_config(slot)
        stack_id = str(proposal.get("tech_stack_id") or "")
        delivery_days = int(proposal.get("delivery_days") or 180)

        tech_stack = self._build_tech_stack(stack_id)
        team_plan = self._build_team_plan(proposal)
        timeline = self._build_timeline(delivery_days)
        req_degradations = self._build_full_requirements()

        configured_rules = proposal.get("writing_rules", [])
        if isinstance(configured_rules, str):
            configured_rules = [configured_rules]
        configured_rules = [str(rule).strip() for rule in configured_rules if str(rule).strip()]

        writing_rules = self._build_writing_rules(tech_stack)
        writing_rules.extend(configured_rules)

        return DegradeStrategy(
            strategy_id=str(proposal.get("id") or "bid_00_winning"),
            bid_index=0 if slot == "winning" else int(slot.split("_")[1]),
            strategy_name=str(proposal.get("name") or tech_stack.name),
            satisfaction_rate=1.0,
            tech_stack=tech_stack,
            team_plan=team_plan,
            timeline=timeline,
            is_winning=slot == "winning",
            proposal_slot=slot,
            task_package_id=task_package_id,
            strategy_prompt="\n".join(configured_rules),
            requirement_degradations=req_degradations,
            content_deletion_sections=[],
            writing_rules=writing_rules,
            export_basename=export_basename(proposal.get("name") or tech_stack.name),
            proposal_metadata={
                "slot": slot,
                "id": str(proposal.get("id") or "bid_00_winning"),
                "name": str(proposal.get("name") or tech_stack.name),
                "tech_stack_id": stack_id,
                "team_profile_id": str(proposal.get("team_profile_id") or ""),
                "delivery_days": delivery_days,
                "writing_rules": list(configured_rules),
                "tech_stack": asdict(tech_stack),
                "team_plan": asdict(team_plan),
            },
        )

    def _build_tech_stack(self, stack_id: str) -> TechStackConfig:
        """从 pipeline_config.yaml 加载技术栈定义。"""
        stack_data = self.config.get_tech_stack(stack_id)
        if not stack_data:
            stacks = self.config.get_tech_stacks()
            stack_data = stacks[0] if stacks else {}
            stack_id = stack_data.get("id", stack_id)

        rows = stack_data.get("rows", [])
        if not isinstance(rows, list):
            rows = []

        return TechStackConfig(
            stack_id=stack_id,
            id=stack_data.get("id", stack_id),
            name=stack_data.get("name", ""),
            summary=stack_data.get("summary", ""),
            rows=[dict(row) for row in rows if isinstance(row, dict)],
            backend_lang=stack_data.get("backend_lang", ""),
            backend_framework=stack_data.get("backend_framework", ""),
            web_server=stack_data.get("web_server", ""),
            orm=stack_data.get("orm", ""),
            database=stack_data.get("database", ""),
            build_tool=stack_data.get("build_tool", ""),
            data_processing=stack_data.get("data_processing", ""),
            ai_ml=stack_data.get("ai_ml", ""),
            frontend=stack_data.get("frontend", ""),
            deployment=stack_data.get("deployment", ""),
            containerization=stack_data.get("containerization", "无"),
            mood_adjectives=stack_data.get("mood_adjectives", []),
        )

    def _build_team_plan(self, proposal: Dict[str, Any]) -> TeamPlan:
        """构建 pipeline_config.yaml 中选定的团队。"""
        profile = self.config.get_proposal_team_profile(proposal)
        roles = [dict(r) for r in profile.get("roles", []) if isinstance(r, dict)]
        total = sum(int(r.get("count", 0) or 0) for r in roles)
        if total > 20:
            raise ValueError(f"团队人数不能超过20人，当前配置为 {total} 人: {profile.get('id', '')}")
        return TeamPlan(total=total, roles=roles, missing_roles=[])

    def _build_timeline(self, total_days: int) -> Timeline:
        """构建按天数表达的阶段计划。"""
        total = max(30, int(total_days or 180))
        if total <= 120:
            phases = [
                {"phase": "需求调研与系统设计", "days": [1, math.ceil(total * 0.20)]},
                {"phase": "核心功能开发与联调", "days": [math.ceil(total * 0.15) + 1, math.ceil(total * 0.55)]},
                {"phase": "集成测试与专项优化", "days": [math.ceil(total * 0.50) + 1, math.ceil(total * 0.75)]},
                {"phase": "部署上线与培训", "days": [math.ceil(total * 0.70) + 1, math.ceil(total * 0.90)]},
                {"phase": "试运行与验收", "days": [math.ceil(total * 0.85) + 1, total]},
            ]
        else:
            phases = [
                {"phase": "需求调研与分析", "days": [1, math.ceil(total * 0.12)]},
                {"phase": "系统架构设计", "days": [math.ceil(total * 0.10) + 1, math.ceil(total * 0.22)]},
                {"phase": "核心功能开发", "days": [math.ceil(total * 0.18) + 1, math.ceil(total * 0.48)]},
                {"phase": "专项能力建设", "days": [math.ceil(total * 0.22) + 1, math.ceil(total * 0.55)]},
                {"phase": "集成测试与联调", "days": [math.ceil(total * 0.48) + 1, math.ceil(total * 0.70)]},
                {"phase": "部署上线与培训", "days": [math.ceil(total * 0.65) + 1, math.ceil(total * 0.88)]},
                {"phase": "试运行与验收", "days": [math.ceil(total * 0.85) + 1, total]},
            ]

        return Timeline(
            total_months=max(1, round(total / 30)),
            total_days=total,
            phases=phases,
            notes="关键阶段可并行执行，所有时间安排以 pipeline_config.yaml 的 delivery_days 为准",
        )

    def _build_full_requirements(self) -> List[RequirementDegradation]:
        """所有需求完全满足。"""
        degradations = []
        for i, req in enumerate(self.requirements or []):
            degradations.append(
                RequirementDegradation(
                    req_id=req.get("req_id", f"REQ-{i + 1:04d}"),
                    original_text=req.get("text", "")[:300],
                    degradation_type="full_satisfy",
                    partial_description="",
                    degraded_response_hint="正常回应，写'完全满足'，并扩展描述技术优势",
                )
            )
        return degradations

    def _build_writing_rules(self, tech_stack: TechStackConfig) -> List[str]:
        """构建主方案写作规则。"""
        rules = [
            "所有技术描述严格围绕 pipeline_config.yaml 中选定的技术栈展开",
            "技术要求详细具体，包含量化指标（响应时间、准确率、吞吐量等）",
            "技术参数精确，不使用模糊范围值",
            "主动展示技术亮点和创新点，体现竞争优势",
            "所有需求均详细回应，不遗漏任何技术要点",
            "方案结构完整、逻辑严密，体现专业水准",
        ]
        if tech_stack.summary:
            rules.append(f"技术栈总体定位：{tech_stack.summary}")
        if tech_stack.mood_adjectives:
            rules.append(f"全文基调形容词：{', '.join(tech_stack.mood_adjectives)}")
        return rules


# 兼容旧导入名。
DegradeEngine = SolutionStrategyEngine


def generate_strategies(
    requirements: List[Dict[str, Any]],
    config: Any,
    num_bids: int,
    main_team_size: int = 16,
    main_timeline_months: int = 8,
) -> List[DegradeStrategy]:
    """兼容函数：返回固定的三份方案策略。"""
    engine = SolutionStrategyEngine(requirements, config, main_team_size, main_timeline_months)
    return engine.generate_strategies(num_bids)


def save_strategies(
    strategies: List[DegradeStrategy],
    output_dir: Path,
) -> List[Path]:
    """将策略列表保存为 JSON 文件。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    for s in strategies:
        path = output_dir / f"{s.strategy_id}_strategy.json"
        path.write_text(
            json.dumps(s.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(path)

    return paths
