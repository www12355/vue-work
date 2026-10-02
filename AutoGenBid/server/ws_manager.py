"""
WebSocket Connection Manager — manages per-session WebSocket connections
and broadcasts progress messages to connected clients.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect

from .models import STAGE_DEFINITIONS, FileInfo, StageInfo


class ConnectionManager:
    """Manages WebSocket connections keyed by session_id.

    Supports multiple connections per session (e.g., multiple browser tabs).
    """

    def __init__(self):
        # {session_id: [WebSocket, ...]}
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, []).append(websocket)

        # Send welcome / session info
        await self._send_json(websocket, {
            "type": "session_info",
            "session_id": session_id,
            "message": "已连接到标书生成服务",
            "timestamp": datetime.now().isoformat(),
        })

        # Send stage definitions so the frontend can initialize its UI
        await self._send_json(websocket, {
            "type": "stage_definitions",
            "stages": STAGE_DEFINITIONS,
            "timestamp": datetime.now().isoformat(),
        })

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket."""
        async with self._lock:
            if session_id in self._connections:
                try:
                    self._connections[session_id].remove(websocket)
                except ValueError:
                    pass
                if not self._connections[session_id]:
                    del self._connections[session_id]

    async def send_progress(self, session_id: str, data: Dict[str, Any]) -> None:
        """Send a progress message to all WebSockets for a session."""
        data.setdefault("timestamp", datetime.now().isoformat())
        await self._broadcast(session_id, data)

    async def send_stage_start(self, session_id: str, stage_id: int, message: str = "", progress_pct: int = 0) -> None:
        """Convenience: send a stage_start message."""
        stage_def = STAGE_DEFINITIONS[stage_id] if 0 <= stage_id < len(STAGE_DEFINITIONS) else {}
        await self.send_progress(session_id, {
            "type": "stage_start",
            "stage": StageInfo(
                id=stage_id,
                name=stage_def.get("name", f"Stage {stage_id}"),
                description=stage_def.get("description", ""),
                status="running",
            ).model_dump(),
            "message": message or f"开始: {stage_def.get('name', f'Stage {stage_id}')}",
            "progress_pct": progress_pct,
        })

    async def send_stage_complete(self, session_id: str, stage_id: int, detail: str = "", progress_pct: int = 0) -> None:
        """Convenience: send a stage_complete message."""
        stage_def = STAGE_DEFINITIONS[stage_id] if 0 <= stage_id < len(STAGE_DEFINITIONS) else {}
        await self.send_progress(session_id, {
            "type": "stage_complete",
            "stage": StageInfo(
                id=stage_id,
                name=stage_def.get("name", f"Stage {stage_id}"),
                description=stage_def.get("description", ""),
                status="completed",
            ).model_dump(),
            "message": f"完成: {stage_def.get('name', f'Stage {stage_id}')}",
            "detail": detail,
            "progress_pct": progress_pct,
        })

    async def send_stage_failed(self, session_id: str, stage_id: int, error: str, progress_pct: int = 0) -> None:
        """Convenience: send a stage_failed message."""
        stage_def = STAGE_DEFINITIONS[stage_id] if 0 <= stage_id < len(STAGE_DEFINITIONS) else {}
        await self.send_progress(session_id, {
            "type": "stage_failed",
            "stage": StageInfo(
                id=stage_id,
                name=stage_def.get("name", f"Stage {stage_id}"),
                description=stage_def.get("description", ""),
                status="failed",
            ).model_dump(),
            "message": f"失败: {stage_def.get('name', f'Stage {stage_id}')}",
            "error": error,
            "progress_pct": progress_pct,
        })

    async def send_echo(self, session_id: str, message: str, level: str = "info") -> None:
        """Convenience: send a log/echo message."""
        await self.send_progress(session_id, {
            "type": "echo",
            "message": message,
            "level": level,
        })

    async def send_pipeline_complete(self, session_id: str, files: List[FileInfo]) -> None:
        """Convenience: send pipeline_complete with file list."""
        await self.send_progress(session_id, {
            "type": "pipeline_complete",
            "message": "🎉 所有阶段已完成！标书文件已生成。",
            "files": [f.model_dump() for f in files],
            "progress_pct": 100,
        })

    async def send_pipeline_failed(self, session_id: str, error: str) -> None:
        """Send pipeline_failed — retries up to 3 times to ensure delivery."""
        data = {
            "type": "pipeline_failed",
            "message": "流水线执行失败",
            "error": error,
            "progress_pct": 0,
            "timestamp": datetime.now().isoformat(),
        }
        # Retry up to 3 times with short delay — the client MUST see this
        for attempt in range(3):
            if not self.has_connections(session_id):
                break
            await self._broadcast(session_id, data)
            if attempt < 2:
                await asyncio.sleep(0.5)

    async def send_keepalive(self, session_id: str, message: str = "") -> None:
        """Send a keepalive ping to prevent proxy/router idle timeout.

        Called from the pipeline thread during long-running stages
        (Claude API calls) to keep the WebSocket from appearing dead.
        """
        await self._broadcast(session_id, {
            "type": "keepalive",
            "message": message or "正在处理中...",
            "timestamp": datetime.now().isoformat(),
        })

    # ── Internal ─────────────────────────────────────────────

    async def _broadcast(self, session_id: str, data: Dict[str, Any]) -> None:
        """Send data to all WebSockets for a session, removing dead connections."""
        if session_id not in self._connections:
            return

        dead: List[WebSocket] = []
        message = json.dumps(data, ensure_ascii=False)

        for ws in self._connections.get(session_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        if dead:
            async with self._lock:
                for ws in dead:
                    try:
                        self._connections.get(session_id, []).remove(ws)
                    except ValueError:
                        pass

    @staticmethod
    async def _send_json(ws: WebSocket, data: Dict[str, Any]) -> None:
        """Send a JSON message to a single WebSocket."""
        try:
            await ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    async def start_heartbeat(self, session_id: str, interval: int = 15) -> None:
        """Start a heartbeat loop for a session (runs as background task)."""
        while session_id in self._connections:
            await asyncio.sleep(interval)
            await self._broadcast(session_id, {
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat(),
            })

    def has_connections(self, session_id: str) -> bool:
        """Check if any WebSocket clients are connected for a session."""
        return bool(self._connections.get(session_id))


# Global singleton
ws_manager = ConnectionManager()
