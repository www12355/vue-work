<script setup lang="ts">
import { computed } from "vue"
import {
  AlertTriangle,
  Blocks,
  CheckCircle2,
  ChevronRight,
  Layers,
  LayoutTemplate,
  Plug,
  ShieldCheck,
  Users,
  Workflow,
  Wrench,
} from "lucide-vue-next"
import Panel from "@/components/admin/ui/Panel.vue"
import {
  activeProxyRules,
  combinableModules,
  combos,
  devModules,
  modules,
  proxyPathConflicts,
  readyModules,
} from "@/stores/registry"
import { accounts, adminCount } from "@/stores/auth"
import { iconOf } from "@/data/icons"

/** 点击快捷入口时切换到对应的后台页面 */
const emit = defineEmits<{ (e: "navigate", key: "modules" | "combos" | "layout" | "accounts"): void }>()

/* ---------- 顶部统计 ---------- */
const stats = computed(() => [
  { label: "功能模块", value: modules.value.length, icon: Blocks, tone: "brand" },
  { label: "待开发", value: devModules.value.length, icon: Wrench, tone: "amber" },
  { label: "组合规则", value: combos.value.length, icon: Workflow, tone: "violet" },
  {
    label: "已启用组合",
    value: combos.value.filter((c) => c.enabled).length,
    icon: CheckCircle2,
    tone: "emerald",
  },
])

/** 统计卡图标容器配色（局部点缀，不改动全局主题色） */
const TONES: Record<string, string> = {
  brand: "bg-brand/10 text-brand",
  amber: "bg-amber-500/10 text-amber-600",
  violet: "bg-violet-500/10 text-violet-600",
  emerald: "bg-emerald-500/10 text-emerald-600",
}

/* ---------- 模块状态分布 ---------- */
const total = computed(() => modules.value.length)

function pct(n: number) {
  return total.value ? Math.round((n / total.value) * 100) : 0
}

const distribution = computed(() => [
  { label: "已上线", value: readyModules.value.length, bar: "bg-emerald-500" },
  { label: "待开发", value: devModules.value.length, bar: "bg-amber-500" },
  { label: "可组合", value: combinableModules.value.length, bar: "bg-brand" },
])

/* ---------- 组合规则概览 ---------- */
const comboRows = computed(() =>
  combos.value.map((c) => ({
    id: c.id,
    title: c.title,
    enabled: c.enabled,
    members: c.members.map((id) => modules.value.find((m) => m.id === id)?.title ?? id),
  })),
)

/* ---------- 账号概览 ---------- */
const accountSummary = computed(() => {
  const list = accounts.value
  return {
    total: list.length,
    admins: adminCount.value,
    disabled: list.filter((a) => !a.enabled).length,
  }
})

/* ---------- 快捷入口 ---------- */
const SHORTCUTS = [
  { key: "modules", label: "模块管理", desc: "新增模块、调整上线状态", icon: Blocks },
  { key: "combos", label: "组合规则", desc: "串联模块，配置流水线", icon: Layers },
  { key: "layout", label: "弹窗布局", desc: "调整功能区块与字段", icon: LayoutTemplate },
  { key: "accounts", label: "账号管理", desc: "维护后台账号与权限", icon: Users },
] as const
</script>

