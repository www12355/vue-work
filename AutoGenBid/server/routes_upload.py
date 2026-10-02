"""
Upload Routes — Session-scoped file upload API.

Provides:
  - POST /api/session/{session_id}/upload   Upload files to session workspace
  - GET  /api/session/{session_id}/uploads  List uploaded files
  - DELETE /api/session/{session_id}/uploads/{filename} Delete a file
  - GET  /api/session/{session_id}/uploads/{filename} Download/preview
  - GET  /api/session/{session_id}/cache-tree  Full workspace tree
  - GET  /api/session/{session_id}/file-content File content viewer

  - POST /api/upload  Combined create+upload+start (backward compat)

Two file categories via ?type= query param:
  type=uploads  → core bid files     → workspaces/sessions/{id}/uploads/
  type=profile  → reference files    → workspaces/sessions/{id}/profile/
"""

from __future__ import annotations

import os
import re
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .session_manager import session_manager
from .models import UploadResponse as OriginalUploadResponse, UserUploadConfig
from .pipeline_adapter import PipelineAdapter

router = APIRouter()

# ── Constants ─────────────────────────────────────────────────
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    ".docx", ".doc", ".pdf", ".txt", ".md",
    ".pptx", ".ppt", ".xlsx", ".xls",
    ".jpg", ".jpeg", ".png", ".bmp",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB general
MAX_BID_SIZE = 200 * 1024 * 1024   # 200 MB for core bid docx
DOCX_MAGIC = b"PK\x03\x04"


# ── Safe filename ─────────────────────────────────────────────
def _safe_filename(name: str) -> str:
    """Remove path traversal characters, keep Chinese characters."""
    name = name.replace("\\", "").replace("/", "")
    name = name.lstrip(".")
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        raise HTTPException(status_code=400, detail="无效的文件名")
    return name


# ── Models ────────────────────────────────────────────────────

class UploadFileInfo(BaseModel):
    filename: str
    size_kb: float
    modified_at: str


class UploadListResponse(BaseModel):
    session_id: str
    files: List[UploadFileInfo]
    count: int


class SessionUploadResponse(BaseModel):
    session_id: str
    message: str
    uploaded: List[str] = []
    skipped: List[str] = []


class FileTreeRequest(BaseModel):
    session_id: str
    tree: dict


