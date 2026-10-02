import { CONFIG_VERSION, type WorkspaceConfig } from "@/data/registry-defaults"

/**
 * 配置读写的唯一出入口。
 *
 * 当前实现把管理后台的配置存在浏览器本地，前端可独立运行、无需后端。
 * 接入真实服务时只需替换下面三个函数体（例如换成 GET/PUT /api/workspace-config），
 * 其它业务代码无需改动。
 */
const STORAGE_KEY = "aicc-workspace-config"

export function readConfig(): WorkspaceConfig | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as WorkspaceConfig
    /* 版本不一致时丢弃旧配置，回落到出厂默认值，避免结构错位 */
    if (!parsed || parsed.version !== CONFIG_VERSION) return null
    if (!Array.isArray(parsed.modules) || !Array.isArray(parsed.combos)) return null
    return parsed
  } catch {
    return null
  }
}

export function writeConfig(config: WorkspaceConfig): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  } catch {
    /* 存储不可用（隐私模式 / 超额）时忽略，页面仍按内存中的配置工作 */
  }
}

export function removeConfig(): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* 同上 */
  }
}
