"""
Contract Route — handles contract generation request.
v3.0: Supports multipart/form-data with optional file uploads.
"""

from __future__ import annotations

import json
import asyncio
import re
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel

from .session_manager import session_manager
from .models import GenerateResponse, ContractGenerateRequest
from .contract_adapter import ContractAdapter

router = APIRouter()

# File upload settings (same as routes_upload.py)
ALLOWED_EXTENSIONS = {
    ".docx", ".doc", ".pdf", ".txt", ".md",
    ".pptx", ".ppt", ".xlsx", ".xls",
    ".jpg", ".jpeg", ".png", ".bmp",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _safe_filename(name: str) -> str:
    """Remove path traversal characters."""
    name = name.replace("\\", "").replace("/", "")
    name = name.lstrip(".")
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        raise HTTPException(status_code=400, detail="无效的文件名")
    return name


def _validate_request(form_data: dict) -> List[str]:
    """Validate required form fields. Returns list of error messages."""
    errors = []
    if not form_data.get("project_name", "").strip():
        errors.append("项目名称不能为空")
    if not form_data.get("party_a", "").strip():
        errors.append("甲方公司名称不能为空")
    if not form_data.get("party_b", "").strip():
        errors.append("乙方公司名称不能为空")
    if not form_data.get("signing_place", "").strip():
        errors.append("签订地点不能为空")

    duration_total = (
        form_data.get("duration_years", 0) +
        form_data.get("duration_months", 0) +
        form_data.get("duration_days", 0)
    )
    if duration_total == 0:
        errors.append("服务时长不能全部为零")

    return errors


@router.post("/api/generate", response_model=GenerateResponse)
async def generate_contract(
    background_tasks: BackgroundTasks,
    # ── Form fields (JSON body OR multipart form fields) ──
    contract_id: str = Form(default=""),
    project_name: str = Form(default=""),
    signing_place: str = Form(default=""),
    signing_date: str = Form(default=""),
    party_a: str = Form(default=""),
    party_b: str = Form(default=""),
    start_date: str = Form(default=""),
    duration_years: int = Form(default=0),
    duration_months: int = Form(default=12),
    duration_days: int = Form(default=0),
    end_date: str = Form(default=""),
    duration_text: str = Form(default=""),
    session_id: str = Form(default=""),
    # ── Optional files ──
    files: List[UploadFile] = File(default=[]),
):
    """Start contract generation.

    Accepts either:
    - JSON body (Content-Type: application/json) — backward compatible
    - multipart/form-data with form fields + optional file uploads
    """
    # Build form data dict
    form_data = {
        "contract_id": contract_id,
        "project_name": project_name,
        "signing_place": signing_place,
        "signing_date": signing_date,
        "party_a": party_a,
        "party_b": party_b,
        "start_date": start_date,
        "duration_years": duration_years,
        "duration_months": duration_months,
        "duration_days": duration_days,
        "end_date": end_date,
        "duration_text": duration_text,
    }

    # ── Validate required fields ──
    errors = _validate_request(form_data)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # ── Create session ──
    preferred_sid = session_id.strip() if session_id else None
    sid = session_manager.create_session(form_data, session_id=preferred_sid if preferred_sid else None)
    workspace = session_manager.get_workspace(sid)

    # ── Save uploaded files to session workspace ──
    uploaded_count = 0
    if files:
        uploads_dir = workspace / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            if not file.filename:
                continue

            safe_name = _safe_filename(file.filename)
            ext = Path(safe_name).suffix.lower()

            if ext not in ALLOWED_EXTENSIONS:
                continue

            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                continue

            dest = uploads_dir / safe_name
            if dest.exists():
                stem = Path(safe_name).stem
                counter = 1
                while dest.exists():
                    dest = uploads_dir / f"{stem}_{counter}{ext}"
                    counter += 1

            dest.write_bytes(content)
            uploaded_count += 1

    # ── Launch generation as background task ──
    adapter = ContractAdapter(
        session_id=sid,
        workspace=workspace,
        form_data=form_data,
    )

    from .ws_manager import ws_manager

    background_tasks.add_task(ws_manager.start_heartbeat, sid)
    background_tasks.add_task(_run_generation_safe, adapter, sid)

    upload_msg = f"，已接收 {uploaded_count} 个文件" if uploaded_count > 0 else ""
    return GenerateResponse(
        session_id=sid,
        message=f"合同生成已启动{upload_msg}。会话ID: {sid}",
        ws_url=f"/ws/{sid}",
    )


# ── JSON body endpoint (backward compatible) ──

@router.post("/api/generate/json", response_model=GenerateResponse)
async def generate_contract_json(
    background_tasks: BackgroundTasks,
    request: ContractGenerateRequest,
):
    """[向后兼容] Start contract generation from JSON body."""
    errors = _validate_request(request.model_dump())
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    form_data = request.model_dump()
    preferred_sid = form_data.pop("session_id", None)

    sid = session_manager.create_session(form_data, session_id=preferred_sid if preferred_sid else None)
    workspace = session_manager.get_workspace(sid)

    adapter = ContractAdapter(
        session_id=sid,
        workspace=workspace,
        form_data=form_data,
    )

    from .ws_manager import ws_manager

    background_tasks.add_task(ws_manager.start_heartbeat, sid)
    background_tasks.add_task(_run_generation_safe, adapter, sid)

    return GenerateResponse(
        session_id=sid,
        message=f"合同生成已启动。会话ID: {sid}",
        ws_url=f"/ws/{sid}",
    )


async def _run_generation_safe(adapter: ContractAdapter, session_id: str) -> None:
    """Run the generation and handle any unexpected errors."""
    from .ws_manager import ws_manager

    try:
        session_manager.update_session(session_id, status="running")
        success = await adapter.run()
        if success:
            session_manager.update_session(session_id, status="completed")
        else:
            session_manager.update_session(session_id, status="failed")
    except Exception as e:
        session_manager.update_session(session_id, status="failed", error=str(e))
        await ws_manager.send_pipeline_failed(session_id, str(e))


# ═══════════════════════════════════════════════════════════════
# Three-step flow: Create Session → Upload Files → Start Generation
# ═══════════════════════════════════════════════════════════════

class SessionCreateResponse(BaseModel):
    session_id: str
    message: str
    upload_url: str
    start_url: str


@router.post("/api/session", response_model=SessionCreateResponse)
async def create_session(form_data: ContractGenerateRequest):
    """Step 1: Create a session workspace without starting generation.

    Returns session_id for subsequent file upload and pipeline start.
    """
    errors = _validate_request(form_data.model_dump())
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    data = form_data.model_dump()
    sid = session_manager.create_session(data)
    session_manager.update_session(sid, status="idle")

    return SessionCreateResponse(
        session_id=sid,
        message=f"会话已创建，可上传文件后启动生成。会话ID: {sid}",
        upload_url=f"/api/session/{sid}/upload",
        start_url=f"/api/session/{sid}/start",
    )


@router.post("/api/session/{session_id}/start", response_model=GenerateResponse)
async def start_generation(
    session_id: str,
    background_tasks: BackgroundTasks,
    form_data: ContractGenerateRequest = None,
):
    """Step 3: Start the contract generation pipeline on an existing session.

    If form_data is provided, the session's stored form data is updated first.
    This ensures the latest user input (after file uploads) is used for generation.
    """
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    # Use updated form data if provided, otherwise use stored data
    if form_data is not None:
        data = form_data.model_dump()
        session_manager.update_session(session_id, form_data=data)
        # Also update contract_config.json
        try:
            workspace = session_manager.get_workspace(session_id)
            (workspace / "contract_config.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except FileNotFoundError:
            pass
    else:
        data = info.get("form_data", {})

    if not data:
        raise HTTPException(status_code=400, detail="会话数据不完整，请重新创建会话")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    adapter = ContractAdapter(
        session_id=session_id,
        workspace=workspace,
        form_data=data,
    )

    from .ws_manager import ws_manager

    background_tasks.add_task(ws_manager.start_heartbeat, session_id)
    background_tasks.add_task(_run_generation_safe, adapter, session_id)

    return GenerateResponse(
        session_id=session_id,
        message=f"合同生成已启动。会话ID: {session_id}",
        ws_url=f"/ws/{session_id}",
    )
