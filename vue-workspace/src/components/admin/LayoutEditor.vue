<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeftRight, ChevronDown, ChevronUp, Eye, EyeOff, Plus, Trash2 } from "lucide-vue-next"
import FieldEditor from "@/components/admin/FieldEditor.vue"
import SectionOptionsEditor from "@/components/admin/SectionOptionsEditor.vue"
import {
  addField,
  addSection,
  canEditStructure,
  deleteSection,
  getOwner,
  moveSection,
  toggleSection,
  updateSection,
} from "@/stores/registry"
import {
  sectionKind,
  SECTION_KIND_LABEL,
  type SectionConfig,
  type SectionKind,
} from "@/data/registry-defaults"

const props = defineProps<{ ownerId: string }>()

const owner = computed(() => getOwner(props.ownerId))
const editable = computed(() => canEditStructure(props.ownerId))

const COLUMNS = [
  { key: "left", label: "左栏" },
  { key: "right", label: "右栏" },
] as const

/** 新增区块时可选的类型 */
const ADD_KINDS: { kind: SectionKind; label: string }[] = [
  { kind: "form", label: "表单字段" },
  { kind: "upload", label: "文件上传" },
  { kind: "result", label: "生成结果" },
]

/** 记录哪个「添加区块」菜单展开（按列区分） */
const openMenu = ref<"left" | "right" | null>(null)

function sectionsIn(column: "left" | "right"): SectionConfig[] {
  return (owner.value?.sections ?? []).filter((s) => s.column === column)
}

function addWith(column: "left" | "right", kind: SectionKind) {
  addSection(props.ownerId, column, kind)
  openMenu.value = null
}

/** 切换所在列：实现「把区块搬到另一栏」 */
function swapColumn(section: SectionConfig) {
  updateSection(props.ownerId, section.id, { column: section.column === "left" ? "right" : "left" })
}

const kindOf = (s: SectionConfig) => sectionKind(s)
</script>

<template>
  <div v-if="owner" class="flex flex-col gap-4">
    <p class="text-xs leading-relaxed text-muted-foreground">
      调整区块的类型、显隐、标题、说明、所在栏与上下顺序，弹窗页面会立即按此布局渲染。
      {{
        editable
          ? "后台新增模块可添加「表单字段 / 文件上传 / 生成结果」三类区块，并配置各自的表单字段、上传格式与结果提示。"
          : "内置模块的区块结构固定，仅可调整布局与标题。"
      }}
    </p>

    <!-- 左右栏宽度比与真实弹窗一致（左 1 : 右 1.25），所见即所得 -->
    <div class="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
      <div v-for="col in COLUMNS" :key="col.key" class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <h4 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{{ col.label }}</h4>

          <!-- 新增区块：可选类型 -->
          <div v-if="editable" class="relative">
            <button
              type="button"
              class="flex items-center gap-1 rounded-xl border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted"
              :aria-expanded="openMenu === col.key"
              @click="openMenu = openMenu === col.key ? null : col.key"
            >
              <Plus class="h-3 w-3" />
              添加区块
            </button>
            <div
              v-if="openMenu === col.key"
              class="absolute right-0 z-10 mt-1 flex w-32 flex-col overflow-hidden rounded-xl border border-border bg-popover shadow-lg"
            >
              <button
                v-for="k in ADD_KINDS"
                :key="k.kind"
                type="button"
                class="px-3 py-2 text-left text-xs text-popover-foreground transition-colors hover:bg-muted"
                @click="addWith(col.key, k.kind)"
              >
                {{ k.label }}
              </button>
            </div>
          </div>
        </div>

        <p
          v-if="!sectionsIn(col.key).length"
          class="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground"
        >
          该栏暂无区块
        </p>

        <div
          v-for="section in sectionsIn(col.key)"
          :key="section.id"
          class="flex flex-col gap-2 rounded-xl border p-3 transition-colors"
          :class="section.visible ? 'border-border bg-background' : 'border-dashed border-border bg-muted/50'"
        >
          <div class="flex items-center gap-1.5">
            <span
              class="shrink-0 rounded-xl bg-muted px-1.5 py-0.5 text-[0.65rem] font-medium text-muted-foreground"
            >
              {{ SECTION_KIND_LABEL[kindOf(section)] }}
            </span>
            <input
              :value="section.label"
              :aria-label="`区块标题：${section.label}`"
              class="field min-w-0 flex-1 px-2.5 py-1.5 font-medium"
              :class="section.visible ? '' : 'text-muted-foreground'"
              @input="updateSection(ownerId, section.id, { label: ($event.target as HTMLInputElement).value })"
            />
            <button
              type="button"
              :aria-label="`${section.visible ? '隐藏' : '显示'}区块：${section.label}`"
              :aria-pressed="!section.visible"
              class="flex h-8 w-8 items-center justify-center rounded-xl transition-colors"
              :class="section.visible ? 'text-brand hover:bg-brand/10' : 'text-muted-foreground hover:bg-muted'"
              @click="toggleSection(ownerId, section.id)"
            >
              <Eye v-if="section.visible" class="h-4 w-4" />
              <EyeOff v-else class="h-4 w-4" />
            </button>
          </div>

          <!-- 区块说明文字（可选） -->
          <input
            :value="section.description ?? ''"
            placeholder="区块说明文字（可选，展示在区块标题下）"
            class="field px-2.5 py-1.5 text-xs"
            @input="updateSection(ownerId, section.id, { description: ($event.target as HTMLInputElement).value })"
          />

          <div class="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              :aria-label="`上移区块：${section.label}`"
              class="flex h-7 w-7 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:bg-muted"
              @click="moveSection(ownerId, section.id, -1)"
            >
              <ChevronUp class="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              :aria-label="`下移区块：${section.label}`"
              class="flex h-7 w-7 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:bg-muted"
              @click="moveSection(ownerId, section.id, 1)"
            >
              <ChevronDown class="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              :aria-label="`将区块「${section.label}」移到${section.column === 'left' ? '右' : '左'}栏`"
              class="flex items-center gap-1 rounded-xl border border-border px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted"
              @click="swapColumn(section)"
            >
              <ArrowLeftRight class="h-3 w-3" />
              移到{{ section.column === "left" ? "右" : "左" }}栏
            </button>
            <button
              v-if="editable"
              type="button"
              :aria-label="`删除区块：${section.label}`"
              class="ml-auto flex h-7 w-7 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
              @click="deleteSection(ownerId, section.id)"
            >
              <Trash2 class="h-3.5 w-3.5" />
            </button>
          </div>

          <!-- 表单字段区块：字段可增删改 -->
          <div v-if="editable && kindOf(section) === 'form'" class="flex flex-col gap-2">
            <FieldEditor
              v-for="f in section.fields ?? []"
              :key="f.id"
              :owner-id="ownerId"
              :section-id="section.id"
              :field="f"
            />
            <button
              type="button"
              class="flex items-center justify-center gap-1 rounded-xl border border-dashed border-border py-2 text-xs text-muted-foreground transition-colors hover:bg-muted"
              @click="addField(ownerId, section.id)"
            >
              <Plus class="h-3 w-3" />
              添加字段
            </button>
          </div>

          <!-- 上传 / 结果区块：类型专属选项 -->
          <SectionOptionsEditor
            v-else-if="editable && kindOf(section) !== 'form'"
            :owner-id="ownerId"
            :section="section"
          />
        </div>
      </div>
    </div>
  </div>
</template>
