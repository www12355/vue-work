import { computed, reactive } from "vue"
import { currentUser } from "@/stores/auth"
import { readWallets, writeWallets } from "@/services/pointsService"
import { checkinReward, welcomePoints } from "@/stores/pointsConfig"

/** 每日签到奖励积分（由后台「积分任务」配置） */
export const dailyCheckinReward = checkinReward
/** 汇率：1 积分 = 1 美金 */
export const POINT_TO_USD = 1

export type TxType = "welcome" | "checkin" | "task" | "recharge" | "consume" | "adjust"

export interface PointsTx {
  id: string
  type: TxType
  /** 正数表示获得，负数表示消耗 */
  amount: number
  desc: string
  at: number
}

export interface Wallet {
  balance: number
  /** 最近签到日期（YYYY-MM-DD，本地时区） */
  lastCheckIn: string | null
  /** 已领取的一次性任务 id */
  claimedTasks: string[]
  txs: PointsTx[]
}

const state = reactive<{ wallets: Record<string, Wallet> }>({
  wallets: readWallets() ?? {},
})

function persist() {
  writeWallets(state.wallets)
}

function uid() {
  return `tx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
}

/** 本地时区的今天（YYYY-MM-DD），避免用 UTC 造成跨日误差 */
function todayStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function freshWallet(): Wallet {
  const welcome = welcomePoints.value
  return {
    balance: welcome,
    lastCheckIn: null,
    claimedTasks: [],
    txs: [{ id: uid(), type: "welcome", amount: welcome, desc: "新用户欢迎积分", at: Date.now() }],
  }
}

/** 当前钱包归属：登录用户按账号 id，未登录归到体验钱包 */
const walletKey = computed(() => currentUser.value?.id ?? "guest")

/** 确保当前 key 存在钱包并返回（会持久化新建的钱包） */
function ensureWallet(): Wallet {
  const key = walletKey.value
  if (!state.wallets[key]) {
    state.wallets[key] = freshWallet()
    persist()
  }
  return state.wallets[key]
}

/* ---------------- 只读派生 ---------------- */

/** 当前钱包（若尚未创建，返回内存中新建的实例） */
export const wallet = computed<Wallet>(() => state.wallets[walletKey.value] ?? ensureWallet())

/** 积分余额 */
export const balance = computed(() => wallet.value.balance)

/** 余额对应的美金 */
export const balanceUsd = computed(() => wallet.value.balance * POINT_TO_USD)

/** 今日是否可签到 */
export const canCheckIn = computed(() => wallet.value.lastCheckIn !== todayStr())

/** 最近的流水（倒序） */
export const recentTxs = computed(() => [...wallet.value.txs].sort((a, b) => b.at - a.at))

/* ---------------- 操作 ---------------- */

export interface PointsResult {
  ok: boolean
  error?: string
}

/** 每日签到领取积分 */
export function checkIn(): PointsResult {
  const w = ensureWallet()
  const today = todayStr()
  if (w.lastCheckIn === today) return { ok: false, error: "今日已签到，明天再来" }
  const reward = checkinReward.value
  w.lastCheckIn = today
  w.balance += reward
  w.txs.push({
    id: uid(),
    type: "checkin",
    amount: reward,
    desc: "每日签到奖励",
    at: Date.now(),
  })
  persist()
  return { ok: true }
}

/** 领取一次性任务奖励 */
export function claimTask(taskId: string, reward: number, desc: string): PointsResult {
  const w = ensureWallet()
  if (w.claimedTasks.includes(taskId)) return { ok: false, error: "该任务奖励已领取" }
  w.claimedTasks.push(taskId)
  w.balance += reward
  w.txs.push({ id: uid(), type: "task", amount: reward, desc, at: Date.now() })
  persist()
  return { ok: true }
}

export function isTaskClaimed(taskId: string): boolean {
  return wallet.value.claimedTasks.includes(taskId)
}

/** 充值：按美金 1:1 兑换积分，可附带赠送积分 */
export function recharge(usd: number, bonus = 0): PointsResult {
  if (usd <= 0) return { ok: false, error: "请输入有效金额" }
  const w = ensureWallet()
  const gained = usd + bonus
  w.balance += gained
  w.txs.push({
    id: uid(),
    type: "recharge",
    amount: gained,
    desc: bonus > 0 ? `充值 $${usd}（赠 ${bonus} 积分）` : `充值 $${usd}`,
    at: Date.now(),
  })
  persist()
  return { ok: true }
}

/* ---------------- 后台：跨用户钱包 ---------------- */

/** 全部钱包（key 为账号 id），供后台「用户管理」统计与查询 */
export const allWallets = computed(() => state.wallets)

/** 读取指定账号的钱包（不存在时返回 null，避免为未使用积分的账号凭空建号） */
export function walletOf(userId: string): Wallet | null {
  return state.wallets[userId] ?? null
}

/**
 * 管理员手动增减某账号的积分。
 * delta 为正表示补发、为负表示扣减；扣减后余额不允许为负。
 */
export function adminAdjust(userId: string, delta: number, reason: string): PointsResult {
  if (!Number.isFinite(delta) || delta === 0) return { ok: false, error: "请输入非零的调整值" }
  if (!state.wallets[userId]) state.wallets[userId] = freshWallet()
  const w = state.wallets[userId]
  const next = Number((w.balance + delta).toFixed(4))
  if (next < 0) return { ok: false, error: "扣减后余额不能为负" }
  w.balance = next
  w.txs.push({
    id: uid(),
    type: "adjust",
    amount: delta,
    desc: reason.trim() || (delta > 0 ? "管理员补发积分" : "管理员扣减积分"),
    at: Date.now(),
  })
  persist()
  return { ok: true }
}

/** 消耗积分（如生成文档），余额不足则失败 */
export function consume(points: number, desc: string): PointsResult {
  const w = ensureWallet()
  if (w.balance < points) return { ok: false, error: "积分余额不足，请先充值" }
  w.balance = Number((w.balance - points).toFixed(4))
  w.txs.push({ id: uid(), type: "consume", amount: -points, desc, at: Date.now() })
  persist()
  return { ok: true }
}
