<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import { iconOf } from "@/data/icons"
import type { ComboCtx } from "@/components/apps/combo/state"

defineProps<{ ctx: ComboCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label">
    <div class="flex flex-wrap gap-2">
      <button
        v-for="st in ctx.stages"
        :key="st.id"
        type="button"
        class="flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-medium transition-colors"
        :class="
          ctx.selectedOutputs.includes(st.id)
            ? 'border-brand bg-brand/10 text-brand'
            : 'border-border text-muted-foreground hover:bg-muted'
        "
        :aria-label="`${ctx.selectedOutputs.includes(st.id) ? '取消导出' : '导出'} ${st.output}`"
        :aria-pressed="ctx.selectedOutputs.includes(st.id)"
        @click="ctx.toggleOutput(st.id)"
      >
        <component :is="iconOf(st.icon)" class="h-3.5 w-3.5" />
        {{ st.output }}
      </button>
    </div>
  </SectionCard>
</template>
