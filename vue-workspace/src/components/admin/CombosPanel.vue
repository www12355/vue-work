<script setup lang="ts">
import { ref } from "vue"
import { ChevronDown, Link2, Plus, Settings2, Trash2 } from "lucide-vue-next"
import Panel from "@/components/admin/ui/Panel.vue"
import Field from "@/components/admin/ui/Field.vue"
import Toggle from "@/components/admin/ui/Toggle.vue"
import LayoutEditor from "@/components/admin/LayoutEditor.vue"
import ComboFlow from "@/components/admin/ComboFlow.vue"
import {
  combinableModules,
  combos,
  createCombo,
  deleteCombo,
  getModule,
  updateCombo,
  updateStage,
} from "@/stores/registry"
import {
  MAX_COMBO_MEMBERS,
  MIN_COMBO_MEMBERS,
  type ComboConfig,
  type StageConfig,
} from "@/data/registry-defaults"
import { iconOf } from "@/data/icons"

const openId = ref<string | null>(null)

/* ---- 自定义新建组合 ---- */
const picked = ref<string[]>([]) // 已选模块 id，顺序即流水线顺序
const customName = ref("")
const createError = ref("")

function togglePick(id: string) {
  createError.value = ""
  const i = picked.value.indexOf(id)
  if (i >= 0) {
    picked.value.splice(i, 1)
  } else {
    if (picked.value.length >= MAX_COMBO_MEMBERS) {
      createError.value = `最多串联 ${MAX_COMBO_MEMBERS} 个模块`
      return
    }
    picked.value.push(id)
  }
}

function pickIndex(id: string) {
  return picked.value.indexOf(id)
}

function createCustom() {
  if (picked.value.length < MIN_COMBO_MEMBERS) {
    createError.value = `至少选择 ${MIN_COMBO_MEMBERS} 个模块`
    return
  }
  const combo = createCombo(...picked.value)
  if (!combo) {
    createError.value = "相同模块组合已存在，请调整所选模块"
    return
  }
  const name = customName.value.trim()
  if (name) updateCombo(combo.id, { title: name })
  openId.value = combo.id
  picked.value = []
  customName.value = ""
  createError.value = ""
}

function patch(id: string, key: keyof ComboConfig, value: unknown) {
  updateCombo(id, { [key]: value } as Partial<ComboConfig>)
}

function patchStage(comboId: string, stageId: string, key: keyof StageConfig, value: unknown) {
  updateStage(comboId, stageId, { [key]: value } as Partial<StageConfig>)
}

function memberTitle(id: string) {
  return getModule(id)?.title ?? "（已删除模块）"
}

function membersText(combo: ComboConfig) {
  return combo.members.map(memberTitle).join(" → ")
}
</script>

