<script setup lang="ts">
import { computed, ref } from "vue"
import {
  CalendarCheck,
  Coins,
  History,
  Minus,
  Plus,
  Search,
  ShieldCheck,
  User,
  Users,
  Wallet,
} from "lucide-vue-next"
import Panel from "@/components/admin/ui/Panel.vue"
import { accounts } from "@/stores/auth"
import { adminAdjust, allWallets, type PointsTx } from "@/stores/points"

/** 本地时区的今天，用于判断"今日是否已签到" */
function todayStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

interface UserRow {
  id: string
  name: string
  username: string
  role: "admin" | "member"
  enabled: boolean
  isGuest: boolean
  hasWallet: boolean
  balance: number
  earned: number
  spent: number
  claimed: number
  checkedToday: boolean
  lastActive: number
  txs: PointsTx[]
}

/** 把账号表与钱包表合并成一张用户资产视图（含未登录的体验钱包） */
const rows = computed<UserRow[]>(() => {
  const wallets = allWallets.value
  const today = todayStr()

  const build = (
    base: { id: string; name: string; username: string; role: "admin" | "member"; enabled: boolean; isGuest: boolean },
  ): UserRow => {
    const w = wallets[base.id]
    const txs = w?.txs ?? []
    return {
      ...base,
      hasWallet: Boolean(w),
      balance: w?.balance ?? 0,
      earned: txs.filter((t) => t.amount > 0).reduce((s, t) => s + t.amount, 0),
      spent: txs.filter((t) => t.amount < 0).reduce((s, t) => s - t.amount, 0),
      claimed: w?.claimedTasks.length ?? 0,
      checkedToday: w?.lastCheckIn === today,
      lastActive: txs.reduce((m, t) => Math.max(m, t.at), 0),
      txs: [...txs].sort((a, b) => b.at - a.at),
    }
  }

  const list = accounts.value.map((a) =>
    build({ id: a.id, name: a.name, username: a.username, role: a.role, enabled: a.enabled, isGuest: false }),
  )

  /* 未登录状态下产生的体验钱包，同样纳入统计，避免积分账目对不上 */
  if (wallets.guest) {
    list.push(
      build({ id: "guest", name: "体验用户", username: "guest", role: "member", enabled: true, isGuest: true }),
    )
  }

  return list.sort((a, b) => b.balance - a.balance)
})

/* ---------------- 搜索 ---------------- */
const keyword = ref("")
const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return rows.value
  return rows.value.filter((r) => r.name.toLowerCase().includes(k) || r.username.toLowerCase().includes(k))
})

/* ---------------- 汇总 ---------------- */
const summary = computed(() => ({
  users: rows.value.length,
  wallets: rows.value.filter((r) => r.hasWallet).length,
  points: rows.value.reduce((s, r) => s + r.balance, 0),
  checked: rows.value.filter((r) => r.checkedToday).length,
}))

const STAT_TONES: Record<string, string> = {
  brand: "bg-brand/10 text-brand",
  emerald: "bg-emerald-500/10 text-emerald-600",
  amber: "bg-amber-500/10 text-amber-600",
  sky: "bg-sky-500/10 text-sky-600",
}

const stats = computed(() => [
  { label: "平台用户", value: summary.value.users, icon: Users, tone: "brand" },
  { label: "已开通钱包", value: summary.value.wallets, icon: Wallet, tone: "sky" },
  { label: "积分总存量", value: summary.value.points, icon: Coins, tone: "amber" },
  { label: "今日已签到", value: summary.value.checked, icon: CalendarCheck, tone: "emerald" },
])

/* ---------------- 行内积分调整 ---------------- */
const adjustingId = ref<string | null>(null)
const deltaInput = ref<number | null>(null)
const reasonInput = ref("")
const rowError = ref<Record<string, string>>({})
const rowOk = ref<Record<string, string>>({})

