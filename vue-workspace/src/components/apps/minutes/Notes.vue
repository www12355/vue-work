<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import type { MinutesCtx } from "@/components/apps/minutes/state"

defineProps<{ ctx: MinutesCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label">
    <textarea
      v-model="ctx.s.notes"
      rows="12"
      placeholder="粘贴会议录音转写文字或速记内容…"
      class="w-full resize-y rounded-xl border border-border bg-background px-3 py-2.5 text-sm leading-relaxed text-foreground outline-none ring-ring/50 focus:ring-2"
    />
  </SectionCard>
</template>
