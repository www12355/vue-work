<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import type { ComboCtx } from "@/components/apps/combo/state"

defineProps<{ ctx: ComboCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label">
    <div class="flex flex-col gap-3">
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        <span>项目名称 <span class="text-brand">*</span></span>
        <input
          v-model="ctx.s.projectName"
          placeholder="例如：智慧园区管理平台建设项目"
          class="rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        输入文本（未上传文件时必填）
        <textarea
          v-model="ctx.s.notes"
          rows="6"
          placeholder="粘贴会议记录、需求说明或方案要点…"
          class="resize-y rounded-xl border border-border bg-background px-3 py-2.5 text-sm leading-relaxed text-foreground outline-none ring-ring/50 focus:ring-2"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs text-muted-foreground">
        项目周期天数
        <input
          v-model.number="ctx.s.durationDays"
          type="number"
          min="1"
          class="w-28 rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
        />
      </label>
    </div>
  </SectionCard>
</template>
