"""Pydantic models for request/response schemas and WebSocket messages."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    session_id: str
    message: str
    ws_url: str


class StageInfo(BaseModel):
    id: int
    name: str
    description: str
    status: str = "pending"
    message: str = ""
    detail: Optional[str] = None


class SessionStatus(BaseModel):
    session_id: str
    created_at: str
    current_stage: int = -1
    completed_stages: int = 0
    total_stages: int = 11
    status: str = "idle"
    stages: List[StageInfo] = Field(default_factory=list)
    error: Optional[str] = None


class FileInfo(BaseModel):
    name: str
    size_kb: float
    download_url: str


class FileListResponse(BaseModel):
    session_id: str
    files: List[FileInfo] = Field(default_factory=list)


class WSMessage(BaseModel):
    type: str
    stage: Optional[StageInfo] = None
    message: str = ""
    detail: Optional[str] = None
    progress_pct: int = 0
    level: str = "info"
    timestamp: str = ""


class WSPipelineComplete(BaseModel):
    type: str = "pipeline_complete"
    message: str = ""
    files: List[FileInfo] = Field(default_factory=list)
    progress_pct: int = 100
    timestamp: str = ""


class CacheTreeNode(BaseModel):
    name: str
    type: str
    path: str
    size_kb: Optional[float] = None
    children: Optional[List["CacheTreeNode"]] = None


CacheTreeNode.model_rebuild()


class CacheTreeResponse(BaseModel):
    session_id: str
    tree: CacheTreeNode


class UserUploadConfig(BaseModel):
    """Deserialized from the JSON part of the multipart upload."""

    name: str = ""
    company: str = ""
    address: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    task_package_id: Optional[int] = None
    pipeline_config_yaml: str = ""


class SessionListItem(BaseModel):
    """Summary of a session for the history list."""

    session_id: str
    created_at: str = ""
    status: str = "idle"
    current_stage: int = -1
    total_stages: int = 11
    company: str = ""


class SessionListResponse(BaseModel):
    sessions: List[SessionListItem] = Field(default_factory=list)


STAGE_DEFINITIONS: List[Dict[str, Any]] = [
    {"id": 0, "name": "文档解析", "description": "解析核心标书 DOCX 文件，提取文本、表格、图片和章节结构"},
    {"id": 1, "name": "标书总结", "description": "基于解析结果生成标书摘要、项目概况、技术要点和评标规则"},
    {"id": 2, "name": "需求提取", "description": "从标书内容中提取结构化需求清单"},
    {"id": 3, "name": "技术章节定位", "description": "用 regex 定位技术方案标号并生成章节编号映射"},
    {"id": 4, "name": "默认格式准备", "description": "准备默认 DOCX 导出格式"},
    {"id": 5, "name": "投标策略生成", "description": "按 pipeline_config.yaml 生成中标和参考方案策略"},
    {"id": 6, "name": "技术方案生成", "description": "AI 生成全部技术方案内容"},
    {"id": 7, "name": "模板拼接跳过", "description": "当前版本跳过格式模板拼接，仅保留独立文档导出"},
    {"id": 8, "name": "DOCX 导出", "description": "将 Markdown 技术方案导出为 DOCX 文件"},
    {"id": 9, "name": "应答表生成", "description": "生成技术一对一应答表"},
    {"id": 10, "name": "独立文档导出", "description": "导出技术方案和技术一对一应答表"},
]

STAGE_ICONS = ["DOC", "SUM", "REQ", "MAP", "FMT", "CFG", "GEN", "TMP", "DOCX", "TAB", "OUT"]
