"""
Session Routes — Session lifecycle management API.

Three-step workflow (fine-grained):
  1. POST /api/session                   Create empty session → session_id
  2. POST /api/session/{id}/upload       Upload files (type=uploads|profile)
  3. POST /api/session/{id}/start        Launch pipeline

Also supports:
  GET  /api/sessions                     List all sessions (history)
  DELETE /api/session/{id}               Delete session
  GET  /api/session/{id}                 Get session status
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from .session_manager import session_manager
from .models import (
    SessionStatus,
    SessionListItem,
    SessionListResponse,
    STAGE_DEFINITIONS,
)
from .pipeline_adapter import PipelineAdapter

router = APIRouter()


# ── Models ────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """Optional data for session creation."""
    company: str = ""
    project_name: str = ""
    session_id: Optional[str] = None  # preferred session ID


class CreateSessionResponse(BaseModel):
    session_id: str
    message: str


class StartPipelineRequest(BaseModel):
    """Config overrides for pipeline start."""
    task_package_id: Optional[int] = None
    winning_enabled: bool = True
    accompany_count: int = 0  # default 0 = winning only (technical solution focus)
    company: str = ""
    pipeline_config_yaml: str = ""
    solution_config: Dict[str, Any] = Field(default_factory=dict)


class StartPipelineResponse(BaseModel):
    session_id: str
    message: str
    ws_url: str


# ═══════════════════════════════════════════════════════════════
# Session lifecycle
# ═══════════════════════════════════════════════════════════════

@router.post("/api/session", response_model=CreateSessionResponse)
async def create_session(body: CreateSessionRequest = CreateSessionRequest()):
    """Create a new empty session workspace.

    Returns a session_id for subsequent upload and start calls.
    This is Step 1 of the 3-step workflow.
    """
    from .models import UserUploadConfig

    user_config = UserUploadConfig(
        company=body.company,
        name=body.project_name,
    )

    session_id = session_manager.create_session(
        user_config,
        session_id=body.session_id if body.session_id else None,
    )

    return CreateSessionResponse(
        session_id=session_id,
        message=f"会话已创建: {session_id}",
    )


@router.post("/api/session/{session_id}/start", response_model=StartPipelineResponse)
async def start_pipeline(
    session_id: str,
    background_tasks: BackgroundTasks,
    body: StartPipelineRequest = StartPipelineRequest(),
):
    """Start the bid generation pipeline on an existing session.

    Session must already exist and have files uploaded.
    This is Step 3 of the 3-step workflow.
    """
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    # Build user config from request + existing session data
    user_config_dict = {
        "company": body.company or info.get("user_config", {}).get("company", ""),
        "task_package_id": body.task_package_id,
        "winning_enabled": body.winning_enabled,
        "accompany_count": body.accompany_count,
        "pipeline_config_yaml": body.pipeline_config_yaml,
        "solution_config": body.solution_config,
    }

    # Create adapter and launch
    adapter = PipelineAdapter(
        session_id=session_id,
        workspace=workspace,
        user_config=user_config_dict,
    )

    from .ws_manager import ws_manager
    from .routes_upload import _run_pipeline_safe

    background_tasks.add_task(ws_manager.start_heartbeat, session_id)
    background_tasks.add_task(_run_pipeline_safe, adapter, session_id)

    return StartPipelineResponse(
        session_id=session_id,
        message=f"流水线已启动。会话ID: {session_id}",
        ws_url=f"/ws/{session_id}",
    )


# ═══════════════════════════════════════════════════════════════
# Session info + listing
# ═══════════════════════════════════════════════════════════════

@router.get("/api/session/{session_id}", response_model=SessionStatus)
async def get_session_status(session_id: str):
    """Get detailed status of a session including all stages."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    # Build stage status list
    stages = []
    current_stage = info.get("current_stage", -1)
    for i, sd in enumerate(STAGE_DEFINITIONS):
        if i < current_stage:
            status = "completed"
        elif i == current_stage and info.get("status") == "running":
            status = "running"
        elif i == current_stage and info.get("status") == "failed":
            status = "failed"
        else:
            status = "pending"
        stages.append({
            "id": sd["id"],
            "name": sd["name"],
            "description": sd["description"],
            "status": status,
        })

    completed = sum(1 for s in stages if s["status"] == "completed")
    return SessionStatus(
        session_id=session_id,
        created_at=info.get("created_at", ""),
        current_stage=current_stage,
        completed_stages=completed,
        total_stages=len(STAGE_DEFINITIONS),
        status=info.get("status", "idle"),
        stages=stages,
        error=info.get("error"),
    )


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions():
    """List all sessions sorted by creation time (newest first)."""
    sessions_data = session_manager.list_sessions()
    items = []
    for s in sessions_data:
        uc = s.get("user_config", {})
        items.append(SessionListItem(
            session_id=s.get("session_id", ""),
            created_at=s.get("created_at", ""),
            status=s.get("status", "idle"),
            current_stage=s.get("current_stage", -1),
            total_stages=len(STAGE_DEFINITIONS),
            company=uc.get("company", uc.get("name", "")),
        ))
    return SessionListResponse(sessions=items)


@router.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its workspace directory."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    success = session_manager.delete_session(session_id)
    if success:
        return {"message": f"会话已删除: {session_id}"}
    raise HTTPException(status_code=500, detail="删除会话失败")
