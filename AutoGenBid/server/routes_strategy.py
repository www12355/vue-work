"""Pipeline configuration routes for the three-proposal bid workspace."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Dict

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from lib.document_output_guard import validate_export_name

router = APIRouter()

SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent
PIPELINE_CONFIG_FILE = PROJECT_ROOT / "pipeline_config.yaml"

WINNING_DEFAULT = ("bid_00_winning", "中标方案", "data_platform", "large_penetration", 180)
REFERENCE_DEFAULTS = (
    ("java_enterprise", "medium_research_dev", 210),
    ("modern_ai", "small_ai", 240),
    ("data_platform", "medium_database", 225),
)


class PipelineConfigPayload(BaseModel):
    content: str = ""


def _read_pipeline_config() -> str:
    return PIPELINE_CONFIG_FILE.read_text(encoding="utf-8") if PIPELINE_CONFIG_FILE.exists() else ""


def _parse_pipeline_config(content: str) -> Dict[str, Any]:
    try:
        parsed = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"pipeline_config.yaml 解析失败: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="pipeline_config.yaml 顶层必须是对象")
    return parsed


def _normalise_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate the former single-solution shape in memory before validation."""
    config = copy.deepcopy(config)
    proposal_set = config.get("proposal_set")
    if not isinstance(proposal_set, dict):
        legacy = config.get("solution") if isinstance(config.get("solution"), dict) else {}
        winning_id, winning_name, stack_id, team_id, days = WINNING_DEFAULT
        proposal_set = {
            "winning": {
                "id": winning_id,
                "name": legacy.get("strategy_name") or winning_name,
                "tech_stack_id": legacy.get("tech_stack_id") or stack_id,
                "team_profile_id": legacy.get("team_profile_id") or team_id,
                "delivery_days": legacy.get("delivery_days") or days,
                "writing_rules": legacy.get("writing_rules") or [],
            }
        }
        for index, (reference_stack, reference_team, reference_days) in enumerate(REFERENCE_DEFAULTS[:2], start=1):
            proposal_set[f"reference_{index}"] = _reference_default(index, reference_stack, reference_team, reference_days)
        config["proposal_set"] = proposal_set

    winning_id, winning_name, stack_id, team_id, days = WINNING_DEFAULT
    winning = proposal_set.get("winning")
    if not isinstance(winning, dict):
        winning = {}
        proposal_set["winning"] = winning
    winning.setdefault("id", winning_id)
    winning.setdefault("name", winning_name)
    winning.setdefault("tech_stack_id", stack_id)
    winning.setdefault("team_profile_id", team_id)
    winning.setdefault("delivery_days", days)
    winning.setdefault("writing_rules", [])

    config.pop("solution", None)
    config.pop("accompany", None)
    return config


def _reference_default(index: int, stack_id: str, team_id: str, days: int) -> Dict[str, Any]:
    return {
        "id": f"bid_{index:02d}", "name": f"参考方案 {index}", "tech_stack_id": stack_id,
        "team_profile_id": team_id, "delivery_days": days, "writing_rules": [],
    }


def _validate_team_profiles(config: Dict[str, Any]) -> None:
    profiles = config.get("team_profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        raise HTTPException(status_code=400, detail="team_profiles 不能为空")
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict) or not isinstance(profile.get("roles"), list):
            raise HTTPException(status_code=400, detail=f"团队配置格式错误: {profile_id}")
        if not profile["roles"]:
            raise HTTPException(status_code=400, detail=f"团队至少需要一个角色: {profile_id}")
        total = 0
        for role in profile["roles"]:
            if not isinstance(role, dict) or not str(role.get("role", "")).strip():
                raise HTTPException(status_code=400, detail=f"团队角色名称不能为空: {profile_id}")
            try:
                count = int(role.get("count", 0))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"团队角色人数必须为整数: {profile_id}") from exc
            if count < 0:
                raise HTTPException(status_code=400, detail=f"团队角色人数不能为负数: {profile_id}")
            role["count"] = count
            total += count
        if total < 1 or total > 20:
            raise HTTPException(status_code=400, detail=f"团队人数必须在 1 到 20 人之间: {profile_id}")
        profile["id"] = profile_id
        profile["total"] = total


