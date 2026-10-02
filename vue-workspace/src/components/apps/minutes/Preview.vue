<script setup lang="ts">
import { ClipboardList } from "lucide-vue-next"
import ResultPanel from "@/components/apps/ResultPanel.vue"
import type { MinutesCtx } from "@/components/apps/minutes/state"

defineProps<{ ctx: MinutesCtx; label: string }>()
</script>

<template>
  <ResultPanel :label="label" :result="ctx.s.result" class="min-h-[320px]">
    <template #empty>
      <ClipboardList class="h-8 w-8 opacity-40" />
      <p class="text-sm">粘贴会议记录后点击生成，纪要将显示在这里</p>
    </template>
  </ResultPanel>
</template>
