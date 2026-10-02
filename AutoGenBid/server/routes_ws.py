"""
WebSocket Route — real-time progress streaming endpoint.

Keeps the connection alive with frequent heartbeats and resilient
error handling so pipeline failures never cause silent disconnects.
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
CLIENT_PING_TIMEOUT = 45      # if client doesn't ping within this, send heartbeat anyway


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time pipeline progress.

    Clients connect here after uploading to receive stage-by-stage progress.
    Heartbeats are sent every 15s to prevent proxy/router idle-timeout kills.
    """
    # Validate session exists
    session_info = session_manager.get_session_info(session_id)
    if not session_info:
        await websocket.close(code=4004, reason="Session not found")
        return

    await ws_manager.connect(session_id, websocket)
    session_manager.touch(session_id)

    last_client_msg = asyncio.get_event_loop().time()

    try:
        while True:
            try:
                # Wait for client message with timeout
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_INTERVAL,
                )
                last_client_msg = asyncio.get_event_loop().time()

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
                    # Connection is dead; exit cleanly
                    break

    except WebSocketDisconnect:
        # Client explicitly disconnected — normal
        pass
    except Exception as e:
        # Unexpected error — log but don't crash
        print(f"[WS] Unexpected error for session {session_id}: {e}")
    finally:
        await ws_manager.disconnect(session_id, websocket)
