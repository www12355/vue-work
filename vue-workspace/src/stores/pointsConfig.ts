import { computed, reactive } from "vue"
import { readPointsConfig, writePointsConfig } from "@/services/pointsConfigService"

/** 可由管理员配置的一次性积分任务 */
export interface PointTask {
  id: string
  name: string
  desc: string
  /** 完成后发放的积分 */
  reward: number
  /** 图标名（取自 @/data/icons 白名单，只存字符串以便持久化） */
  icon: string
  /** 停用后不再展示给用户领取 */
  enabled: boolean
}

export interface PointsConfig {
  /** 每日签到奖励 */
  checkinReward: number
  /** 新用户注册赠送 */
  welcomePoints: number
  tasks: PointTask[]
}

/** 出厂默认：与改造前写死在个人中心里的任务保持一致 */
function seedConfig(): PointsConfig {
  return {
    checkinReward: 2,
    welcomePoints: 20,
    tasks: [
      { id: "profile", name: "完善个人资料", desc: "补全昵称与联系方式", reward: 5, icon: "CheckCircle2", enabled: true },
      { id: "first-gen", name: "完成首次文档生成", desc: "体验任意一个生成模块", reward: 3, icon: "Sparkles", enabled: true },
      { id: "invite", name: "邀请一位好友", desc: "把平台分享给同事", reward: 10, icon: "Gift", enabled: true },
    ],
  }
}

const state = reactive<{ config: PointsConfig }>({
  config: readPointsConfig() ?? seedConfig(),
})

function persist() {
  writePointsConfig(state.config)
}

function uid() {
  return `task_${Math.random().toString(36).slice(2, 9)}`
}

/* ---------------- 只读派生 ---------------- */

export const pointsConfig = computed(() => state.config)

/** 每日签到奖励 */
export const checkinReward = computed(() => state.config.checkinReward)

/** 新用户欢迎积分 */
export const welcomePoints = computed(() => state.config.welcomePoints)

/** 全部任务（含停用，供后台管理） */
export const allTasks = computed(() => state.config.tasks)

/** 启用中的任务（展示给用户领取） */
export const activeTasks = computed(() => state.config.tasks.filter((t) => t.enabled))

/* ---------------- 配置操作 ---------------- */

export interface ConfigResult {
  ok: boolean
  error?: string
}

/** 校验奖励值：必须是 0~10000 之间的有限数 */
function validReward(n: number): boolean {
  return Number.isFinite(n) && n >= 0 && n <= 10000
}

export function updateRules(patch: { checkinReward?: number; welcomePoints?: number }): ConfigResult {
  if (patch.checkinReward !== undefined) {
    if (!validReward(patch.checkinReward)) return { ok: false, error: "签到奖励需为 0~10000 的数字" }
    state.config.checkinReward = patch.checkinReward
  }
  if (patch.welcomePoints !== undefined) {
    if (!validReward(patch.welcomePoints)) return { ok: false, error: "欢迎积分需为 0~10000 的数字" }
    state.config.welcomePoints = patch.welcomePoints
  }
  persist()
  return { ok: true }
}

export function createTask(input: { name: string; desc: string; reward: number; icon: string }): ConfigResult {
  const name = input.name.trim()
  if (!name) return { ok: false, error: "请输入任务名称" }
  if (!validReward(input.reward)) return { ok: false, error: "奖励积分需为 0~10000 的数字" }
  state.config.tasks.push({
    id: uid(),
    name,
    desc: input.desc.trim(),
    reward: input.reward,
    icon: input.icon,
    enabled: true,
  })
  persist()
  return { ok: true }
}

export function updateTask(id: string, patch: Partial<Omit<PointTask, "id">>): ConfigResult {
  const task = state.config.tasks.find((t) => t.id === id)
  if (!task) return { ok: false, error: "任务不存在" }
  if (patch.name !== undefined && !patch.name.trim()) return { ok: false, error: "任务名称不能为空" }
  if (patch.reward !== undefined && !validReward(patch.reward))
    return { ok: false, error: "奖励积分需为 0~10000 的数字" }
  Object.assign(task, patch)
  if (patch.name !== undefined) task.name = patch.name.trim()
  if (patch.desc !== undefined) task.desc = patch.desc.trim()
  persist()
  return { ok: true }
}

export function deleteTask(id: string): ConfigResult {
  const exists = state.config.tasks.some((t) => t.id === id)
  if (!exists) return { ok: false, error: "任务不存在" }
  state.config.tasks = state.config.tasks.filter((t) => t.id !== id)
  persist()
  return { ok: true }
}

/** 恢复出厂积分规则 */
export function resetPointsConfig(): void {
  state.config = seedConfig()
  persist()
}
