<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import type { MinutesCtx } from "@/components/apps/minutes/state"

defineProps<{ ctx: MinutesCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label">
    <input
      v-model="ctx.s.topic"
      placeholder="例如：Q3 产品规划评审会"
      class="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
    />
  </SectionCard>
</template>
