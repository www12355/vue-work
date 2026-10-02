/**
 * 后端连接健康检查 — 周期性轮询 /api/health 端点。
 *
 * 每个内置模块（tender/contract/minutes等）独立检查，
 * 使用硬编码模块列表（不依赖 registry store，参考旧项目可靠模式）。
 *
 * 用法：
 *   const health = useBackendHealth()
 *   health.start()       // 启动周期性轮询（5s 间隔）
 *   health.checkNow()    // 立即执行一次检查
 *
 *   // 响应式状态：
 *   health.statuses      // Record<string, { ok, latencyMs, error, checkedAt }>
 *   health.allOk         // 所有模块都正常时为 true
 *   health.checking      // 正在检查中
 */

import { ref, reactive, onBeforeUnmount } from "vue"

export interface BackendStatus {
  ok: boolean
  latencyMs: number | null
  error: string | null
  checkedAt: number | null
}

/** 内置模块健康检查配置（硬编码，无忧 registry store） */
interface HealthCheckModule {
  id: string
  path: string
  target: string
}

const BUILTIN_MODULES: HealthCheckModule[] = [
  { id: "tender",   target: "http://127.0.0.1:8001", path: "/api/tender" },
  { id: "contract", target: "http://127.0.0.1:8002", path: "/api/contract" },
  { id: "minutes",  target: "http://localhost:4002",  path: "/api/minutes" },
]

const DEFAULT_INTERVAL_MS = 5_000
const REQUEST_TIMEOUT_MS = 3_000

export function useBackendHealth() {
  const statuses = reactive<Record<string, BackendStatus>>({})
  const checking = ref(false)
  const allOk = ref(false)

  let timer: ReturnType<typeof setInterval> | null = null
  let aborted = false

  /** 使用硬编码模块列表初始化状态 */
  function initStatuses() {
    for (const mod of BUILTIN_MODULES) {
      if (!statuses[mod.id]) {
        statuses[mod.id] = { ok: false, latencyMs: null, error: null, checkedAt: null }
      }
    }
  }

  async function checkModule(mod: HealthCheckModule): Promise<void> {
    // 优先直连 target 做健康检查（绕过 Vite 代理，最可靠）
    const url = `${mod.target.replace(/\/+$/, "")}/api/health`

    const started = Date.now()
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

      const resp = await fetch(url, {
        signal: controller.signal,
        cache: "no-store",
      })
      clearTimeout(timeoutId)

      const latencyMs = Date.now() - started
      statuses[mod.id] = {
        ok: resp.ok,
        latencyMs,
        error: resp.ok ? null : `HTTP ${resp.status}`,
        checkedAt: Date.now(),
      }
    } catch (e: any) {
      statuses[mod.id] = {
        ok: false,
        latencyMs: Date.now() - started,
        error: e.name === "AbortError" ? "请求超时" : (e.message || "未知错误"),
        checkedAt: Date.now(),
      }
    }
  }

  async function checkAll() {
    initStatuses()
    checking.value = true
    await Promise.allSettled(BUILTIN_MODULES.map((mod) => checkModule(mod)))
    allOk.value = Object.values(statuses).every((s) => s.ok)
    checking.value = false
  }

  function start(intervalMs = DEFAULT_INTERVAL_MS) {
    stop()
    aborted = false
    checkAll()
    timer = setInterval(() => {
      if (aborted) return
      checkAll()
    }, intervalMs)
  }

  function stop() {
    aborted = true
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function checkNow() {
    return checkAll()
  }

  onBeforeUnmount(() => stop())

  return {
    statuses,
    allOk,
    checking,
    checkNow,
    start,
    stop,
  }
}
