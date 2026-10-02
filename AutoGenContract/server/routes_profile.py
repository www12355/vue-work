"""
Profile Routes — User reference document management.

Provides CRUD API for profile/ directory:
  - GET  /api/profile              List all uploaded documents
  - POST /api/profile/upload       Upload one or more documents
  - DELETE /api/profile/{filename} Delete a document
  - GET  /api/profile/{filename}   Download/preview a document
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()

# ── Path resolution ──────────────────────────────────────────
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent  # 自动合同生成/
PROFILE_DIR = PROJECT_ROOT / "profile"

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {
    ".docx", ".doc", ".pdf", ".txt", ".md",
    ".pptx", ".ppt", ".xlsx", ".xls",
    ".jpg", ".jpeg", ".png", ".bmp",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# ── Ensure profile/ exists ───────────────────────────────────
def _ensure_profile_dir():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)


# ── Safe filename ────────────────────────────────────────────
def _safe_filename(name: str) -> str:
    """Remove path traversal characters, keep Chinese characters."""
    # Remove any path separators
    name = name.replace("\\", "").replace("/", "")
    # Remove leading dots (hidden files)
    name = name.lstrip(".")
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        raise HTTPException(status_code=400, detail="无效的文件名")
    return name


# ── Models ───────────────────────────────────────────────────

class ProfileFileInfo(BaseModel):
    filename: str
    size_kb: float
    modified_at: str


class ProfileListResponse(BaseModel):
    files: List[ProfileFileInfo]
    count: int


class ProfileUploadResponse(BaseModel):
    message: str
    uploaded: List[str]
    skipped: List[str] = []


# ── Routes ───────────────────────────────────────────────────

@router.get("/api/profile", response_model=ProfileListResponse)
async def list_profile_files():
    """List all documents in the profile/ directory."""
    _ensure_profile_dir()

    files: List[ProfileFileInfo] = []
    for f in sorted(PROFILE_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file() and not f.name.startswith("."):
            stat = f.stat()
            files.append(ProfileFileInfo(
                filename=f.name,
                size_kb=round(stat.st_size / 1024, 1),
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            ))

    return ProfileListResponse(files=files, count=len(files))


@router.post("/api/profile/upload", response_model=ProfileUploadResponse)
async def upload_profile_files(files: List[UploadFile] = File(...)):
    """Upload one or more reference documents to profile/."""
    _ensure_profile_dir()

    uploaded = []
    skipped = []

    for file in files:
        if not file.filename:
            skipped.append("(empty filename)")
            continue

        safe_name = _safe_filename(file.filename)
        ext = Path(safe_name).suffix.lower()

        # Validate extension
        if ext not in ALLOWED_EXTENSIONS:
            skipped.append(f"{safe_name} (不支持的文件类型: {ext})")
            continue

        # Validate file size by reading content
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            skipped.append(f"{safe_name} (文件过大: {len(content) / 1024 / 1024:.1f}MB > 50MB)")
            continue

        # Save to profile/
        dest = PROFILE_DIR / safe_name

        # If file exists, add version suffix
        if dest.exists():
            stem = Path(safe_name).stem
            counter = 1
            while dest.exists():
                dest = PROFILE_DIR / f"{stem}_{counter}{ext}"
                counter += 1

        dest.write_bytes(content)
        uploaded.append(dest.name)

    return ProfileUploadResponse(
        message=f"成功上传 {len(uploaded)} 个文件" + (f"，跳过 {len(skipped)} 个" if skipped else ""),
        uploaded=uploaded,
        skipped=skipped,
    )


@router.delete("/api/profile/{filename:path}")
async def delete_profile_file(filename: str):
    """Delete a document from the profile/ directory."""
    _ensure_profile_dir()

    safe_name = _safe_filename(filename)
    file_path = PROFILE_DIR / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_name}")

    # Security: ensure the resolved path is inside PROFILE_DIR
    try:
        file_path.resolve().relative_to(PROFILE_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="不允许访问该路径")

    try:
        file_path.unlink()
        return {"message": f"文件已删除: {safe_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.get("/api/profile/{filename:path}")
async def download_profile_file(filename: str):
    """Download or preview a document from the profile/ directory."""
    _ensure_profile_dir()

    safe_name = _safe_filename(filename)
    file_path = PROFILE_DIR / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_name}")

    # Security check
    try:
        file_path.resolve().relative_to(PROFILE_DIR.resolve())
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
