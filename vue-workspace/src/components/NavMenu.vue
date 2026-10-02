<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"
import { ChevronDown, LayoutGrid, Menu } from "lucide-vue-next"
import { goTo, view, type ViewName } from "@/stores/view"

const open = ref(false)
const root = ref<HTMLElement | null>(null)

/* 下拉项：仅保留工作台（个人中心与管理后台已在右上角头像菜单中提供入口） */
const items: { label: string; view: ViewName; icon: typeof Menu; desc: string }[] = [
  { label: "工作台", view: "workspace", icon: LayoutGrid, desc: "AI 应用与生成模块" },
]

function close() {
  open.value = false
}

function onSelect(name: ViewName) {
  close()
  goTo(name)
}

function onClickOutside(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) close()
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") close()
}
onMounted(() => {
  document.addEventListener("click", onClickOutside)
  document.addEventListener("keydown", onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener("click", onClickOutside)
  document.removeEventListener("keydown", onKeydown)
})
</script>

<template>
  <div ref="root" class="relative">
    <!-- 触发按钮 -->
    <button
      type="button"
      class="flex items-center gap-2 font-medium transition-colors"
      :class="open || view === 'workspace' ? 'text-brand' : 'text-foreground/80 hover:text-foreground'"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <Menu class="h-5 w-5" />
      菜单
      <ChevronDown class="h-3.5 w-3.5 transition-transform" :class="open ? 'rotate-180' : ''" />
    </button>

    <!-- 下拉面板 -->
    <div
      v-if="open"
      role="menu"
      class="ws-fade-in absolute left-0 top-9 z-50 w-64 overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-3)]"
    >
      <div class="p-1.5">
        <button
          v-for="item in items"
          :key="item.view"
          type="button"
          role="menuitem"
          class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-muted"
          :class="view === item.view ? 'bg-brand/10' : ''"
          @click="onSelect(item.view)"
        >
          <component
            :is="item.icon"
            class="h-4 w-4 shrink-0"
            :class="view === item.view ? 'text-brand' : 'text-muted-foreground'"
          />
          <span class="min-w-0 flex-1">
            <span
              class="block truncate text-sm font-medium"
              :class="view === item.view ? 'text-brand' : 'text-card-foreground'"
            >
              {{ item.label }}
            </span>
            <span class="block truncate text-xs text-muted-foreground">{{ item.desc }}</span>
          </span>
        </button>
      </div>
    </div>
  </div>
</template>
