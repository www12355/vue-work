import { computed, reactive, ref } from "vue"
import {
  clearSession,
  readAccounts,
  readSession,
  writeAccounts,
  writeSession,
} from "@/services/authService"

export type AccountRole = "admin" | "member"

export interface Account {
  id: string
  /** 登录用户名（唯一） */
  username: string
  /** 密码（原型：明文本地存储；接入后端后应改为服务端校验） */
  password: string
  /** 显示名称 */
  name: string
  role: AccountRole
  /** 停用后无法登录 */
  enabled: boolean
  createdAt: number
}

/** 出厂内置的超级管理员，保证首次一定能进入后台 */
function seedAccounts(): Account[] {
  return [
    {
      id: "acc_admin",
      username: "admin",
      password: "admin123",
      name: "超级管理员",
      role: "admin",
      enabled: true,
      createdAt: Date.now(),
    },
  ]
}

const state = reactive<{ accounts: Account[] }>({
  accounts: readAccounts() ?? seedAccounts(),
})

/** 当前登录用户 id（null 表示未登录） */
const currentId = ref<string | null>(readSession())

/* 首次运行时把内置管理员写入本地，避免刷新后丢失 */
if (!readAccounts()) writeAccounts(state.accounts)

function persist() {
  writeAccounts(state.accounts)
}

function uid() {
  return `acc_${Math.random().toString(36).slice(2, 9)}`
}

/* ---------------- 只读派生 ---------------- */

export const accounts = computed(() => state.accounts)

export const currentUser = computed(() => state.accounts.find((a) => a.id === currentId.value) ?? null)

export const isAuthed = computed(() => currentUser.value !== null)

export const isAdmin = computed(() => currentUser.value?.role === "admin" && currentUser.value.enabled)

export const adminCount = computed(
  () => state.accounts.filter((a) => a.role === "admin" && a.enabled).length,
)

/* ---------------- 会话 ---------------- */

export interface LoginResult {
  ok: boolean
  error?: string
}

/** 管理员登录：校验用户名/密码，仅启用的管理员账号可通过 */
export function login(username: string, password: string): LoginResult {
  const uname = username.trim()
  if (!uname || !password) return { ok: false, error: "请输入用户名和密码" }
  const acc = state.accounts.find((a) => a.username === uname)
  if (!acc || acc.password !== password) return { ok: false, error: "用户名或密码错误" }
  if (!acc.enabled) return { ok: false, error: "该账号已被停用，请联系管理员" }
  if (acc.role !== "admin") return { ok: false, error: "该账号无管理员权限，无法进入后台" }
  currentId.value = acc.id
  writeSession(acc.id)
  return { ok: true }
}

export function logout() {
  currentId.value = null
  clearSession()
}

/* ---------------- 账号管理（CRUD） ---------------- */

export interface AccountResult {
  ok: boolean
  error?: string
}

export function createAccount(input: {
  username: string
  password: string
  name: string
  role: AccountRole
}): AccountResult {
  const username = input.username.trim()
  const name = input.name.trim() || username
  if (!username) return { ok: false, error: "请输入用户名" }
  if (!input.password || input.password.length < 6) return { ok: false, error: "密码至少 6 位" }
  if (state.accounts.some((a) => a.username === username))
    return { ok: false, error: "该用户名已存在" }
  state.accounts.push({
    id: uid(),
    username,
    password: input.password,
    name,
    role: input.role,
    enabled: true,
    createdAt: Date.now(),
  })
  persist()
  return { ok: true }
}

export function updateAccount(
  id: string,
  patch: Partial<Pick<Account, "name" | "role" | "enabled" | "password">>,
): AccountResult {
  const acc = state.accounts.find((a) => a.id === id)
  if (!acc) return { ok: false, error: "账号不存在" }
  /* 不允许把最后一个启用的管理员降级 / 停用，避免锁死后台 */
  const willLoseAdmin =
    (patch.role === "member" || patch.enabled === false) && acc.role === "admin" && acc.enabled
  if (willLoseAdmin && adminCount.value <= 1)
    return { ok: false, error: "至少保留一个启用的管理员账号" }
  if (patch.password !== undefined && patch.password.length > 0 && patch.password.length < 6)
    return { ok: false, error: "密码至少 6 位" }
  Object.assign(acc, patch)
  persist()
  return { ok: true }
}

export function deleteAccount(id: string): AccountResult {
  const acc = state.accounts.find((a) => a.id === id)
  if (!acc) return { ok: false, error: "账号不存在" }
  if (acc.id === currentId.value) return { ok: false, error: "不能删除当前登录的账号" }
  if (acc.role === "admin" && acc.enabled && adminCount.value <= 1)
    return { ok: false, error: "至少保留一个启用的管理员账号" }
  state.accounts = state.accounts.filter((a) => a.id !== id)
  persist()
  return { ok: true }
}
