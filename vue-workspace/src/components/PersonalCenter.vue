<script setup lang="ts">
import { computed, ref, watch } from "vue"
import {
  ArrowLeft,
  Calendar,
  CalendarDays,
  Check,
  CheckCircle2,
  ClipboardList,
  Coins,
  Cpu,
  FileSignature,
  FileText,
  Layers,
  LogIn,
  Pencil,
  Plus,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Wallet,
  X,
} from "lucide-vue-next"
import { currentUser, isAdmin, isAuthed, updateAccount } from "@/stores/auth"
import { goTo } from "@/stores/view"
import {
  canCheckIn,
  checkIn,
  claimTask,
  dailyCheckinReward,
  isTaskClaimed,
  recentTxs,
  recharge,
  wallet,
} from "@/stores/points"
import { activeTasks, type PointTask } from "@/stores/pointsConfig"
import { iconOf } from "@/data/icons"
import PointsWallet from "@/components/PointsWallet.vue"
import {
  COMBO_DISCOUNT,
  comboCost,
  DOC_PRICING,
  docCost,
  MODELS,
  tokensPerDollar,
} from "@/data/pricing"

/* ---------------- 顶部提示条 ---------------- */
const notice = ref("")
let noticeTimer: ReturnType<typeof setTimeout> | null = null
function flash(msg: string) {
  notice.value = msg
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => (notice.value = ""), 2400)
}

/* ---------------- 个人资料 ---------------- */
const displayName = computed(() => currentUser.value?.name ?? "体验用户")
const initial = computed(() => displayName.value.trim().charAt(0) || "客")
const roleLabel = computed(() => {
  if (!isAuthed.value) return "游客 · 体验模式"
  return isAdmin.value ? "管理员" : "普通成员"
})
const joinedAt = computed(() => {
  const ts = currentUser.value?.createdAt
  if (!ts) return "—"
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
})

/* 资料编辑：仅登录用户可用 */
const editing = ref(false)
const formName = ref("")
const formPassword = ref("")

function startEdit() {
  formName.value = currentUser.value?.name ?? ""
  formPassword.value = ""
  editing.value = true
}
function cancelEdit() {
  editing.value = false
}
function saveProfile() {
  const acc = currentUser.value
  if (!acc) return
  const name = formName.value.trim()
  if (!name) {
    flash("显示名称不能为空")
    return
  }
  const patch: { name: string; password?: string } = { name }
  if (formPassword.value) patch.password = formPassword.value
  const r = updateAccount(acc.id, patch)
  if (!r.ok) {
    flash(r.error || "保存失败")
    return
  }
  editing.value = false
  flash("资料已更新")
}

/* 切换账号时关闭编辑态，避免把上一个账号的输入残留下来 */
watch(currentUser, () => (editing.value = false))

/* ---------------- 账户统计 ---------------- */
const totalEarned = computed(() =>
  wallet.value.txs.filter((t) => t.amount > 0).reduce((s, t) => s + t.amount, 0),
)
const totalSpent = computed(() =>
  wallet.value.txs.filter((t) => t.amount < 0).reduce((s, t) => s - t.amount, 0),
)

/* ---------------- 签到 ---------------- */
function onCheckIn() {
  const r = checkIn()
  flash(r.ok ? `签到成功，+${dailyCheckinReward.value} 积分` : r.error || "签到失败")
}

/* ---------------- 每日 / 一次性任务（任务清单由后台「积分任务」配置） ---------------- */
function onClaimTask(t: PointTask) {
  const r = claimTask(t.id, t.reward, `任务奖励：${t.name}`)
  flash(r.ok ? `领取成功，+${t.reward} 积分` : r.error || "领取失败")
}

/* ---------------- 计费：模型选择 ---------------- */
const selectedModelId = ref(MODELS[2].id) // 默认 GPT-4o
const selectedModel = computed(() => MODELS.find((m) => m.id === selectedModelId.value) ?? MODELS[0])

const DOC_ICONS: Record<string, typeof FileText> = {
  minutes: ClipboardList,
  contract: FileSignature,
  tender: FileText,
}
const docRows = computed(() =>
  DOC_PRICING.map((d) => ({
    ...d,
    icon: DOC_ICONS[d.id] ?? FileText,
    cost: docCost(d, selectedModel.value),
  })),
)
const combo = computed(() => comboCost(selectedModel.value))
const comboTokens = computed(() => DOC_PRICING.reduce((s, d) => s + d.tokens, 0))

