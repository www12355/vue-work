"""
Download Routes — session status, file listing, and file download.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .session_manager import session_manager
from .models import (
    SessionStatus,
    FileListResponse,
    FileInfo,
    StageInfo,
    STAGE_DEFINITIONS,
    TOTAL_STAGES,
    SessionListItem,
    SessionListResponse,
)

router = APIRouter()


def _media_type_for_name(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lower.endswith(".doc"):
        return "application/msword"
    if lower.endswith(".md"):
        return "text/markdown"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".txt"):
        return "text/plain"
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".pptx"):
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if lower.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def _resolve_workspace_file(session_id: str, relative_path: str) -> Path | None:
    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        return None

    clean = relative_path.lstrip("/").lstrip("\\")
    if clean.startswith(workspace.name + "/"):
        clean = clean[len(workspace.name) + 1:]

    candidate = (workspace / clean).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "active_sessions": session_manager.active_count,
    }


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions():
    """List all sessions by scanning workspaces/sessions/ on disk."""
    items: List[SessionListItem] = []

    from .session_manager import SESSIONS_DIR

    scan_dirs = [SESSIONS_DIR]

    for base_dir in scan_dirs:
        if not base_dir.exists():
            continue

        for ws_dir in sorted(base_dir.iterdir(), reverse=True):
            if not ws_dir.is_dir():
                continue
            sid = ws_dir.name
            if sid.startswith(".") or sid == "sessions.json":
                continue

            # Read contract_config.json for project name
            # Check workspace root first, then 01_config/ subdirectory
            project = ""
            for config_dir in [ws_dir, ws_dir / "01_config"]:
                config_path = config_dir / "contract_config.json"
                if config_path.exists():
                    try:
                        uc = _json.loads(config_path.read_text(encoding="utf-8"))
                        # Handle nested structure (form_data may be inside)
                        if "form_data" in uc:
                            project = uc["form_data"].get("project_name", "") or ""
                        else:
                            project = uc.get("project_name", "") or ""
                    except (_json.JSONDecodeError, IOError):
                        pass
                    break

            # Read session registry for status
            info = session_manager.get_session_info(sid)
            status = info.get("status", "idle") if info else "idle"
            current_stage = info.get("current_stage", -1) if info else -1
            created_at = info.get("created_at", "") if info else ""

            if not created_at:
                mtime = ws_dir.stat().st_mtime
                created_at = datetime.fromtimestamp(mtime).isoformat()

            # Skip empty sessions with no config
            if not project and not info:
                continue

            items.append(SessionListItem(
                session_id=sid,
                created_at=created_at,
                status=status,
                current_stage=current_stage,
                total_stages=TOTAL_STAGES,
                project=project,
            ))

    items.sort(key=lambda x: x.created_at, reverse=True)
    return SessionListResponse(sessions=items)


@router.get("/api/session/{session_id}", response_model=SessionStatus)
async def get_session_status(session_id: str):
    """Get the current status of a contract generation session."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

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
        total_stages=4,      # v2.0: 4-stage pipeline
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
    return FileListResponse(session_id=session_id, files=files)


@router.get("/api/download/{session_id}")
async def download_file_by_query(session_id: str, file: str = Query(..., description="Relative file path within workspace")):
    """Download any visible workspace file by relative path."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    file_path = _resolve_workspace_file(session_id, file)
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在或路径不合法: {file}")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=_media_type_for_name(file_path.name),
    )


@router.get("/api/download/{session_id}/{filename:path}")
async def download_file(session_id: str, filename: str):
    """Download a generated file from a session workspace."""
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


@router.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Cancel and clean up a session."""
    info = session_manager.get_session_info(session_id)
    workspace_exists = False
    try:
        workspace_exists = session_manager.get_workspace(session_id).exists()
    except FileNotFoundError:
        workspace_exists = False

    if not info and not workspace_exists:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    session_manager.delete_session(session_id)
    return {"message": f"会话 {session_id} 已清理"}


# ═══════════════════════════════════════════════════════════════
# DOCX to PDF conversion (Windows COM)
# ═══════════════════════════════════════════════════════════════

