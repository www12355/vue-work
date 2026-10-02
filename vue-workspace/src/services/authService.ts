import type { Account } from "@/stores/auth"

/**
 * 账号与会话读写的唯一出入口（客户端原型实现）。
 *
 * 说明：当前应用是纯前端 SPA，账号、密码、会话均存在浏览器本地，
 * 这属于原型级鉴权，并非真实安全边界。接入真实后端时只需替换这里的
 * 函数体（例如换成 POST /api/login、GET/PUT /api/accounts），业务代码无需改动。
 */
const ACCOUNTS_KEY = "aicc-accounts"
const SESSION_KEY = "aicc-session"

export function readAccounts(): Account[] | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(ACCOUNTS_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Account[]
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

export function writeAccounts(accounts: Account[]): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts))
  } catch {
    /* 存储不可用（隐私模式 / 超额）时忽略，页面仍按内存中的数据工作 */
  }
}

export function readSession(): string | null {
  if (typeof window === "undefined") return null
  try {
    return window.localStorage.getItem(SESSION_KEY)
  } catch {
    return null
  }
}

export function writeSession(accountId: string): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(SESSION_KEY, accountId)
  } catch {
    /* 同上 */
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.removeItem(SESSION_KEY)
  } catch {
    /* 同上 */
  }
}
