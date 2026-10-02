"""
Session Manager — UUID-based session isolation with workspace directories.

Each contract generation request gets a unique session. All artifacts are
stored in an isolated workspace under `workspaces/sessions/{uuid}/`.
"""

from __future__ import annotations

import json
import shutil
import uuid
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import FileInfo

# Resolve the server root and project root
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent  # 自动合同生成/

# Session workspace storage
SESSIONS_DIR = PROJECT_ROOT / "workspaces" / "sessions"

# Default session TTL: 24 hours
DEFAULT_SESSION_TTL_SECONDS = 24 * 60 * 60

# Template files to copy into each session workspace
TEMPLATES_SRC = PROJECT_ROOT / "templates"
TEMPLATE_FILES = ["contract_template.md"]


def _copy_templates(workspace: Path):
    """Copy template reference files into the session workspace."""
    dest_dir = workspace / "templates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for fname in TEMPLATE_FILES:
        src = TEMPLATES_SRC / fname
        if src.exists():
            import shutil
            shutil.copy2(str(src), str(dest_dir / fname))


class SessionManager:
    """Manages isolated user workspaces keyed by session UUID.

    Sessions stored under workspaces/sessions/{uuid}/,
    registry at workspaces/sessions_index.json.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._registry_path = SESSIONS_DIR.parent / "sessions_index.json"
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

    # ── Session lifecycle ────────────────────────────────────

    def create_session(self, form_data: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None) -> str:
        """Create a new session with a unique UUID workspace.

        If session_id is provided and valid, it will be used.
        Otherwise a random 12-char hex ID is generated.
        """
        if session_id:
            import re
            if not re.match(r'^[a-zA-Z0-9_\-]{1,32}$', session_id):
                session_id = None
            elif session_id in self._registry:
                session_id = None

        if not session_id:
            session_id = uuid.uuid4().hex[:12]

        workspace = SESSIONS_DIR / session_id
        workspace.mkdir(parents=True, exist_ok=True)

        # Save form data as config
        if form_data:
            config_path = workspace / "contract_config.json"
            config_path.write_text(
                json.dumps(form_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # Copy template to session workspace
        _copy_templates(workspace)

        # Record in registry
        now = datetime.now().isoformat()
        project_name = form_data.get("project_name", "") if form_data else ""
        self._registry[session_id] = {
            "session_id": session_id,
            "created_at": now,
            "last_active": now,
            "status": "idle",
            "current_stage": -1,
            "project": project_name,
            "form_data": form_data or {},
        }
        self._save_registry()

        return session_id

    def get_workspace(self, session_id: str) -> Path:
        """Return the workspace directory for a session."""
        workspace = SESSIONS_DIR / session_id
        if workspace.exists():
            return workspace

        raise FileNotFoundError(f"Session {session_id} not found")

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

        Scans 04_output/ subdirectory first, then workspace root,
        for .docx, .md, and .json output files.
        """
        workspace = self.get_workspace(session_id)
        files: List[FileInfo] = []

        output_dir = workspace / "04_output"
        search_dirs = [output_dir] if output_dir.exists() else []
        search_dirs.append(workspace)

        seen = set()
        for search_dir in search_dirs:
            for pattern in ["*.docx", "*.md", "*.json"]:
                for f in search_dir.glob(pattern):
                    if f.name in seen:
                        continue
                    seen.add(f.name)
                    size_kb = f.stat().st_size / 1024
                    files.append(FileInfo(
                        name=f.name,
                        size_kb=round(size_kb, 1),
                        download_url=f"/api/download/{session_id}/{f.name}",
                    ))

        return files

    def get_file_path(self, session_id: str, filename: str) -> Optional[Path]:
        """Resolve a filename to an actual file path within the session workspace.

        Searches 04_output/ subdirectory first, then workspace root, then recursive.
        """
        workspace = self.get_workspace(session_id)

        candidates = [
            workspace / "04_output" / filename,
            workspace / filename,
        ]

        for root, dirs, filenames in os.walk(str(workspace)):
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

        removed = self._registry.pop(session_id, None) is not None
        self._save_registry()
        return removed

    def cleanup_expired(self) -> int:
        """Delete all expired sessions. Returns count of cleaned sessions."""
        expired = [sid for sid in self._registry if self.is_expired(sid)]
        for sid in expired:
            self.delete_session(sid)
        return len(expired)

    @property
    def active_count(self) -> int:
        return len(self._registry)

    # ── Stage Directory Helpers ──────────────────────────────

    def get_stage_cache_dir(self, session_id: str, stage_id: int) -> Path:
        """Return the cache directory for a specific pipeline stage.

        Stage directories:
            0 → 01_config/
            1 → 02_examples/
            2 → 03_contract/
            3 → 04_output/
        """
        stage_names = {
            0: "01_config",
            1: "02_examples",
            2: "03_contract",
            3: "04_output",
        }
        dir_name = stage_names.get(stage_id, f"{stage_id:02d}_stage")
        workspace = self.get_workspace(session_id)
        stage_dir = workspace / dir_name
        stage_dir.mkdir(parents=True, exist_ok=True)
        return stage_dir

    def get_session_cache_dir(self, session_id: str) -> Path:
        """Return the session's root workspace directory."""
        return self.get_workspace(session_id)


# Global singleton
session_manager = SessionManager()
