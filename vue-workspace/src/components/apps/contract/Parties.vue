<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import type { ContractCtx } from "@/components/apps/contract/state"

const props = defineProps<{ ctx: ContractCtx; label: string; sectionId?: string }>()
const field =
  "rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
</script>

<template>
  <SectionCard :title="label || '甲乙方信息'">
    <div class="flex flex-col gap-3">
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        <span>甲方（委托方） <span class="text-brand">*</span></span>
        <input v-model="props.ctx.s.partyA" :class="field" />
      </label>
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        <span>乙方（服务方） <span class="text-brand">*</span></span>
        <input v-model="props.ctx.s.partyB" :class="field" />
      </label>
    </div>
  </SectionCard>
</template>
