<script setup lang="ts">
defineProps<{ label: string; hint?: string }>()

const model = defineModel<boolean>({ default: false })
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="model"
    class="neu-inset flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition-colors"
    @click="model = !model"
  >
    <span class="min-w-0">
      <span class="block text-sm font-medium text-foreground">{{ label }}</span>
      <span v-if="hint" class="mt-0.5 block text-xs text-muted-foreground">{{ hint }}</span>
    </span>
    <span
      class="relative h-5 w-9 shrink-0 rounded-full transition-colors"
      :class="model ? 'bg-brand' : 'bg-border'"
    >
      <span
        class="absolute top-0.5 h-4 w-4 rounded-full bg-card transition-all"
        :class="model ? 'left-[1.125rem]' : 'left-0.5'"
      />
    </span>
  </button>
</template>
