<script setup lang="ts">
import { computed, ref } from "vue"
import {
  Blocks,
  ChevronLeft,
  Home,
  Layers,
  LayoutDashboard,
  LayoutTemplate,
  ListChecks,
  LogOut,
  Moon,
  PanelLeft,
  RotateCcw,
  Sun,
  Users,
  Wallet,
} from "lucide-vue-next"
import OverviewPanel from "@/components/admin/OverviewPanel.vue"
import ModulesPanel from "@/components/admin/ModulesPanel.vue"
import CombosPanel from "@/components/admin/CombosPanel.vue"
import LayoutPanel from "@/components/admin/LayoutPanel.vue"
import UsersPanel from "@/components/admin/UsersPanel.vue"
import TasksPanel from "@/components/admin/TasksPanel.vue"
import AccountsPanel from "@/components/admin/AccountsPanel.vue"
import { resetConfig } from "@/stores/registry"
import { currentUser, logout } from "@/stores/auth"
import { theme, toggleTheme } from "@/stores/theme"
import { goTo } from "@/stores/view"

const NAV = [
  { key: "overview", label: "综合管理", icon: LayoutDashboard, desc: "平台整体运行概览与快捷入口" },
  { key: "modules", label: "模块管理", icon: Blocks, desc: "维护功能模块与待开发项" },
  { key: "combos", label: "组合规则", icon: Layers, desc: "配置模块间的组合流程" },
  { key: "layout", label: "弹窗布局", icon: LayoutTemplate, desc: "调整弹窗功能区块与布局" },
  { key: "users", label: "用户管理", icon: Wallet, desc: "查看用户积分资产与流水" },
  { key: "tasks", label: "积分任务", icon: ListChecks, desc: "配置签到规则与积分任务" },
  { key: "accounts", label: "账号管理", icon: Users, desc: "管理后台账号与权限" },
] as const

type NavKey = (typeof NAV)[number]["key"]

const active = ref<NavKey>("overview")
const collapsed = ref(false)
const confirming = ref(false)

const activeMeta = computed(() => NAV.find((n) => n.key === active.value)!)

const initial = computed(() => currentUser.value?.name?.trim().charAt(0) || "管")

function reset() {
  resetConfig()
  confirming.value = false
}

function signOut() {
  logout()
  goTo("workspace")
}
</script>

