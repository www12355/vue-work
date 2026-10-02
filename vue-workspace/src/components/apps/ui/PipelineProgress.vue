<script setup lang="ts">
/**
 * Pipeline 进度面板 — 顶部进度条 + 阶段卡片列表 + 运行日志 + 输出文件。
 * 替换表单区域显示，流水线运行中/完成后自动出现。
 */

import { computed, ref, watch, nextTick } from "vue"
import {
  Download,
  ExternalLink,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Terminal,
  ChevronDown,
} from "lucide-vue-next"
import StageCard from "./StageCard.vue"
import type { StageState, DownloadableFile } from "@/services/api/types"

export interface PipelineLogEntry {
  level: "info" | "success" | "error"
  text: string
  time: string
}

const props = defineProps<{
  stages: StageState[]
  currentStageId: number
  overallProgress: number
  completedCount: number
  totalStages: number
  isComplete: boolean
  isFailed: boolean
  error: string | null
  outputFiles: DownloadableFile[]
  estimatedTime: string
  logs?: PipelineLogEntry[]
}>()

const emit = defineEmits<{
  (e: "back"): void
  (e: "download", file: DownloadableFile): void
  (e: "newSession"): void
}>()

const progressPct = computed(() =>
  Math.round((props.completedCount / Math.max(props.totalStages, 1)) * 100),
)

/* ── 运行日志控制台 ── */
const showLogs = ref(true)
const logBox = ref<HTMLElement | null>(null)

watch(
  () => props.logs?.length,
  async () => {
    if (!showLogs.value) return
    await nextTick()
    logBox.value?.scrollTo({ top: logBox.value.scrollHeight })
  },
)

function logColor(level: string): string {
  if (level === "success") return "text-emerald-500"
  if (level === "error") return "text-red-400"
  return "text-muted-foreground"
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <!-- 顶部：进度概览 -->
    <div class="rounded-2xl border border-border bg-card p-5">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-lg font-bold text-card-foreground">
            <template v-if="isComplete">
              <span class="text-emerald-500">✓ 全部完成</span>
            </template>
            <template v-else-if="isFailed">
              <span class="text-red-500">✗ 流水线失败</span>
            </template>
            <template v-else>
              正在生成…
            </template>
          </h3>
          <p class="mt-1 text-sm text-muted-foreground">
            {{ completedCount }} / {{ totalStages }} 阶段完成
            <span v-if="estimatedTime && !isComplete && !isFailed" class="ml-2 text-xs">
              {{ estimatedTime }}
            </span>
          </p>
        </div>

        <div class="flex items-center gap-2">
          <button
            v-if="isComplete || isFailed"
            class="flex items-center gap-1.5 rounded-xl bg-brand px-4 py-2 text-sm font-medium text-brand-foreground transition-opacity hover:opacity-90"
            @click="emit('newSession')"
          >
            新建
          </button>
          <button
            class="flex items-center gap-1.5 rounded-xl bg-muted px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
            @click="emit('back')"
          >
            <ArrowLeft class="h-4 w-4" />
            返回
          </button>
        </div>
      </div>

      <!-- 整体进度条 -->
      <div
        v-if="!isComplete && !isFailed"
        class="mt-4 h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          class="h-full rounded-full bg-gradient-to-r from-brand via-brand/85 to-brand/55 transition-all duration-700 ease-out"
          :style="{ width: `${Math.max(overallProgress || progressPct, 2)}%` }"
        />
      </div>

      <!-- 错误信息 -->
      <div
        v-if="isFailed && error"
        class="mt-3 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3"
      >
        <XCircle class="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
        <p class="text-sm text-red-400">{{ error }}</p>
      </div>
    </div>

    <!-- 阶段卡片列表 -->
    <div class="flex flex-col gap-2">
      <StageCard
        v-for="stage in stages"
        :key="stage.id"
        :stage="stage"
        :is-current="stage.id === currentStageId"
      />
    </div>

    <!-- 运行日志控制台 -->
    <div v-if="logs?.length" class="rounded-2xl border border-border bg-card p-4">
      <button
        class="flex w-full items-center justify-between text-left"
        @click="showLogs = !showLogs"
      >
        <span class="flex items-center gap-2 text-sm font-bold text-card-foreground">
          <Terminal class="h-4 w-4 text-muted-foreground" />
          运行日志
          <span class="text-xs font-normal text-muted-foreground">{{ logs.length }} 条</span>
        </span>
        <ChevronDown
          class="h-4 w-4 text-muted-foreground transition-transform"
          :class="showLogs && 'rotate-180'"
        />
      </button>
      <div
        v-show="showLogs"
        ref="logBox"
        class="mt-3 max-h-56 space-y-1 overflow-auto rounded-xl bg-background p-3 font-mono text-[12px] leading-relaxed"
      >
        <div v-for="(log, idx) in logs" :key="idx" class="flex gap-2">
          <span class="shrink-0 text-muted-foreground/50">{{ log.time }}</span>
          <span class="shrink-0" :class="logColor(log.level)">
            {{ log.level === "success" ? "✓" : log.level === "error" ? "✗" : "·" }}
          </span>
          <span class="whitespace-pre-wrap break-all" :class="logColor(log.level)">{{ log.text }}</span>
        </div>
      </div>
    </div>

    <!-- 输出文件（流水线完成后） -->
    <div v-if="isComplete && outputFiles.length" class="rounded-2xl border border-border bg-card p-5">
      <h4 class="mb-3 text-sm font-bold text-card-foreground">输出文件</h4>
      <div class="flex flex-col gap-2">
        <div
          v-for="file in outputFiles"
          :key="file.path"
          class="flex items-center justify-between rounded-xl border border-border bg-muted/50 px-4 py-3"
        >
          <div class="flex items-center gap-2 min-w-0">
            <CheckCircle2 class="h-4 w-4 shrink-0 text-emerald-500" />
            <span class="text-sm text-card-foreground truncate">{{ file.name }}</span>
            <span v-if="file.size_kb" class="text-xs text-muted-foreground shrink-0">
              {{ file.size_kb }} KB
            </span>
          </div>
          <button
            class="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-brand transition-colors hover:bg-brand/10"
            @click="emit('download', file)"
          >
            <Download class="h-3.5 w-3.5" />
            下载
          </button>
        </div>
      </div>
    </div>

    <!-- 空输出（流水线完成但没有文件） -->
    <div
      v-if="isComplete && !outputFiles.length"
      class="flex flex-col items-center gap-2 rounded-2xl border border-border bg-card p-8 text-center"
    >
      <AlertTriangle class="h-6 w-6 text-muted-foreground/60" />
      <p class="text-sm text-muted-foreground">生成完成，暂无可下载的输出文件</p>
    </div>
  </div>
</template>
