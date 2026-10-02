<script setup lang="ts">
import { ICON_OPTIONS, iconOf } from "@/data/icons"

defineProps<{ label: string }>()

const model = defineModel<string>({ default: "Sparkles" })
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <span class="text-xs font-medium text-muted-foreground">{{ label }}</span>
    <div class="flex flex-wrap gap-2">
      <button
        v-for="name in ICON_OPTIONS"
        :key="name"
        type="button"
        :aria-label="name"
        :aria-pressed="model === name"
        class="flex h-9 w-9 items-center justify-center rounded-xl border transition-colors"
        :class="
          model === name
            ? 'border-brand bg-brand/10 text-brand'
            : 'border-border text-muted-foreground hover:bg-muted'
        "
        @click="model = name"
      >
        <component :is="iconOf(name)" class="h-4 w-4" />
      </button>
    </div>
  </div>
</template>