function flashRow(map: typeof rowError, id: string, msg: string) {
  map.value = { ...map.value, [id]: msg }
  window.setTimeout(() => {
    const next = { ...map.value }
    delete next[id]
    map.value = next
  }, 3000)
}

function startAdjust(id: string) {
  adjustingId.value = adjustingId.value === id ? null : id
  deltaInput.value = null
  reasonInput.value = ""
}

function submitAdjust(id: string, sign: 1 | -1) {
  const amount = Number(deltaInput.value)
  if (!Number.isFinite(amount) || amount <= 0) {
    flashRow(rowError, id, "请输入大于 0 的积分数")
    return
  }
  const res = adminAdjust(id, sign * amount, reasonInput.value)
  if (!res.ok) {
    flashRow(rowError, id, res.error ?? "调整失败")
    return
  }
  flashRow(rowOk, id, sign > 0 ? `已补发 ${amount} 积分` : `已扣减 ${amount} 积分`)
  adjustingId.value = null
  deltaInput.value = null
  reasonInput.value = ""
}

/* ---------------- 流水展开 ---------------- */
const expandedId = ref<string | null>(null)

const TX_LABEL: Record<string, string> = {
  welcome: "欢迎积分",
  checkin: "每日签到",
  task: "任务奖励",
  recharge: "充值",
  consume: "消耗",
  adjust: "管理员调整",
}

