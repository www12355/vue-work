"""
Upload Routes — Session-scoped file upload API.

Provides CRUD API for session workspace uploads:
  - POST /api/session/{session_id}/upload   Upload files to session workspace
  - GET  /api/session/{session_id}/uploads  List uploaded files
  - DELETE /api/session/{session_id}/uploads/{filename} Delete a file
  - GET  /api/session/{session_id}/uploads/{filename} Download/preview

Files are stored in workspaces/sessions/{session_id}/uploads/.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .session_manager import session_manager

router = APIRouter()

# ── Path resolution ──────────────────────────────────────────
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent  # 自动合同生成/

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    ".docx", ".doc", ".pdf", ".txt", ".md",
    ".pptx", ".ppt", ".xlsx", ".xls",
    ".jpg", ".jpeg", ".png", ".bmp",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# ── Safe filename ────────────────────────────────────────────
def _safe_filename(name: str) -> str:
    """Remove path traversal characters, keep Chinese characters."""
    name = name.replace("\\", "").replace("/", "")
    name = name.lstrip(".")
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        raise HTTPException(status_code=400, detail="无效的文件名")
    return name


# ── Models ───────────────────────────────────────────────────

class UploadFileInfo(BaseModel):
    filename: str
    size_kb: float
    modified_at: str


class UploadListResponse(BaseModel):
    session_id: str
    files: List[UploadFileInfo]
    count: int


class UploadResponse(BaseModel):
    session_id: str
    message: str
    uploaded: List[str]
    skipped: List[str] = []


# ── Routes ───────────────────────────────────────────────────

@router.get("/api/session/{session_id}/uploads", response_model=UploadListResponse)
async def list_uploaded_files(session_id: str):
    """List all files uploaded to a session workspace."""
    # Validate session exists
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    uploads_dir = workspace / "uploads"
    if not uploads_dir.exists():
        return UploadListResponse(session_id=session_id, files=[], count=0)

    files: List[UploadFileInfo] = []
    for f in sorted(uploads_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file() and not f.name.startswith("."):
            stat = f.stat()
            files.append(UploadFileInfo(
                filename=f.name,
                size_kb=round(stat.st_size / 1024, 1),
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            ))

    return UploadListResponse(session_id=session_id, files=files, count=len(files))


@router.post("/api/session/{session_id}/upload", response_model=UploadResponse)
async def upload_files_to_session(
    session_id: str,
    files: List[UploadFile] = File(default=[]),
    text: str = Form(default=""),
    type: str = "uploads",
):
    """Upload files + optional text to session workspace.

    Query params:
        type=uploads  → save to workspace/uploads/ (核心文件)
        type=profile  → save to workspace/profile/ (参考文件)
        text          → user text, saved as uploads/user_input.md
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
        if len(content) > MAX_FILE_SIZE:
            skipped.append(f"{safe_name} (文件过大)")
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
    return UploadResponse(
        session_id=session_id,
        message=f"[{subdir}] 上传 {len(uploaded)} 个文件" + (f"，跳过 {len(skipped)} 个" if skipped else ""),
        uploaded=uploaded,
        skipped=skipped,
    )


@router.delete("/api/session/{session_id}/uploads/{filename:path}")
async def delete_uploaded_file(session_id: str, filename: str):
    """Delete a file from a session workspace uploads/ directory."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    safe_name = _safe_filename(filename)

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    file_path = workspace / "uploads" / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_name}")

    # Security: ensure the resolved path is inside the uploads directory
    try:
        file_path.resolve().relative_to((workspace / "uploads").resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")

    try:
        file_path.unlink()
        return {"message": f"文件已删除: {safe_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.get("/api/session/{session_id}/uploads/{filename:path}")
async def download_uploaded_file(session_id: str, filename: str):
    """Download or preview a file from a session workspace uploads/ directory."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    safe_name = _safe_filename(filename)

    try:
        workspace = session_manager.get_workspace(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话工作区不存在")

    file_path = workspace / "uploads" / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_name}")

    # Security check
    try:
        file_path.resolve().relative_to((workspace / "uploads").resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")

    # Determine media type
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
# File Manager APIs — cache tree + file content
# ═══════════════════════════════════════════════════════════════

def _build_file_tree(directory: Path, base_path: str = "") -> List[dict]:
    """Recursively build a file tree structure for a directory.

    Returns a list of tree nodes sorted: directories first, then files.
    """
    if not directory.exists() or not directory.is_dir():
        return []

    items = []
    try:
        entries = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return []

    for entry in entries:
        # Skip hidden files and __pycache__
        if entry.name.startswith(".") or entry.name == "__pycache__":
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

    # The workspace root is the session directory itself
    session_name = workspace.name
    tree = {
        "name": session_name,
        "type": "directory",
        "path": session_name,
        "children": _build_file_tree(workspace, session_name),
    }

    return {"session_id": session_id, "tree": tree}


@router.get("/api/session/{session_id}/file-content")
async def get_file_content(session_id: str, path: str = ""):
    """Get the text content of a file in the session workspace.

    For text files (.md, .txt, .json, .yaml, .html): returns plain text.
    For binary files (.docx, .pdf): returns as file download.
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

    # Security: prevent path traversal
    # path is relative to workspace, strip leading session_id prefix if present
    clean_path = path
    if clean_path.startswith(workspace.name + "/"):
        clean_path = clean_path[len(workspace.name) + 1:]

    file_path = (workspace / clean_path).resolve()

    # Ensure the resolved path is within the workspace
    try:
        file_path.relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

    # Determine how to serve based on extension
    ext = file_path.suffix.lower()
    text_extensions = {".md", ".txt", ".json", ".yaml", ".yml", ".html", ".css", ".js", ".py", ".xml", ".csv"}

    if ext in text_extensions:
        try:
            content = file_path.read_text(encoding="utf-8")
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(content)
        except UnicodeDecodeError:
            # Fall through to binary
            pass

    # Binary files — return as download
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
