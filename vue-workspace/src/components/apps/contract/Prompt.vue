<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import type { ContractCtx } from "@/components/apps/contract/state"

defineProps<{ ctx: ContractCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label">
    <textarea
      v-model="ctx.s.prompt"
      rows="10"
      class="w-full resize-y rounded-xl border border-border bg-background px-3 py-2 text-xs leading-relaxed text-foreground outline-none focus:border-brand"
    />
  </SectionCard>
</template>
