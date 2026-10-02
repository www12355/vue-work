<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { LayoutGrid, MessageSquarePlus, Zap, Wand2, Search, Menu, X } from "lucide-vue-next"
import { goTo, view, type ViewName } from "@/stores/view"
import UserMenu from "@/components/UserMenu.vue"
import type { BackendStatus } from "@/composables/useBackendHealth"

const props = defineProps<{
  healthStatuses?: Record<string, BackendStatus>
  healthAllOk?: boolean
  healthChecking?: boolean
}>()

const mobileOpen = ref(false)

function isActive(v: ViewName) {
  return view.value === v
}

/** 后端状态 → 显示用的模块列表 */
const backendModules = computed(() => {
  const statuses = props.healthStatuses
  if (!statuses) return []
  return Object.entries(statuses).map(([id, s]) => ({ id, ...s }))
})

/** 整体状态描述 */
const overallLabel = computed(() => {
  if (props.healthChecking && backendModules.value.length === 0) return "检测中…"
  if (!backendModules.value.length) return "无后端"
  const allUp = backendModules.value.every((m) => m.ok)
  const someUp = backendModules.value.some((m) => m.ok)
  if (allUp) return "服务正常"
  if (someUp) return "部分异常"
  return "服务断开"
})

function statusDotClass(ok: boolean, checkedAt: number | null) {
  if (checkedAt === null) return "bg-muted-foreground/40"
  return ok ? "bg-emerald-500" : "bg-red-500"
}

/** 模块名称映射（对应 registry 中的 id） */
const moduleLabel: Record<string, string> = {
  tender: "标书",
  contract: "合同",
  minutes: "纪要",
}

function closeMobile() {
  mobileOpen.value = false
}

function onNavClick(v: ViewName) {
  goTo(v)
  closeMobile()
}

let root: HTMLElement | null = null
function onClickOutside(e: MouseEvent) {
  if (root && !root.contains(e.target as Node)) closeMobile()
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") closeMobile()
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
  <div ref="root">
    <!-- 移动端汉堡按钮 -->
    <button
      class="fixed left-4 top-4 z-50 flex h-10 w-10 items-center justify-center rounded-xl bg-card shadow-sm lg:hidden"
      aria-label="打开导航菜单"
      @click="mobileOpen = !mobileOpen"
    >
      <Menu v-if="!mobileOpen" class="h-5 w-5 text-foreground" />
      <X v-else class="h-5 w-5 text-foreground" />
    </button>

    <!-- 移动端遮罩 -->
    <div
      v-if="mobileOpen"
      class="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm lg:hidden"
      @click="closeMobile"
    />

    <!-- 侧边栏本体 -->
    <aside
      class="fixed left-0 top-0 z-40 flex h-full w-52 flex-col bg-background/90 backdrop-blur-sm transition-transform duration-300 lg:translate-x-0"
      :class="mobileOpen ? 'translate-x-0' : '-translate-x-full'"
    >
      <!-- Logo 区域 -->
      <div class="flex items-center gap-3 px-4 py-5">
        <button
          class="flex items-center gap-3"
          aria-label="返回工作台首页"
          @click="onNavClick('workspace')"
        >
          <div class="relative flex h-10 w-10 items-center justify-center rounded-xl border-[3px] border-foreground">
            <span
              class="absolute -bottom-1.5 left-2 h-2.5 w-2.5 rotate-45 border-b-[3px] border-l-[3px] border-foreground bg-background"
            />
            <span class="text-lg font-extrabold italic text-brand">X</span>
          </div>
          <div class="text-lg font-extrabold leading-none tracking-tight text-foreground">AICC</div>
        </button>
      </div>

      <!-- 搜索框 -->
      <div class="px-2 pb-3">
        <div class="flex items-center gap-2 rounded-xl bg-muted px-3 py-2">
          <Search class="h-4 w-4 text-muted-foreground shrink-0" />
          <input
            type="text"
            placeholder="搜索..."
            class="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none border-none min-w-0"
          />
        </div>
      </div>

      <!-- 导航区域 -->
      <nav class="flex flex-col gap-0.5 px-2 py-1">
        <!-- 工作台 -->
        <button
          class="flex items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-colors"
          :class="isActive('workspace') ? 'bg-brand/10 text-brand' : 'text-foreground/70 hover:bg-muted hover:text-foreground'"
          @click="onNavClick('workspace')"
        >
          <LayoutGrid class="h-4 w-4" />
          工作台
        </button>

        <!-- 新建对话 -->
        <button
          class="flex items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-colors"
          :class="isActive('chat') ? 'bg-brand/10 text-brand' : 'text-foreground/70 hover:bg-muted hover:text-foreground'"
          @click="onNavClick('chat')"
        >
          <MessageSquarePlus class="h-4 w-4" />
          新建对话
        </button>

        <!-- 自动任务 -->
        <button
          class="flex items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-colors"
          :class="isActive('tasks') ? 'bg-brand/10 text-brand' : 'text-foreground/70 hover:bg-muted hover:text-foreground'"
          @click="onNavClick('tasks')"
        >
          <Zap class="h-4 w-4" />
          自动任务
        </button>

        <!-- 技能广场 -->
        <button
          class="flex items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-colors"
          :class="isActive('skills') ? 'bg-brand/10 text-brand' : 'text-foreground/70 hover:bg-muted hover:text-foreground'"
          @click="onNavClick('skills')"
        >
          <Wand2 class="h-4 w-4" />
          技能广场
        </button>
      </nav>

      <!-- 底部区域 -->
      <div class="mt-auto flex flex-col gap-3 px-2 py-4">
        <!-- 后端连接状态指示器 -->
        <div
          v-if="backendModules.length"
          class="rounded-xl bg-card px-3 py-2"
          :title="backendModules.map(m => `${moduleLabel[m.id] || m.id}: ${m.ok ? '已连接' : m.error || '未连接'}`).join('\n')"
        >
          <span class="text-[10px] font-medium text-muted-foreground">{{ overallLabel }}</span>
          <div class="mt-1.5 flex gap-1.5">
            <span
              v-for="m in backendModules"
              :key="m.id"
              class="h-2 w-2 rounded-full transition-colors duration-300"
              :class="[statusDotClass(m.ok, m.checkedAt), healthChecking ? 'animate-pulse' : '']"
            />
          </div>
        </div>

        <!-- 头像下拉菜单 -->
        <div class="px-1">
          <UserMenu />
        </div>
      </div>
    </aside>
  </div>
</template>
