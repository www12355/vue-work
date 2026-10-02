<script setup lang="ts">
import { Trash2 } from "lucide-vue-next"
import { deleteField, updateField } from "@/stores/registry"
import type { FieldConfig } from "@/data/registry-defaults"

const props = defineProps<{ ownerId: string; sectionId: string; field: FieldConfig }>()

const TYPES = [
  { value: "text", label: "单行文本" },
  { value: "textarea", label: "多行文本" },
  { value: "number", label: "数字" },
  { value: "date", label: "日期" },
  { value: "select", label: "下拉选择" },
] as const

function patch(key: keyof FieldConfig, value: unknown) {
  updateField(props.ownerId, props.sectionId, props.field.id, { [key]: value } as Partial<FieldConfig>)
}
</script>

<template>
  <div class="neu-inset flex flex-col gap-2 p-3">
    <div class="flex flex-wrap items-center gap-2">
      <input
        :value="field.label"
        placeholder="字段名称"
        class="field min-w-0 flex-1 px-2.5 py-1.5"
        @input="patch('label', ($event.target as HTMLInputElement).value)"
      />
      <select
        :value="field.type"
        class="field px-2 py-1.5 text-xs"
        @change="patch('type', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="t in TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
      <button
        type="button"
        class="flex items-center gap-1 rounded-xl border border-border px-2 py-1.5 text-xs transition-colors"
        :class="field.required ? 'border-brand bg-brand/10 text-brand' : 'text-muted-foreground hover:bg-muted'"
        :aria-pressed="!!field.required"
        @click="patch('required', !field.required)"
      >
        必填
      </button>
      <button
        type="button"
        aria-label="删除字段"
        class="flex h-8 w-8 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        @click="deleteField(ownerId, sectionId, field.id)"
      >
        <Trash2 class="h-3.5 w-3.5" />
      </button>
    </div>

    <input
      :value="field.placeholder ?? ''"
      placeholder="输入框提示文案（可选）"
      class="field px-2.5 py-1.5 text-xs"
      @input="patch('placeholder', ($event.target as HTMLInputElement).value)"
    />

    <input
      v-if="field.type === 'select'"
      :value="(field.options ?? []).join('、')"
      placeholder="下拉选项，用「、」分隔"
      class="field px-2.5 py-1.5 text-xs"
      @input="
        patch(
          'options',
          ($event.target as HTMLInputElement).value
            .split(/[、,，]/)
            .map((v) => v.trim())
            .filter(Boolean),
        )
      "
    />
  </div>
</template>
