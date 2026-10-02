import { computed, reactive } from "vue"
import {
  createContractSession,
  uploadContractText,
  startContractPipeline,
  contractDownloadUrl,
  contractUploadUrl,
  contractWsUrl,
  fetchContractSessions,
  deleteContractSession,
  fetchContractCacheTree,
  fetchContractFileContent,
  type ContractFormData,
} from "@/services/api/contract"
import { validateUploadFiles } from "@/services/fileValidation"
import { xhrUploadFile } from "@/composables/useUpload"
import type { DownloadableFile, SessionListItem, FileTreeNode } from "@/services/api/types"
import { usePipeline } from "@/composables/usePipeline"
import { useWebSocket } from "@/composables/useWebSocket"
import { useHistory } from "@/composables/useHistory"

export const DEFAULT_PROMPT = `请基于上传的核心文件和参考文件，生成一份完整的通用型中文服务合同。

## 合同要素
- 根据上传文件中的项目信息，确定合同类型（技术服务/软件开发/算力服务/采购等）
- 合同需包含全部 13 个章节：项目概况与定义、服务内容、甲方权利和义务、乙方权利和义务、服务期限、收费标准及支付方式、验收标准与交付、知识产权、保密条款、违约责任、合同解除、争议解决、其他
- 条款需具体可执行，金额使用「人民币 XXX 元」格式，待填写项使用【】占位符

## 格式要求
- 使用规范的合同书面语，条款分级编号
- 输出为可直接导出的 DOCX 结构`

export const DURATION_UNITS = [
  { key: "years", label: "年" },
  { key: "months", label: "个月" },
  { key: "days", label: "日" },
] as const

export type DurationKey = (typeof DURATION_UNITS)[number]["key"]

/** 合同流水线 5 阶段定义（对应后端 pipeline_config.yaml） */
export const CONTRACT_STAGE_DEFS = [
  { id: 0, name: "文件收集", description: "收集上传文件、模板、源文档作为上下文" },
  { id: 1, name: "合同内容生成", description: "DeepSeek 生成完整 13 章服务合同" },
  { id: 2, name: "合同质量审查", description: "AI 质量审查（完整性、合法性、格式）" },
  { id: 3, name: "工作量统计", description: "AI 提取服务项、交付物、里程碑" },
  { id: 4, name: "文档导出", description: "生成格式化 DOCX 及审查/统计报告" },
]

export function cn(d: Date) {
  return `${d.getFullYear()}年${String(d.getMonth() + 1).padStart(2, "0")}月${String(d.getDate()).padStart(2, "0")}日`
}

export function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

export function fileNames(list: FileList | null) {
  return list?.length ? Array.from(list).map((f) => f.name) : []
}

/**
 * 合同弹窗的共享状态：各区块拆成独立组件，顺序与显隐由管理后台配置。
 */
