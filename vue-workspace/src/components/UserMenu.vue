<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ChevronDown, LogIn, LogOut, Moon, Settings, Sun, User } from "lucide-vue-next"
import { currentUser, isAdmin, isAuthed, logout } from "@/stores/auth"
import { balance } from "@/stores/points"
import { theme, toggleTheme } from "@/stores/theme"
import { goTo, view } from "@/stores/view"

const open = ref(false)
const root = ref<HTMLElement | null>(null)

/** 头像展示：已登录取名字首字，未登录显示访客图标位 */
const initial = computed(() => currentUser.value?.name?.trim().charAt(0) || "客")
const displayName = computed(() => currentUser.value?.name ?? "未登录")
const roleLabel = computed(() => {
  if (!isAuthed.value) return "游客 · 未登录"
  return isAdmin.value ? "管理员" : "普通成员"
})

function close() {
  open.value = false
}

function onClickOutside(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) close()
}
onMounted(() => document.addEventListener("click", onClickOutside))
onBeforeUnmount(() => document.removeEventListener("click", onClickOutside))

/* 个人中心入口 */
function onProfile() {
  close()
  goTo("profile")
}

/* 管理后台入口：已在后台则返回工作台；管理员则进后台；否则去登录 */
function onAdmin() {
  close()
  if (view.value === "admin") goTo("workspace")
  else if (isAdmin.value) goTo("admin")
  else goTo("login")
}

function onAuth() {
  close()
  if (isAuthed.value) {
    logout()
    goTo("workspace")
  } else {
    goTo("login")
  }
}
</script>

<template>
  <div ref="root" class="relative">
    <!-- 头像触发按钮 -->
    <button
      type="button"
      class="flex h-10 items-center gap-2 rounded-full border border-border bg-card pl-1 pr-2.5 transition-colors hover:bg-muted"
      :aria-expanded="open"
      aria-haspopup="menu"
      aria-label="账户菜单"
      @click="open = !open"
    >
      <span
        class="flex h-8 w-8 items-center justify-center rounded-full bg-brand text-sm font-bold text-brand-foreground"
      >
        {{ initial }}
      </span>
      <ChevronDown class="h-3.5 w-3.5 text-muted-foreground transition-transform" :class="open ? '' : 'rotate-180'" />
    </button>

    <!-- 上拉菜单（头像在侧栏底部，向上展开避免被视口裁剪） -->
    <div
      v-if="open"
      role="menu"
      class="ws-fade-in absolute bottom-12 left-0 z-50 w-64 overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-3)]"
    >
      <!-- 用户信息 -->
      <div class="flex items-center gap-3 border-b border-border px-4 py-3.5">
        <span
          class="flex h-10 w-10 items-center justify-center rounded-full bg-brand text-base font-bold text-brand-foreground"
        >
          {{ initial }}
        </span>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold text-card-foreground">{{ displayName }}</p>
          <p class="truncate text-xs text-muted-foreground">{{ roleLabel }}</p>
        </div>
      </div>

      <!-- 菜单项 -->
      <div class="p-1.5">
        <!-- 个人中心 -->
        <button
          type="button"
          role="menuitem"
          class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-card-foreground transition-colors hover:bg-muted"
          @click="onProfile"
        >
          <User class="h-4 w-4 text-muted-foreground" />
          <span class="flex-1 text-left">个人中心</span>
          <span class="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-semibold text-brand">
            {{ balance.toFixed(0) }} 积分
          </span>
        </button>

        <!-- 管理后台 -->
        <button
          type="button"
          role="menuitem"
          class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-card-foreground transition-colors hover:bg-muted"
          @click="onAdmin"
        >
          <Settings class="h-4 w-4 text-muted-foreground" />
          <span class="flex-1 text-left">{{ view === "admin" ? "返回工作台" : "管理后台" }}</span>
        </button>

        <!-- 主题切换 -->
        <button
          type="button"
          role="menuitem"
          class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-card-foreground transition-colors hover:bg-muted"
          @click="toggleTheme"
        >
          <Moon v-if="theme === 'light'" class="h-4 w-4 text-muted-foreground" />
          <Sun v-else class="h-4 w-4 text-muted-foreground" />
          <span class="flex-1 text-left">主题</span>
          <span class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {{ theme === "light" ? "浅色" : "深色" }}
          </span>
        </button>
      </div>

      <!-- 登录 / 退出 -->
      <div class="border-t border-border p-1.5">
        <button
          type="button"
          role="menuitem"
          class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors"
          :class="isAuthed ? 'text-destructive hover:bg-destructive/10' : 'text-card-foreground hover:bg-muted'"
          @click="onAuth"
        >
          <LogOut v-if="isAuthed" class="h-4 w-4" />
          <LogIn v-else class="h-4 w-4 text-muted-foreground" />
          <span class="flex-1 text-left">{{ isAuthed ? "退出登录" : "登录" }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
