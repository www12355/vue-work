<script setup lang="ts">
import { Minus, Plus } from "lucide-vue-next"
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import { DURATION_UNITS, type ContractCtx } from "@/components/apps/contract/state"

const props = defineProps<{ ctx: ContractCtx; label: string; sectionId?: string }>()
const field =
  "rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
const readonlyField = "rounded-xl border border-border bg-muted px-3 py-2.5 text-sm text-muted-foreground"
</script>

<template>
  <SectionCard :title="label || '服务期限'">
    <div class="flex flex-col gap-3">
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        服务开始时间
        <input v-model="props.ctx.s.startDate" type="date" :class="field" />
      </label>

      <div class="flex flex-col gap-1 text-xs text-muted-foreground">
        服务时长
        <div class="grid grid-cols-3 gap-2">
          <div
            v-for="unit in DURATION_UNITS"
            :key="unit.key"
            class="flex items-center justify-between rounded-xl border border-border bg-background px-2 py-1.5"
          >
            <button
              class="flex h-6 w-6 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"
              :aria-label="`减少${unit.label}`"
              @click="props.ctx.step(unit.key, -1)"
            >
              <Minus class="h-3.5 w-3.5" />
            </button>
            <span class="text-sm font-semibold text-foreground">{{ props.ctx.s.duration[unit.key] }}</span>
            <span class="text-xs text-muted-foreground">{{ unit.label }}</span>
            <button
              class="flex h-6 w-6 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"
              :aria-label="`增加${unit.label}`"
              @click="props.ctx.step(unit.key, 1)"
            >
              <Plus class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        时长预览
        <input :value="props.ctx.durationText" readonly :class="readonlyField" />
      </label>
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        预计结束时间
        <input
          :value="props.ctx.endDate"
          readonly
          class="rounded-xl border border-border bg-background px-3 py-2.5 text-sm font-semibold text-accent"
        />
      </label>
    </div>
  </SectionCard>
</template>
