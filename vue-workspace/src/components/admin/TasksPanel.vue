<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue"
import { CalendarCheck, Check, Gift, Pencil, Plus, RotateCcw, Trash2, X } from "lucide-vue-next"
import Panel from "@/components/admin/ui/Panel.vue"
import {
  allTasks,
  checkinReward,
  createTask,
  deleteTask,
  resetPointsConfig,
  updateRules,
  updateTask,
  welcomePoints,
  type PointTask,
} from "@/stores/pointsConfig"
import { allWallets } from "@/stores/points"
import { ICON_OPTIONS, iconOf } from "@/data/icons"

/* ---------------- 积分规则 ---------------- */
const rules = reactive({ checkin: checkinReward.value, welcome: welcomePoints.value })
const ruleMsg = ref("")
const ruleErr = ref("")

/* 外部（如恢复出厂配置）改动规则时同步回表单 */
watch([checkinReward, welcomePoints], ([c, w]) => {
  rules.checkin = c
  rules.welcome = w
})

function saveRules() {
  const res = updateRules({ checkinReward: Number(rules.checkin), welcomePoints: Number(rules.welcome) })
  if (!res.ok) {
    ruleErr.value = res.error ?? "保存失败"
    ruleMsg.value = ""
    return
  }
  ruleErr.value = ""
  ruleMsg.value = "积分规则已保存"
  window.setTimeout(() => (ruleMsg.value = ""), 2400)
}

const confirmingReset = ref(false)
function doReset() {
  resetPointsConfig()
  confirmingReset.value = false
  ruleMsg.value = "已恢复默认积分规则"
  window.setTimeout(() => (ruleMsg.value = ""), 2400)
}

/* ---------------- 任务统计 ---------------- */
/** 某个任务被多少个钱包领取过 */
function claimedCount(taskId: string) {
  return Object.values(allWallets.value).filter((w) => w.claimedTasks.includes(taskId)).length
}

const taskStats = computed(() => ({
  total: allTasks.value.length,
  enabled: allTasks.value.filter((t) => t.enabled).length,
  pool: allTasks.value.filter((t) => t.enabled).reduce((s, t) => s + t.reward, 0),
}))

/* ---------------- 新增任务 ---------------- */
const showAdd = ref(false)
const draft = reactive({ name: "", desc: "", reward: 5, icon: "Sparkles" })
const addError = ref("")

function resetDraft() {
  draft.name = ""
  draft.desc = ""
  draft.reward = 5
  draft.icon = "Sparkles"
  addError.value = ""
}

function submitAdd() {
  const res = createTask({ ...draft, reward: Number(draft.reward) })
  if (!res.ok) {
    addError.value = res.error ?? "添加失败"
    return
  }
  resetDraft()
  showAdd.value = false
}

/* ---------------- 行内编辑 ---------------- */
const editingId = ref<string | null>(null)
const editDraft = reactive({ name: "", desc: "", reward: 0, icon: "Sparkles" })
const rowError = ref<Record<string, string>>({})
const confirmDeleteId = ref<string | null>(null)

function setRowError(id: string, msg: string) {
  rowError.value = { ...rowError.value, [id]: msg }
  window.setTimeout(() => {
    const next = { ...rowError.value }
    delete next[id]
    rowError.value = next
  }, 3000)
}

function startEdit(t: PointTask) {
  editingId.value = t.id
  editDraft.name = t.name
  editDraft.desc = t.desc
  editDraft.reward = t.reward
  editDraft.icon = t.icon
}

function saveEdit(id: string) {
  const res = updateTask(id, { ...editDraft, reward: Number(editDraft.reward) })
  if (!res.ok) {
    setRowError(id, res.error ?? "保存失败")
    return
  }
  editingId.value = null
}

function toggleEnabled(t: PointTask) {
  const res = updateTask(t.id, { enabled: !t.enabled })
  if (!res.ok) setRowError(t.id, res.error ?? "")
}

