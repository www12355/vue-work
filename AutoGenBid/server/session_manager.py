"""
Session Manager — UUID-based session isolation with workspace directories.

Each session gets an isolated workspace under `workspaces/sessions/{uuid}/`.
Pattern aligned with 合同网页 project for consistent sandbox design.

Directory layout per session:
    workspaces/sessions/{uuid}/
        uploads/          # Core bid files (main analysis target)
        profile/          # Reference files (analyzed first)
        templates/        # Extracted template (if found in bid doc)
        output/           # Final deliverables
        .cache/           # Pipeline intermediate artifacts
        pipeline_config.yaml
"""

from __future__ import annotations

import json
import shutil
import uuid
import os
from urllib.parse import quote
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import UserUploadConfig, FileInfo

# Resolve the server root and workspace root
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent  # 标书自动生成/
WORKSPACES_DIR = PROJECT_ROOT / "workspaces"
SESSIONS_DIR = WORKSPACES_DIR / "sessions"

# Default session TTL: 24 hours
DEFAULT_SESSION_TTL_SECONDS = 24 * 60 * 60

# Global templates directory
GLOBAL_TEMPLATES_DIR = PROJECT_ROOT / "templates"

# Subdirectories to create per session
SESSION_SUBDIRS = ["uploads", "profile", "templates", "output", ".cache"]


