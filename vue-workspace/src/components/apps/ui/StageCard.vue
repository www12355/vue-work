<script setup lang="ts">
/**
 * 单个阶段卡片 — 图标 + 标题 + 状态指示。
 * 状态：pending（灰） / running（品牌色 + 脉冲动画） / completed（绿） / failed（红） / skipped（灰）
 */

import { computed } from "vue"
import {
  Check,
  Loader2,
  XCircle,
  MinusCircle,
  Clock,
} from "lucide-vue-next"
import type { StageState } from "@/services/api/types"

const props = defineProps<{
  stage: StageState
  isCurrent: boolean
}>()

const statusIcon = computed(() => {
  switch (props.stage.status) {
    case "completed": return Check
    case "running": return Loader2
    case "failed": return XCircle
    case "skipped": return MinusCircle
    default: return Clock
  }
})

const statusColor = computed(() => {
  switch (props.stage.status) {
    case "completed": return "text-emerald-500"
    case "running": return "text-brand"
    case "failed": return "text-red-500"
    case "skipped": return "text-muted-foreground/50"
    default: return "text-muted-foreground/60"
  }
})

const statusLabel = computed(() => {
  switch (props.stage.status) {
    case "pending": return "等待中"
    case "running": return "执行中"
    case "completed": return "已完成"
    case "failed": return "失败"
    case "skipped": return "已跳过"
    default: return ""
  }
})
</script>

<template>
  <div
    class="flex items-start gap-3 rounded-xl border p-3 transition-all duration-300"
    :class="[
      isCurrent && stage.status === 'running'
        ? 'border-brand bg-brand/5'
        : stage.status === 'failed'
          ? 'border-red-500/30 bg-red-500/5'
          : stage.status === 'completed'
            ? 'border-emerald-500/20 bg-emerald-500/5'
            : 'border-border bg-card/50',
    ]"
  >
    <div
      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
      :class="[
        stage.status === 'running' ? 'bg-brand/15' : 'bg-muted',
      ]"
    >
      <component
        :is="statusIcon"
        class="h-4 w-4"
        :class="[
          statusColor,
          stage.status === 'running' && 'animate-spin',
        ]"
      />
    </div>

    <div class="min-w-0 flex-1">
      <div class="flex items-center justify-between gap-2">
        <p class="text-sm font-medium text-card-foreground">
          {{ stage.name }}
        </p>
        <span class="shrink-0 text-[11px] font-medium" :class="statusColor">
          {{ statusLabel }}
        </span>
      </div>

      <p
        v-if="stage.message"
        class="mt-0.5 text-xs text-muted-foreground line-clamp-2"
      >
        {{ stage.message }}
      </p>

      <!-- 进度条（仅当前运行阶段） -->
      <div
        v-if="isCurrent && stage.status === 'running'"
        class="mt-2 h-1 overflow-hidden rounded-full bg-muted"
      >
        <div
          class="h-full animate-pulse rounded-full bg-brand"
          style="width: 100%"
        />
      </div>
    </div>
  </div>
</template>
