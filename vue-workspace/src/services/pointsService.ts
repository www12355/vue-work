import type { Wallet } from "@/stores/points"

/**
 * 积分钱包读写的唯一出入口（客户端原型实现）。
 *
 * 说明：当前应用是纯前端 SPA，积分余额、签到与流水均存在浏览器本地，
 * 按账号 id 隔离（未登录时归到 guest 体验钱包）。接入真实后端时只需替换
 * 这里的函数体（例如换成 GET/PUT /api/wallet），业务代码无需改动。
 */
const WALLETS_KEY = "aicc-wallets"

export function readWallets(): Record<string, Wallet> | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(WALLETS_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Record<string, Wallet>
    return parsed && typeof parsed === "object" ? parsed : null
  } catch {
    return null
  }
}

export function writeWallets(wallets: Record<string, Wallet>): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(WALLETS_KEY, JSON.stringify(wallets))
  } catch {
    /* 存储不可用（隐私模式 / 超额）时忽略，页面仍按内存中的数据工作 */
  }
}
