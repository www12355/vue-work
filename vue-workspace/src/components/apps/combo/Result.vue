<script setup lang="ts">
import { Download, Layers } from "lucide-vue-next"
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import type { ComboCtx } from "@/components/apps/combo/state"

defineProps<{ ctx: ComboCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label">
    <template v-if="ctx.hasResult" #action>
      <button
        type="button"
        class="flex items-center gap-1 rounded-xl border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
      >
        <Download class="h-3.5 w-3.5" />
        导出全部
      </button>
    </template>

    <div v-if="ctx.hasResult" class="flex flex-col gap-2">
      <div class="flex flex-wrap gap-2" role="tablist" aria-label="阶段产出">
        <button
          v-for="st in ctx.stages"
          :key="st.id"
          type="button"
          role="tab"
          :id="`combo-tab-${st.id}`"
          :aria-selected="ctx.tab === st.id"
          :aria-controls="`combo-panel-${st.id}`"
          :aria-label="`查看产出内容：${st.output}`"
          class="rounded-xl px-3 py-1.5 text-xs font-semibold transition-colors"
          :class="ctx.tab === st.id ? 'bg-brand text-brand-foreground' : 'bg-muted text-muted-foreground'"
          @click="ctx.tab = st.id"
        >
          {{ st.output }}
        </button>
      </div>
      <pre
        role="tabpanel"
        :id="`combo-panel-${ctx.tab}`"
        :aria-labelledby="`combo-tab-${ctx.tab}`"
        tabindex="0"
        class="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-muted p-3 text-xs leading-relaxed text-foreground"
        >{{ ctx.activeText || "该阶段仍在生成…" }}</pre
      >
    </div>

    <div v-else class="flex flex-col items-center gap-2 py-8 text-muted-foreground">
      <Layers class="h-7 w-7 opacity-40" />
      <p class="text-xs">运行流水线后，各阶段产出将分别显示在这里</p>
    </div>
  </SectionCard>
</template>
