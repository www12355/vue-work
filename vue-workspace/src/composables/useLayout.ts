import { computed } from "vue"
import { getOwner, visibleSections } from "@/stores/registry"

/**
 * 弹窗布局：把「区块显隐 / 排序 / 标题 / 提交按钮文案」交给管理后台配置。
 * 各弹窗实现按 left / right 两列循环渲染区块，因此后台调整顺序即刻生效。
 */
export function useLayout(ownerId: string) {
  const owner = computed(() => getOwner(ownerId))
  const left = computed(() => visibleSections(ownerId, "left"))
  const right = computed(() => visibleSections(ownerId, "right"))

  /** 区块是否可见 */
  const has = (sectionId: string) =>
    !!owner.value?.sections.find((s) => s.id === sectionId && s.visible)

  /** 区块标题（后台可改名） */
  const label = (sectionId: string, fallback = "") =>
    owner.value?.sections.find((s) => s.id === sectionId)?.label || fallback

  const submitLabel = computed(() => owner.value?.submitLabel || "开始生成")

  return { owner, left, right, has, label, submitLabel }
}
