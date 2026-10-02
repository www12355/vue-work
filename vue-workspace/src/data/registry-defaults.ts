/**
 * 工作台配置的数据模型与出厂默认值。
 *
 * - modules：功能模块（内置模块 + 管理后台新增的待开发模块）
 * - combos：组合规则（哪两个模块可以组合、组合后的流水线阶段与产出）
 * - 每个模块 / 组合都带 sections（弹窗区块），决定弹窗页面的显隐、排序与标题
 */

/** ready = 已上线可用；dev = 待开发（工作台以占位样式展示，不可载入） */
export type ModuleStatus = "ready" | "dev"

/** 弹窗渲染器：内置模块用专属实现，后台新增模块统一用 dynamic 表单渲染器 */
export type RendererKind = "tender" | "minutes" | "contract" | "dynamic"

export type FieldType = "text" | "textarea" | "number" | "date" | "select"

/** dynamic 渲染器的表单字段 */
export interface FieldConfig {
  id: string
  label: string
  type: FieldType
  placeholder?: string
  /** type = select 时的候选项 */
  options?: string[]
  required?: boolean
}

/**
 * 区块类型（dynamic 渲染器）：
 * - form：表单字段区块
 * - upload：文件上传区块
 * - result：生成结果预览区块
 */
export type SectionKind = "form" | "upload" | "result"

/** 文件上传区块的可配置项（对应前端上传区的实际能力） */
export interface UploadConfig {
  /** 上传框主提示文案 */
  hint?: string
  /** 接受的文件类型说明（展示用），如「DOCX / PDF / Markdown」 */
  formats?: string
  /** input accept 属性，如「.doc,.docx,.pdf,.md」 */
  accept?: string
  /** 是否允许多选 */
  multiple?: boolean
}

/** 生成结果区块的可配置项 */
export interface ResultConfig {
  /** 结果为空时的占位提示文案 */
  emptyHint?: string
  /** 结果区最小高度（px） */
  minHeight?: number
}

/** 弹窗区块：id 对应弹窗实现里的一块内容，label / column / visible 由后台控制 */
export interface SectionConfig {
  id: string
  label: string
  column: "left" | "right"
  visible: boolean
  /** 区块类型；缺省时按 id 推断（见 sectionKind） */
  kind?: SectionKind
  /** 区块副标题 / 说明文字（可选） */
  description?: string
  /** kind = form 时的表单字段 */
  fields?: FieldConfig[]
  /** kind = upload 时的上传配置 */
  upload?: UploadConfig
  /** kind = result 时的结果配置 */
  result?: ResultConfig
}

/** 推断区块类型：优先用显式 kind，否则按内置 id 兼容旧数据 */
export function sectionKind(section: SectionConfig): SectionKind {
  if (section.kind) return section.kind
  if (section.id === "upload") return "upload"
  if (section.id === "result" || section.id === "preview") return "result"
  return "form"
}

export const SECTION_KIND_LABEL: Record<SectionKind, string> = {
  form: "表单字段",
  upload: "文件上传",
  result: "生成结果",
}

/**
 * 模块的接口代理配置：Vite 开发服务器按 path 前缀把请求代理到不同后端。
 * 例如 path="/api/tender"、target="http://localhost:4001" 时，
 * 前端请求 /api/tender/xxx 会被转发到 http://localhost:4001/...。
 */
export interface ApiProxyConfig {
  /** 是否启用该代理规则 */
  enabled: boolean
  /** 路径前缀，需以 / 开头，例如 /api/tender */
  path: string
  /** 后端目标地址，例如 http://localhost:4001 */
  target: string
  /** 转发时改写 Host 头为目标地址（跨域后端通常需要） */
  changeOrigin: boolean
  /** 是否去掉 path 前缀后再转发（rewrite） */
  stripPrefix: boolean
  /** 是否代理 WebSocket */
  ws: boolean
}

/** 新增模块 / 未配置时的默认代理规则 */
export function defaultApiProxy(path = ""): ApiProxyConfig {
  return {
    enabled: false,
    path,
    target: "",
    changeOrigin: true,
    stripPrefix: false,
    ws: false,
  }
}

