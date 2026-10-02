/**
 * 工作台共享类型与常量。
 * 功能模块、组合规则、弹窗布局的「数据」全部来自配置中心（@/stores/registry），
 * 这里只保留与交互相关的类型与视觉常量。
 */

/** 功能标识：内置模块为固定 id，后台新增模块为自动生成的 id */
export type AppId = string

/** 停靠到主卡片时展示的元数据 */
export type DockedApp = {
  title: string
  desc: string
  image: string
  imageAlt: string
  tags: string[]
}

/** 拖拽状态：null 表示当前没有拖拽 */
export type DragState = {
  app: AppId
  dx: number
  dy: number
  overDrop: boolean
} | null

/** 悬停触发组合所需的时长（毫秒） */
export const COMBO_HOLD_MS = 5000

/** 功能卡右下角挖角尺寸 */
export const NOTCH = "68px"