@router.get("/api/session/{session_id}/docx-as-pdf")
async def convert_docx_to_pdf(session_id: str, path: str = ""):
    """Convert a DOCX file to PDF using Microsoft Word COM (Windows only).

    Caches the PDF in workspace/.temp/ for subsequent requests.
    """
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    if not path:
        raise HTTPException(status_code=400, detail="缺少 path 参数")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    # Security: resolve and verify path is within workspace
    clean_path = path
    ws_name = workspace.name
    if clean_path.startswith(ws_name + "/"):
        clean_path = clean_path[len(ws_name) + 1:]

    file_path = (workspace / clean_path).resolve()
    try:
        file_path.relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

    if file_path.suffix.lower() not in ('.docx', '.doc'):
        raise HTTPException(status_code=400, detail="仅支持 DOCX/DOC 文件转换")

    # Cache directory
    temp_dir = workspace / ".temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = temp_dir / f"{file_path.stem}.pdf"

    # Check cache: if PDF exists and is newer than source, use cached
    if pdf_path.exists():
        if pdf_path.stat().st_mtime >= file_path.stat().st_mtime:
            return FileResponse(
                path=str(pdf_path),
                filename=pdf_path.name,
                media_type="application/pdf",
                headers={"Cache-Control": "max-age=3600"},
            )

    # Convert using Word COM
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()

        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            word.ScreenUpdating = False

            try:
                doc = word.Documents.Open(str(file_path))
                doc.ExportAsFixedFormat(
                    OutputFileName=str(pdf_path),
                    ExportFormat=17,  # wdExportFormatPDF
                    OpenAfterExport=False,
                    OptimizeFor=0,    # wdExportOptimizeForPrint
                    CreateBookmarks=1,
                )
                doc.Close(SaveChanges=False)
            finally:
                word.Quit()
        finally:
            pythoncom.CoUninitialize()

        if not pdf_path.exists():
            raise HTTPException(status_code=500, detail="PDF 转换失败：输出文件未生成")

        return FileResponse(
            path=str(pdf_path),
            filename=pdf_path.name,
            media_type="application/pdf",
            headers={"Cache-Control": "max-age=3600"},
        )

    except ImportError:
        return FileResponse(path=str(file_path), filename=file_path.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    except Exception:
        return FileResponse(path=str(file_path), filename=file_path.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _resolve_file_path(session_id: str, path: str):
    """Resolve and validate a file path within a session workspace. Returns Path or raises HTTPException."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    if not path:
        raise HTTPException(status_code=400, detail="缺少 path 参数")
    workspace = session_manager.get_workspace(session_id)
    clean = path
    if clean.startswith(workspace.name + "/"):
        clean = clean[len(workspace.name) + 1:]
    fp = (workspace / clean).resolve()
    try:
        fp.relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    return workspace, fp


# ═══════════════════════════════════════════════════════════════
# PPTX to PDF conversion (PowerPoint COM)
# ═══════════════════════════════════════════════════════════════

@router.get("/api/session/{session_id}/pptx-as-pdf")
async def convert_pptx_to_pdf(session_id: str, path: str = ""):
    """Convert a PPTX file to PDF using Microsoft PowerPoint COM (Windows only)."""
    workspace, file_path = _resolve_file_path(session_id, path)
    if file_path.suffix.lower() not in ('.pptx', '.ppt'):
        raise HTTPException(status_code=400, detail="仅支持 PPTX/PPT 文件转换")

    temp_dir = workspace / ".temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = temp_dir / f"{file_path.stem}_pptx.pdf"

    if pdf_path.exists() and pdf_path.stat().st_mtime >= file_path.stat().st_mtime:
        return FileResponse(path=str(pdf_path), filename=pdf_path.name,
            media_type="application/pdf", headers={"Cache-Control": "max-age=3600"})

    try:
        import pythoncom, win32com.client
        pythoncom.CoInitialize()
        try:
            ppt = win32com.client.Dispatch("PowerPoint.Application")
            ppt.Visible = False
            try:
                pres = ppt.Presentations.Open(str(file_path), WithWindow=False)
                pres.ExportAsFixedFormat(str(pdf_path), 2)  # 2 = ppFixedFormatTypePDF
                pres.Close()
            finally:
                ppt.Quit()
        finally:
            pythoncom.CoUninitialize()
        if not pdf_path.exists():
            raise HTTPException(status_code=500, detail="PDF 转换失败")
        return FileResponse(path=str(pdf_path), filename=pdf_path.name,
            media_type="application/pdf", headers={"Cache-Control": "max-age=3600"})
    except ImportError:
        return FileResponse(path=str(file_path), filename=file_path.name,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    except Exception:
        return FileResponse(path=str(file_path), filename=file_path.name,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


# ═══════════════════════════════════════════════════════════════
# Excel to JSON table
# ═══════════════════════════════════════════════════════════════

@router.get("/api/session/{session_id}/xlsx-as-json")
async def convert_xlsx_to_json(session_id: str, path: str = ""):
    """Read an Excel file and return its sheets as JSON array-of-arrays."""
    workspace, file_path = _resolve_file_path(session_id, path)
    if file_path.suffix.lower() not in ('.xlsx', '.xls'):
        raise HTTPException(status_code=400, detail="仅支持 XLSX/XLS 文件")

    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(file_path), data_only=True)
        sheets = {}
        for name in wb.sheetnames:
            ws = wb[name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append([str(c) if c is not None else "" for c in row])
            sheets[name] = rows
        wb.close()
        return {"sheets": sheets, "filename": file_path.name}
    except ImportError:
        raise HTTPException(status_code=500, detail="需要安装 openpyxl")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel 读取失败: {e}")
