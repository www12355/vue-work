<script setup lang="ts">
import { ArrowDown, Check, Loader2 } from "lucide-vue-next"
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import { iconOf } from "@/data/icons"
import type { ComboCtx } from "@/components/apps/combo/state"

defineProps<{ ctx: ComboCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label">
    <div class="flex flex-col">
      <template v-for="(st, i) in ctx.stages" :key="st.id">
        <div
          class="flex items-start gap-3 rounded-xl border p-3 transition-colors"
          :class="
            ctx.stageState(i) === 'done'
              ? 'border-accent/50 bg-accent/10'
              : ctx.stageState(i) === 'running'
                ? 'border-brand bg-brand/5'
                : 'border-border bg-card'
          "
        >
          <span
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl"
            :class="
              ctx.stageState(i) === 'done'
                ? 'bg-accent/20 text-accent'
                : ctx.stageState(i) === 'running'
                  ? 'bg-brand text-brand-foreground'
                  : 'bg-muted text-muted-foreground'
            "
          >
            <Check v-if="ctx.stageState(i) === 'done'" class="h-4 w-4" />
            <Loader2 v-else-if="ctx.stageState(i) === 'running'" class="h-4 w-4 animate-spin" />
            <component :is="iconOf(st.icon)" v-else class="h-4 w-4" />
          </span>
          <div class="min-w-0">
            <p class="text-sm font-semibold text-card-foreground">{{ st.label }}</p>
            <p class="mt-0.5 text-xs text-muted-foreground">{{ st.desc }}</p>
          </div>
        </div>
        <ArrowDown
          v-if="i < ctx.stages.length - 1"
          class="mx-auto my-1 h-4 w-4 text-muted-foreground"
        />
      </template>
    </div>
  </SectionCard>
</template>
