/**
 * 合同生成 API — session 生命周期 + 历史记录。
 * 对应后端：AutoGenContract/server (FastAPI, port 8002)
 *
 * 自包含连接配置（参考旧项目 AutoGenUnified 的可靠模式）。
 * target 为空 = Vite 代理模式，请求走同源 /api/contract/* → Vite 转发到 localhost:8002
 */

import { createApiClient, type ApiClient } from "./client"
import type {
  CreateSessionResponse,
  FileInfo,
  SessionDetail,
  SessionListItem,
  SessionListResponse,
  StartPipelineResponse,
  FileTreeNode,
  CacheTreeResponse,
} from "./types"

// ── 合同模块配置（硬编码，不依赖 registry store）──
const contractConfig = {
  enabled: true,
  path: "/api/contract",
  target: "",  // 空 = Vite 代理模式 → http://127.0.0.1:8002
}

/** 创建 API 客户端 */
function contractApi(): ApiClient {
  return createApiClient(contractConfig)
}

/** 合同表单数据（对应后端 ContractGenerateRequest） */
export interface ContractFormData {
  contract_id?: string
  project_name: string
  party_a: string
  party_b: string
  signing_place: string
  signing_date: string
  start_date: string
  duration_years: number
  duration_months: number
  duration_days: number
  /** 后端字段：结束日期与时长文本（前端已算好一并传） */
  end_date?: string
  duration_text?: string
}

/** 创建 session（带表单数据 JSON body） */
export async function createContractSession(
  formData: ContractFormData,
): Promise<CreateSessionResponse> {
  return contractApi().post("/api/session", formData)
}

/**
 * 上传文件到 session。后端 multipart 字段名 `files`（复数）。
 */
export async function uploadContractFile(
  sessionId: string,
  file: File,
  uploadType: "uploads" | "profile" = "uploads",
): Promise<any> {
  const formData = new FormData()
  formData.append("files", file)
  return contractApi().upload(
    `/api/session/${sessionId}/upload?type=${uploadType}`,
    formData,
  )
}

/** 上传多个文件 */
export async function uploadContractFiles(
  sessionId: string,
  files: File[],
  uploadType: "uploads" | "profile" = "uploads",
): Promise<any> {
  const formData = new FormData()
  for (const file of files) {
    formData.append("files", file)
  }
  return contractApi().upload(
    `/api/session/${sessionId}/upload?type=${uploadType}`,
    formData,
  )
}

/** 上传文本到 session（保存为 uploads/user_input.md） */
export async function uploadContractText(
  sessionId: string,
  text: string,
): Promise<any> {
  const formData = new FormData()
  formData.append("text", text)
  return contractApi().upload(`/api/session/${sessionId}/upload`, formData)
}

/** 启动流水线（可选再次传入表单 JSON 覆盖已存数据） */
export async function startContractPipeline(
  sessionId: string,
  formData?: ContractFormData,
): Promise<StartPipelineResponse> {
  return contractApi().post(`/api/session/${sessionId}/start`, formData ?? {})
}

/** 获取 session 详情 */
export async function fetchContractSession(
  sessionId: string,
): Promise<SessionDetail> {
  return contractApi().get(`/api/session/${sessionId}`)
}

/** 获取所有 session（历史列表）。后端返回 { sessions: [...] } */
export async function fetchContractSessions(): Promise<SessionListItem[]> {
  const resp: SessionListResponse | SessionListItem[] = await contractApi().get(
    "/api/sessions",
  )
  if (Array.isArray(resp)) return resp
  return resp?.sessions ?? []
}

/** 删除 session */
export async function deleteContractSession(sessionId: string): Promise<void> {
  return contractApi().del(`/api/session/${sessionId}`)
}

/** 获取 session 文件树。后端返回 { session_id, tree } */
export async function fetchContractCacheTree(
  sessionId: string,
): Promise<FileTreeNode> {
  const resp: CacheTreeResponse | FileTreeNode = await contractApi().get(
    `/api/session/${sessionId}/cache-tree`,
  )
  return (resp as CacheTreeResponse)?.tree ?? (resp as FileTreeNode)
}

/** 读取文件内容 */
export async function fetchContractFileContent(
  sessionId: string,
  filePath: string,
): Promise<string> {
  const resp = await contractApi().get(
    `/api/session/${sessionId}/file-content?path=${encodeURIComponent(filePath)}`,
  )
  return typeof resp === "string" ? resp : resp?.content ?? JSON.stringify(resp)
}

/** 获取输出文件列表 */
export async function fetchContractFiles(
  sessionId: string,
): Promise<FileInfo[]> {
  const resp = await contractApi().get(`/api/session/${sessionId}/files`)
  if (Array.isArray(resp)) return resp
  return resp?.files ?? []
}

/** 构建下载 URL */
export function contractDownloadUrl(
  sessionId: string,
  fileOrUrl: string,
): string {
  if (fileOrUrl.startsWith("/api/") || fileOrUrl.startsWith("http")) {
    return fileOrUrl.startsWith("http")
      ? fileOrUrl
      : contractApi().resolveUrl(fileOrUrl)
  }
  return contractApi().resolveUrl(
    `/api/download/${sessionId}/${encodeURIComponent(fileOrUrl)}`,
  )
}

/** 构建 WebSocket URL */
export function contractWsUrl(sessionId: string): string {
  return `${contractApi().wsBase()}/ws/${sessionId}`
}