export interface ModuleConfig {
  id: string
  title: string
  /** 右栏功能卡描述 */
  desc: string
  /** 载入工作区后主卡片上的描述 */
  heroDesc: string
  /** 弹窗标题栏副标题 */
  windowDesc: string
  image: string
  imageAlt: string
  tags: string[]
  icon: string
  status: ModuleStatus
  /** 是否允许参与组合 */
  combinable: boolean
  renderer: RendererKind
  /** 内置模块不可删除 */
  builtin: boolean
  submitLabel: string
  sections: SectionConfig[]
  /** 接口代理：Vite 按 path 前缀代理到该模块的后端 */
  api: ApiProxyConfig
}

export interface StageConfig {
  id: string
  label: string
  desc: string
  icon: string
  /** 产出文件名 */
  output: string
}

/** 一个组合最少 2 个、最多 4 个模块串联 */
export const MIN_COMBO_MEMBERS = 2
export const MAX_COMBO_MEMBERS = 4

export interface ComboConfig {
  id: string
  /** 参与组合的模块 id，长度 2 ~ MAX_COMBO_MEMBERS，顺序即流水线顺序 */
  members: string[]
  title: string
  desc: string
  heroDesc: string
  windowDesc: string
  image: string
  imageAlt: string
  tags: string[]
  icon: string
  enabled: boolean
  stages: StageConfig[]
  submitLabel: string
  sections: SectionConfig[]
}

export interface WorkspaceConfig {
  version: number
  modules: ModuleConfig[]
  combos: ComboConfig[]
}

/** 4：区块新增 kind（表单/上传/结果）及上传、结果的可配置项 */
export const CONFIG_VERSION = 4

/** 可选封面图：public/images 下已有的素材，新增模块时从中挑选 */
export const IMAGE_OPTIONS = [
  { value: "", label: "无封面（纯深色卡片）" },
  { value: "/images/tender-doc.png", label: "投标文件" },
  { value: "/images/meeting-notes.png", label: "会议笔记" },
  { value: "/images/contract-doc.png", label: "合同文件" },
  { value: "/images/combo-workflow.png", label: "组合工作流" },
  { value: "/images/data-report.png", label: "数据报告" },
  { value: "/images/finance-sheet.png", label: "财务报表" },
  { value: "/images/weekly-plan.png", label: "周报计划" },
  { value: "/images/email-marketing.png", label: "邮件营销" },
  { value: "/images/presentation.png", label: "演示文稿" },
  { value: "/images/hr-recruit.png", label: "招聘人事" },
]

/** 组合弹窗的默认区块（组合页结构固定，后台可调显隐与排序） */
const COMBO_SECTIONS: SectionConfig[] = [
  { id: "upload", label: "文件上传", column: "left", visible: true },
  { id: "info", label: "项目信息", column: "left", visible: true },
  { id: "pipeline", label: "组合流水线", column: "right", visible: true },
  { id: "outputs", label: "输出文档", column: "right", visible: true },
  { id: "result", label: "组合产出", column: "right", visible: true },
]

