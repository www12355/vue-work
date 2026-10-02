/**
 * 基础 HTTP 客户端 — fetch 封装。
 *
 * 两种用法：
 *   1. createApiClient(config) — 直接传入配置，不依赖 registry store（推荐，旧项目可靠模式）
 *   2. apiClient(ownerId)      — 从 registry store 读取配置（兼容现有其他模块）
 *
 * 两种连接模式：
 *   1. Vite 代理模式（开发环境）：target 为空，所有请求发往同源，
 *      路径前自动拼接 pathPrefix（如 /api/contract），由 Vite 代理到后端。
 *   2. 直连模式：target 非空，直接 fetch 到后端。
 *
 * 后端不可达时自动抛 ApiError，调用方 catch 后可降级到 mock 行为。
 */

import { getModule } from "@/stores/registry"
import { ApiError } from "./types"

const DEFAULT_TIMEOUT_MS = 30_000

// ═══════════════════════════════════════════════════════════════
// 模式一：createApiClient(config) — 纯配置驱动，不依赖 registry
// ═══════════════════════════════════════════════════════════════

/** 模块 API 配置（纯数据，不依赖 registry store） */
export interface ModuleApiConfig {
  enabled: boolean
  path: string       // 如 "/api/contract"
  target: string     // 空字符串 = 代理模式，非空 = 直连模式
}

/**
 * 根据模块配置解析 base URL 与 pathPrefix。
 * - 直连模式（target 非空）：base = "http://localhost:8002"，pathPrefix = ""
 * - 代理模式（target 为空）：base = ""，pathPrefix = "/api/contract"
 */
function resolveFromConfig(config: ModuleApiConfig): { base: string; pathPrefix: string } {
  if (!config.enabled) {
    return { base: "", pathPrefix: "" }
  }
  const target = config.target.trim()
  const pathPrefix = config.path.trim()

  if (target) {
    // 直连模式：target 已包含协议+主机+端口
    return { base: target.replace(/\/+$/, ""), pathPrefix: "" }
  }

  // 代理模式：target 为空，请求发往同源，路径前拼接 path 前缀
  return { base: "", pathPrefix: pathPrefix.startsWith("/") ? pathPrefix : `/${pathPrefix}` }
}

// ═══════════════════════════════════════════════════════════════
// 模式二：apiClient(ownerId) — 从 registry store 读取（兼容旧代码）
// ═══════════════════════════════════════════════════════════════

/**
 * 根据模块 id 读取其 api.target 与 api.path。
 * 返回 { base, pathPrefix }：
 * - 代理模式（开发环境）：pathPrefix = "/api/tender"，base = ""（发往当前页面同源，由 Vite proxy 转发）
 * - 直连模式（生产环境 或 path 为空）：pathPrefix = ""，base = target
 * - 未启用：抛出 ApiError，完全阻止请求
 */
function resolveBaseUrl(ownerId: string): { base: string; pathPrefix: string } {
  const mod = getModule(ownerId)

  // 代理未启用：立即阻止，不允许任何请求通过
  if (!mod?.api?.enabled) {
    throw new ApiError(0, "代理未启用，请在管理后台「接口代理」中启用该模块并设置后端地址")
  }

  const target = mod.api.target.trim()
  const path = mod.api.path.trim()

  // 必须至少配置 path 或 target 之一
  if (!path && !target) {
    throw new ApiError(0, "后端地址未配置，请在管理后台「接口代理」中设置 path 或 target")
  }

  // 生产环境无 Vite 代理服务器，必须直连后端
  if (import.meta.env.PROD) {
    const base = target || path // 生产环境优先使用 target，否则用 path 作为兜底
    return { base: base.replace(/\/+$/, ""), pathPrefix: "" }
  }

  if (path) {
    // Vite 代理模式（开发环境）：请求发往同源 + pathPrefix，Vite 代理转发到 target
    return { base: "", pathPrefix: path.startsWith("/") ? path : `/${path}` }
  }

  // 直连模式：没有 path 但有 target → 直接发往后端
  return { base: target.replace(/\/+$/, ""), pathPrefix: "" }
}


/** 超时 fetch 包装 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit & { timeout?: number },
): Promise<Response> {
  const { timeout = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
    })
    return response
  } finally {
    clearTimeout(timer)
  }
}

/** 统一解析响应：JSON/文本 → 解析值；二进制（docx/pdf/图片等）→ Blob 交给调用方 */
async function handleResponse(resp: Response): Promise<any> {
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const body = JSON.parse(await resp.text())
      detail = body.detail || body.message || detail
    } catch {
      /* 无法解析响应体时使用默认错误信息 */
    }
    throw new ApiError(resp.status, detail)
  }

  const contentType = resp.headers.get("content-type") ?? ""
  const isBinary =
    contentType.startsWith("application/") &&
    !contentType.includes("json") &&
    !contentType.includes("javascript")

  if (isBinary) {
    return resp.blob()
  }

  const text = await resp.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export interface ApiClient {
  get(path: string, signal?: AbortSignal): Promise<any>
  post(path: string, body?: any, signal?: AbortSignal): Promise<any>
  del(path: string, signal?: AbortSignal): Promise<any>
  /** 带 FormData 的上传请求（不设 Content-Type，让浏览器自动加 boundary） */
  upload(path: string, formData: FormData, signal?: AbortSignal): Promise<any>
  /** 拼接后的完整 URL，用于 WebSocket / 直接下载等场景 */
  resolveUrl(path: string): string
  /** 从 http://target 推导 ws://target，代理模式下推导出 ws://当前页面host/pathPrefix */
  wsBase(): string
}

