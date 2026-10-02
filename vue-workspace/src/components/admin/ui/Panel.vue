<script setup lang="ts">
withDefaults(defineProps<{ title: string; desc?: string }>(), { desc: "" })
</script>

<template>
  <section class="ios-card p-5">
    <header class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 class="text-base font-bold text-card-foreground">{{ title }}</h2>
        <p v-if="desc" class="mt-1 text-xs leading-relaxed text-muted-foreground">{{ desc }}</p>
      </div>
      <div v-if="$slots.action" class="flex shrink-0 items-center gap-2">
        <slot name="action" />
      </div>
    </header>

    <div class="mt-4">
      <slot />
    </div>
  </section>
</template>