export const DEFAULT_CONFIG: WorkspaceConfig = {
  version: CONFIG_VERSION,
  modules: [
    {
      id: "tender",
      title: "标书生成",
      desc: "输入项目信息与招标需求，AI 一键生成结构化投标书",
      heroDesc: "输入项目信息与招标需求，AI 一键生成结构化投标书，涵盖项目概述、技术方案与报价说明",
      windowDesc: "上传招标文件，按 pipeline_config.yaml 的技术栈、团队和工期生成主方案",
      image: "/images/tender-doc.png",
      imageAlt: "深色桌面上的投标文件与合同资料",
      tags: ["AI 生成", "结构化文档", "一键导出"],
      icon: "FileText",
      status: "ready",
      combinable: true,
      renderer: "tender",
      builtin: true,
      submitLabel: "生成中标方案",
      sections: [
        { id: "main-upload", label: "招标文件上传", column: "left", visible: true },
        { id: "ref-upload", label: "参考文件上传", column: "left", visible: true },
        { id: "gen-config", label: "生成配置", column: "right", visible: true },
        { id: "tech-stack", label: "技术栈", column: "right", visible: true },
        { id: "team-config", label: "团队配置", column: "right", visible: true },
      ],
      api: {
        enabled: true,
        path: "/api/tender",
        target: "http://localhost:8001",
        changeOrigin: true,
        stripPrefix: false,
        ws: true,
      },
    },
    {
      id: "minutes",
      title: "会议纪要生成",
      desc: "粘贴会议记录原文，自动提炼要点、决议与待办事项",
      heroDesc: "粘贴会议记录原文，自动提炼会议要点、决议事项与待办清单，快速沉淀会议成果",
      windowDesc: "粘贴会议记录，自动提炼要点与待办",
      image: "/images/meeting-notes.png",
      imageAlt: "会议室中带手写笔记的笔记本与笔记本电脑",
      tags: ["智能提炼", "要点归纳", "待办清单"],
      icon: "ClipboardList",
      status: "ready",
      combinable: true,
      renderer: "minutes",
      builtin: true,
      submitLabel: "生成会议纪要",
      sections: [
        { id: "topic", label: "会议主题", column: "left", visible: true },
        { id: "notes", label: "会议记录原文", column: "left", visible: true },
        { id: "preview", label: "纪要预览", column: "right", visible: true },
      ],
      api: {
        enabled: true,
        path: "/api/minutes",
        target: "http://localhost:4002",
        changeOrigin: true,
        stripPrefix: false,
        ws: false,
      },
    },
    {
      id: "contract",
      title: "合同生成",
      desc: "填写双方信息与关键条款，一键生成标准合同文本",
      heroDesc: "填写合同名称、甲乙双方与关键条款，AI 一键生成含支付方式、保密与违约责任的标准合同文本",
      windowDesc: "填写合同信息，AI 自动生成合同文档",
      image: "/images/contract-doc.png",
      imageAlt: "深色办公桌上待签署的合同文件与钢笔",
      tags: ["标准条款", "双方信息", "一键导出"],
      icon: "FileSignature",
      status: "ready",
      combinable: true,
      renderer: "contract",
      builtin: true,
      submitLabel: "开始生成合同",
      sections: [
        { id: "basic", label: "基本信息", column: "left", visible: true },
        { id: "parties", label: "甲乙方信息", column: "left", visible: true },
        { id: "duration", label: "服务期限", column: "left", visible: true },
        { id: "summary", label: "生成配置", column: "right", visible: true },
        { id: "core-files", label: "核心文件（本次生成主要依据）", column: "right", visible: true },
        { id: "ref-files", label: "参考文件（辅助参考）", column: "right", visible: true },
        { id: "prompt", label: "补充需求说明", column: "right", visible: true },
      ],
      api: {
        enabled: true,
        path: "/api/contract",
        target: "http://localhost:8002",
        changeOrigin: true,
        stripPrefix: true,
        ws: true,
      },
    },
  ],
  combos: [
    {
      id: "combo-tender-minutes",
      members: ["minutes", "tender"],
      title: "标书 × 会议纪要",
      desc: "会议记录一次输入，自动提炼纪要并同步产出标书草案",
      heroDesc: "组合模式：会议记录一次输入，自动提炼纪要要点，并基于会议结论同步产出标书草案",
      windowDesc: "组合模式专属页面：纪要提炼与标书生成串联执行，一次输入产出两份文档",
      image: "/images/combo-workflow.png",
      imageAlt: "投标文件与会议笔记在办公桌上相连的组合工作流",
      tags: ["组合模式", "纪要提炼", "标书草案"],
      icon: "Layers",
      enabled: true,
      submitLabel: "运行组合流水线：会议纪要 → 标书草案",
      stages: [
        {
          id: "minutes",
          label: "阶段一 · 会议纪要提炼",
          desc: "识别会议要点、决议与待办",
          icon: "ClipboardList",
          output: "会议纪要.docx",
        },
        {
          id: "tender",
          label: "阶段二 · 标书草案生成",
          desc: "以纪要结论作为标书输入",
          icon: "FileText",
          output: "标书草案.docx",
        },
      ],
      sections: COMBO_SECTIONS.map((s) => ({ ...s })),
    },
    {
      id: "combo-tender-contract",
      members: ["tender", "contract"],
      title: "标书 × 合同",
      desc: "以中标方案要点为依据，串联生成配套服务合同草案",
      heroDesc: "组合模式：先提炼标书方案要点，再据此生成条款完整的配套服务合同草案",
      windowDesc: "组合模式专属页面：标书要点提炼与合同起草串联执行，一次输入产出两份文档",
      image: "/images/combo-workflow.png",
      imageAlt: "投标文件与合同文件相连的组合工作流",
      tags: ["组合模式", "方案要点", "合同草案"],
      icon: "Layers",
      enabled: true,
      submitLabel: "运行组合流水线：标书要点 → 合同草案",
      stages: [
        {
          id: "tender",
          label: "阶段一 · 标书要点提炼",
          desc: "梳理项目范围、技术方案与交付承诺",
          icon: "FileText",
          output: "标书要点.docx",
        },
        {
          id: "contract",
          label: "阶段二 · 合同草案生成",
          desc: "按标书承诺生成对应权责与付款条款",
          icon: "FileSignature",
          output: "服务合同草案.docx",
        },
      ],
      sections: COMBO_SECTIONS.map((s) => ({ ...s })),
    },
    {
      id: "combo-minutes-contract",
      members: ["minutes", "contract"],
      title: "会议纪要 × 合同",
      desc: "从会议决议直接提取商务口径，生成合同草案",
      heroDesc: "组合模式：先沉淀会议决议，再把决议中的商务口径落成合同草案",
      windowDesc: "组合模式专属页面：纪要提炼与合同起草串联执行，一次输入产出两份文档",
      image: "/images/combo-workflow.png",
      imageAlt: "会议笔记与合同文件相连的组合工作流",
      tags: ["组合模式", "会议决议", "合同草案"],
      icon: "Layers",
      enabled: false,
      submitLabel: "运行组合流水线：会议纪要 → 合同草案",
      stages: [
        {
          id: "minutes",
          label: "阶段一 · 会议纪要提炼",
          desc: "识别会议要点、决议与待办",
          icon: "ClipboardList",
          output: "会议纪要.docx",
        },
        {
          id: "contract",
          label: "阶段二 · 合同草案生成",
          desc: "把会议决议转成合同条款",
          icon: "FileSignature",
          output: "服务合同草案.docx",
        },
      ],
      sections: COMBO_SECTIONS.map((s) => ({ ...s })),
    },
    {
      id: "combo-minutes-tender-contract",
      members: ["minutes", "tender", "contract"],
      title: "会议纪要 × 标书 × 合同",
      desc: "一次输入贯通会议决议、标书方案与服务合同三份文档",
      heroDesc: "组合模式：会议决议 → 标书方案 → 服务合同 依次串联执行，一次输入产出三份文档",
      windowDesc: "组合模式专属页面：纪要提炼、标书生成与合同起草依次执行",
      image: "/images/combo-workflow.png",
      imageAlt: "会议笔记、投标文件与合同文件相连的组合工作流",
      tags: ["组合模式", "会议纪要生成", "标书生成", "合同生成"],
      icon: "Layers",
      enabled: true,
      submitLabel: "运行组合流水线：会议纪要 → 标书 → 合同",
      stages: [
        {
          id: "minutes",
          label: "阶段一 · 会议纪要提炼",
          desc: "识别会议要点、决议与待办",
          icon: "ClipboardList",
          output: "会议纪要.docx",
        },
        {
          id: "tender",
          label: "阶段二 · 标书草案生成",
          desc: "以纪要结论作为标书输入",
          icon: "FileText",
          output: "标书草案.docx",
        },
        {
          id: "contract",
          label: "阶段三 · 合同草案生成",
          desc: "按标书承诺生成对应权责与付款条款",
          icon: "FileSignature",
          output: "服务合同草案.docx",
        },
      ],
      sections: COMBO_SECTIONS.map((s) => ({ ...s })),
    },
  ],
}

/** 新增模块时的默认弹窗区块（dynamic 渲染器） */
export function defaultDynamicSections(): SectionConfig[] {
  return [
  {
  id: "inputs",
  label: "基本信息",
  column: "left",
  visible: true,
  kind: "form",
  fields: [
  { id: "title", label: "文档名称", type: "text", placeholder: "请输入文档名称", required: true },
  { id: "note", label: "补充说明", type: "textarea", placeholder: "补充生成要求…" },
  ],
  },
  {
  id: "upload",
  label: "文件上传",
  column: "left",
  visible: true,
  kind: "upload",
  upload: {
  hint: "点击选择文件",
  formats: "DOCX / PDF / Markdown",
  accept: ".doc,.docx,.pdf,.md",
  multiple: true,
  },
  },
  {
  id: "result",
  label: "生成结果",
  column: "right",
  visible: true,
  kind: "result",
  result: { emptyHint: "填写表单后点击底部按钮生成", minHeight: 220 },
  },
  ]
}
