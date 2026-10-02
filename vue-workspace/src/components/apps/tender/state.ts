import { computed, reactive, ref } from "vue"
import {
  createBidSession,
  uploadBidText,
  startBidPipeline,
  bidDownloadUrl,
  bidUploadUrl,
  bidWsUrl,
  fetchBidSessions,
  deleteBidSession,
  fetchBidCacheTree,
  fetchBidFileContent,
  fetchBidPipelineConfig,
  saveBidPipelineConfig,
} from "@/services/api/bid"
import { validateUploadFiles } from "@/services/fileValidation"
import { xhrUploadFile } from "@/composables/useUpload"
import type {
  DownloadableFile,
  SessionListItem,
  FileTreeNode,
  TechStackConfig,
  TeamProfileConfig,
  TeamRole,
  ProposalConfig,
} from "@/services/api/types"
import { usePipeline } from "@/composables/usePipeline"
import { useWebSocket } from "@/composables/useWebSocket"
import { useHistory } from "@/composables/useHistory"

/* ───────── 规模 / focus 选项（前端 UI 固定不变） ───────── */
export const SIZE_OPTIONS = [
  { id: "small", label: "小型", hint: "6人" },
  { id: "medium", label: "中型", hint: "12人" },
  { id: "large", label: "大型", hint: "18人" },
] as const

export const FOCUS_OPTIONS = [
  { id: "penetration", label: "渗透", sub: "安全评估" },
  { id: "database", label: "数据库", sub: "数据治理" },
  { id: "ai", label: "人工智能", sub: "模型应用" },
  { id: "research_dev", label: "研发", sub: "交付研发" },
] as const

/** 标书流水线 11 阶段定义 */
export const BID_STAGE_DEFS = [
  { id: 0, name: "文档解析", description: "解析 DOCX 为文本、表格、图片与章节" },
  { id: 1, name: "标书总结", description: "AI 生成标书摘要" },
  { id: 2, name: "需求提取", description: "从标书中提取结构化需求" },
  { id: 3, name: "技术章节定位", description: "定位技术章节编号与结构" },
  { id: 4, name: "默认格式准备", description: "准备默认 DOCX 导出格式" },
  { id: 5, name: "投标策略生成", description: "生成中标与陪标策略方案" },
  { id: 6, name: "标书内容生成", description: "AI 生成全部技术方案内容" },
  { id: 7, name: "模板拼接", description: "模板填充（跳过）" },
  { id: 8, name: "DOCX 导出", description: "Markdown → 格式化 DOCX" },
  { id: 9, name: "应答表生成", description: "生成技术一对一应答表" },
  { id: 10, name: "最终整合导出", description: "导出全部文件至 output/" },
]

const WINNING_DEFAULT: [string, string, string, number] = ["data_platform", "large_penetration", "中标方案", 180]
const REFERENCE_DEFAULTS: [string, string, number][] = [
  ["reference_java_classic", "small_research_dev", 240],
  ["reference_python_classic", "small_ai", 240],
  ["reference_data_basic", "small_database", 260],
  ["reference_lowcode_delivery", "small_research_dev", 210],
  ["reference_dotnet_standard", "medium_research_dev", 240],
  ["reference_php_legacy", "small_research_dev", 270],
]

export function randomId() {
  return Math.random().toString(16).slice(2, 12)
}

function deepClone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v))
}

/* ───────── 内置 fallback（后端不可用时使用） ───────── */
const FALLBACK_CONFIG: Record<string, any> = {
  proposal_set: {
    winning: {
      id: "bid_00_winning",
      name: "中标方案",
      tech_stack_id: "data_platform",
      team_profile_id: "large_penetration",
      delivery_days: 180,
      writing_rules: [],
    },
  },
  tech_stacks: {
    data_platform: {
      id: "data_platform",
      tier: "winning",
      name: "数据治理平台技术方案",
      summary: "面向数据汇聚、治理、质量监控和可视化分析的数据平台技术栈。",
      rows: [
        { key: "backend_lang", label: "后端语言", value: "Python 3.11 + Java 17" },
        { key: "backend_framework", label: "后端框架", value: "FastAPI + Spring Boot" },
        { key: "database", label: "数据库", value: "PostgreSQL + ClickHouse + Redis" },
        { key: "frontend", label: "前端", value: "Vue 3 + ECharts + AntV" },
        { key: "deployment", label: "部署", value: "Kubernetes + 对象存储" },
      ],
    },
  } as Record<string, TechStackConfig>,
  team_profiles: {
    large_penetration: {
      id: "large_penetration",
      size: "large",
      focus: "penetration",
      name: "大型渗透安全团队",
      summary: "18人复杂项目团队",
      total: 18,
      roles: [
        { role: "项目经理", count: 1, focus: "总体统筹和质量验收" },
        { role: "安全测试工程师", count: 5, focus: "渗透测试、漏洞复核" },
        { role: "后端开发工程师", count: 4, focus: "服务开发和安全整改" },
        { role: "前端开发工程师", count: 2, focus: "前端实现和安全联调" },
        { role: "数据库工程师", count: 2, focus: "数据权限、审计和备份" },
        { role: "测试工程师", count: 2, focus: "回归验证和验收测试" },
        { role: "运维工程师", count: 1, focus: "部署加固和运行监控" },
      ],
    },
  } as Record<string, TeamProfileConfig>,
}