function fmtTime(ts: number) {
  if (!ts) return "从未活跃"
  return new Date(ts).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <!-- 资产汇总 -->
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div v-for="s in stats" :key="s.label" class="ios-card ios-hover flex items-center gap-3 px-4 py-3.5">
        <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" :class="STAT_TONES[s.tone]">
          <component :is="s.icon" class="h-5 w-5" />
        </span>
        <div class="min-w-0">
          <p class="truncate text-xs text-muted-foreground">{{ s.label }}</p>
          <p class="mt-0.5 text-2xl font-bold leading-none text-card-foreground">{{ s.value }}</p>
        </div>
      </div>
    </div>

    <Panel title="用户资产" desc="查看平台用户的积分余额与收支情况，可手动补发或扣减积分。">
      <template #action>
        <label class="relative flex items-center">
          <Search class="pointer-events-none absolute left-3 h-3.5 w-3.5 text-muted-foreground" />
          <input
            v-model="keyword"
            type="search"
            placeholder="搜索用户名 / 昵称"
            class="field w-52 py-1.5 pl-9 text-xs"
            aria-label="搜索用户"
          />
        </label>
      </template>

      <ul class="flex flex-col gap-2.5">
        <li v-for="u in filtered" :key="u.id" class="neu-inset p-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <!-- 用户身份 -->
            <div class="flex min-w-0 items-center gap-3">
              <span
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                :class="u.role === 'admin' ? 'bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'"
              >
                <ShieldCheck v-if="u.role === 'admin'" class="h-5 w-5" />
                <User v-else class="h-5 w-5" />
              </span>
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="truncate text-sm font-semibold text-card-foreground">{{ u.name }}</p>
                  <span v-if="u.isGuest" class="chip">体验钱包</span>
                  <span v-else-if="u.role === 'admin'" class="chip chip-brand">管理员</span>
                  <span
                    v-if="!u.enabled"
                    class="rounded-full bg-destructive/10 px-2 py-0.5 text-[0.65rem] font-medium text-destructive"
                  >
                    已停用
                  </span>
                  <span
                    v-if="u.checkedToday"
                    class="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[0.65rem] font-medium text-emerald-600"
                  >
                    今日已签到
                  </span>
                </div>
                <p class="mt-0.5 truncate text-xs text-muted-foreground">
                  @{{ u.username }} · 最近活跃 {{ fmtTime(u.lastActive) }} · 已领任务 {{ u.claimed }}
                </p>
              </div>
            </div>

            <!-- 资产数据 -->
            <div class="flex items-center gap-5">
              <div class="text-right">
                <p class="text-lg font-bold leading-none text-card-foreground">{{ u.balance }}</p>
                <p class="mt-1 text-[0.7rem] text-muted-foreground">当前余额</p>
              </div>
              <div class="hidden text-right sm:block">
                <p class="text-sm font-semibold leading-none text-emerald-600">+{{ u.earned }}</p>
                <p class="mt-1 text-[0.7rem] text-muted-foreground">累计获得</p>
              </div>
              <div class="hidden text-right sm:block">
                <p class="text-sm font-semibold leading-none text-muted-foreground">
                  {{ u.spent ? `-${u.spent}` : 0 }}
                </p>
                <p class="mt-1 text-[0.7rem] text-muted-foreground">累计消耗</p>
              </div>

              <div class="flex items-center gap-1.5">
                <button
                  type="button"
                  class="flex items-center gap-1 rounded-xl border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
                  @click="startAdjust(u.id)"
                >
                  <Coins class="h-3.5 w-3.5" />
                  调整积分
                </button>
                <button
                  type="button"
                  :aria-label="`查看 ${u.name} 的积分流水`"
                  class="flex h-8 w-8 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:bg-muted"
                  @click="expandedId = expandedId === u.id ? null : u.id"
                >
                  <History class="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>

          <!-- 积分调整表单 -->
          <div v-if="adjustingId === u.id" class="mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-muted/40 p-3">
            <input
              v-model.number="deltaInput"
              type="number"
              min="1"
              placeholder="积分数量"
              class="field w-28 py-1.5"
              aria-label="调整积分数量"
            />
            <input
              v-model="reasonInput"
              type="text"
              placeholder="备注（可选），如 活动补发"
              class="field min-w-0 flex-1 py-1.5"
              aria-label="调整原因"
            />
            <button type="button" class="btn btn-primary btn-sm" @click="submitAdjust(u.id, 1)">
              <Plus class="h-3.5 w-3.5" />
              补发
            </button>
            <button type="button" class="btn btn-soft btn-sm" @click="submitAdjust(u.id, -1)">
              <Minus class="h-3.5 w-3.5" />
              扣减
            </button>
            <button
              type="button"
              class="rounded-xl border border-border px-3 py-1.5 text-xs text-muted-foreground"
              @click="adjustingId = null"
            >
              取消
            </button>
          </div>

          <!-- 积分流水 -->
          <div v-if="expandedId === u.id" class="mt-3 rounded-xl bg-muted/40 p-3">
            <ul v-if="u.txs.length" class="flex flex-col gap-1.5">
              <li
                v-for="t in u.txs.slice(0, 8)"
                :key="t.id"
                class="flex items-center justify-between gap-3 rounded-xl bg-card px-3 py-2"
              >
                <div class="min-w-0">
                  <p class="truncate text-xs font-medium text-card-foreground">{{ t.desc }}</p>
                  <p class="mt-0.5 text-[0.7rem] text-muted-foreground">
                    {{ TX_LABEL[t.type] ?? t.type }} · {{ fmtTime(t.at) }}
                  </p>
                </div>
                <span
                  class="shrink-0 text-xs font-bold"
                  :class="t.amount > 0 ? 'text-emerald-600' : 'text-muted-foreground'"
                >
                  {{ t.amount > 0 ? "+" : "" }}{{ t.amount }}
                </span>
              </li>
            </ul>
            <p v-else class="py-4 text-center text-xs text-muted-foreground">该用户还没有任何积分流水</p>
          </div>

          <p v-if="rowError[u.id]" class="mt-2 text-xs font-medium text-destructive">{{ rowError[u.id] }}</p>
          <p v-if="rowOk[u.id]" class="mt-2 text-xs font-medium text-emerald-600">{{ rowOk[u.id] }}</p>
        </li>

        <li v-if="!filtered.length" class="rounded-xl bg-muted/50 px-3 py-8 text-center text-xs text-muted-foreground">
          没有匹配的用户
        </li>
      </ul>
    </Panel>
  </div>
</template>
