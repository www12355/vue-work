/**
 * 共享 API 类型 — 从后端 Pydantic models 映射过来。
 * bid / contract 两个后端共用 Session、Stage、WS 消息等基础结构。
 */

/** session 整体状态 */
export type SessionStatus = "idle" | "running" | "completed" | "failed"

/** 单个阶段状态 */
export type StageStatus = "pending" | "running" | "completed" | "failed" | "skipped"

/** 历史列表中的单条 session（GET /api/sessions → { sessions: [...] }） */
export interface SessionListItem {
  session_id: string
  created_at: string
  status: SessionStatus
  current_stage: number
  total_stages: number
  /** 标书后端用 company */
  company?: string
  /** 合同后端用 project */
  project?: string
  /** 已完成阶段数（详情接口才有） */
  completed_stages?: number
}

/** GET /api/sessions 的包裹响应 */
export interface SessionListResponse {
  sessions: SessionListItem[]
}

/** 后端 FileInfo（pipeline_complete.files 与 /files 接口） */
export interface FileInfo {
  name: string
  size_kb?: number
  /** 后端给的相对下载地址，如 /api/download/{id}/xxx.docx */
  download_url: string
}

/** 单个阶段的详细信息（来自 GET /api/session/{id}） */
export interface StageInfo {
  id: number
  name: string
  description: string
  status: StageStatus
  message?: string
  detail?: string
}

/** session 详情（GET /api/session/{id}） */
export interface SessionDetail {
  session_id: string
  created_at: string
  current_stage: number
  completed_stages: number
  total_stages: number
  status: SessionStatus
  stages: StageInfo[]
  error?: string
  output_files?: OutputFile[]
}

/** 输出文件 */
export interface OutputFile {
  name: string
  path: string
  size_kb?: number
}

/** WebSocket 消息类型（对应后端 ws_manager） */
export type WSMessageType =
  | "session_info"
  | "stage_definitions"
  | "stage_start"
  | "stage_complete"
  | "stage_failed"
  | "progress"
  | "echo"
  | "pipeline_complete"
  | "pipeline_failed"
  | "keepalive"
  | "heartbeat"
  | "pong"

/** WebSocket 推送的单条消息 */
export interface WSMessage {
  type: WSMessageType
  /** stage_start/complete/failed 携带的嵌套阶段对象；阶段身份由 stage.id (数字) 标识 */
  stage?: StageInfo
  /** stage_definitions 携带的原始阶段列表 */
  stages?: StageInfo[]
  message?: string
  detail?: string
  /** stage_failed / pipeline_failed 携带的错误 */
  error?: string
  /** pipeline_complete 携带的输出文件（唯一来源） */
  files?: FileInfo[]
  progress_pct?: number
  level?: string
  timestamp?: string
}

/** 文件树节点（cache-tree 的 tree 字段） */
export interface FileTreeNode {
  name: string
  type: "file" | "directory"
  path: string
  size_kb?: number
  children?: FileTreeNode[]
}

/** GET /api/session/{id}/cache-tree 的包裹响应 */
export interface CacheTreeResponse {
  session_id: string
  tree: FileTreeNode
}

/** session 创建响应 */
export interface CreateSessionResponse {
  session_id: string
}

/** pipeline 启动响应 */
export interface StartPipelineResponse {
  session_id: string
  status: string
  message?: string
}

/** 可下载文件 */
export interface DownloadableFile {
  name: string
  path: string
  size_kb?: number
  /** 完整下载 URL */
  url: string
}

/** 流水线阶段定义（前端传入，配置化） */
export interface StageDef {
  id: number
  name: string
  description: string
}

/** 带运行时状态的阶段 */
export interface StageState extends StageDef {
  status: StageStatus
  message: string
  detail?: string
}

/** API 错误 */
export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(`API Error ${status}: ${detail}`)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

/* ─────── pipeline_config 类型 ─────── */

/** 单个方案配置（中标方案或参考方案） */
export interface ProposalConfig {
  id: string
  name: string
  tech_stack_id: string
  team_profile_id: string
  delivery_days: number
  writing_rules: string[]
}

/** 技术栈行 */
export interface TechStackRow {
  key: string
  label: string
  value: string
}

/** 技术栈配置 */
export interface TechStackConfig {
  id: string
  tier: "winning" | "reference"
  name: string
  summary: string
  rows: TechStackRow[]
}

/** 团队角色 */
export interface TeamRole {
  role: string
  count: number
  focus: string
}

/** 团队模板配置 */
export interface TeamProfileConfig {
  id: string
  size: string
  focus: string
  name: string
  summary: string
  total: number
  roles: TeamRole[]
}

/** GET /api/pipeline-config 返回体 */
export interface PipelineConfigResponse {
  pipeline_config_yaml: string
  config: Record<string, any>
  proposal_set: Record<string, ProposalConfig>
  tech_stacks: Record<string, TechStackConfig>
  team_profiles: Record<string, TeamProfileConfig>
}