/**
 * 标书弹窗的共享状态。
 * generate() 优先调用真实后端 API，失败时自动降级到本地 mock。
 */
export function createTenderState() {
  const s = reactive({
    mainFiles: [] as string[],
    refFiles: [] as string[],
    refCount: 0,
    planName: "中标方案",
    durationDays: 180,
    targetPackage: "",
    sessionId: randomId(),
    loading: false,
    result: "",
  })

  /* ──── pipeline config 状态 ──── */
  const pipelineCfg = reactive({
    loading: false,
    saving: false,
    error: "",
    message: "",
    rawYaml: "",
    config: {} as Record<string, any>,
  })

  const selectedProposalSlot = ref("winning")

  /* 从 config 中派生 */
  const proposals = computed<Record<string, ProposalConfig>>(() => {
    const ps = pipelineCfg.config.proposal_set
    return (ps && typeof ps === "object") ? ps as Record<string, ProposalConfig> : {}
  })

  const techStacks = computed<Record<string, TechStackConfig>>(() => {
    const ts = pipelineCfg.config.tech_stacks
    return (ts && typeof ts === "object") ? ts as Record<string, TechStackConfig> : {}
  })

  const teamProfiles = computed<Record<string, TeamProfileConfig>>(() => {
    const tp = pipelineCfg.config.team_profiles
    return (tp && typeof tp === "object") ? tp as Record<string, TeamProfileConfig> : {}
  })

  const techStackList = computed(() =>
    Object.values(techStacks.value).sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "", "zh-CN")),
  )

  const teamProfileList = computed(() =>
    Object.values(teamProfiles.value).sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "", "zh-CN")),
  )

  const activeProposal = computed<ProposalConfig | null>(() => proposals.value[selectedProposalSlot.value] ?? null)

  const selectedTechStack = computed<TechStackConfig | null>(() => {
    if (!activeProposal.value) return null
    return techStacks.value[activeProposal.value.tech_stack_id] ?? techStackList.value[0] ?? null
  })

  const selectedTeamProfile = computed<TeamProfileConfig | null>(() => {
    if (!activeProposal.value) return null
    return teamProfiles.value[activeProposal.value.team_profile_id] ?? teamProfileList.value[0] ?? null
  })

  const selectedTeamRoles = computed<TeamRole[]>(() =>
    Array.isArray(selectedTeamProfile.value?.roles) ? selectedTeamProfile.value!.roles : [],
  )

  const selectedTeamTotal = computed(() =>
    selectedTeamRoles.value.reduce((sum, r) => sum + (Number(r.count) || 0), 0),
  )

  /* 参考方案 slots */
  const referenceSlots = computed(() =>
    Object.keys(proposals.value)
      .filter((slot) => /^reference_[1-9]\d*$/.test(slot))
      .sort((a, b) => Number(a.split("_")[1]) - Number(b.split("_")[1])),
  )

  const referenceCount = computed(() => referenceSlots.value.length)

  const proposalTabs = computed(() => [
    { slot: "winning", label: proposals.value.winning?.name ?? "中标方案" },
    ...referenceSlots.value.map((slot, idx) => ({
      slot,
      label: proposals.value[slot]?.name ?? `参考方案 ${idx + 1}`,
    })),
  ])

  /* 规模 / focus 选择（UI 状态） */
  const selectedSize = ref("large")
  const selectedFocus = ref("penetration")

  function syncSelectionFromProfile(profileId: string) {
    const parts = String(profileId).split("_")
    if (parts.length >= 1) selectedSize.value = parts[0]
    if (parts.length >= 2) selectedFocus.value = parts[1]
  }

  /* ──── pipeline config 加载 ──── */
  async function loadPipelineConfig() {
    pipelineCfg.loading = true
    pipelineCfg.error = ""
    try {
      const resp = await fetchBidPipelineConfig()
      pipelineCfg.rawYaml = resp.pipeline_config_yaml ?? ""
      pipelineCfg.config = resp.config ?? {}
      pipelineCfg.message = "配置已加载"
      /* 同步方案选中 */
      const ps = resp.config?.proposal_set
      if (ps?.winning) {
        selectedProposalSlot.value = "winning"
        syncSelectionFromProfile(ps.winning.team_profile_id ?? "")
      }
    } catch (e: any) {
      console.warn("pipeline-config 加载失败，使用内置默认配置:", e.message)
      pipelineCfg.config = deepClone(FALLBACK_CONFIG)
      pipelineCfg.error = `配置加载失败：${e.message || "未知错误"}。当前使用内置默认配置，部分功能可能受限。`
      selectedProposalSlot.value = "winning"
      syncSelectionFromProfile("large_penetration")
    } finally {
      pipelineCfg.loading = false
    }
  }

  function buildPipelineConfig(): Record<string, any> {
    persistCurrentProposal()
    const next = deepClone(pipelineCfg.config)
    delete (next as any).solution
    delete (next as any).accompany
    return next
  }

  async function savePipelineConfig() {
    pipelineCfg.saving = true
    pipelineCfg.error = ""
    pipelineCfg.message = ""
    try {
      const content = JSON.stringify(buildPipelineConfig(), null, 2)
      await saveBidPipelineConfig(content)
      pipelineCfg.message = "配置已保存"
      await loadPipelineConfig()
    } catch (e: any) {
      pipelineCfg.error = e.message ?? "保存失败"
    } finally {
      pipelineCfg.saving = false
    }
  }

  /* ──── 方案切换 ──── */
  function persistCurrentProposal() {
    const proposalsSrc = pipelineCfg.config.proposal_set as Record<string, any> | undefined
    if (!proposalsSrc?.[selectedProposalSlot.value]) return
    const p = activeProposal.value
    if (!p) return
    Object.assign(proposalsSrc[selectedProposalSlot.value], {
      id: p.id,
      name: p.name,
      tech_stack_id: p.tech_stack_id,
      team_profile_id: p.team_profile_id,
      delivery_days: Math.max(1, Math.round(Number(p.delivery_days) || 180)),
      writing_rules: Array.isArray(p.writing_rules) ? p.writing_rules : [],
    })
  }

  function selectProposal(slot: string) {
    if (!proposals.value[slot]) return
    persistCurrentProposal()
    selectedProposalSlot.value = slot
    const p = proposals.value[slot]
    syncSelectionFromProfile(p.team_profile_id ?? "")
  }

  function setReferenceCount(nextCount: number) {
    persistCurrentProposal()
    const target = Number(nextCount)
    const proposalsSrc = pipelineCfg.config.proposal_set as Record<string, any>
    if (!proposalsSrc) return
    const existing = [...referenceSlots.value]
    if (target < existing.length) {
      for (const slot of existing.slice(target)) delete proposalsSrc[slot]
      if (!proposalsSrc[selectedProposalSlot.value]) selectProposal("winning")
      return
    }
    for (let idx = existing.length + 1; idx <= target; idx++) {
      const def = REFERENCE_DEFAULTS[(idx - 1) % REFERENCE_DEFAULTS.length]
      proposalsSrc[`reference_${idx}`] = {
        id: `bid_${String(idx).padStart(2, "0")}`,
        name: `参考方案 ${idx}`,
        tech_stack_id: techStacks.value[def[0]] ? def[0] : Object.keys(techStacks.value)[0],
        team_profile_id: teamProfiles.value[def[1]] ? def[1] : Object.keys(teamProfiles.value)[0],
        delivery_days: def[2],
        writing_rules: [],
      }
    }
  }

  /* ──── 技术栈 ──── */
  const editingTechStack = ref(false)

  function selectTechStack(stackId: string) {
    if (!activeProposal.value || !techStacks.value[stackId]) return
    activeProposal.value.tech_stack_id = stackId
  }

  function addTechRow() {
    const stack = selectedTechStack.value as any
    if (!stack?.rows) return
    stack.rows.push({ key: `custom_${stack.rows.length + 1}`, label: "新配置项", value: "" })
  }

  function deleteTechRow(index: number) {
    const stack = selectedTechStack.value as any
    if (!stack?.rows || stack.rows.length <= 1) return
    stack.rows.splice(index, 1)
  }

  function addTechStack() {
    let idx = 1; let id = `custom_stack_${idx}`
    while (techStacks.value[id]) id = `custom_stack_${++idx}`
    const src = pipelineCfg.config.tech_stacks as Record<string, any>
    if (!src) return
    src[id] = {
      id, tier: "winning", name: `自定义技术方案 ${idx}`,
      summary: "可在此直接维护技术路线。",
      rows: [{ key: "backend_lang", label: "后端语言", value: "" }],
    }
    selectTechStack(id)
    editingTechStack.value = true
  }

  function deleteTechStack() {
    const stackId = activeProposal.value?.tech_stack_id
    if (!stackId) return
    const fallback = Object.keys(techStacks.value).find(k => k !== stackId)
    if (!fallback) { pipelineCfg.error = "至少需要保留一个技术栈。"; return }
    if (activeProposal.value) activeProposal.value.tech_stack_id = fallback
    const src = pipelineCfg.config.tech_stacks as Record<string, any>
    if (src) delete src[stackId]
  }

  /* ──── 团队 ──── */
  const editingTeam = ref(false)

  function ensureProfileSelection(force = false) {
    const profileId = `${selectedSize.value}_${selectedFocus.value}`
    if (!force && teamProfiles.value[profileId]) {
      selectTeamProfile(profileId)
      return
    }
    if (teamProfiles.value[profileId]) { selectTeamProfile(profileId); return }
    const fallback = Object.keys(teamProfiles.value).find(k => k.startsWith(`${selectedSize.value}_`)) ?? Object.keys(teamProfiles.value)[0]
    if (fallback) selectTeamProfile(fallback)
  }

  function selectSize(size: string) {
    selectedSize.value = size
    ensureProfileSelection(true)
  }

  function selectFocus(focus: string) {
    selectedFocus.value = focus
    ensureProfileSelection(true)
  }

  function selectTeamProfile(profileId: string) {
    if (!activeProposal.value || !teamProfiles.value[profileId]) return
    activeProposal.value.team_profile_id = profileId
    syncSelectionFromProfile(profileId)
  }

  function addTeamRole() {
    const team = selectedTeamProfile.value as any
    if (!team?.roles) return
    team.roles.push({ role: "新角色", count: 1, focus: "补充职责说明" })
  }

  function deleteTeamRole(index: number) {
    const team = selectedTeamProfile.value as any
    if (!team?.roles || team.roles.length <= 1) return
    team.roles.splice(index, 1)
  }

  function addTeamProfile() {
    let idx = 1; let id = `custom_team_${idx}`
    while (teamProfiles.value[id]) id = `custom_team_${++idx}`
    const src = pipelineCfg.config.team_profiles as Record<string, any>
    if (!src) return
    const source = deepClone(selectedTeamProfile.value ?? {})
    src[id] = {
      ...source,
      id, size: "custom", focus: "custom",
      name: `自定义团队 ${idx}`,
      summary: "可按当前方案调整角色、人数和职责。",
      roles: (source as any).roles?.length ? (source as any).roles : [{ role: "项目经理", count: 1, focus: "统筹交付" }],
    }
    selectTeamProfile(id)
    editingTeam.value = true
  }

  function deleteTeamProfile() {
    const profileId = activeProposal.value?.team_profile_id
    if (!profileId) return
    const fallback = Object.keys(teamProfiles.value).find(k => k !== profileId)
    if (!fallback) { pipelineCfg.error = "至少需要保留一个团队模板。"; return }
    if (activeProposal.value) activeProposal.value.team_profile_id = fallback
    const src = pipelineCfg.config.team_profiles as Record<string, any>
    if (src) delete src[profileId]
  }

  /* ──── pipeline / upload / history ──── */
  const uploadPhase = reactive({ current: "idle" as "idle" | "uploading" | "starting", progress: 0 })
  const pipeline = usePipeline(BID_STAGE_DEFS)
  const wsClient = useWebSocket()
  const history = useHistory("tender")

  const canSubmit = computed(() =>
    !s.loading && !pipeline.isProcessing.value && proposalTabs.value.every(tab => {
      const proposal = proposals.value[tab.slot]
      if (!proposal) return false
      const team = teamProfiles.value[proposal.team_profile_id]
      if (!team) return false
      const total = (team.roles ?? []).reduce((sum, r) => sum + Number(r.count ?? 0), 0)
      return total > 0 && total <= 20
    }),
  )

  const submitLabel = computed(() => {
    if (uploadPhase.current === "uploading") return `正在上传… ${uploadPhase.progress}%`
    if (uploadPhase.current === "starting") return "正在启动流水线…"
    if (s.loading) return "正在生成方案…"
    return `生成 1 份中标方案 + ${referenceCount.value} 份参考方案`
  })

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
      url: bidDownloadUrl(pipeline.sessionId.value || "", f.download_url || f.name),
    })),
  )

  let _mainFiles: File[] = []
  let _refFiles: File[] = []

  function onMainFilesSelected(files: File[]) { _mainFiles = files }
  function onRefFilesSelected(files: File[]) { _refFiles = files }

  /* ──── 历史 API ──── */
  async function fetchHistorySessions(): Promise<SessionListItem[]> { return fetchBidSessions() }
  async function removeSession(sid: string): Promise<void> { return deleteBidSession(sid) }
  async function loadCacheTree(sid: string): Promise<FileTreeNode> { return fetchBidCacheTree(sid) }
  async function loadFileContent(sid: string, path: string): Promise<string> { return fetchBidFileContent(sid, path) }
  function buildDownloadUrl(sid: string, file: string): string { return bidDownloadUrl(sid, file) }

  function newSession() {
    s.sessionId = randomId()
    pipeline.reset()
    uploadPhase.current = "idle"
    uploadPhase.progress = 0
  }

  /* ──── 生成 ──── */
  async function generate() {
    if (!canSubmit.value) return
    s.loading = true
    s.result = ""

    /* 上传前预校验（与后端规则一致），不合法直接报错，不创建会话 */
    const allFiles = [..._mainFiles, ..._refFiles]
    const fileError = validateUploadFiles(allFiles)
    if (fileError) {
      s.loading = false
      throw new Error(fileError)
    }

    uploadPhase.current = "uploading"
    uploadPhase.progress = 0
    const session = await createBidSession()
    const sid = session.session_id
    pipeline.startProcessing(sid)

    /* 逐文件 XHR 上传，进度按「文件区间 + 字节进度」合成，粗到细都平滑 */
    for (let i = 0; i < allFiles.length; i++) {
      const file = allFiles[i]
      const type = _mainFiles.includes(file) ? "uploads" as const : "profile" as const
      const basePct = (i / allFiles.length) * 100
      const span = 100 / allFiles.length
      await xhrUploadFile(file, bidUploadUrl(sid, type), (pct) => {
        uploadPhase.progress = Math.min(99, Math.round(basePct + (pct / 100) * span))
      })
      uploadPhase.progress = Math.round(((i + 1) / allFiles.length) * 100)
    }

    if (!allFiles.length && activeProposal.value?.name) {
      await uploadBidText(sid, `方案名称: ${activeProposal.value.name}\n目标标包: ${s.targetPackage || "全包"}\n工期: ${activeProposal.value.delivery_days}天`)
    }

    uploadPhase.current = "starting"
    const pipelinePayload = buildPipelineConfig()
    // 先建 WS 再启动：流水线由后端后台任务立即执行，start 返回后才连接会丢掉最早的阶段消息
    wsClient.connect(bidWsUrl(sid), pipeline.handleMessage)
    await startBidPipeline(sid, {
      task_package_id: s.targetPackage ? Number(s.targetPackage) || null : null,
      winning_enabled: true,
      accompany_count: referenceCount.value,
      company: "",
      pipeline_config_yaml: JSON.stringify(pipelinePayload, null, 2),
    })

    s.loading = false
  }

  /* 进入时自动加载 */
  loadPipelineConfig()

  return reactive({
    s,
    /* pipeline config */
    pipelineCfg,
    selectedProposalSlot,
    proposals,
    techStacks,
    teamProfiles,
    techStackList,
    teamProfileList,
    activeProposal,
    selectedTechStack,
    selectedTeamProfile,
    selectedTeamRoles,
    selectedTeamTotal,
    referenceSlots,
    referenceCount,
    proposalTabs,
    selectedSize,
    selectedFocus,
    editingTechStack,
    editingTeam,
    loadPipelineConfig,
    savePipelineConfig,
    buildPipelineConfig,
    selectProposal,
    setReferenceCount,
    selectTechStack,
    addTechRow,
    deleteTechRow,
    addTechStack,
    deleteTechStack,
    ensureProfileSelection,
    selectSize,
    selectFocus,
    selectTeamProfile,
    addTeamRole,
    deleteTeamRole,
    addTeamProfile,
    deleteTeamProfile,
    /* core */
    canSubmit,
    submitLabel,
    uploadPhase,
    pipeline,
    wsClient,
    history,
    appPhase,
    outputDownloads,
    onMainFilesSelected,
    onRefFilesSelected,
    fetchHistorySessions,
    removeSession,
    loadCacheTree,
    loadFileContent,
    buildDownloadUrl,
    newSession,
    generate,
  })
}

export type TenderCtx = ReturnType<typeof createTenderState>
