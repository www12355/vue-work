<script setup lang="ts">
import { computed, reactive, ref } from "vue"
import { KeyRound, Plus, ShieldCheck, Trash2, User, UserCog, X } from "lucide-vue-next"
import Panel from "@/components/admin/ui/Panel.vue"
import {
  accounts,
  createAccount,
  currentUser,
  deleteAccount,
  updateAccount,
  type AccountRole,
} from "@/stores/auth"

/* ---------------- 新增账号 ---------------- */
const showAdd = ref(false)
const draft = reactive({
  username: "",
  name: "",
  password: "",
  role: "member" as AccountRole,
})
const addError = ref("")

function resetDraft() {
  draft.username = ""
  draft.name = ""
  draft.password = ""
  draft.role = "member"
  addError.value = ""
}

function submitAdd() {
  const res = createAccount({ ...draft })
  if (!res.ok) {
    addError.value = res.error ?? "添加失败"
    return
  }
  resetDraft()
  showAdd.value = false
}

/* ---------------- 行内操作 ---------------- */
const rowError = ref<Record<string, string>>({})
const resettingId = ref<string | null>(null)
const newPwd = ref("")
const confirmDeleteId = ref<string | null>(null)

function setRowError(id: string, msg: string) {
  rowError.value = { ...rowError.value, [id]: msg }
  window.setTimeout(() => {
    const next = { ...rowError.value }
    delete next[id]
    rowError.value = next
  }, 3000)
}

function toggleRole(id: string, role: AccountRole) {
  const res = updateAccount(id, { role: role === "admin" ? "member" : "admin" })
  if (!res.ok) setRowError(id, res.error ?? "")
}

function toggleEnabled(id: string, enabled: boolean) {
  const res = updateAccount(id, { enabled: !enabled })
  if (!res.ok) setRowError(id, res.error ?? "")
}

function startReset(id: string) {
  resettingId.value = id
  newPwd.value = ""
}

function saveReset(id: string) {
  const res = updateAccount(id, { password: newPwd.value })
  if (!res.ok) {
    setRowError(id, res.error ?? "")
    return
  }
  resettingId.value = null
  newPwd.value = ""
}

function remove(id: string) {
  const res = deleteAccount(id)
  if (!res.ok) setRowError(id, res.error ?? "")
  confirmDeleteId.value = null
}

const sorted = computed(() =>
  [...accounts.value].sort((a, b) => {
    /* 管理员在前，其次按创建时间 */
    if (a.role !== b.role) return a.role === "admin" ? -1 : 1
    return a.createdAt - b.createdAt
  }),
)

function fmtDate(ts: number) {
  return new Date(ts).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" })
}
</script>

