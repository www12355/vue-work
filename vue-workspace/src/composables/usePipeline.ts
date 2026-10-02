/**
 * Pipeline 状态追踪 — 通过 WebSocket 消息实时更新阶段进度。
 *
 * 用法：
 *   const pipeline = usePipeline(STAGE_DEFS)
 *   ws.connect(url, pipeline.handleMessage)
 *   pipeline.startProcessing(sessionId)
 *
 * STAGE_DEFS 按后端的阶段 id 定义名称与描述，
 * 收到 WS 消息时自动匹配并更新对应阶段的状态。
 */

import { ref, reactive, computed } from "vue"
import type { WSMessage, StageDef, StageState, FileInfo } from "@/services/api/types"

export function usePipeline(stageDefs: StageDef[]) {
  const phase = ref<"idle" | "uploading" | "processing" | "completed" | "failed">("idle")
  const sessionId = ref<string | null>(null)

  /* 以 StageDef 为模板初始化运行时阶段列表 */
  const stages = reactive<StageState[]>(
    stageDefs.map((def) => ({
      ...def,
      status: "pending" as const,
      message: "",
      detail: "",
    })),
  )

  const overallProgress = ref(0)
  const currentStageId = ref(-1)
  const outputFiles = reactive<FileInfo[]>([])
  const pipelineError = ref<string | null>(null)
  /** 运行日志（阶段起止、进度、回显），带级别与时间戳，供日志控制台展示 */
  const statusMessages = reactive<{ level: "info" | "success" | "error"; text: string; time: string }[]>([])
  const startTime = ref<number | null>(null)

  const MAX_LOGS = 200

  function addLog(level: "info" | "success" | "error", text: string) {
    if (!text) return
    statusMessages.push({ level, text, time: new Date().toLocaleTimeString("zh-CN", { hour12: false }) })
    if (statusMessages.length > MAX_LOGS) statusMessages.splice(0, statusMessages.length - MAX_LOGS)
  }

  const totalStages = stageDefs.length
  const completedCount = computed(() => stages.filter((s) => s.status === "completed").length)
  const isComplete = computed(() => phase.value === "completed")
  const isProcessing = computed(() => phase.value === "processing")

  /** 估算剩余时间文本 */
  const estimatedRemainingText = computed(() => {
    if (!startTime.value || completedCount.value === 0) return ""
    const elapsed = Date.now() - startTime.value
    const avgMs = elapsed / completedCount.value
    const remaining = totalStages - completedCount.value
    const remainingMs = avgMs * remaining
    if (remainingMs < 60_000) return "预计 < 1 分钟"
    if (remainingMs < 3_600_000) return `预计 ~${Math.round(remainingMs / 60_000)} 分钟`
    return `预计 ~${Math.round(remainingMs / 3_600_000)} 小时`
  })

  /** 处理 WebSocket 消息，更新阶段状态 */
  function handleMessage(msg: WSMessage) {
    switch (msg.type) {
      case "stage_start":
        if (msg.stage) {
          const stage = stages.find((s) => s.id === msg.stage!.id)
          if (stage) {
            stage.status = "running"
            stage.message = msg.message || msg.stage.name
            stage.detail = msg.detail || ""
          }
          currentStageId.value = msg.stage.id
        }
        phase.value = "processing"
        if (!startTime.value) startTime.value = Date.now()
        addLog("info", msg.message || (msg.stage ? `开始：${msg.stage.name}` : ""))
        break

      case "stage_complete":
        if (msg.stage) {
          const stage = stages.find((s) => s.id === msg.stage!.id)
          if (stage) {
            stage.status = "completed"
            stage.message = msg.message || `${stage.name} 已完成`
            stage.detail = msg.detail || ""
          }
        }
        overallProgress.value = Math.round(
          ((completedCount.value + 1) / totalStages) * 100,
        )
        addLog("success", msg.message || (msg.stage ? `完成：${msg.stage.name}` : ""))
        break

      case "stage_failed":
        if (msg.stage) {
          const stage = stages.find((s) => s.id === msg.stage!.id)
          if (stage) {
            stage.status = "failed"
            stage.message = msg.message || `${stage.name} 失败`
            stage.detail = msg.error || msg.detail || ""
          }
        }
        pipelineError.value = msg.error || msg.message || "阶段执行失败"
        phase.value = "failed"
        addLog("error", msg.message || msg.error || (msg.stage ? `失败：${msg.stage.name}` : "阶段执行失败"))
        break

      case "progress":
        overallProgress.value = msg.progress_pct ?? overallProgress.value
        addLog("info", msg.message || msg.detail || "")
        break

      case "pipeline_complete":
        phase.value = "completed"
        overallProgress.value = 100
        /* 把所有 pending / running 阶段标记为 completed */
        stages.forEach((s) => {
          if (s.status === "pending" || s.status === "running") s.status = "completed"
        })
        /* 输出文件仅通过 pipeline_complete.files 交付（FileInfo 数组） */
        if (Array.isArray(msg.files)) {
          outputFiles.splice(0, outputFiles.length, ...msg.files)
        }
        addLog("success", msg.message || "生成完成！")
        break

      case "pipeline_failed":
        phase.value = "failed"
        pipelineError.value = msg.error || msg.message || "流水线执行失败"
        addLog("error", `❌ 流水线失败: ${pipelineError.value}`)
        break

      case "stage_definitions":
        /* 后端连接时下发的完整阶段定义，可用它对齐名称/描述 */
        if (Array.isArray(msg.stages)) {
          msg.stages.forEach((def) => {
            const stage = stages.find((s) => s.id === def.id)
            if (stage) {
              stage.name = def.name || stage.name
              stage.description = def.description || stage.description
            }
          })
        }
        break

      case "session_info":
      case "keepalive":
        /* 仅信息性消息，无需处理 */
        break

      case "echo":
        addLog((msg.level as "info" | "success" | "error") || "info", msg.message || "")
        break

      default:
        break
    }
  }

  /** 进入处理状态 */
  function startProcessing(sid: string) {
    phase.value = "processing"
    sessionId.value = sid
    startTime.value = Date.now()
    pipelineError.value = null
    statusMessages.splice(0)
    outputFiles.splice(0)
    stages.forEach((s) => {
      s.status = "pending"
      s.message = ""
      s.detail = ""
    })
    overallProgress.value = 0
    currentStageId.value = -1
  }

  /** 重置到初始状态 */
  function reset() {
    phase.value = "idle"
    sessionId.value = null
    startTime.value = null
    pipelineError.value = null
    statusMessages.splice(0)
    outputFiles.splice(0)
    stages.forEach((s) => {
      s.status = "pending"
      s.message = ""
      s.detail = ""
    })
    overallProgress.value = 0
    currentStageId.value = -1
  }

  return {
    phase,
    sessionId,
    stages,
    overallProgress,
    currentStageId,
    outputFiles,
    pipelineError,
    statusMessages,
    startTime,
    totalStages,
    completedCount,
    isComplete,
    isProcessing,
    estimatedRemainingText,
    handleMessage,
    startProcessing,
    reset,
  }
}