/* ---------------- 充值 ---------------- */
const RECHARGE_PACKAGES = [
  { usd: 10, bonus: 0 },
  { usd: 50, bonus: 5 },
  { usd: 100, bonus: 15 },
  { usd: 500, bonus: 100 },
]
const customUsd = ref<number | null>(null)
function onRecharge(usd: number, bonus = 0) {
  const r = recharge(usd, bonus)
  flash(r.ok ? `充值成功，+${usd + bonus} 积分` : r.error || "充值失败")
}
function onCustomRecharge() {
  const amount = Number(customUsd.value)
  if (!amount || amount <= 0) {
    flash("请输入有效的充值金额")
    return
  }
  onRecharge(amount)
  customUsd.value = null
}

/* ---------------- 格式化 ---------------- */
const fmtPoints = (n: number) => n.toFixed(2)
const fmtUsd = (n: number) => `$${n.toFixed(2)}`
const fmtInt = (n: number) => n.toLocaleString("en-US")
function fmtTime(ts: number) {
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, "0")
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const TX_LABEL: Record<string, string> = {
  welcome: "欢迎积分",
  checkin: "每日签到",
  task: "任务奖励",
  recharge: "充值",
  consume: "消耗",
  adjust: "管理员调整",
}
</script>

<template>
  <div class="mx-auto max-w-7xl pb-10">
    <!-- 页头 -->
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="min-w-0">
        <h1 class="text-2xl font-bold text-foreground md:text-3xl">个人中心</h1>
      </div>
      <button
        type="button"
        class="btn btn-soft h-10 font-medium"
        @click="goTo('workspace')"
      >
        <ArrowLeft class="h-4 w-4" />
        返回工作台
      </button>
    </header>

    <!-- 轻提示 -->
    <div
      v-if="notice"
      class="ws-fade-in mt-4 flex items-center gap-2 rounded-xl border border-brand/30 bg-brand/10 px-4 py-3 text-sm font-medium text-brand"
      role="status"
    >
      <CheckCircle2 class="h-4 w-4" />
      {{ notice }}
    </div>

    <!-- ===== 三栏主体：左资料 / 中内容 / 右积分 ===== -->
    <div class="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-12">
      <!-- ============ 左栏：个人资料 ============ -->
      <aside class="flex flex-col gap-5 lg:col-span-3">
        <section class="ios-card ios-hover relative overflow-hidden">
          <span class="ios-sheen" aria-hidden="true" />

          <!-- 横幅头图 -->
          <div class="profile-banner" aria-hidden="true" />

          <!-- 头像跨在横幅边缘 -->
          <div class="relative -mt-11 flex flex-col items-center px-5 text-center">
            <span
              class="flex h-[5.5rem] w-[5.5rem] items-center justify-center rounded-full border-4 border-card bg-brand text-3xl font-bold text-brand-foreground shadow-[0_10px_24px_-10px_var(--brand)]"
            >
              {{ initial }}
            </span>
            <p class="mt-3 max-w-full truncate text-lg font-bold text-card-foreground">{{ displayName }}</p>
            <span class="chip chip-brand mt-1.5 font-semibold">
              <ShieldCheck class="h-3.5 w-3.5" />
              {{ roleLabel }}
            </span>
          </div>

          <!-- 账号信息 -->
          <dl class="relative mx-5 mt-5 flex flex-col gap-2.5 border-t border-border pt-4 text-sm">
            <div class="flex items-center justify-between gap-2">
              <dt class="text-xs text-muted-foreground">登录账号</dt>
              <dd class="truncate font-medium text-card-foreground">
                {{ currentUser?.username ?? "guest" }}
              </dd>
            </div>
            <div class="flex items-center justify-between gap-2">
              <dt class="flex items-center gap-1 text-xs text-muted-foreground">
                <CalendarDays class="h-3.5 w-3.5" />
                注册时间
              </dt>
              <dd class="font-medium text-card-foreground">{{ joinedAt }}</dd>
            </div>
          </dl>

          <!-- 编辑资料 -->
          <div class="relative mx-5 mb-5 mt-4">
            <!-- 未登录：引导登录 -->
            <div v-if="!isAuthed" class="rounded-xl border border-dashed border-border bg-muted p-3">
              <p class="text-xs text-muted-foreground">当前为体验模式，积分暂存本机。登录后可编辑资料并绑定积分。</p>
              <button
                type="button"
                class="btn btn-primary btn-sm mt-2.5 w-full"
                @click="goTo('login')"
              >
                <LogIn class="h-3.5 w-3.5" />
                去登录
              </button>
            </div>

            <!-- 已登录：编辑入口 -->
            <button
              v-else-if="!editing"
              type="button"
              class="btn btn-soft h-10 w-full"
              @click="startEdit"
            >
              <Pencil class="h-4 w-4" />
              编辑资料
            </button>

            <!-- 已登录：编辑表单 -->
            <form v-else class="flex flex-col gap-3" @submit.prevent="saveProfile">
              <div>
                <label for="pf-name" class="text-xs font-medium text-muted-foreground">显示名称</label>
                <input
                  id="pf-name"
                  v-model="formName"
                  type="text"
                  maxlength="20"
                  class="mt-1.5 h-10 w-full field"
                />
              </div>
              <div>
                <label for="pf-pwd" class="text-xs font-medium text-muted-foreground">新密码（留空不改）</label>
                <input
                  id="pf-pwd"
                  v-model="formPassword"
                  type="password"
                  placeholder="至少 6 位"
                  autocomplete="new-password"
                  class="mt-1.5 h-10 w-full field"
                />
              </div>
              <div class="flex gap-2">
                <button
                  type="submit"
                  class="btn btn-primary btn-sm h-9 flex-1"
                >
                  <Check class="h-3.5 w-3.5" />
                  保存
                </button>
                <button
                  type="button"
                  class="btn btn-soft btn-sm h-9 flex-1"
                  @click="cancelEdit"
                >
                  <X class="h-3.5 w-3.5" />
                  取消
                </button>
              </div>
            </form>
          </div>
        </section>

        <!-- 账户统计 -->
        <section class="ios-card p-5">
          <div class="flex items-center gap-2">
            <TrendingUp class="h-5 w-5 text-brand" />
            <h2 class="text-base font-bold text-card-foreground">账户统计</h2>
          </div>
          <ul class="mt-4 flex flex-col gap-3">
            <li class="flex items-center gap-3">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
                <TrendingUp class="h-4 w-4" />
              </span>
              <span class="flex-1 text-sm text-muted-foreground">累计获得</span>
              <span class="text-sm font-bold text-brand">+{{ fmtPoints(totalEarned) }}</span>
            </li>
            <li class="flex items-center gap-3">
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive"
              >
                <TrendingDown class="h-4 w-4" />
              </span>
              <span class="flex-1 text-sm text-muted-foreground">累计消耗</span>
              <span class="text-sm font-bold text-destructive">-{{ fmtPoints(totalSpent) }}</span>
            </li>
            <li class="flex items-center gap-3 border-t border-border pt-3">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                <Coins class="h-4 w-4" />
              </span>
              <span class="flex-1 text-sm text-muted-foreground">流水记录</span>
              <span class="text-sm font-bold text-card-foreground">{{ wallet.txs.length }} 条</span>
            </li>
          </ul>
        </section>

        <!-- 计费规则 -->
        <section class="ios-card grow p-5">
          <div class="flex items-center gap-2">
            <Cpu class="h-5 w-5 text-brand" />
            <h2 class="text-base font-bold text-card-foreground">计费规则</h2>
          </div>
          <ul class="mt-4 flex flex-col gap-3 text-sm">
            <li class="flex items-start gap-2.5">
              <Coins class="mt-0.5 h-4 w-4 shrink-0 text-brand" />
              <span class="text-muted-foreground">1 积分 = 1 美金，充值与消耗均按此汇率结算。</span>
            </li>
            <li class="flex items-start gap-2.5">
              <Calendar class="mt-0.5 h-4 w-4 shrink-0 text-brand" />
              <span class="text-muted-foreground">每日登录签到可领取 {{ dailyCheckinReward }} 积分。</span>
            </li>
            <li class="flex items-start gap-2.5">
              <Cpu class="mt-0.5 h-4 w-4 shrink-0 text-brand" />
              <span class="text-muted-foreground">1 美金可购买的调用 token 数量依模型定价而定。</span>
            </li>
          </ul>

          <!-- 各模型 $1 兑换 token -->
          <div class="neu-inset mt-4 p-3">
            <p class="text-xs font-medium text-muted-foreground">$1（1 积分）可购买 token</p>
            <ul class="mt-2 flex flex-col gap-1.5">
              <li
                v-for="m in MODELS"
                :key="m.id"
                class="flex items-center justify-between text-xs"
                :class="m.id === selectedModelId ? 'font-semibold text-brand' : 'text-muted-foreground'"
              >
                <span>{{ m.name }}</span>
                <span>{{ fmtInt(tokensPerDollar(m)) }} tokens</span>
              </li>
            </ul>
          </div>
        </section>
      </aside>

      <!-- ============ 中栏：任务 / 计费 / 明细 ============ -->
      <div class="flex flex-col gap-5 lg:col-span-6">
        <!-- 任务中心 -->
        <section class="ios-card p-5">
          <div class="flex items-center gap-2">
            <TrendingUp class="h-5 w-5 text-brand" />
            <h2 class="text-base font-bold text-card-foreground">任务中心</h2>
            <span class="ml-auto text-xs text-muted-foreground">完成任务赚取积分</span>
          </div>

          <!-- 每日签到任务 -->
          <div class="neu-inset mt-4 flex items-center gap-3 p-3.5">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
              <Calendar class="h-5 w-5" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-card-foreground">每日签到</p>
              <p class="text-xs text-muted-foreground">每天登录领取 {{ dailyCheckinReward }} 积分</p>
            </div>
            <span class="shrink-0 text-sm font-bold text-brand">+{{ dailyCheckinReward }}</span>
            <button
              type="button"
              class="h-9 shrink-0 rounded-xl px-4 text-xs font-semibold transition-colors"
              :class="
                canCheckIn
                  ? 'bg-brand text-brand-foreground hover:opacity-90'
                  : 'cursor-not-allowed bg-muted text-muted-foreground'
              "
              :disabled="!canCheckIn"
              @click="onCheckIn"
            >
              {{ canCheckIn ? "签到" : "已完成" }}
            </button>
          </div>

          <!-- 一次性任务 -->
          <ul class="mt-3 flex flex-col gap-3">
            <li
              v-for="t in activeTasks"
              :key="t.id"
              class="neu-inset flex items-center gap-3 p-3.5"
            >
              <span
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground"
              >
                <component :is="iconOf(t.icon)" class="h-5 w-5" />
              </span>
              <div class="min-w-0 flex-1">
                <p class="text-sm font-semibold text-card-foreground">{{ t.name }}</p>
                <p class="text-xs text-muted-foreground">{{ t.desc }}</p>
              </div>
              <span class="shrink-0 text-sm font-bold text-brand">+{{ t.reward }}</span>
              <button
                type="button"
                class="h-9 shrink-0 rounded-xl px-4 text-xs font-semibold transition-colors"
                :class="
                  isTaskClaimed(t.id)
                    ? 'cursor-not-allowed bg-muted text-muted-foreground'
                    : 'bg-brand text-brand-foreground hover:opacity-90'
                "
                :disabled="isTaskClaimed(t.id)"
                @click="onClaimTask(t)"
              >
                {{ isTaskClaimed(t.id) ? "已领取" : "领取" }}
              </button>
            </li>
          </ul>

          <p
            v-if="!activeTasks.length"
            class="neu-inset mt-3 px-3 py-6 text-center text-xs text-muted-foreground"
          >
            暂无进行中的积分任务
          </p>
        </section>

        <!-- 生成计费 -->
        <section class="ios-card p-5">
          <div class="flex flex-wrap items-center gap-2">
            <Cpu class="h-5 w-5 text-brand" />
            <h2 class="text-base font-bold text-card-foreground">生成计费</h2>
            <div class="ml-auto flex items-center gap-2">
              <label for="model" class="text-xs text-muted-foreground">计费模型</label>
              <select
                id="model"
                v-model="selectedModelId"
                class="field w-40"
              >
                <option v-for="m in MODELS" :key="m.id" :value="m.id">{{ m.name }}</option>
              </select>
            </div>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">
            成本按所选模型的 token 单价换算，1 积分 = 1 美金。{{ selectedModel.name }}：{{ selectedModel.note }}
          </p>

          <!-- 表头 -->
          <div class="mt-4 hidden grid-cols-12 gap-2 px-3 text-xs font-medium text-muted-foreground sm:grid">
            <span class="col-span-5">文档类型</span>
            <span class="col-span-3 text-right">预估 token</span>
            <span class="col-span-2 text-right">美金</span>
            <span class="col-span-2 text-right">积分</span>
          </div>

          <!-- 单文档行 -->
          <div class="mt-2 flex flex-col gap-2">
            <div
              v-for="d in docRows"
              :key="d.id"
              class="neu-inset grid grid-cols-2 items-center gap-2 p-3 sm:grid-cols-12"
            >
              <div class="col-span-2 flex items-center gap-2.5 sm:col-span-5">
                <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-brand/10 text-brand">
                  <component :is="d.icon" class="h-4 w-4" />
                </span>
                <span class="text-sm font-semibold text-card-foreground">{{ d.name }}</span>
              </div>
              <span class="text-xs text-muted-foreground sm:col-span-3 sm:text-right">
                <span class="sm:hidden">token：</span>{{ fmtInt(d.tokens) }}
              </span>
              <span class="text-sm text-muted-foreground sm:col-span-2 sm:text-right">{{ fmtUsd(d.cost) }}</span>
              <span class="text-right text-sm font-bold text-brand sm:col-span-2">{{ fmtPoints(d.cost) }}</span>
            </div>

            <!-- 组合生成 -->
            <div
              class="grid grid-cols-2 items-center gap-2 rounded-xl border border-brand/30 bg-brand/5 p-3 sm:grid-cols-12"
            >
              <div class="col-span-2 flex items-center gap-2.5 sm:col-span-5">
                <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-brand-foreground">
                  <Layers class="h-4 w-4" />
                </span>
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-card-foreground">组合生成</p>
                  <p class="text-xs text-muted-foreground">
                    纪要 + 合同 + 标书 · {{ Math.round((1 - COMBO_DISCOUNT) * 100) }}% 组合优惠
                  </p>
                </div>
              </div>
              <span class="text-xs text-muted-foreground sm:col-span-3 sm:text-right">
                <span class="sm:hidden">token：</span>{{ fmtInt(comboTokens) }}
              </span>
              <span class="text-sm text-muted-foreground line-through sm:col-span-2 sm:text-right">
                {{ fmtUsd(combo.original) }}
              </span>
              <span class="text-right text-sm font-bold text-brand sm:col-span-2">
                {{ fmtPoints(combo.discounted) }}
              </span>
            </div>
          </div>
        </section>

        <!-- 积分明细 -->
        <section class="ios-card grow p-5">
          <div class="flex items-center gap-2">
            <Coins class="h-5 w-5 text-brand" />
            <h2 class="text-base font-bold text-card-foreground">积分明细</h2>
            <span class="ml-auto text-xs text-muted-foreground">共 {{ wallet.txs.length }} 条</span>
          </div>
          <ul class="mt-4 flex flex-col divide-y divide-border">
            <li v-for="tx in recentTxs" :key="tx.id" class="flex items-center gap-3 py-3">
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-xs font-semibold"
                :class="tx.amount >= 0 ? 'bg-brand/10 text-brand' : 'bg-destructive/10 text-destructive'"
              >
                {{ TX_LABEL[tx.type]?.charAt(0) ?? "·" }}
              </span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium text-card-foreground">{{ tx.desc }}</p>
                <p class="text-xs text-muted-foreground">{{ fmtTime(tx.at) }} · {{ TX_LABEL[tx.type] }}</p>
              </div>
              <span
                class="shrink-0 text-sm font-bold"
                :class="tx.amount >= 0 ? 'text-brand' : 'text-destructive'"
              >
                {{ tx.amount >= 0 ? "+" : "" }}{{ fmtPoints(tx.amount) }}
              </span>
            </li>
          </ul>
        </section>
      </div>

      <!-- ============ 右栏：积分余额 / 充值 / 规则 ============ -->
      <div class="flex flex-col gap-5 lg:col-span-3">
        <!-- 积分钱包：口袋式余额 + 模型计费卡 -->
        <section class="ios-card p-5">
          <div class="flex items-center gap-2">
            <Wallet class="h-5 w-5 text-brand" />
            <h2 class="text-base font-bold text-card-foreground">积分钱包</h2>
          </div>

          <PointsWallet />

          <p class="mt-4 text-center text-xs text-muted-foreground">汇率固定 1 积分 = 1 美金</p>

          <div class="mt-3 flex flex-col gap-2.5">
            <button
              type="button"
              class="btn btn-primary"
              :disabled="!canCheckIn"
              @click="onCheckIn"
            >
              <Calendar class="h-4 w-4" />
              {{ canCheckIn ? `每日签到 +${dailyCheckinReward}` : "今日已签到" }}
            </button>
            <a
              href="#recharge"
              class="btn btn-soft"
            >
              <Plus class="h-4 w-4" />
              立即充值
            </a>
          </div>
        </section>

        <!-- 充值中心 -->
        <section id="recharge" class="ios-card grow p-5">
          <div class="flex items-center gap-2">
            <Plus class="h-5 w-5 text-brand" />
            <h2 class="text-base font-bold text-card-foreground">充值中心</h2>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">按 1 美金 = 1 积分充值，大额赠送更多</p>
          <p class="mt-2 text-[11px] text-muted-foreground">悬停卡片查看到账明细</p>

          <div class="mt-3 grid grid-cols-2 gap-3">
            <button
              v-for="p in RECHARGE_PACKAGES"
              :key="p.usd"
              type="button"
              class="flip-card h-24"
              :aria-label="`充值 ${p.usd} 美金，到账 ${p.usd + p.bonus} 积分`"
              @click="onRecharge(p.usd, p.bonus)"
            >
              <span class="flip-card-inner">
                <!-- 正面：价格 -->
                <span class="flip-face ios-card flex flex-col items-start justify-center gap-0.5 p-3 text-left">
                  <span class="text-lg font-bold text-card-foreground">${{ p.usd }}</span>
                  <span class="text-xs text-muted-foreground">
                    {{ p.usd }} 积分<template v-if="p.bonus"> · 赠 {{ p.bonus }}</template>
                  </span>
                  <span
                    v-if="p.bonus"
                    class="mt-1 rounded-full bg-brand/12 px-2 py-0.5 text-[10px] font-semibold text-brand"
                  >
                    超值
                  </span>
                </span>
                <!-- 背面：到账明细 -->
                <span
                  class="flip-face flip-face-back flex flex-col items-center justify-center gap-0.5 bg-brand p-3 text-brand-foreground"
                >
                  <span class="text-[11px] opacity-80">到账</span>
                  <span class="text-xl font-bold leading-none">{{ p.usd + p.bonus }}</span>
                  <span class="flex items-center gap-1 text-[11px] font-medium">
                    <Plus class="h-3 w-3" />
                    立即充值
                  </span>
                </span>
              </span>
            </button>
          </div>

          <div class="mt-4">
            <label for="custom" class="text-xs font-medium text-muted-foreground">自定义金额（美金）</label>
            <div class="mt-1.5 flex gap-2">
              <input
                id="custom"
                v-model.number="customUsd"
                type="number"
                min="1"
                placeholder="输入金额"
                class="h-10 min-w-0 flex-1 field"
              />
              <button
                type="button"
                class="btn btn-primary h-10 shrink-0"
                @click="onCustomRecharge"
              >
                充值
              </button>
            </div>
          </div>
        </section>

      </div>
    </div>
  </div>
</template>

<style scoped>
/* 资料卡横幅：品牌色底 + 同色系斜纹肌理，头像跨在其下沿 */
.profile-banner {
  height: 96px;
  width: 100%;
  background-color: var(--brand);
  background-image: repeating-linear-gradient(
    -45deg,
    color-mix(in oklch, white 10%, transparent) 0 10px,
    transparent 10px 20px
  );
}
</style>