def _validate_tech_stacks(config: Dict[str, Any]) -> None:
    stacks = config.get("tech_stacks", {})
    if not isinstance(stacks, dict) or not stacks:
        raise HTTPException(status_code=400, detail="tech_stacks 不能为空")
    for stack_id, stack in stacks.items():
        if not isinstance(stack, dict) or not str(stack.get("name", "")).strip():
            raise HTTPException(status_code=400, detail=f"技术栈名称不能为空: {stack_id}")
        rows = stack.get("rows", [])
        if not isinstance(rows, list) or not rows:
            raise HTTPException(status_code=400, detail=f"技术栈 rows 不能为空: {stack_id}")
        keys = set()
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("key", "")).strip() or not str(row.get("label", "")).strip():
                raise HTTPException(status_code=400, detail=f"技术栈行必须包含 key 和 label: {stack_id}")
            if row["key"] in keys:
                raise HTTPException(status_code=400, detail=f"技术栈行 key 重复: {stack_id}.{row['key']}")
            keys.add(row["key"])
        stack["id"] = stack_id
        tier = str(stack.get("tier") or "winning")
        if tier not in {"winning", "reference"}:
            raise HTTPException(status_code=400, detail=f"技术栈 tier 必须为 winning 或 reference: {stack_id}")
        stack["tier"] = tier


def _validate_proposal_set(config: Dict[str, Any]) -> None:
    proposals = config.get("proposal_set", {})
    if not isinstance(proposals, dict):
        raise HTTPException(status_code=400, detail="proposal_set 必须是对象")
    stacks = config["tech_stacks"]
    profiles = config["team_profiles"]
    seen_ids = set()
    seen_names = set()
    proposal_items = [("winning", proposals.get("winning"))]
    reference_slots = sorted(
        (slot for slot in proposals if re.fullmatch(r"reference_[1-9]\d*", slot)),
        key=lambda slot: int(slot.split("_")[1]),
    )
    if len(reference_slots) > 20:
        raise HTTPException(status_code=400, detail="参考方案数量不能超过 20 份")
    proposal_items.extend((slot, proposals[slot]) for slot in reference_slots)
    for slot, proposal in proposal_items:
        if not isinstance(proposal, dict):
            raise HTTPException(status_code=400, detail=f"缺少方案配置: {slot}")
        expected_id = "bid_00_winning" if slot == "winning" else f"bid_{int(slot.split('_')[1]):02d}"
        if proposal.get("id") != expected_id:
            raise HTTPException(status_code=400, detail=f"{slot}.id 必须为 {expected_id}")
        if not str(proposal.get("name", "")).strip():
            raise HTTPException(status_code=400, detail=f"{slot}.name 不能为空")
        if proposal["id"] in seen_ids:
            raise HTTPException(status_code=400, detail="方案 id 不能重复")
        seen_ids.add(proposal["id"])
        try:
            proposal["name"] = validate_export_name(proposal.get("name"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{slot}.name {exc}") from exc
        if proposal["name"] in seen_names:
            raise HTTPException(status_code=400, detail="方案名称不能重复")
        seen_names.add(proposal["name"])
        if proposal.get("tech_stack_id") not in stacks:
            raise HTTPException(status_code=400, detail=f"{slot}.tech_stack_id 不存在")
        if proposal.get("team_profile_id") not in profiles:
            raise HTTPException(status_code=400, detail=f"{slot}.team_profile_id 不存在")
        try:
            proposal["delivery_days"] = int(proposal.get("delivery_days", 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{slot}.delivery_days 必须是整数") from exc
        if proposal["delivery_days"] < 1:
            raise HTTPException(status_code=400, detail=f"{slot}.delivery_days 必须大于 0")
        rules = proposal.get("writing_rules", [])
        proposal["writing_rules"] = [str(rule).strip() for rule in (rules if isinstance(rules, list) else [rules]) if str(rule).strip()]


def _validated_config(content: str) -> Dict[str, Any]:
    config = _normalise_config(_parse_pipeline_config(content))
    _validate_tech_stacks(config)
    _validate_team_profiles(config)
    _validate_proposal_set(config)
    return config


@router.get("/api/pipeline-config")
async def get_pipeline_config():
    config = _validated_config(_read_pipeline_config())
    content = yaml.safe_dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return {"pipeline_config_yaml": content, "config": config, "proposal_set": config["proposal_set"], "tech_stacks": config["tech_stacks"], "team_profiles": config["team_profiles"]}


@router.post("/api/pipeline-config")
async def save_pipeline_config(payload: PipelineConfigPayload):
    config = _validated_config(payload.content)
    PIPELINE_CONFIG_FILE.write_text(yaml.safe_dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")
    return {"message": "pipeline_config.yaml 已保存", "path": str(PIPELINE_CONFIG_FILE)}