function remove(id: string) {
  const res = deleteTask(id)
  if (!res.ok) setRowError(id, res.error ?? "")
  confirmDeleteId.value = null
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <!-- 积分规则 -->
    <Panel title="积分规则" desc="调整每日签到奖励与新用户注册赠送积分，保存后立即对前台生效。">
      <template #action>
        <button
          v-if="!confirmingReset"
          type="button"
          class="flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
          @click="confirmingReset = true"
        >
          <RotateCcw class="h-3.5 w-3.5" />
          恢复默认
        </button>
        <div v-else class="flex items-center gap-2">
          <span class="text-xs text-foreground">将重置规则与任务清单？</span>
          <button
            type="button"
            class="rounded-xl bg-destructive px-2.5 py-1 text-xs font-semibold text-destructive-foreground"
            @click="doReset"
          >
            确认
          </button>
          <button
            type="button"
            class="rounded-xl border border-border px-2.5 py-1 text-xs text-muted-foreground"
            @click="confirmingReset = false"
          >
            取消
          </button>
        </div>
      </template>

      <div class="grid gap-3 md:grid-cols-3">
        <label class="neu-inset flex items-center gap-3 p-3.5">
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
            <CalendarCheck class="h-5 w-5" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-xs font-medium text-muted-foreground">每日签到奖励</span>
            <input
              v-model.number="rules.checkin"
              type="number"
              min="0"
              class="field mt-1.5 py-1.5"
              aria-label="每日签到奖励积分"
            />
          </span>
        </label>

        <label class="neu-inset flex items-center gap-3 p-3.5">
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-600">
            <Gift class="h-5 w-5" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-xs font-medium text-muted-foreground">新用户欢迎积分</span>
            <input
              v-model.number="rules.welcome"
              type="number"
              min="0"
              class="field mt-1.5 py-1.5"
              aria-label="新用户欢迎积分"
            />
          </span>
        </label>

        <div class="neu-inset flex flex-col justify-center gap-2 p-3.5">
          <div class="flex items-baseline justify-between">
            <span class="text-xs text-muted-foreground">启用任务</span>
            <span class="text-sm font-bold text-card-foreground">
              {{ taskStats.enabled }} / {{ taskStats.total }}
            </span>
          </div>
          <div class="flex items-baseline justify-between">
            <span class="text-xs text-muted-foreground">单人可领上限</span>
            <span class="text-sm font-bold text-brand">{{ taskStats.pool }} 积分</span>
          </div>
          <button type="button" class="btn btn-primary btn-sm mt-1" @click="saveRules">保存规则</button>
        </div>
      </div>

      <p v-if="ruleErr" class="mt-3 text-xs font-medium text-destructive">{{ ruleErr }}</p>
      <p v-else-if="ruleMsg" class="mt-3 text-xs font-medium text-emerald-600">{{ ruleMsg }}</p>
    </Panel>

    <!-- 任务清单 -->
    <Panel title="积分任务" desc="维护一次性任务清单，用户可在个人中心任务中心领取奖励。">
      <template #action>
        <button v-if="!showAdd" type="button" class="btn btn-primary btn-sm" @click="showAdd = true">
          <Plus class="h-3.5 w-3.5" />
          添加任务
        </button>
      </template>

      <!-- 新增表单 -->
      <div v-if="showAdd" class="mb-4 rounded-2xl border border-dashed border-border bg-muted/20 p-4">
        <div class="flex items-center justify-between">
          <p class="text-sm font-semibold text-foreground">新增任务</p>
          <button
            type="button"
            class="flex h-7 w-7 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted"
            aria-label="取消"
            @click="((showAdd = false), resetDraft())"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <label class="flex flex-col gap-1.5">
            <span class="text-xs font-medium text-muted-foreground">任务名称</span>
            <input v-model="draft.name" type="text" placeholder="如 绑定企业邮箱" class="field" />
          </label>
          <label class="flex flex-col gap-1.5">
            <span class="text-xs font-medium text-muted-foreground">奖励积分</span>
            <input v-model.number="draft.reward" type="number" min="0" class="field" />
          </label>
          <label class="flex flex-col gap-1.5 sm:col-span-2">
            <span class="text-xs font-medium text-muted-foreground">任务说明</span>
            <input v-model="draft.desc" type="text" placeholder="一句话说明如何完成" class="field" />
          </label>
          <div class="flex flex-col gap-1.5 sm:col-span-2">
            <span class="text-xs font-medium text-muted-foreground">图标</span>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="name in ICON_OPTIONS"
                :key="name"
                type="button"
                class="flex h-9 w-9 items-center justify-center rounded-xl border transition-colors"
                :class="
                  draft.icon === name
                    ? 'border-brand bg-brand/10 text-brand'
                    : 'border-border bg-card text-muted-foreground hover:bg-muted'
                "
                :aria-label="name"
                :aria-pressed="draft.icon === name"
                @click="draft.icon = name"
              >
                <component :is="iconOf(name)" class="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        <p v-if="addError" class="mt-2 text-xs font-medium text-destructive">{{ addError }}</p>

        <div class="mt-3 flex justify-end">
          <button type="button" class="btn btn-primary btn-sm" @click="submitAdd">创建任务</button>
        </div>
      </div>

      <!-- 任务列表 -->
      <ul class="flex flex-col gap-2.5">
        <li v-for="t in allTasks" :key="t.id" class="neu-inset p-4">
          <!-- 展示态 -->
          <div v-if="editingId !== t.id" class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex min-w-0 items-center gap-3">
              <span
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                :class="t.enabled ? 'bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'"
              >
                <component :is="iconOf(t.icon)" class="h-5 w-5" />
              </span>
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <p class="truncate text-sm font-semibold text-card-foreground">{{ t.name }}</p>
                  <span
                    class="rounded-full px-2 py-0.5 text-[0.65rem] font-medium"
                    :class="
                      t.enabled ? 'bg-emerald-500/10 text-emerald-600' : 'bg-muted text-muted-foreground'
                    "
                  >
                    {{ t.enabled ? "进行中" : "已下架" }}
                  </span>
                </div>
                <p class="mt-0.5 truncate text-xs text-muted-foreground">
                  {{ t.desc || "暂无说明" }} · 已被 {{ claimedCount(t.id) }} 人领取
                </p>
              </div>
            </div>

            <div class="flex items-center gap-3">
              <span class="text-sm font-bold text-brand">+{{ t.reward }}</span>
              <div class="flex items-center gap-1.5">
                <button
                  type="button"
                  class="rounded-xl border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
                  @click="toggleEnabled(t)"
                >
                  {{ t.enabled ? "下架" : "上架" }}
                </button>
                <button
                  type="button"
                  :aria-label="`编辑 ${t.name}`"
                  class="flex h-8 w-8 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:bg-muted"
                  @click="startEdit(t)"
                >
                  <Pencil class="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  :aria-label="`删除 ${t.name}`"
                  class="flex h-8 w-8 items-center justify-center rounded-xl border border-destructive/40 text-destructive transition-colors hover:bg-destructive/10"
                  @click="confirmDeleteId = t.id"
                >
                  <Trash2 class="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>

          <!-- 编辑态 -->
          <div v-else class="flex flex-col gap-3">
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="flex flex-col gap-1.5">
                <span class="text-xs font-medium text-muted-foreground">任务名称</span>
                <input v-model="editDraft.name" type="text" class="field py-1.5" />
              </label>
              <label class="flex flex-col gap-1.5">
                <span class="text-xs font-medium text-muted-foreground">奖励积分</span>
                <input v-model.number="editDraft.reward" type="number" min="0" class="field py-1.5" />
              </label>
              <label class="flex flex-col gap-1.5 sm:col-span-2">
                <span class="text-xs font-medium text-muted-foreground">任务说明</span>
                <input v-model="editDraft.desc" type="text" class="field py-1.5" />
              </label>
            </div>

            <div class="flex flex-wrap gap-2">
              <button
                v-for="name in ICON_OPTIONS"
                :key="name"
                type="button"
                class="flex h-9 w-9 items-center justify-center rounded-xl border transition-colors"
                :class="
                  editDraft.icon === name
                    ? 'border-brand bg-brand/10 text-brand'
                    : 'border-border bg-card text-muted-foreground hover:bg-muted'
                "
                :aria-label="name"
                :aria-pressed="editDraft.icon === name"
                @click="editDraft.icon = name"
              >
                <component :is="iconOf(name)" class="h-4 w-4" />
              </button>
            </div>

            <div class="flex justify-end gap-2">
              <button type="button" class="btn btn-primary btn-sm" @click="saveEdit(t.id)">
                <Check class="h-3.5 w-3.5" />
                保存
              </button>
              <button
                type="button"
                class="rounded-xl border border-border px-3 py-1.5 text-xs text-muted-foreground"
                @click="editingId = null"
              >
                取消
              </button>
            </div>
          </div>

          <!-- 删除确认 -->
          <div
            v-if="confirmDeleteId === t.id"
            class="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-3"
          >
            <span class="text-xs text-foreground">
              确认删除任务「{{ t.name }}」？已领取的积分不会被收回。
            </span>
            <button
              type="button"
              class="rounded-xl bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground"
              @click="remove(t.id)"
            >
              确认删除
            </button>
            <button
              type="button"
              class="rounded-xl border border-border px-3 py-1.5 text-xs text-muted-foreground"
              @click="confirmDeleteId = null"
            >
              取消
            </button>
          </div>

          <p v-if="rowError[t.id]" class="mt-2 text-xs font-medium text-destructive">{{ rowError[t.id] }}</p>
        </li>

        <li v-if="!allTasks.length" class="rounded-xl bg-muted/50 px-3 py-8 text-center text-xs text-muted-foreground">
          还没有任务，点击右上角「添加任务」创建第一个
        </li>
      </ul>
    </Panel>
  </div>
</template>
