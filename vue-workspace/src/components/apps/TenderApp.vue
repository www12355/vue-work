<script setup lang="ts">
import { ref, computed, type Component } from "vue"
import { Loader2, Sparkles, History, FileText, AlertTriangle } from "lucide-vue-next"
import ResultPanel from "@/components/apps/ResultPanel.vue"
import PipelineProgress from "@/components/apps/ui/PipelineProgress.vue"
import LiveFileTree from "@/components/apps/ui/LiveFileTree.vue"
import MainUpload from "@/components/apps/tender/MainUpload.vue"
import RefUpload from "@/components/apps/tender/RefUpload.vue"
import GenConfig from "@/components/apps/tender/GenConfig.vue"
import TechStack from "@/components/apps/tender/TechStack.vue"
import TeamConfig from "@/components/apps/tender/TeamConfig.vue"
import { createTenderState } from "@/components/apps/tender/state"
import { useLayout } from "@/composables/useLayout"
import { goToHistory } from "@/stores/view"
import { bidFileContentUrl } from "@/services/api/bid"
import type { DownloadableFile } from "@/services/api/types"

const props = defineProps<{ ownerId: string; readonlyMode?: boolean }>()

const ctx = createTenderState()
const { left, right } = useLayout(props.ownerId)

/* 区块 id → 组件：后台调整顺序/所在列/显隐后，这里循环渲染即可生效 */
const SECTIONS: Record<string, Component> = {
  "main-upload": MainUpload,
  "ref-upload": RefUpload,
  "gen-config": GenConfig,
  "tech-stack": TechStack,
  "team-config": TeamConfig,
}

const twoColumns = computed(() => left.value.length > 0 && right.value.length > 0)

/* 视图切换 — 历史记录跳转到独立页面，非弹窗内显示
   注意：ctx 是 reactive 包装，内部 ref 已自动解包，直接读属性即可 */
const showPipeline = computed(
  () =>
    ctx.pipeline.isProcessing ||
    ctx.pipeline.isComplete ||
    ctx.pipeline.phase === "failed",
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
  ctx.newSession()
  ctx.s.mainFiles = []
  ctx.s.refFiles = []
  ctx.s.result = ""
  ctx.uploadPhase.current = "idle"
  ctx.uploadPhase.progress = 0
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
        @click="goToHistory('tender')"
      >
        <History class="h-4 w-4" />
        历史记录
      </button>
    </div>

    <!-- Pipeline 进度 -->
    <PipelineProgress
      v-if="showPipeline"
      :stages="ctx.pipeline.stages"
      :current-stage-id="ctx.pipeline.currentStageId"
      :overall-progress="ctx.pipeline.overallProgress"
      :completed-count="ctx.pipeline.completedCount"
      :total-stages="ctx.pipeline.totalStages"
      :is-complete="ctx.pipeline.isComplete"
      :is-failed="ctx.pipeline.phase === 'failed'"
      :error="ctx.pipeline.pipelineError"
      :output-files="ctx.outputDownloads"
      :estimated-time="ctx.pipeline.estimatedRemainingText"
      :logs="ctx.pipeline.statusMessages"
      @back="onBackToForm"
      @new-session="onNewSession"
      @download="onDownload"
    />

    <!-- 处理期间实时工作区文件树（3 秒轮询） -->
    <LiveFileTree
      v-if="showPipeline"
      :session-id="ctx.pipeline.sessionId"
      :active="ctx.pipeline.isProcessing"
      :fetch-tree="ctx.loadCacheTree"
      :build-download-url="ctx.buildDownloadUrl"
      :file-content-url="bidFileContentUrl"
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

      <!-- 底部提交条 -->
      <div v-if="generateError" class="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">
        <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
        <span>{{ generateError }}</span>
      </div>
      <button
        :disabled="!ctx.canSubmit || readonlyMode"
        class="flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-brand via-brand/85 to-brand/55 px-4 py-4 text-sm font-semibold text-brand-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        @click="onGenerate"
      >
        <Loader2 v-if="ctx.s.loading || ctx.uploadPhase.current !== 'idle'" class="h-4 w-4 animate-spin" />
        <Sparkles v-else class="h-4 w-4" />
        {{ ctx.submitLabel }}
      </button>

      <ResultPanel
        v-if="ctx.s.loading || ctx.s.result"
        label="方案预览"
        :result="ctx.s.result"
        :files="ctx.outputDownloads"
        class="min-h-[220px]"
      >
        <template #empty>
          <Loader2 class="h-8 w-8 animate-spin opacity-40" />
          <p class="text-sm">正在按配置生成投标主方案…</p>
        </template>
      </ResultPanel>
    </template>
  </div>
</template>
