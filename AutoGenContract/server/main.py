"""
AutoGenContract Server — FastAPI Application Entry Point.

Provides:
- JSON-based contract generation request
- WebSocket real-time progress streaming
- Session-isolated workspaces with UUID
- File download for generated contract DOCX
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes_contract import router as contract_router
from .routes_ws import router as ws_router
from .routes_download import router as download_router
from .routes_profile import router as profile_router
from .routes_upload import router as upload_router
from .session_manager import session_manager


# ── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Startup: clean expired sessions
    cleaned = session_manager.cleanup_expired()
    if cleaned:
        print(f"[Startup] Cleaned {cleaned} expired sessions")

    # Start periodic cleanup task
    cleanup_task = asyncio.create_task(_periodic_cleanup())

    print(f"[Startup] AutoGenContract Server ready")
    print(f"  Workspaces: {session_manager._registry_path.parent}")

    yield

    # Shutdown: cancel cleanup
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    print("[Shutdown] AutoGenContract Server stopped")


async def _periodic_cleanup(interval_minutes: int = 30):
    """Periodically clean up expired sessions."""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            cleaned = session_manager.cleanup_expired()
            if cleaned:
                print(f"[Cleanup] Removed {cleaned} expired sessions")
        except Exception as e:
            print(f"[Cleanup] Error: {e}")


# ── App Factory ──────────────────────────────────────────────

app = FastAPI(
    title="AutoGenContract — 合同智能生成服务",
    description="填写合同信息，AI 自动生成合同文档，实时进度推送",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow localhost + LAN access
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|\[::1\])(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(contract_router)
app.include_router(ws_router)
app.include_router(download_router)
app.include_router(profile_router)
app.include_router(upload_router)

# ── Serve frontend static files in production ──
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "AutoGenContract" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


# ── CLI Entry Point ──────────────────────────────────────────

_SERVER_DIR = Path(__file__).resolve().parent           # server/
_PROJECT_ROOT = _SERVER_DIR.parent                      # 自动合同生成/
_WATCH_DIRS = [
    str(_SERVER_DIR),                                   # server/
    str(_PROJECT_ROOT / "src"),                         # src/
    str(_PROJECT_ROOT / "skills"),                      # skills/
]


def main():
    """Run the server via uvicorn."""
    import os
    import uvicorn

    # Change CWD to server/ so uvicorn doesn't watch .cache/
    os.chdir(str(_SERVER_DIR))

    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        reload_dirs=_WATCH_DIRS,
        log_level="info",
    )


if __name__ == "__main__":
    main()