class SessionManager:
    """Manages isolated session workspaces keyed by session UUID."""

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._registry_path = WORKSPACES_DIR / "sessions_index.json"
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._load_registry()

    # ── Registry persistence ─────────────────────────────────

    def _load_registry(self) -> None:
        if self._registry_path.exists():
            try:
                self._registry = json.loads(self._registry_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                self._registry = {}

    def _save_registry(self) -> None:
        self._registry_path.write_text(
            json.dumps(self._registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Template copying ─────────────────────────────────────

    def _copy_templates(self, workspace: Path) -> None:
        """Copy global templates into the session workspace templates/ directory.

        Only copies files that exist in the global templates directory.
        Session-scoped copy ensures template isolation between sessions.
        """
        templates_dir = workspace / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)

        if GLOBAL_TEMPLATES_DIR.exists() and GLOBAL_TEMPLATES_DIR.is_dir():
            for item in GLOBAL_TEMPLATES_DIR.iterdir():
                if item.is_file():
                    dest = templates_dir / item.name
                    if not dest.exists():
                        shutil.copy2(str(item), str(dest))

    # ── Session lifecycle ────────────────────────────────────

    def create_session(
        self,
        user_config: Optional[UserUploadConfig] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Create a new session with an isolated workspace.

        If session_id is provided and valid/available, it will be used.
        Otherwise a random 12-char hex ID is generated.

        Returns the session_id string.
        """
        if session_id:
            # Validate: only allow alphanumeric, dash, underscore, max 32 chars
            import re
            if not re.match(r'^[a-zA-Z0-9_\-]{1,32}$', session_id):
                session_id = None  # fall back to random
            elif session_id in self._registry:
                session_id = None  # already in use, fall back to random

        if not session_id:
            session_id = uuid.uuid4().hex[:12]  # 12-char short UUID

        workspace = SESSIONS_DIR / session_id
        workspace.mkdir(parents=True, exist_ok=True)

        # Create standard subdirectories
        for subdir in SESSION_SUBDIRS:
            (workspace / subdir).mkdir(exist_ok=True)

        # Copy global templates into session workspace
        self._copy_templates(workspace)

        # Save user config
        if user_config:
            config_path = workspace / "user_config.json"
            config_path.write_text(
                user_config.model_dump_json(indent=2),
                encoding="utf-8",
            )

        # Record in registry
        now = datetime.now().isoformat()
        self._registry[session_id] = {
            "session_id": session_id,
            "created_at": now,
            "last_active": now,
            "status": "idle",
            "current_stage": -1,
            "has_template": None,  # None=unknown, True/False after Stage 3
            "user_config": user_config.model_dump() if user_config else {},
        }
        self._save_registry()

        return session_id

    def get_workspace(self, session_id: str) -> Path:
        """Return the workspace directory for a session."""
        workspace = SESSIONS_DIR / session_id
        if not workspace.exists():
            # Fallback: check old location (backward compat)
            old_workspace = WORKSPACES_DIR / session_id
            if old_workspace.exists() and old_workspace.is_dir():
                return old_workspace
            raise FileNotFoundError(f"Session {session_id} not found")
        return workspace

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return session metadata or None if not found."""
        return self._registry.get(session_id)

    def update_session(self, session_id: str, **kwargs) -> None:
        """Update session metadata fields."""
        if session_id in self._registry:
            self._registry[session_id].update(kwargs)
            self._registry[session_id]["last_active"] = datetime.now().isoformat()
            self._save_registry()

    def touch(self, session_id: str) -> None:
        """Update last_active timestamp."""
        if session_id in self._registry:
            self._registry[session_id]["last_active"] = datetime.now().isoformat()
            self._save_registry()

    # ── File discovery ───────────────────────────────────────

    def list_output_files(self, session_id: str) -> List[FileInfo]:
        """List downloadable output files for a session.

        Scans output/ directory first, then .cache/11_final/,
        then .cache/07_bids/ for any generated docx files.
        """
        try:
            workspace = self.get_workspace(session_id)
        except FileNotFoundError:
            return []

        files: List[FileInfo] = []
        seen_names: set = set()

        # Priority 1: output/ directory (final deliverables)
        output_dir = workspace / "output"
        if output_dir.exists():
            for f in output_dir.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    size_kb = f.stat().st_size / 1024
                    rel_path = f"output/{f.name}"
                    files.append(FileInfo(
                        name=f.name,
                        size_kb=round(size_kb, 1),
                        download_url=f"/api/download/{session_id}?file={quote(rel_path, safe='')}",
                    ))
                    seen_names.add(f.name)

        # Priority 2: .cache/11_final/ (merged final files)
        final_dir = workspace / ".cache" / "11_final"
        if final_dir.exists():
            for f in final_dir.glob("*.docx"):
                if f.name not in seen_names:
                    size_kb = f.stat().st_size / 1024
                    rel_path = f".cache/11_final/{f.name}"
                    files.append(FileInfo(
                        name=f.name,
                        size_kb=round(size_kb, 1),
                        download_url=f"/api/download/{session_id}?file={quote(rel_path, safe='')}",
                    ))
                    seen_names.add(f.name)

        # Priority 3: Project root for exported files (backward compat)
        for f in PROJECT_ROOT.glob("*_完整.docx"):
            if f.name not in seen_names:
                size_kb = f.stat().st_size / 1024
                files.append(FileInfo(
                    name=f.name,
                    size_kb=round(size_kb, 1),
                    download_url=f"/api/download/{session_id}/{quote(f.name)}",
                ))
                seen_names.add(f.name)

        # Priority 4: .cache/07_bids/ for individual bid docx files
        bids_dir = workspace / ".cache" / "07_bids"
        if bids_dir.exists():
            for bid_dir in bids_dir.iterdir():
                if bid_dir.is_dir():
                    for f in bid_dir.glob("*.docx"):
                        if f.name not in seen_names:
                            size_kb = f.stat().st_size / 1024
                            rel_path = str(f.relative_to(workspace)).replace("\\", "/")
                            files.append(FileInfo(
                                name=f.name,
                                size_kb=round(size_kb, 1),
                                download_url=f"/api/download/{session_id}?file={quote(rel_path, safe='')}",
                            ))
                            seen_names.add(f.name)

        return files

    def get_file_path(self, session_id: str, filename: str) -> Optional[Path]:
        """Resolve a filename to an actual file path within the session workspace.

        Search order: output/ → .cache/11_final/ → project root → recursive .cache/
        """
        try:
            workspace = self.get_workspace(session_id)
        except FileNotFoundError:
            return None

        candidates = [
            workspace / "output" / filename,
            workspace / ".cache" / "11_final" / filename,
            PROJECT_ROOT / filename,
            workspace / filename,
        ]

        # Also search recursively in .cache
        cache_dir = workspace / ".cache"
        if cache_dir.exists():
            for root, dirs, filenames in os.walk(str(cache_dir)):
                for fn in filenames:
                    if fn == filename:
                        candidates.append(Path(root) / fn)

        for path in candidates:
            if path.exists() and path.is_file():
                return path

        return None

    # ── Cleanup ──────────────────────────────────────────────

    def is_expired(self, session_id: str) -> bool:
        """Check if a session has exceeded its TTL."""
        info = self._registry.get(session_id)
        if not info:
            return True
        try:
            created = datetime.fromisoformat(info["created_at"])
            return datetime.now() - created > timedelta(seconds=self.ttl_seconds)
        except (ValueError, KeyError):
            return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session's workspace and registry entry."""
        workspace = SESSIONS_DIR / session_id
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

        # Also clean old workspace location if exists
        old_workspace = WORKSPACES_DIR / session_id
        if old_workspace.exists() and old_workspace.is_dir():
            shutil.rmtree(old_workspace, ignore_errors=True)

        removed = self._registry.pop(session_id, None) is not None
        self._save_registry()
        return removed

    def cleanup_expired(self) -> int:
        """Delete all expired sessions. Returns count of cleaned sessions."""
        expired = [sid for sid in self._registry if self.is_expired(sid)]
        for sid in expired:
            self.delete_session(sid)
        return len(expired)

    # ── Cache tree exploration ──────────────────────────────

    def get_cache_tree(self, session_id: str) -> dict:
        """Walk workspace recursively and return a nested dict tree."""
        try:
            workspace = self.get_workspace(session_id)
        except FileNotFoundError:
            return {"name": session_id, "type": "directory", "path": session_id, "children": []}

        return self._build_tree_node(workspace, workspace, workspace)

    def _build_tree_node(self, root: Path, current: Path, workspace: Path) -> dict:
        """Recursively build a tree node, rooted at workspace for relative paths."""
        rel = str(current.relative_to(workspace)).replace("\\", "/")
        if current.is_dir():
            children = []
            try:
                entries = sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                entries = []
            for entry in entries:
                if entry.name.startswith(".") and entry.name != ".cache":
                    continue
                if self._should_hide_tree_entry(entry, workspace):
                    continue
                child = self._build_tree_node(root, entry, workspace)
                if child.get("type") == "directory" and not child.get("children"):
                    continue
                children.append(child)
            return {"name": current.name, "type": "directory", "path": rel, "children": children}
        else:
            try:
                size_kb = round(current.stat().st_size / 1024, 1)
            except OSError:
                size_kb = 0
            return {"name": current.name, "type": "file", "path": rel, "size_kb": size_kb}

    @staticmethod
    def _should_hide_tree_entry(path: Path, workspace: Path) -> bool:
        """Filter noisy/internal files from the right-side file explorer."""
        name = path.name.lower()
        try:
            rel = str(path.relative_to(workspace)).replace("\\", "/")
        except ValueError:
            rel = path.name

        if path.is_file():
            if path.suffix.lower() in {".txt", ".log"}:
                return True
            if name in {"pipeline_config.yaml", "user_config.json"} and "/" not in rel:
                return True
            if "claude" in name or name in {"pipeline.log"}:
                return True
        return False

    def get_cache_file_path(self, session_id: str, relative_path: str) -> Optional[Path]:
        """Safely resolve a relative path within the session workspace.

        Returns the absolute Path if within workspace, or None if traversal detected.
        """
        try:
            workspace = self.get_workspace(session_id)
        except FileNotFoundError:
            return None

        # Normalize: strip leading slashes, handle ..
        clean = relative_path.lstrip("/").lstrip("\\")
        candidate = (workspace / clean).resolve()
        workspace_resolved = workspace.resolve()
        try:
            candidate.relative_to(workspace_resolved)
        except ValueError:
            return None  # path traversal attempt
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    # ── Session listing ──────────────────────────────────────

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions (active + expired) sorted by creation time desc."""
        sessions = list(self._registry.values())
        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return sessions

    @property
    def active_count(self) -> int:
        return len(self._registry)


# Global singleton
session_manager = SessionManager()
