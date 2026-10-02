<script setup lang="ts">
import { ref, computed, type Component } from "vue"
import { Loader2, FileSignature, History, FileText, AlertTriangle } from "lucide-vue-next"
import ResultPanel from "@/components/apps/ResultPanel.vue"
import PipelineProgress from "@/components/apps/ui/PipelineProgress.vue"
import BasicInfo from "@/components/apps/contract/BasicInfo.vue"
import Parties from "@/components/apps/contract/Parties.vue"
import Duration from "@/components/apps/contract/Duration.vue"
import Summary from "@/components/apps/contract/Summary.vue"
import CoreFiles from "@/components/apps/contract/CoreFiles.vue"
import RefFiles from "@/components/apps/contract/RefFiles.vue"
import Prompt from "@/components/apps/contract/Prompt.vue"
import { createContractState } from "@/components/apps/contract/state"
import { useLayout } from "@/composables/useLayout"
import { goToHistory } from "@/stores/view"
import type { DownloadableFile } from "@/services/api/types"

const props = defineProps<{ ownerId: string }>()

const ctx = createContractState()
const { left, right, submitLabel } = useLayout(props.ownerId)

/* 区块 id → 组件：顺序、所在列与显隐均来自管理后台配置 */
const SECTIONS: Record<string, Component> = {
  basic: BasicInfo,
  parties: Parties,
  duration: Duration,
  summary: Summary,
  "core-files": CoreFiles,
  "ref-files": RefFiles,
  prompt: Prompt,
}

const twoColumns = computed(() => left.value.length > 0 && right.value.length > 0)

/* 视图切换 — 历史记录跳转到独立页面，非弹窗内显示 */
const showPipeline = computed(
  () =>
    ctx.pipeline.isProcessing.value ||
    ctx.pipeline.isComplete.value ||
    ctx.pipeline.phase.value === "failed",
)

const showForm = computed(() => !showPipeline.value)

const generateError = ref<string | null>(null)

async function onGenerate() {
  generateError.value = null
  try {
    await ctx.generate()
  } catch (e: any) {
    generateError.value = e?.message || e?.detail || "生成失败，请检查后端服务是否可用"
    ctx.s.loading = false
    ctx.uploadPhase.current = "idle"
    ctx.uploadPhase.progress = 0
  }
}

function onDownload(file: DownloadableFile) {
  window.open(file.url, "_blank")
}

function onBackToForm() {
  ctx.pipeline.reset()
  ctx.uploadPhase.current = "idle"
  ctx.uploadPhase.progress = 0
}

function onNewSession() {
  ctx.s.coreFiles = []
  ctx.s.refFiles = []
  ctx.s.result = ""
  ctx.uploadPhase.current = "idle"
  ctx.uploadPhase.progress = 0
  ctx.pipeline.reset()
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- 顶部操作栏 -->
    <div class="flex items-center gap-1 rounded-2xl bg-muted p-1 w-fit">
      <span
        class="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium bg-card text-card-foreground shadow-sm"
      >
        <FileText class="h-4 w-4" />
        新建
      </span>
      <button
        class="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        @click="goToHistory('contract')"
      >
        <History class="h-4 w-4" />
        历史记录
      </button>
    </div>

    <!-- Pipeline 进度 -->
    <PipelineProgress
      v-if="showPipeline"
      :stages="ctx.pipeline.stages"
      :current-stage-id="ctx.pipeline.currentStageId.value"
      :overall-progress="ctx.pipeline.overallProgress.value"
      :completed-count="ctx.pipeline.completedCount.value"
      :total-stages="ctx.pipeline.totalStages"
      :is-complete="ctx.pipeline.isComplete.value"
      :is-failed="ctx.pipeline.phase.value === 'failed'"
      :error="ctx.pipeline.pipelineError.value"
      :output-files="ctx.outputDownloads"
      :estimated-time="ctx.pipeline.estimatedRemainingText.value"
      @back="onBackToForm"
      @new-session="onNewSession"
      @download="onDownload"
    />

    <!-- 表单视图 -->
    <template v-if="showForm">
      <div class="grid gap-4" :class="twoColumns ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]' : ''">
        <div v-if="left.length" class="flex flex-col gap-4">
          <component
            v-for="sec in left"
            :key="sec.id"
            :is="SECTIONS[sec.id]"
            v-bind="SECTIONS[sec.id] ? { ctx, label: sec.label, uploadProgress: ctx.uploadPhase.progress, uploading: ctx.uploadPhase.current === 'uploading' } : {}"
          />
        </div>

        <div v-if="right.length" class="flex flex-col gap-4">
          <component
            v-for="sec in right"
            :key="sec.id"
            :is="SECTIONS[sec.id]"
            v-bind="SECTIONS[sec.id] ? { ctx, label: sec.label, uploadProgress: ctx.uploadPhase.progress, uploading: ctx.uploadPhase.current === 'uploading' } : {}"
          />
        </div>
      </div>

      <div v-if="generateError" class="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">
        <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
        <span>{{ generateError }}</span>
      </div>
      <button
        :disabled="ctx.disabled"
        class="flex w-full items-center justify-center gap-2 rounded-2xl bg-brand px-4 py-4 text-sm font-semibold text-brand-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        @click="onGenerate"
      >
        <Loader2 v-if="ctx.s.loading || ctx.uploadPhase.current !== 'idle'" class="h-4 w-4 animate-spin" />
        <FileSignature v-else class="h-4 w-4" />
        {{
          ctx.uploadPhase.current === "uploading"
            ? `正在上传… ${ctx.uploadPhase.progress}%`
            : ctx.uploadPhase.current === "starting"
              ? "正在启动流水线…"
              : ctx.s.loading
                ? "正在生成合同…"
                : submitLabel
        }}
      </button>

      <ResultPanel
        v-if="ctx.s.loading || ctx.s.result"
        label="合同预览"
        :result="ctx.s.result"
        :files="ctx.outputDownloads"
        class="min-h-[220px]"
      >
        <template #empty>
          <Loader2 class="h-8 w-8 animate-spin opacity-40" />
          <p class="text-sm">正在按填写的信息生成合同文档…</p>
        </template>
      </ResultPanel>
    </template>
  </div>
</template>