<template>
  <div class="flex min-h-screen w-full bg-background">
    <!-- 左侧可收纳导航栏（拟态风格，与内容区一致） -->
    <aside
      class="sticky top-0 flex h-screen shrink-0 flex-col gap-3 bg-background p-3 transition-[width] duration-200"
      :class="collapsed ? 'w-[76px]' : 'w-64'"
    >
      <!-- 品牌 + 收纳按钮 -->
      <div class="ios-card flex h-16 items-center" :class="collapsed ? 'justify-center px-0' : 'gap-2.5 px-3.5'">
        <!-- 收起态：宽度仅够放一个元素，故品牌图标本身即为展开按钮 -->
        <button
          v-if="collapsed"
          type="button"
          class="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-brand-foreground transition-opacity hover:opacity-85"
          aria-label="展开导航栏"
          title="展开导航栏"
          @click="collapsed = false"
        >
          <PanelLeft class="h-5 w-5" />
        </button>

        <template v-else>
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand text-brand-foreground">
            <LayoutTemplate class="h-5 w-5" />
          </span>
          <span class="min-w-0 flex-1 truncate text-base font-bold text-card-foreground">管理后台</span>
          <button
            type="button"
            class="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted"
            aria-label="收起导航栏"
            @click="collapsed = true"
          >
            <ChevronLeft class="h-4 w-4" />
          </button>
        </template>
      </div>

      <!-- 导航项：激活项浮起、其余内凹式悬停 -->
      <nav class="ios-card flex flex-1 flex-col gap-1.5 p-2.5">
        <button
          v-for="n in NAV"
          :key="n.key"
          type="button"
          class="flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium transition-all"
          :class="[
            active === n.key
              ? 'bg-brand text-brand-foreground shadow-[4px_4px_10px_var(--neu-shadow),-4px_-4px_10px_var(--neu-highlight)]'
              : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            collapsed ? 'justify-center' : '',
          ]"
          :aria-current="active === n.key ? 'page' : undefined"
          :title="collapsed ? n.label : undefined"
          @click="active = n.key"
        >
          <component :is="n.icon" class="h-5 w-5 shrink-0" />
          <span v-if="!collapsed" class="truncate">{{ n.label }}</span>
        </button>
      </nav>

      <!-- 底部账户操作：返回工作台 / 主题 / 退出 -->
      <div class="ios-card flex flex-col gap-1 p-2.5">
        <button
          type="button"
          class="flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          :class="collapsed ? 'justify-center' : ''"
          :title="collapsed ? '返回工作台' : undefined"
          @click="goTo('workspace')"
        >
          <Home class="h-5 w-5 shrink-0" />
          <span v-if="!collapsed" class="truncate">返回工作台</span>
        </button>

        <button
          type="button"
          class="flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          :class="collapsed ? 'justify-center' : ''"
          :title="collapsed ? '切换主题' : undefined"
          @click="toggleTheme"
        >
          <Moon v-if="theme === 'light'" class="h-5 w-5 shrink-0" />
          <Sun v-else class="h-5 w-5 shrink-0" />
          <span v-if="!collapsed" class="flex-1 truncate text-left">主题</span>
          <span
            v-if="!collapsed"
            class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
          >
            {{ theme === "light" ? "浅色" : "深色" }}
          </span>
        </button>

        <button
          type="button"
          class="flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium text-destructive transition-colors hover:bg-destructive/10"
          :class="collapsed ? 'justify-center' : ''"
          :title="collapsed ? '退出登录' : undefined"
          @click="signOut"
        >
          <LogOut class="h-5 w-5 shrink-0" />
          <span v-if="!collapsed" class="truncate">退出登录</span>
        </button>

        <!-- 当前账号：内凹卡片 -->
        <div
          class="neu-inset mt-1.5 flex items-center gap-2.5 px-2.5 py-2"
          :class="collapsed ? 'justify-center' : ''"
        >
          <span
            class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand text-xs font-bold text-brand-foreground"
          >
            {{ initial }}
          </span>
          <div v-if="!collapsed" class="min-w-0">
            <p class="truncate text-xs font-semibold text-card-foreground">{{ currentUser?.name }}</p>
            <p class="truncate text-[0.7rem] text-muted-foreground">管理员</p>
          </div>
        </div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <div class="flex min-w-0 flex-1 flex-col">
      <!-- 页头 -->
      <header class="px-5 py-5 md:px-8">
        <div class="mx-auto flex w-full max-w-[1440px] flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-2xl bg-brand/10 text-brand">
            <component :is="activeMeta.icon" class="h-5 w-5" />
          </span>
          <div>
            <h1 class="text-xl font-bold text-foreground">{{ activeMeta.label }}</h1>
            <p class="text-sm text-muted-foreground">{{ activeMeta.desc }}</p>
          </div>
        </div>

        <div>
          <button
            v-if="!confirming"
            type="button"
            class="flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
            @click="confirming = true"
          >
            <RotateCcw class="h-3.5 w-3.5" />
            恢复出厂配置
          </button>
          <div
            v-else
            class="flex items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/5 px-3 py-2"
          >
            <span class="text-xs text-foreground">将清空所有自定义配置？</span>
            <button
              type="button"
              class="rounded-xl bg-destructive px-2.5 py-1 text-xs font-semibold text-destructive-foreground"
              @click="reset"
            >
              确认
            </button>
            <button
              type="button"
              class="rounded-xl border border-border px-2.5 py-1 text-xs text-muted-foreground"
              @click="confirming = false"
            >
              取消
            </button>
          </div>
        </div>
        </div>
      </header>

      <!-- 主体：当前独立页面（统计概览仅在「综合管理」中展示） -->
      <div class="p-5 md:p-8">
        <div class="mx-auto flex w-full max-w-[1440px] flex-col gap-5">
          <OverviewPanel v-if="active === 'overview'" @navigate="active = $event" />
          <ModulesPanel v-else-if="active === 'modules'" />
          <CombosPanel v-else-if="active === 'combos'" />
          <LayoutPanel v-else-if="active === 'layout'" />
          <UsersPanel v-else-if="active === 'users'" />
          <TasksPanel v-else-if="active === 'tasks'" />
          <AccountsPanel v-else />
        </div>
      </div>
    </div>
  </div>
</template>
