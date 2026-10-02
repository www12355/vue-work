<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 卡片标题 */
    title?: string
    /** 标题下方的说明文字 */
    hint?: string
    /** 高亮样式：用于「核心文件」等重点区块 */
    highlight?: boolean
  }>(),
  { title: "", hint: "", highlight: false },
)
</script>

<template>
  <section
    class="rounded-2xl border p-4"
    :class="highlight ? 'border-brand/40 bg-brand/5' : 'border-border bg-card'"
  >
    <header v-if="title || $slots.action" class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 v-if="title" class="text-sm font-semibold text-card-foreground">{{ title }}</h3>
        <p v-if="hint" class="mt-1 text-xs text-muted-foreground">{{ hint }}</p>
      </div>
      <div v-if="$slots.action" class="flex shrink-0 items-center gap-2">
        <slot name="action" />
      </div>
    </header>

    <div :class="title || $slots.action ? 'mt-3' : ''">
      <slot />
    </div>
  </section>
</template>
