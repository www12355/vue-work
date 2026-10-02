import type { PointsConfig } from "@/stores/pointsConfig"

/**
 * 积分规则配置读写的唯一出入口（客户端原型实现）。
 *
 * 与 pointsService 一致：当前存在浏览器本地，接入真实后端时只需替换
 * 这里的函数体（例如换成 GET/PUT /api/points-config），业务代码无需改动。
 */
const CONFIG_KEY = "aicc-points-config"

export function readPointsConfig(): PointsConfig | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(CONFIG_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PointsConfig
    if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.tasks)) return null
    return parsed
  } catch {
    return null
  }
}

export function writePointsConfig(config: PointsConfig): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(CONFIG_KEY, JSON.stringify(config))
  } catch {
    /* 存储不可用（隐私模式 / 超额）时忽略，页面仍按内存中的配置工作 */
  }
}
