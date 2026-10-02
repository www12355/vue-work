<script setup lang="ts">
/**
 * 区块类型专属选项编辑器：
 * - upload：上传提示文案、接受格式（展示 + accept）、是否多选
 * - result：空状态文案、结果区最小高度
 * 表单字段区块（form）的字段仍由 LayoutEditor 内的 FieldEditor 维护。
 */
import { computed } from "vue"
import { updateSection } from "@/stores/registry"
import { sectionKind, type SectionConfig, type UploadConfig, type ResultConfig } from "@/data/registry-defaults"

const props = defineProps<{ ownerId: string; section: SectionConfig }>()

const kind = computed(() => sectionKind(props.section))
const upload = computed<UploadConfig>(() => props.section.upload ?? {})
const result = computed<ResultConfig>(() => props.section.result ?? {})

function patchUpload(patch: Partial<UploadConfig>) {
  updateSection(props.ownerId, props.section.id, { upload: { ...upload.value, ...patch } })
}
function patchResult(patch: Partial<ResultConfig>) {
  updateSection(props.ownerId, props.section.id, { result: { ...result.value, ...patch } })
}
</script>

<template>
  <!-- 文件上传区块选项 -->
  <div v-if="kind === 'upload'" class="neu-inset flex flex-col gap-2 p-3">
    <label class="flex flex-col gap-1 text-xs text-muted-foreground">
      上传框提示文案
      <input
        :value="upload.hint ?? ''"
        placeholder="点击选择文件"
        class="field px-2.5 py-1.5"
        @input="patchUpload({ hint: ($event.target as HTMLInputElement).value })"
      />
    </label>
    <label class="flex flex-col gap-1 text-xs text-muted-foreground">
      接受格式（展示文案）
      <input
        :value="upload.formats ?? ''"
        placeholder="DOCX / PDF / Markdown"
        class="field px-2.5 py-1.5"
        @input="patchUpload({ formats: ($event.target as HTMLInputElement).value })"
      />
    </label>
    <label class="flex flex-col gap-1 text-xs text-muted-foreground">
      accept 属性（文件选择过滤）
      <input
        :value="upload.accept ?? ''"
        placeholder=".doc,.docx,.pdf,.md"
        class="field px-2.5 py-1.5"
        @input="patchUpload({ accept: ($event.target as HTMLInputElement).value })"
      />
    </label>
    <button
      type="button"
      class="flex items-center gap-1.5 self-start rounded-xl border px-2.5 py-1.5 text-xs transition-colors"
      :class="upload.multiple !== false ? 'border-brand bg-brand/10 text-brand' : 'border-border text-muted-foreground hover:bg-muted'"
      :aria-pressed="upload.multiple !== false"
      @click="patchUpload({ multiple: !(upload.multiple !== false) })"
    >
      允许多选文件
    </button>
  </div>

  <!-- 生成结果区块选项 -->
  <div v-else-if="kind === 'result'" class="neu-inset flex flex-col gap-2 p-3">
    <label class="flex flex-col gap-1 text-xs text-muted-foreground">
      空状态提示文案
      <input
        :value="result.emptyHint ?? ''"
        placeholder="填写表单后点击底部按钮生成"
        class="field px-2.5 py-1.5"
        @input="patchResult({ emptyHint: ($event.target as HTMLInputElement).value })"
      />
    </label>
    <label class="flex flex-col gap-1 text-xs text-muted-foreground">
      结果区最小高度（px）
      <input
        type="number"
        min="120"
        step="20"
        :value="result.minHeight ?? 220"
        class="field px-2.5 py-1.5"
        @input="patchResult({ minHeight: Number(($event.target as HTMLInputElement).value) || 220 })"
      />
    </label>
  </div>
</template>
