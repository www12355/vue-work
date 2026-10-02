"""
Download Routes — session status, file listing, and file download.
Updated for workspaces/sessions/{id}/ layout.
"""

from __future__ import annotations

import os
import tempfile
import subprocess
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from .session_manager import session_manager, SESSIONS_DIR
from .models import (
    SessionStatus,
    FileListResponse,
    FileInfo,
    StageInfo,
    STAGE_DEFINITIONS,
    CacheTreeResponse,
    CacheTreeNode,
    SessionListItem,
    SessionListResponse,
)

router = APIRouter()


def _media_type_for_name(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lower.endswith(".md"):
        return "text/markdown"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".txt"):
        return "text/plain"
    if lower.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"


@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "active_sessions": session_manager.active_count,
    }


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions():
    """List all sessions by scanning workspaces/sessions/ on disk.

    Scans both new path (workspaces/sessions/) and old path (workspaces/)
    for backward compatibility.
    """
    import json as _json

    items: List[SessionListItem] = []
    seen_sids: set = set()

    # Collect directories to scan
    dirs_to_scan = []
    if SESSIONS_DIR.exists():
        dirs_to_scan.append(SESSIONS_DIR)
    # Also scan old workspaces/ root for backward compat
    from .session_manager import WORKSPACES_DIR as _WS_DIR
    if _WS_DIR.exists():
        dirs_to_scan.append(_WS_DIR)

    for scan_dir in dirs_to_scan:
        if not scan_dir.exists():
            continue
        for ws_dir in sorted(scan_dir.iterdir(), reverse=True):
            if not ws_dir.is_dir():
                continue
            sid = ws_dir.name
            # Skip non-session dirs
            if sid.startswith(".") or sid in ("sessions", "sessions_index.json", "sessions.json"):
                continue
            if sid in seen_sids:
                continue
            seen_sids.add(sid)

            # ── Read user_config.json for company name ──
            company = ""
            user_config_path = ws_dir / "user_config.json"
            if user_config_path.exists():
                try:
                    uc = _json.loads(user_config_path.read_text(encoding="utf-8"))
                    company = uc.get("company", "") or ""
                except (_json.JSONDecodeError, IOError):
                    pass

            # ── Read pipeline_state.json for status & progress ──
            status = "idle"
            current_stage = -1
            created_at = ""
            state_path = ws_dir / ".cache" / "pipeline_state.json"
            if state_path.exists():
                try:
                    ps = _json.loads(state_path.read_text(encoding="utf-8"))
                    completed = ps.get("completed_stages", 0)
                    current_stage = completed
                    created_at = ps.get("started_at") or ps.get("last_updated", "")
                    if completed >= 11:
                        status = "completed"
                    elif completed > 0:
                        status = "running"
                    else:
                        status = "idle"
                except (_json.JSONDecodeError, IOError):
                    pass

            # ── Fallback: use directory modification time ──
            if not created_at:
                from datetime import datetime
                mtime = ws_dir.stat().st_mtime
                created_at = datetime.fromtimestamp(mtime).isoformat()

            # ── A valid history entry must have some content ──
            cache_dir = ws_dir / ".cache"
            has_content = cache_dir.exists() and any(cache_dir.iterdir())
            has_config = user_config_path.exists()
            if not has_content and not has_config:
                continue

            items.append(SessionListItem(
                session_id=sid,
                created_at=created_at,
                status=status,
                current_stage=current_stage,
                total_stages=11,
                company=company,
            ))

    # Sort by created_at descending (newest first)
    items.sort(key=lambda x: x.created_at, reverse=True)
    return SessionListResponse(sessions=items)


@router.get("/api/session/{session_id}", response_model=SessionStatus)
async def get_session_status(session_id: str):
    """Get the current status of a pipeline session."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    # Build stage status list
    stages: List[StageInfo] = []
    completed = info.get("current_stage", -1)
    for sd in STAGE_DEFINITIONS:
        sid = sd["id"]
        if sid < completed:
            status = "completed"
        elif sid == completed and info.get("status") == "running":
            status = "running"
        elif sid == completed and info.get("status") == "failed":
            status = "failed"
        else:
            status = "pending"

        stages.append(StageInfo(
            id=sid,
            name=sd["name"],
            description=sd["description"],
            status=status,
        ))

    return SessionStatus(
        session_id=session_id,
        created_at=info.get("created_at", ""),
        current_stage=info.get("current_stage", -1),
        completed_stages=info.get("current_stage", 0),
        total_stages=11,
        status=info.get("status", "idle"),
        stages=stages,
        error=info.get("error"),
    )


@router.get("/api/session/{session_id}/files", response_model=FileListResponse)
async def list_session_files(session_id: str):
    """List all downloadable output files for a session."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    files = session_manager.list_output_files(session_id)

    return FileListResponse(
        session_id=session_id,
        files=files,
    )