<template>
  <div class="flex flex-col gap-5">
    <!-- 概览统计：仅在综合管理页展示 -->
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div v-for="s in stats" :key="s.label" class="ios-card ios-hover flex items-center gap-3 px-4 py-3.5">
        <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" :class="TONES[s.tone]">
          <component :is="s.icon" class="h-5 w-5" />
        </span>
        <div class="min-w-0">
          <p class="truncate text-xs text-muted-foreground">{{ s.label }}</p>
          <p class="mt-0.5 text-2xl font-bold leading-none text-card-foreground">{{ s.value }}</p>
        </div>
      </div>
    </div>

    <div class="grid gap-5 lg:grid-cols-2">
      <!-- 模块状态分布 -->
      <Panel title="模块状态分布" desc="按上线状态与组合能力统计当前模块占比">
        <div class="flex flex-col gap-4">
          <div v-for="d in distribution" :key="d.label" class="flex flex-col gap-1.5">
            <div class="flex items-baseline justify-between">
              <span class="text-sm font-medium text-card-foreground">{{ d.label }}</span>
              <span class="text-xs text-muted-foreground">
                {{ d.value }} / {{ total }} · {{ pct(d.value) }}%
              </span>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-muted">
              <div class="h-full rounded-full transition-all" :class="d.bar" :style="{ width: `${pct(d.value)}%` }" />
            </div>
          </div>

          <p v-if="!total" class="rounded-xl bg-muted/50 px-3 py-6 text-center text-xs text-muted-foreground">
            暂无模块，请前往「模块管理」新增
          </p>
        </div>
      </Panel>

      <!-- 接口代理状态 -->
      <Panel title="接口代理状态" desc="已启用的后端代理规则与路径冲突检测">
        <div class="flex flex-col gap-3">
          <div class="flex items-center gap-3 rounded-xl bg-muted/50 px-4 py-3">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
              <Plug class="h-5 w-5" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-card-foreground">{{ activeProxyRules.length }} 条生效规则</p>
              <p class="truncate text-xs text-muted-foreground">已配置 path 与 target 且启用的模块代理</p>
            </div>
          </div>

          <!-- 冲突告警 -->
          <div
            v-if="proxyPathConflicts.length"
            class="flex items-start gap-2.5 rounded-xl border border-destructive/40 bg-destructive/5 px-3.5 py-3"
          >
            <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div class="min-w-0">
              <p class="text-xs font-semibold text-destructive">路径被重复占用</p>
              <p class="mt-1 break-all text-xs text-muted-foreground">{{ proxyPathConflicts.join("、") }}</p>
            </div>
          </div>
          <div
            v-else
            class="flex items-center gap-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-3.5 py-3"
          >
            <ShieldCheck class="h-4 w-4 shrink-0 text-emerald-600" />
            <p class="text-xs text-muted-foreground">未检测到路径冲突</p>
          </div>

          <ul v-if="activeProxyRules.length" class="flex flex-col gap-1.5">
            <li
              v-for="r in activeProxyRules.slice(0, 4)"
              :key="r.path"
              class="flex items-center justify-between gap-3 rounded-xl border border-border px-3 py-2"
            >
              <code class="shrink-0 text-xs font-semibold text-brand">{{ r.path }}</code>
              <span class="truncate text-xs text-muted-foreground">{{ r.target }}</span>
            </li>
          </ul>
        </div>
      </Panel>

      <!-- 组合规则概览 -->
      <Panel title="组合规则概览" desc="模块串联流程及其启用状态">
        <div class="flex flex-col gap-2">
          <div
            v-for="c in comboRows"
            :key="c.id"
            class="flex flex-col gap-2 rounded-xl border border-border px-3.5 py-3"
          >
            <div class="flex items-center justify-between gap-3">
              <span class="min-w-0 truncate text-sm font-semibold text-card-foreground">{{ c.title }}</span>
              <span
                class="shrink-0 rounded-full px-2 py-0.5 text-[0.7rem] font-medium"
                :class="
                  c.enabled ? 'bg-emerald-500/10 text-emerald-600' : 'bg-muted text-muted-foreground'
                "
              >
                {{ c.enabled ? "已启用" : "已停用" }}
              </span>
            </div>
            <div class="flex flex-wrap items-center gap-1">
              <template v-for="(m, i) in c.members" :key="m + i">
                <span class="rounded-xl bg-muted px-1.5 py-0.5 text-[0.7rem] text-muted-foreground">{{ m }}</span>
                <ChevronRight v-if="i < c.members.length - 1" class="h-3 w-3 text-muted-foreground" />
              </template>
            </div>
          </div>

          <p
            v-if="!comboRows.length"
            class="rounded-xl bg-muted/50 px-3 py-6 text-center text-xs text-muted-foreground"
          >
            暂无组合规则，请前往「组合规则」创建
          </p>
        </div>
      </Panel>

      <!-- 账号与快捷入口 -->
      <div class="flex flex-col gap-5">
        <Panel title="账号概览" desc="后台账号数量与权限分布">
          <div class="grid grid-cols-3 gap-3">
            <div class="rounded-xl bg-muted/50 px-3 py-3 text-center">
              <p class="text-2xl font-bold leading-none text-card-foreground">{{ accountSummary.total }}</p>
              <p class="mt-1.5 text-xs text-muted-foreground">总账号</p>
            </div>
            <div class="rounded-xl bg-muted/50 px-3 py-3 text-center">
              <p class="text-2xl font-bold leading-none text-brand">{{ accountSummary.admins }}</p>
              <p class="mt-1.5 text-xs text-muted-foreground">管理员</p>
            </div>
            <div class="rounded-xl bg-muted/50 px-3 py-3 text-center">
              <p class="text-2xl font-bold leading-none text-card-foreground">{{ accountSummary.disabled }}</p>
              <p class="mt-1.5 text-xs text-muted-foreground">已禁用</p>
            </div>
          </div>
        </Panel>

        <Panel title="快捷入口" desc="跳转到对应的管理页面">
          <div class="grid gap-2 sm:grid-cols-2">
            <button
              v-for="s in SHORTCUTS"
              :key="s.key"
              type="button"
              class="flex items-center gap-3 rounded-xl border border-border px-3.5 py-3 text-left transition-colors hover:bg-muted"
              @click="emit('navigate', s.key)"
            >
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
                <component :is="s.icon" class="h-4.5 w-4.5" />
              </span>
              <span class="min-w-0">
                <span class="block truncate text-sm font-semibold text-card-foreground">{{ s.label }}</span>
                <span class="block truncate text-xs text-muted-foreground">{{ s.desc }}</span>
              </span>
            </button>
          </div>
        </Panel>
      </div>
    </div>

    <!-- 模块清单 -->
    <Panel title="模块清单" desc="全部功能模块及其当前状态">
      <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="m in modules"
          :key="m.id"
          class="flex items-center gap-3 rounded-xl border border-border px-3.5 py-3"
        >
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
            <component :is="iconOf(m.icon)" class="h-4.5 w-4.5" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-semibold text-card-foreground">{{ m.title }}</p>
            <p class="truncate text-xs text-muted-foreground">{{ m.desc }}</p>
          </div>
          <span
            class="shrink-0 rounded-full px-2 py-0.5 text-[0.7rem] font-medium"
            :class="
              m.status === 'ready' ? 'bg-emerald-500/10 text-emerald-600' : 'bg-amber-500/10 text-amber-600'
            "
          >
            {{ m.status === "ready" ? "已上线" : "待开发" }}
          </span>
        </div>

        <p
          v-if="!modules.length"
          class="rounded-xl bg-muted/50 px-3 py-6 text-center text-xs text-muted-foreground sm:col-span-2 lg:col-span-3"
        >
          暂无模块
        </p>
      </div>
    </Panel>
  </div>
</template>
