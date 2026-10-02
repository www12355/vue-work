<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    hint?: string
    /** 单行输入 / 多行文本 */
    type?: "text" | "textarea" | "number"
    placeholder?: string
    rows?: number
  }>(),
  { hint: "", type: "text", placeholder: "", rows: 3 },
)

const model = defineModel<string | number>({ default: "" })
</script>

<template>
  <label class="flex flex-col gap-1.5">
    <span class="text-xs font-medium text-muted-foreground">{{ label }}</span>
    <textarea
      v-if="type === 'textarea'"
      v-model="model"
      :rows="rows"
      :placeholder="placeholder"
      class="w-full field resize-y"
    />
    <input
      v-else
      v-model="model"
      :type="type"
      :placeholder="placeholder"
      class="w-full field"
    />
    <span v-if="hint" class="text-xs text-muted-foreground/80">{{ hint }}</span>
  </label>
</template>
