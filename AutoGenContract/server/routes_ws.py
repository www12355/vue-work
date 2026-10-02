"""
WebSocket Route — real-time progress streaming endpoint.
"""

from __future__ import annotations

import json
import asyncio
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .ws_manager import ws_manager
from .session_manager import session_manager

router = APIRouter()

HEARTBEAT_INTERVAL = 15       # seconds between server→client heartbeats


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time pipeline progress."""
    # Validate session exists
    session_info = session_manager.get_session_info(session_id)
    if not session_info:
        await websocket.close(code=4004, reason="Session not found")
        return

    await ws_manager.connect(session_id, websocket)
    session_manager.touch(session_id)

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_INTERVAL,
                )

                # Handle client ping
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": datetime.now().isoformat(),
                        }, ensure_ascii=False))
                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # No client message within heartbeat interval — send keepalive
                try:
                    await websocket.send_text(json.dumps({
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat(),
                    }, ensure_ascii=False))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Unexpected error for session {session_id}: {e}")
    finally:
        await ws_manager.disconnect(session_id, websocket)