# ═══════════════════════════════════════════════════════════════
# Session-scoped upload endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/api/session/{session_id}/uploads", response_model=UploadListResponse)
async def list_uploaded_files(session_id: str):
    """List all files uploaded to a session workspace."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    all_files: List[UploadFileInfo] = []

    # Scan both uploads/ and profile/
    for subdir in ["uploads", "profile"]:
        dir_path = workspace / subdir
        if dir_path.exists():
            for f in sorted(dir_path.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.is_file() and not f.name.startswith("."):
                    stat = f.stat()
                    all_files.append(UploadFileInfo(
                        filename=f"{subdir}/{f.name}",
                        size_kb=round(stat.st_size / 1024, 1),
                        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    ))

    return UploadListResponse(session_id=session_id, files=all_files, count=len(all_files))


@router.post("/api/session/{session_id}/upload", response_model=SessionUploadResponse)
async def upload_files_to_session(
    session_id: str,
    files: List[UploadFile] = File(default=[]),
    text: str = Form(default=""),
    type: str = "uploads",
):
    """Upload files + optional text to session workspace.

    Query params:
        type=uploads  → save to workspace/uploads/ (核心标书文件)
        type=profile  → save to workspace/profile/ (参考文件)
        text          → user input text, saved as uploads/user_input.md
    """
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    # Determine target directory
    subdir = "uploads" if type != "profile" else "profile"
    target_dir = workspace / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    skipped = []

    # ── Save uploaded files ──
    for file in files:
        if not file.filename:
            skipped.append("(empty filename)")
            continue

        safe_name = _safe_filename(file.filename)
        ext = Path(safe_name).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            skipped.append(f"{safe_name} (不支持的文件类型: {ext})")
            continue

        content = await file.read()

        # Core bid files have higher size limit
        size_limit = MAX_BID_SIZE if (subdir == "uploads" and ext == ".docx") else MAX_FILE_SIZE
        if len(content) > size_limit:
            skipped.append(f"{safe_name} (文件过大, 最大 {size_limit // 1024 // 1024} MB)")
            continue

        dest = target_dir / safe_name
        if dest.exists():
            stem = Path(safe_name).stem
            counter = 1
            while dest.exists():
                dest = target_dir / f"{stem}_{counter}{ext}"
                counter += 1

        dest.write_bytes(content)
        uploaded.append(dest.name)
        print(f"[Upload:{subdir}] {session_id}: {safe_name} ({len(content)} bytes)")

    # ── Save user text as user_input.md ──
    if text and text.strip():
        uploads_dir = workspace / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        text_path = uploads_dir / "user_input.md"
        text_path.write_text(text.strip(), encoding="utf-8")
        print(f"[Upload:text] {session_id}: user_input.md ({len(text)} chars)")

    session_manager.touch(session_id)
    return SessionUploadResponse(
        session_id=session_id,
        message=f"[{subdir}] 上传 {len(uploaded)} 个文件" + (f"，跳过 {len(skipped)} 个" if skipped else ""),
        uploaded=uploaded,
        skipped=skipped,
    )


@router.delete("/api/session/{session_id}/uploads/{filename:path}")
async def delete_uploaded_file(session_id: str, filename: str):
    """Delete a file from a session workspace uploads/ or profile/ directory."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    safe_name = _safe_filename(filename)

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    # Try both uploads/ and profile/
    file_path = None
    for subdir in ["uploads", "profile"]:
        candidate = workspace / subdir / safe_name
        if candidate.exists():
            file_path = candidate
            break

    if file_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_name}")

    # Security: path within workspace
    try:
        file_path.resolve().relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")

    try:
        file_path.unlink()
        return {"message": f"文件已删除: {safe_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.get("/api/session/{session_id}/uploads/{filename:path}")
async def download_uploaded_file(session_id: str, filename: str):
    """Download or preview a file from session uploads/ or profile/."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    safe_name = _safe_filename(filename)

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    # Try both subdirectories
    file_path = None
    for subdir in ["uploads", "profile"]:
        candidate = workspace / subdir / safe_name
        if candidate.exists():
            file_path = candidate
            break

    if file_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_name}")

    # Security
    try:
        file_path.resolve().relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")

    ext = file_path.suffix.lower()
    media_types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type=media_type,
    )


# ═══════════════════════════════════════════════════════════════
# Combined upload + start (backward compatible)
# ═══════════════════════════════════════════════════════════════

@router.post("/api/upload", response_model=OriginalUploadResponse)
async def upload_bid_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="标书 DOCX 文件"),
    config: str = Form(..., description="JSON 格式的用户配置信息"),
    reference_files: List[UploadFile] = File(default=[], description="参考文件"),
):
    """Upload a bid DOCX file + optional reference files + config, then start pipeline.

    This is the one-step upload endpoint for backward compatibility.
    For fine-grained control, use POST /api/session + POST /api/session/{id}/upload.
    """
    # ── Validate config JSON ──
    try:
        user_config_dict = json.loads(config)
        user_config = UserUploadConfig(**user_config_dict)
    except (json.JSONDecodeError, Exception) as e:
        raise HTTPException(status_code=400, detail=f"配置 JSON 解析失败: {e}")

    # ── Validate core file is DOCX ──
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="核心标书文件只接受 .docx 格式")

    content = await file.read()
    if len(content) > MAX_BID_SIZE:
        raise HTTPException(status_code=400, detail=f"文件过大，最大 {MAX_BID_SIZE // 1024 // 1024} MB")

    if len(content) < 4 or content[:4] != DOCX_MAGIC:
        raise HTTPException(status_code=400, detail="文件格式无效，非有效的 DOCX/ZIP 文件")

    # ── Create session ──
    preferred_sid = user_config_dict.get("_session_id", "").strip() if isinstance(user_config_dict, dict) else ""
    session_id = session_manager.create_session(user_config, session_id=preferred_sid if preferred_sid else None)
    workspace = session_manager.get_workspace(session_id)

    # ── Save core bid file to uploads/ ──
    upload_path = workspace / "uploads" / "bid_document.docx"
    upload_path.write_bytes(content)

    # ── Save reference files to profile/ ──
    for ref_file in reference_files:
        if not ref_file.filename:
            continue
        safe_name = _safe_filename(ref_file.filename)
        ext = Path(safe_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        try:
            ref_content = await ref_file.read()
            if len(ref_content) <= MAX_FILE_SIZE:
                ref_path = workspace / "profile" / safe_name
                ref_path.write_bytes(ref_content)
        except Exception:
            pass  # Skip individual reference file errors

    # ── Launch pipeline as background task ──
    adapter = PipelineAdapter(
        session_id=session_id,
        workspace=workspace,
        user_config=user_config_dict,
    )

    from .ws_manager import ws_manager

    background_tasks.add_task(ws_manager.start_heartbeat, session_id)
    background_tasks.add_task(_run_pipeline_safe, adapter, session_id)

    return OriginalUploadResponse(
        session_id=session_id,
        message=f"文件上传成功，已开始生成。会话ID: {session_id}",
        ws_url=f"/ws/{session_id}",
    )


async def _run_pipeline_safe(adapter: PipelineAdapter, session_id: str) -> None:
    """Run the pipeline and handle any unexpected errors."""
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
# Cache tree + file content
# ═══════════════════════════════════════════════════════════════

def _build_file_tree(directory: Path, base_path: str = "") -> List[dict]:
    """Recursively build a file tree structure for a directory."""
    if not directory.exists() or not directory.is_dir():
        return []

    items = []
    try:
        entries = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return []

    for entry in entries:
        if (entry.name.startswith(".") and entry.name != ".cache") or entry.name == "__pycache__":
            continue

        rel_path = f"{base_path}/{entry.name}" if base_path else entry.name

        if entry.is_dir():
            children = _build_file_tree(entry, rel_path)
            items.append({
                "name": entry.name,
                "type": "directory",
                "path": rel_path,
                "children": children,
            })
        else:
            try:
                size_kb = round(entry.stat().st_size / 1024, 1)
            except OSError:
                size_kb = 0
            items.append({
                "name": entry.name,
                "type": "file",
                "path": rel_path,
                "size_kb": size_kb,
            })

    return items


@router.get("/api/session/{session_id}/cache-tree")
async def get_cache_tree(session_id: str):
    """Get the full directory tree of a session workspace."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    tree = session_manager.get_cache_tree(session_id)

    return {"session_id": session_id, "tree": tree}


@router.get("/api/session/{session_id}/pipeline-log")
async def get_pipeline_log(session_id: str):
    """Get the pipeline execution log (last 500 lines) for a session."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    log_path = workspace / ".cache" / "pipeline.log"
    if not log_path.exists():
        return PlainTextResponse("(日志文件尚未生成)")

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").split("\n")
        recent = lines[-500:] if len(lines) > 500 else lines
        return PlainTextResponse("\n".join(recent))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败: {e}")


@router.get("/api/session/{session_id}/file-content")
async def get_file_content(session_id: str, path: str = ""):
    """Get the text content of a file in the session workspace."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    if not path:
        raise HTTPException(status_code=400, detail="缺少 path 参数")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    clean_path = path
    if clean_path.startswith(workspace.name + "/"):
        clean_path = clean_path[len(workspace.name) + 1:]

    file_path = (workspace / clean_path).resolve()

    try:
        file_path.relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

    ext = file_path.suffix.lower()
    text_extensions = {".md", ".txt", ".json", ".yaml", ".yml", ".html", ".css", ".js", ".py", ".xml", ".csv"}

    if ext in text_extensions:
        try:
            content = file_path.read_text(encoding="utf-8")
            return PlainTextResponse(content)
        except UnicodeDecodeError:
            pass

    media_types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".pdf": "application/pdf",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
    )
