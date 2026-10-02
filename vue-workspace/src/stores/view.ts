import { ref } from "vue"

export type ViewName =
  | "workspace"
  | "admin"
  | "login"
  | "news"
  | "resources"
  | "devices"
  | "profile"
  | "history"
  | "chat"
  | "tasks"
  | "skills"

/**
 * 当前页面（单页切换，无需引入路由依赖）：
 * - workspace：工作台首页（对应导航「菜单」）
 * - login / admin：管理员登录 / 管理后台
 * - news / resources / devices：新闻动态 / 资源中心 / 设备工具（待开发占位页）
 * - profile：个人中心（积分账户 / 签到 / 任务 / 充值 / 计费）
 * - history：历史记录页面
 */
export const view = ref<ViewName>("workspace")

/** 历史记录模块类型：tender（标书）或 contract（合同） */
export const historyModule = ref<"tender" | "contract">("tender")

export function goTo(name: ViewName) {
  view.value = name
  if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" })
}

/** 跳转到历史记录页面 */
export function goToHistory(module: "tender" | "contract" = "tender") {
  historyModule.value = module
  view.value = "history"
}

/** 从历史记录页面返回工作台 */
export function goBackToWorkspace() {
  view.value = "workspace"
}
