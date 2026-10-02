<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import { cn, type ContractCtx } from "@/components/apps/contract/state"

const props = defineProps<{ ctx: ContractCtx; label: string; sectionId?: string }>()
const field =
  "rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
</script>

<template>
  <SectionCard :title="label || '基本信息'">
    <div class="flex flex-col gap-3">
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        合同编号
        <input v-model="props.ctx.s.contractNo" :class="[field, 'text-brand']" />
      </label>
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        <span>项目名称 <span class="text-brand">*</span></span>
        <input
          v-model="props.ctx.s.projectName"
          placeholder="请输入项目名称，例如：智慧城市数据平台建设项目"
          :class="field"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        <span>签订地点 <span class="text-brand">*</span></span>
        <input v-model="props.ctx.s.signPlace" :class="field" />
      </label>
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        签订日期
        <input
          :value="cn(props.ctx.s.today)"
          readonly
          class="rounded-xl border border-border bg-muted px-3 py-2.5 text-sm text-muted-foreground"
        />
      </label>
    </div>
  </SectionCard>
</template>
