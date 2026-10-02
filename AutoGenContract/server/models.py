"""
Pydantic models for request/response schemas and WebSocket messages.
v3.0: 5-stage pipeline (文件收集→合同生成→质量审查→工作量统计→文档导出)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Generate Request ─────────────────────────────────────────

class ContractGenerateRequest(BaseModel):
    """Form input data from the frontend contract form."""
    contract_id: str = ""
    project_name: str = ""
    signing_place: str = ""
    signing_date: str = ""          # e.g., "2026年07月10日"
    party_a: str = ""               # 甲方（委托方）
    party_b: str = ""               # 乙方（服务方）
    start_date: str = ""            # e.g., "2026年07月10日"
    duration_years: int = 0
    duration_months: int = 12
    duration_days: int = 0
    end_date: str = ""              # computed end date string
    duration_text: str = ""         # computed duration string
    session_id: Optional[str] = None  # optional preferred session ID


# ── Generate Response ────────────────────────────────────────

class GenerateResponse(BaseModel):
    session_id: str
    message: str
    ws_url: str


# ── Session Info ─────────────────────────────────────────────

class StageInfo(BaseModel):
    id: int
    name: str
    description: str
    status: str = "pending"  # pending | running | completed | failed
    message: str = ""
    detail: Optional[str] = None


class SessionStatus(BaseModel):
    session_id: str
    created_at: str
    current_stage: int = -1
    completed_stages: int = 0
    total_stages: int = 5    # v3.0: 5-stage pipeline
    status: str = "idle"  # idle | running | completed | failed
    stages: List[StageInfo] = Field(default_factory=list)
    error: Optional[str] = None


class FileInfo(BaseModel):
    name: str
    size_kb: float
    download_url: str


class FileListResponse(BaseModel):
    session_id: str
    files: List[FileInfo] = Field(default_factory=list)


# ── WebSocket Messages ───────────────────────────────────────

class WSMessage(BaseModel):
    type: str  # stage_start | stage_complete | stage_failed | echo | pipeline_complete | pipeline_failed | heartbeat
    stage: Optional[StageInfo] = None
    message: str = ""
    detail: Optional[str] = None
    progress_pct: int = 0
    level: str = "info"  # info | warn | error
    timestamp: str = ""


class WSPipelineComplete(BaseModel):
    type: str = "pipeline_complete"
    message: str = ""
    files: List[FileInfo] = Field(default_factory=list)
    progress_pct: int = 100
    timestamp: str = ""


# ── Session Listing ──────────────────────────────────────────

class SessionListItem(BaseModel):
    """Summary of a session for the history list."""
    session_id: str
    created_at: str = ""
    status: str = "idle"          # idle | running | completed | failed
    current_stage: int = -1
    total_stages: int = 5         # v3.0: 5-stage pipeline
    project: str = ""              # project name from config


class SessionListResponse(BaseModel):
    sessions: List[SessionListItem] = Field(default_factory=list)


# ── Upload Models ────────────────────────────────────────────

class UploadFileInfo(BaseModel):
    """Uploaded file metadata."""
    filename: str
    size_kb: float
    modified_at: str = ""


class UploadListResponse(BaseModel):
    session_id: str
    files: List[UploadFileInfo] = Field(default_factory=list)
    count: int = 0


class UploadResponse(BaseModel):
    session_id: str
    message: str
    uploaded: List[str] = Field(default_factory=list)
    skipped: List[str] = Field(default_factory=list)


# ── Stage Definitions (v3.0: 5-stage pipeline) ─────────────

STAGE_DEFINITIONS: List[Dict[str, Any]] = [
    {"id": 0, "name": "文件收集",       "description": "收集用户上传文件、source/参考文档和合同案例，加载为生成上下文"},
    {"id": 1, "name": "合同内容生成",   "description": "AI 一次性生成包含全部13个章节的完整中文服务合同"},
    {"id": 2, "name": "合同质量审查",   "description": "AI 对已生成合同进行完整性、合法性、格式、可操作性审查"},
    {"id": 3, "name": "工作量统计",     "description": "AI 从合同中提取服务项目、交付物、里程碑和工时汇总"},
    {"id": 4, "name": "文档导出",       "description": "生成格式化 DOCX 合同文档、审查报告和工作量统计报告"},
]

STAGE_ICONS = ["📁", "🤖", "🔍", "📊", "📄"]

# Total stages
TOTAL_STAGES = 5

# Phase grouping (for frontend display)
PHASE_DEFINITIONS = [
    {"id": 0, "name": "合同内容生成", "stages": [0, 1], "icon": "📝"},
    {"id": 1, "name": "质量审查",     "stages": [2],    "icon": "🔍"},
    {"id": 2, "name": "工作量汇总",   "stages": [3],    "icon": "📊"},
]
