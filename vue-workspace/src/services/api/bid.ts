/**
 * 标书生成 API — session 生命周期 + 历史记录。
 * 对应后端：AutoGenBid/server (FastAPI, port 8001)
 *
 * 契约要点（已对照后端源码核对）：
 * - 上传文件字段名为 `files`（复数），query `?type=uploads|profile`
 * - GET /api/sessions 返回 { sessions: [...] }
 * - cache-tree 返回 { session_id, tree }
 * - 输出文件仅通过 WS pipeline_complete.files 交付（FileInfo: name/size_kb/download_url）
 * - session id 字段统一为 session_id
 */

import { apiClient, type ApiClient } from "./client"
import type {
  CreateSessionResponse,
  FileInfo,
  SessionDetail,
  SessionListItem,
  SessionListResponse,
  StartPipelineResponse,
  FileTreeNode,
  CacheTreeResponse,
  PipelineConfigResponse,
} from "./types"

/** 创建 API 客户端（ownerId = "tender"） */
function bid(): ApiClient {
  return apiClient("tender")
}

/** 创建空 session（可选传 company / project_name） */
export async function createBidSession(
  body?: { company?: string; project_name?: string },
): Promise<CreateSessionResponse> {
  return bid().post("/api/session", body ?? {})
}

/**
 * 上传文件到 session。
 * 后端 multipart 字段名为 `files`（复数），一次可传多个。
 */
export async function uploadBidFile(
  sessionId: string,
  file: File,
  uploadType: "uploads" | "profile" = "uploads",
): Promise<any> {
  const formData = new FormData()
  formData.append("files", file)
  return bid().upload(`/api/session/${sessionId}/upload?type=${uploadType}`, formData)
}

/** 上传文本到 session（保存为 uploads/user_input.md） */
export async function uploadBidText(
  sessionId: string,
  text: string,
): Promise<any> {
  const formData = new FormData()
  formData.append("text", text)
  return bid().upload(`/api/session/${sessionId}/upload`, formData)
}

/**
 * 启动流水线。
 * 后端 StartPipelineRequest 字段：task_package_id, wining_enabled,
 * accompany_count, company, pipeline_config_yaml, solution_config。
 */
export async function startBidPipeline(
  sessionId: string,
  config?: Record<string, any>,
): Promise<StartPipelineResponse> {
  return bid().post(`/api/session/${sessionId}/start`, config ?? {})
}

/** 获取单个 session 详情（含阶段列表） */
export async function fetchBidSession(sessionId: string): Promise<SessionDetail> {
  return bid().get(`/api/session/${sessionId}`)
}

/** 获取所有 session（历史列表）。后端返回 { sessions: [...] }，这里解包成数组 */
export async function fetchBidSessions(): Promise<SessionListItem[]> {
  const resp: SessionListResponse | SessionListItem[] = await bid().get("/api/sessions")
  if (Array.isArray(resp)) return resp
  return resp?.sessions ?? []
}

/** 删除 session */
export async function deleteBidSession(sessionId: string): Promise<void> {
  return bid().del(`/api/session/${sessionId}`)
}

/** 获取 session 工作目录文件树。后端返回 { session_id, tree }，这里解包出 tree */
export async function fetchBidCacheTree(sessionId: string): Promise<FileTreeNode> {
  const resp: CacheTreeResponse | FileTreeNode = await bid().get(
    `/api/session/${sessionId}/cache-tree`,
  )
  return (resp as CacheTreeResponse)?.tree ?? (resp as FileTreeNode)
}

/** 读取 session 中某个文件的内容（text/plain 直接返回文本） */
export async function fetchBidFileContent(
  sessionId: string,
  filePath: string,
): Promise<string> {
  const resp = await bid().get(
    `/api/session/${sessionId}/file-content?path=${encodeURIComponent(filePath)}`,
  )
  return typeof resp === "string" ? resp : resp?.content ?? JSON.stringify(resp)
}

/** 获取输出文件列表（{ session_id, files: FileInfo[] }） */
export async function fetchBidFiles(sessionId: string): Promise<FileInfo[]> {
  const resp = await bid().get(`/api/session/${sessionId}/files`)
  if (Array.isArray(resp)) return resp
  return resp?.files ?? []
}

/**
 * 构建下载 URL。
 * 后端 download_url 已是相对路径（如 /api/download/{id}/xxx.docx），
 * 若传入的是完整相对路径则直接拼 base；否则按 /api/download/{id}/{file} 拼。
 */
export function bidDownloadUrl(sessionId: string, fileOrUrl: string): string {
  if (fileOrUrl.startsWith("/api/") || fileOrUrl.startsWith("http")) {
    return fileOrUrl.startsWith("http") ? fileOrUrl : bid().resolveUrl(fileOrUrl)
  }
  return bid().resolveUrl(`/api/download/${sessionId}/${encodeURIComponent(fileOrUrl)}`)
}

/** 构建 WebSocket URL */
export function bidWsUrl(sessionId: string): string {
  return `${bid().wsBase()}/ws/${sessionId}`
}

/** 获取 pipeline 配置（技术栈、团队模板、方案集） */
export async function fetchBidPipelineConfig(): Promise<PipelineConfigResponse> {
  return bid().get("/api/pipeline-config")
}

/** 保存 pipeline 配置（YAML 文本） */
export async function saveBidPipelineConfig(content: string): Promise<{ message: string; path: string }> {
  return bid().post("/api/pipeline-config", { content })
}