@router.get("/api/download/{session_id}")
async def download_file_by_query(session_id: str, file: str = Query(..., description="Relative file path within workspace")):
    """Download a file by workspace-relative path."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    file_path = session_manager.get_cache_file_path(session_id, file)
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在或路径不合法: {file}")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=_media_type_for_name(file_path.name),
    )


@router.get("/api/download/{session_id}/{filename:path}")
async def download_file(session_id: str, filename: str):
    """Download a generated file from a session workspace.

    Searches output/ first, then .cache/11_final/, then workspace root.
    """
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    file_path = session_manager.get_file_path(session_id, filename)
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=_media_type_for_name(file_path.name),
    )


@router.get("/api/session/{session_id}/cache-tree", response_model=CacheTreeResponse)
async def get_cache_tree(session_id: str):
    """Get the full workspace directory tree for the file explorer panel."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    tree = session_manager.get_cache_tree(session_id)
    return CacheTreeResponse(session_id=session_id, tree=tree)


@router.get("/api/session/{session_id}/file-content")
async def get_file_content(session_id: str, path: str = Query(..., description="Relative path within workspace")):
    """Get raw file content for the document viewer panel."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    file_path = session_manager.get_cache_file_path(session_id, path)
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在或路径不合法: {path}")

    # Determine media type
    if path.endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif path.endswith(".md"):
        media_type = "text/markdown; charset=utf-8"
    elif path.endswith(".json"):
        media_type = "application/json; charset=utf-8"
    elif path.endswith(".txt"):
        media_type = "text/plain; charset=utf-8"
    elif path.endswith(".yaml") or path.endswith(".yml"):
        media_type = "text/yaml; charset=utf-8"
    elif path.endswith(".pdf"):
        media_type = "application/pdf"
    elif path.endswith(".html"):
        media_type = "text/html; charset=utf-8"
    else:
        media_type = "application/octet-stream"

    # For binary files, return raw bytes
    if media_type.startswith("application/") and "charset" not in media_type:
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
        )

    # For text files, read and return as plain text
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return FileResponse(path=str(file_path), media_type="application/octet-stream")

    return PlainTextResponse(content=content, media_type=media_type)


@router.get("/api/session/{session_id}/docx-as-pdf")
async def get_docx_as_pdf(session_id: str, path: str = Query(..., description="Relative path to .docx file")):
    """Convert a DOCX file to PDF using Word COM and return the PDF.

    The PDF is cached in the session's .temp/ directory.
    """
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    # Strip workspace name prefix if present (same as file-content endpoint)
    workspace = session_manager.get_workspace(session_id)
    clean_path = path
    if clean_path.startswith(workspace.name + "/"):
        clean_path = clean_path[len(workspace.name) + 1:]

    docx_path = session_manager.get_cache_file_path(session_id, clean_path)
    if docx_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    if not docx_path.suffix.lower() == ".docx":
        raise HTTPException(status_code=400, detail="仅支持 .docx 文件转换")

    temp_dir = workspace / ".temp"
    temp_dir.mkdir(exist_ok=True)

    pdf_name = Path(path).stem + ".pdf"
    pdf_path = temp_dir / pdf_name

    if pdf_path.exists() and pdf_path.stat().st_mtime >= docx_path.stat().st_mtime:
        return FileResponse(path=str(pdf_path), media_type="application/pdf",
                            headers={"Cache-Control": "max-age=3600"})

    # ── Convert DOCX → PDF via Word COM ──
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        word.ScreenUpdating = False

        doc = word.Documents.Open(str(docx_path))
        try:
            doc.ExportAsFixedFormat(
                OutputFileName=str(pdf_path),
                ExportFormat=17,
                OpenAfterExport=False,
                OptimizeFor=0,
                CreateBookmarks=1,
            )
        finally:
            doc.Close(SaveChanges=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DOCX 转 PDF 失败: {e}")
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

    if not pdf_path.exists():
        raise HTTPException(status_code=500, detail="PDF 生成失败，输出文件不存在")

    return FileResponse(path=str(pdf_path), media_type="application/pdf",
                        headers={"Cache-Control": "max-age=3600"})


@router.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Cancel and clean up a session."""
    if not session_manager.get_session_info(session_id):
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    session_manager.delete_session(session_id)
    return {"message": f"会话 {session_id} 已清理"}