<template>
  <Panel title="账号管理" desc="添加或维护登录账号。只有「管理员」角色且启用的账号才能进入管理后台。">
    <template #action>
      <button
        v-if="!showAdd"
        type="button"
        class="btn btn-primary btn-sm"
        @click="showAdd = true"
      >
        <Plus class="h-3.5 w-3.5" />
        添加账号
      </button>
    </template>

    <!-- 新增表单 -->
    <div v-if="showAdd" class="mb-4 rounded-2xl border border-dashed border-border bg-muted/20 p-4">
      <div class="flex items-center justify-between">
        <p class="text-sm font-semibold text-foreground">新增账号</p>
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
          <span class="text-xs font-medium text-muted-foreground">用户名（登录用）</span>
          <input
            v-model="draft.username"
            type="text"
            placeholder="如 zhangsan"
            class="field"
          />
        </label>
        <label class="flex flex-col gap-1.5">
          <span class="text-xs font-medium text-muted-foreground">显示名称</span>
          <input
            v-model="draft.name"
            type="text"
            placeholder="如 张三"
            class="field"
          />
        </label>
        <label class="flex flex-col gap-1.5">
          <span class="text-xs font-medium text-muted-foreground">初始密码（至少 6 位）</span>
          <input
            v-model="draft.password"
            type="text"
            placeholder="至少 6 位"
            class="field"
          />
        </label>
        <label class="flex flex-col gap-1.5">
          <span class="text-xs font-medium text-muted-foreground">角色</span>
          <div class="flex gap-2">
            <button
              v-for="r in (['admin', 'member'] as AccountRole[])"
              :key="r"
              type="button"
              class="flex-1 rounded-xl border px-3 py-2 text-xs font-medium transition-colors"
              :class="
                draft.role === r
                  ? 'border-brand bg-brand/10 text-brand'
                  : 'border-border bg-card text-muted-foreground hover:bg-muted'
              "
              @click="draft.role = r"
            >
              {{ r === "admin" ? "管理员" : "普通成员" }}
            </button>
          </div>
        </label>
      </div>

      <p v-if="addError" class="mt-2 text-xs font-medium text-destructive">{{ addError }}</p>

      <div class="mt-3 flex justify-end">
        <button
          type="button"
          class="btn btn-primary btn-sm"
          @click="submitAdd"
        >
          创建账号
        </button>
      </div>
    </div>

    <!-- 账号列表 -->
    <ul class="flex flex-col gap-2.5">
      <li
        v-for="acc in sorted"
        :key="acc.id"
        class="neu-inset p-4"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex min-w-0 items-center gap-3">
            <span
              class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
              :class="acc.role === 'admin' ? 'bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'"
            >
              <ShieldCheck v-if="acc.role === 'admin'" class="h-5 w-5" />
              <User v-else class="h-5 w-5" />
            </span>
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <p class="truncate text-sm font-semibold text-card-foreground">{{ acc.name }}</p>
                <span
                  class="rounded-full px-2 py-0.5 text-[0.65rem] font-medium"
                  :class="acc.role === 'admin' ? 'bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'"
                >
                  {{ acc.role === "admin" ? "管理员" : "普通成员" }}
                </span>
                <span
                  v-if="!acc.enabled"
                  class="rounded-full bg-destructive/10 px-2 py-0.5 text-[0.65rem] font-medium text-destructive"
                >
                  已停用
                </span>
                <span
                  v-if="acc.id === currentUser?.id"
                  class="rounded-full bg-accent/15 px-2 py-0.5 text-[0.65rem] font-medium text-accent"
                >
                  当前登录
                </span>
              </div>
              <p class="mt-0.5 truncate text-xs text-muted-foreground">
                @{{ acc.username }} · 创建于 {{ fmtDate(acc.createdAt) }}
              </p>
            </div>
          </div>

          <div class="flex items-center gap-1.5">
            <button
              type="button"
              class="flex items-center gap-1 rounded-xl border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
              @click="toggleRole(acc.id, acc.role)"
            >
              <UserCog class="h-3.5 w-3.5" />
              {{ acc.role === "admin" ? "设为成员" : "设为管理员" }}
            </button>
            <button
              type="button"
              class="rounded-xl border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
              @click="toggleEnabled(acc.id, acc.enabled)"
            >
              {{ acc.enabled ? "停用" : "启用" }}
            </button>
            <button
              type="button"
              aria-label="重置密码"
              class="flex h-8 w-8 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:bg-muted"
              @click="startReset(acc.id)"
            >
              <KeyRound class="h-3.5 w-3.5" />
            </button>
            <button
              v-if="acc.id !== currentUser?.id"
              type="button"
              aria-label="删除账号"
              class="flex h-8 w-8 items-center justify-center rounded-xl border border-destructive/40 text-destructive transition-colors hover:bg-destructive/10"
              @click="confirmDeleteId = acc.id"
            >
              <Trash2 class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <!-- 重置密码行内表单 -->
        <div v-if="resettingId === acc.id" class="mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-muted/40 p-3">
          <span class="text-xs font-medium text-foreground">新密码</span>
          <input
            v-model="newPwd"
            type="text"
            placeholder="至少 6 位"
            class="min-w-0 flex-1 field py-1.5"
          />
          <button
            type="button"
            class="btn btn-primary btn-sm"
            @click="saveReset(acc.id)"
          >
            保存
          </button>
          <button
            type="button"
            class="rounded-xl border border-border px-3 py-1.5 text-xs text-muted-foreground"
            @click="resettingId = null"
          >
            取消
          </button>
        </div>

        <!-- 删除确认 -->
        <div
          v-if="confirmDeleteId === acc.id"
          class="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-3"
        >
          <span class="text-xs text-foreground">确认删除账号「{{ acc.name }}」？此操作不可恢复。</span>
          <button
            type="button"
            class="rounded-xl bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground"
            @click="remove(acc.id)"
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

        <p v-if="rowError[acc.id]" class="mt-2 text-xs font-medium text-destructive">{{ rowError[acc.id] }}</p>
      </li>
    </ul>
  </Panel>
</template>
