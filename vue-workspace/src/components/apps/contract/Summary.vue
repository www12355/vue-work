<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import type { ContractCtx } from "@/components/apps/contract/state"

defineProps<{ ctx: ContractCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label">
    <template #action>
      <button type="button" class="text-xs text-brand underline underline-offset-4">历史记录</button>
    </template>

    <dl class="flex flex-col">
      <div
        v-for="row in ctx.summary"
        :key="row.label"
        class="flex items-center justify-between gap-3 border-b border-border/60 py-2 text-sm last:border-b-0"
      >
        <dt class="shrink-0 text-muted-foreground">{{ row.label }}</dt>
        <dd class="min-w-0 truncate text-right font-medium text-card-foreground">{{ row.value }}</dd>
      </div>
    </dl>
  </SectionCard>
</template>