<template>
  <Panel
    title="组合规则"
    desc="以连线的方式编排模块流水线：每条组合最多串联 4 个模块，节点按箭头方向依次执行、一次输入产出多份文档。拖动节点可调整顺序，点「添加节点」接入更多模块。"
  >
    <div class="flex flex-col gap-4">
      <!-- 自定义新建组合流程 -->
      <div class="rounded-2xl border border-dashed border-border bg-muted/20 p-4">
        <div class="flex items-center gap-2">
          <span class="flex h-7 w-7 items-center justify-center rounded-xl bg-brand/10 text-brand">
            <Plus class="h-4 w-4" />
          </span>
          <p class="text-sm font-semibold text-foreground">自定义新建组合</p>
        </div>
        <p class="mt-1 text-xs text-muted-foreground">
          按需勾选 {{ MIN_COMBO_MEMBERS }} ~ {{ MAX_COMBO_MEMBERS }} 个模块自由组合，点击顺序即流水线执行顺序；也可填写自定义名称。
        </p>

        <!-- 模块选择器 -->
        <div v-if="combinableModules.length" class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="mod in combinableModules"
            :key="mod.id"
            type="button"
            class="flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition-colors"
            :class="
              pickIndex(mod.id) >= 0
                ? 'border-brand bg-brand/10 text-brand'
                : 'border-border bg-card text-foreground hover:border-brand hover:bg-brand/5'
            "
            :aria-pressed="pickIndex(mod.id) >= 0"
            @click="togglePick(mod.id)"
          >
            <span
              v-if="pickIndex(mod.id) >= 0"
              class="flex h-4 w-4 items-center justify-center rounded-full bg-brand text-[0.6rem] font-bold text-brand-foreground"
            >
              {{ pickIndex(mod.id) + 1 }}
            </span>
            <component v-else :is="iconOf(mod.icon)" class="h-3.5 w-3.5 text-muted-foreground" />
            {{ mod.title }}
          </button>
        </div>
        <p v-else class="mt-3 text-xs text-muted-foreground">
          暂无可组合的模块，请先在「模块管理」中上线并允许组合的模块。
        </p>

        <!-- 名称 + 创建 -->
        <div v-if="combinableModules.length" class="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            v-model="customName"
            type="text"
            placeholder="组合名称（可选，默认自动命名）"
            class="field min-w-0 flex-1"
          />
          <div class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">已选 {{ picked.length }} / {{ MAX_COMBO_MEMBERS }}</span>
            <button
              type="button"
              class="btn btn-primary btn-sm"
              :disabled="picked.length < MIN_COMBO_MEMBERS"
              @click="createCustom"
            >
              <Plus class="h-3.5 w-3.5" />
              创建组合流程
            </button>
          </div>
        </div>

        <p v-if="createError" class="mt-2 text-xs font-medium text-destructive">{{ createError }}</p>
      </div>

      <!-- 组合流程列表 -->
      <div v-for="combo in combos" :key="combo.id" class="neu-inset p-4">
        <!-- 流程头部 -->
        <div class="flex flex-wrap items-center gap-3">
          <span
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
            :class="combo.enabled ? 'bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'"
          >
            <component :is="iconOf(combo.icon)" class="h-4 w-4" />
          </span>

          <div class="min-w-0 flex-1">
            <p class="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
              {{ combo.title }}
              <span
                class="rounded-full px-2 py-0.5 text-[0.65rem] font-medium"
                :class="combo.enabled ? 'bg-accent/15 text-accent' : 'bg-muted text-muted-foreground'"
              >
                {{ combo.enabled ? "已启用" : "已停用" }}
              </span>
            </p>
            <p class="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
              <Link2 class="h-3 w-3 shrink-0" />
              <span class="truncate">{{ membersText(combo) }}</span>
              <span class="shrink-0">· {{ combo.members.length }} / {{ MAX_COMBO_MEMBERS }} 个模块</span>
            </p>
          </div>

          <button
            type="button"
            class="flex items-center gap-1 rounded-xl border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
            :aria-expanded="openId === combo.id"
            @click="openId = openId === combo.id ? null : combo.id"
          >
            <Settings2 class="h-3.5 w-3.5" />
            高级配置
            <ChevronDown class="h-3.5 w-3.5 transition-transform" :class="openId === combo.id ? 'rotate-180' : ''" />
          </button>

          <button
            type="button"
            :aria-label="`删除${combo.title}`"
            class="flex h-8 w-8 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
            @click="deleteCombo(combo.id)"
          >
            <Trash2 class="h-3.5 w-3.5" />
          </button>
        </div>

        <!-- 连线画布：主编辑区，始终可见 -->
        <div class="mt-4">
          <ComboFlow :combo="combo" />
        </div>

        <!-- 高级配置（可展开） -->
        <div v-if="openId === combo.id" class="mt-4 flex flex-col gap-4 border-t border-border pt-4">
          <Toggle
            :model-value="combo.enabled"
            label="启用该组合"
            hint="停用后，工作台中这两张卡拖到一起不会触发组合"
            @update:model-value="patch(combo.id, 'enabled', $event)"
          />

          <div class="grid gap-3 md:grid-cols-2">
            <Field
              :model-value="combo.title"
              label="组合名称"
              @update:model-value="patch(combo.id, 'title', $event)"
            />
            <Field
              :model-value="combo.submitLabel"
              label="运行按钮文案"
              @update:model-value="patch(combo.id, 'submitLabel', $event)"
            />
          </div>
          <Field
            :model-value="combo.heroDesc"
            label="工作区主卡片描述"
            type="textarea"
            :rows="2"
            @update:model-value="patch(combo.id, 'heroDesc', $event)"
          />
          <Field
            :model-value="combo.windowDesc"
            label="弹窗顶部说明"
            type="textarea"
            :rows="2"
            @update:model-value="patch(combo.id, 'windowDesc', $event)"
          />

          <!-- 流水线阶段 -->
          <div class="neu-inset p-4">
            <h3 class="text-sm font-bold text-card-foreground">流水线阶段</h3>
            <p class="mt-1 text-xs text-muted-foreground">阶段按顺序串联执行，后一阶段以前一阶段的产出为输入。</p>
            <div class="mt-3 flex flex-col gap-2">
              <div
                v-for="(stage, i) in combo.stages"
                :key="stage.id"
                class="neu-inset flex flex-col gap-2 p-3"
              >
                <p class="text-xs font-semibold text-muted-foreground">阶段 {{ i + 1 }}</p>
                <Field
                  :model-value="stage.label"
                  label="阶段标题"
                  @update:model-value="patchStage(combo.id, stage.id, 'label', $event)"
                />
                <Field
                  :model-value="stage.desc"
                  label="阶段说明"
                  @update:model-value="patchStage(combo.id, stage.id, 'desc', $event)"
                />
                <Field
                  :model-value="stage.output"
                  label="产出文件名"
                  @update:model-value="patchStage(combo.id, stage.id, 'output', $event)"
                />
              </div>
            </div>
          </div>

          <!-- 组合弹窗布局 -->
          <div class="neu-inset p-4">
            <h3 class="text-sm font-bold text-card-foreground">组合弹窗布局</h3>
            <div class="mt-3">
              <LayoutEditor :owner-id="combo.id" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </Panel>
</template>