export function createContractState() {
  const today = new Date()

  const s = reactive({
    today,
    contractNo: `HT-${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, "0")}${String(
      today.getDate(),
    ).padStart(2, "0")}-${Math.random().toString(16).slice(2, 8)}`,
    projectName: "",
    signPlace: "天津市河北区",
    partyA: "天津人工智能计算中心",
    partyB: "天津智算数字产业发展有限公司",
    startDate: iso(today),
    duration: { years: 0, months: 6, days: 0 } as Record<DurationKey, number>,
    coreFiles: [] as string[],
    refFiles: [] as string[],
    prompt: DEFAULT_PROMPT,
    loading: false,
    result: "",
  })

  /* ---- 真实 API 相关状态 ---- */
  const uploadPhase = reactive({ current: "idle" as "idle" | "uploading" | "starting", progress: 0 })
  const pipeline = usePipeline(CONTRACT_STAGE_DEFS)
  const wsClient = useWebSocket()
  const history = useHistory("contract")

  const durationText = computed(() => {
    const parts: string[] = []
    if (s.duration.years) parts.push(`${s.duration.years}年`)
    if (s.duration.months) parts.push(`${s.duration.months}个月`)
    if (s.duration.days) parts.push(`${s.duration.days}日`)
    return parts.length ? parts.join("") : "未设置"
  })

  const endDate = computed(() => {
    const base = new Date(s.startDate || iso(today))
    if (Number.isNaN(base.getTime())) return "—"
    const d = new Date(base)
    d.setFullYear(d.getFullYear() + s.duration.years)
    d.setMonth(d.getMonth() + s.duration.months)
    d.setDate(d.getDate() + s.duration.days)
    return cn(d)
  })

  const summary = computed(() => [
    { label: "合同编号", value: s.contractNo },
    { label: "项目名称", value: s.projectName.trim() || "（未填写）" },
    { label: "甲方", value: s.partyA.trim() || "（未填写）" },
    { label: "乙方", value: s.partyB.trim() || "（未填写）" },
    { label: "服务期限", value: durationText.value },
    { label: "签订地点", value: s.signPlace.trim() || "（未填写）" },
  ])

  const disabled = computed(
    () =>
      s.loading || pipeline.isProcessing.value || !s.projectName.trim() || !s.signPlace.trim() || !s.partyA.trim() || !s.partyB.trim(),
  )

  const appPhase = computed(() => {
    if (pipeline.isProcessing.value || pipeline.isComplete.value || pipeline.phase.value === "failed") {
      return pipeline.phase.value
    }
    return uploadPhase.current === "idle" ? "idle" : "uploading"
  })

  const outputDownloads = computed<DownloadableFile[]>(() =>
    pipeline.outputFiles.map((f) => ({
      name: f.name,
      path: f.download_url || f.name,
      size_kb: f.size_kb,
      url: contractDownloadUrl(pipeline.sessionId.value || "", f.download_url || f.name),
    })),
  )

  /* ---- 真实上传文件追踪 ---- */
  let _coreFiles: File[] = []
  let _refFiles: File[] = []

  function onCoreFilesSelected(files: File[]) {
    _coreFiles = files
  }
  function onRefFilesSelected(files: File[]) {
    _refFiles = files
  }

  /* ---- API 历史方法 ---- */
  async function fetchHistorySessions(): Promise<SessionListItem[]> {
    return fetchContractSessions()
  }
  async function removeSession(sid: string): Promise<void> {
    return deleteContractSession(sid)
  }
  async function loadCacheTree(sid: string): Promise<FileTreeNode> {
    return fetchContractCacheTree(sid)
  }
  async function loadFileContent(sid: string, path: string): Promise<string> {
    return fetchContractFileContent(sid, path)
  }
  function buildDownloadUrl(sid: string, file: string): string {
    return contractDownloadUrl(sid, file)
  }

  function step(key: DurationKey, delta: number) {
    s.duration[key] = Math.max(0, s.duration[key] + delta)
  }

  /** 正式生成：三步流程 → 后端 pipeline */
  async function generate() {
    if (disabled.value) return
    s.loading = true
    s.result = ""

    /* 上传前预校验（与后端规则一致），不合法直接报错，不创建会话 */
    const allFiles = [..._coreFiles, ..._refFiles]
    const fileError = validateUploadFiles(allFiles)
    if (fileError) {
      s.loading = false
      throw new Error(fileError)
    }

    /* Step 1: 创建 session */
    uploadPhase.current = "uploading"
    uploadPhase.progress = 0

    const formData: ContractFormData = {
      contract_id: s.contractNo,
      project_name: s.projectName,
      party_a: s.partyA,
      party_b: s.partyB,
      signing_place: s.signPlace,
      signing_date: cn(today),
      start_date: s.startDate,
      duration_years: s.duration.years,
      duration_months: s.duration.months,
      duration_days: s.duration.days,
      end_date: endDate.value,
      duration_text: durationText.value,
    }
    const session = await createContractSession(formData)
    const sid = session.session_id
    pipeline.startProcessing(sid)

    /* Step 2: 上传文件（逐文件 XHR，字节级进度） */
    for (let i = 0; i < allFiles.length; i++) {
      const file = allFiles[i]
      const type = _coreFiles.includes(file) ? "uploads" as const : "profile" as const
      const basePct = (i / allFiles.length) * 100
      const span = 100 / allFiles.length
      await xhrUploadFile(file, contractUploadUrl(sid, type), (pct) => {
        uploadPhase.progress = Math.min(99, Math.round(basePct + (pct / 100) * span))
      })
      uploadPhase.progress = Math.round(((i + 1) / allFiles.length) * 100)
    }

    /* 上传补充需求文本 */
    if (s.prompt) {
      await uploadContractText(sid, s.prompt)
    }

    /* Step 3: 启动 pipeline + WebSocket（先建 WS 再启动，避免丢最早的阶段消息） */
    uploadPhase.current = "starting"
    wsClient.connect(contractWsUrl(sid), pipeline.handleMessage)
    await startContractPipeline(sid)

    s.loading = false
  }

  return reactive({
    s,
    durationText,
    endDate,
    summary,
    disabled,
    step,
    generate,
    /* 新 API */
    uploadPhase,
    pipeline,
    wsClient,
    history,
    appPhase,
    outputDownloads,
    onCoreFilesSelected,
    onRefFilesSelected,
    fetchHistorySessions,
    removeSession,
    loadCacheTree,
    loadFileContent,
    buildDownloadUrl,
  })
}

export type ContractCtx = ReturnType<typeof createContractState>