// ═══════════════════════════════════════════════════════════════
// Factory 函数
// ═══════════════════════════════════════════════════════════════

/**
 * 方式一：纯配置创建 API 客户端（推荐，参考旧项目 AutoGenUnified 的可靠模式）。
 * 不依赖 registry store，不受管理后台配置影响。
 *
 * @example
 *   const api = createApiClient({ enabled: true, path: "/api/contract", target: "" })
 *   const data = await api.get("/api/session")
 */
export function createApiClient(config: ModuleApiConfig): ApiClient {
  const { base, pathPrefix } = resolveFromConfig(config)

  function resolveUrl(path: string): string {
    const p = path.startsWith("/") ? path : `/${path}`
    return `${base}${pathPrefix}${p}`
  }

  function ensureEnabled(): void {
    if (!config.enabled) {
      throw new ApiError(0, "后端地址未配置")
    }
  }

  return {
    resolveUrl,
    wsBase() {
      ensureEnabled()
      if (base) {
        // 直连模式：http → ws
        return base.replace(/^http/, "ws")
      }
      // 代理模式：构造相对路径 WebSocket URL，Vite 代理会处理 ws 升级
      const proto = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss" : "ws"
      const host = typeof window !== "undefined" ? window.location.host : "localhost:5174"
      return `${proto}://${host}${pathPrefix}`
    },

    async get(path: string, signal?: AbortSignal) {
      ensureEnabled()
      const resp = await fetchWithTimeout(resolveUrl(path), { signal })
      return handleResponse(resp)
    },

    async post(path: string, body?: any, signal?: AbortSignal) {
      ensureEnabled()
      const isFormData = body instanceof FormData
      const resp = await fetchWithTimeout(resolveUrl(path), {
        method: "POST",
        headers: isFormData ? {} : { "Content-Type": "application/json" },
        body: isFormData ? body : body ? JSON.stringify(body) : undefined,
        signal,
      })
      return handleResponse(resp)
    },

    async del(path: string, signal?: AbortSignal) {
      ensureEnabled()
      const resp = await fetchWithTimeout(resolveUrl(path), {
        method: "DELETE",
        signal,
      })
      return handleResponse(resp)
    },

    async upload(path: string, formData: FormData, signal?: AbortSignal) {
      ensureEnabled()
      const resp = await fetchWithTimeout(resolveUrl(path), {
        method: "POST",
        body: formData,
        signal,
      })
      return handleResponse(resp)
    },
  }
}

/**
 * 方式二：从 registry store 读取模块配置创建 API 客户端（兼容现有代码）。
 * 受管理后台「接口代理」配置影响。
 *
 * @example
 *   const api = apiClient("tender")
 *   const data = await api.get("/api/sessions")
 */
export function apiClient(ownerId: string): ApiClient {
  const mod = getModule(ownerId)
  const { base, pathPrefix } = resolveBaseUrl(ownerId)

  function resolveUrl(path: string): string {
    const p = path.startsWith("/") ? path : `/${path}`
    return `${base}${pathPrefix}${p}`
  }

  function ensureBase(): void {
    if (!mod?.api?.enabled) {
      throw new ApiError(0, "后端地址未配置，请在管理后台「接口代理」中设置")
    }
  }

  return {
    resolveUrl,
    wsBase() {
      ensureBase()
      if (base) {
        // 直连模式：http → ws
        return base.replace(/^http/, "ws")
      }
      // 代理模式：构造相对路径 WebSocket URL，Vite 代理会处理 ws 升级
      const proto = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss" : "ws"
      const host = typeof window !== "undefined" ? window.location.host : "localhost:5174"
      return `${proto}://${host}${pathPrefix}`
    },

    async get(path: string, signal?: AbortSignal) {
      ensureBase()
      const resp = await fetchWithTimeout(resolveUrl(path), { signal })
      return handleResponse(resp)
    },

    async post(path: string, body?: any, signal?: AbortSignal) {
      ensureBase()
      const isFormData = body instanceof FormData
      const resp = await fetchWithTimeout(resolveUrl(path), {
        method: "POST",
        headers: isFormData ? {} : { "Content-Type": "application/json" },
        body: isFormData ? body : body ? JSON.stringify(body) : undefined,
        signal,
      })
      return handleResponse(resp)
    },

    async del(path: string, signal?: AbortSignal) {
      ensureBase()
      const resp = await fetchWithTimeout(resolveUrl(path), {
        method: "DELETE",
        signal,
      })
      return handleResponse(resp)
    },

    async upload(path: string, formData: FormData, signal?: AbortSignal) {
      ensureBase()
      const resp = await fetchWithTimeout(resolveUrl(path), {
        method: "POST",
        body: formData,
        signal,
      })
      return handleResponse(resp)
    },
  }
}
