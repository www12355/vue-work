import { computed, reactive, watch } from "vue"
import {
  CONFIG_VERSION,
  DEFAULT_CONFIG,
  defaultApiProxy,
  defaultDynamicSections,
  MAX_COMBO_MEMBERS,
  MIN_COMBO_MEMBERS,
  type ApiProxyConfig,
  type ComboConfig,
  type FieldConfig,
  type ModuleConfig,
  type SectionConfig,
  type SectionKind,
  type StageConfig,
  type WorkspaceConfig,
} from "@/data/registry-defaults"
import { readConfig, removeConfig, writeConfig } from "@/services/configService"
import type { DockedApp } from "@/data/apps"

/** 模块与组合共享同一套「弹窗区块」结构，统一称为 owner */
export type LayoutOwner = ModuleConfig | ComboConfig

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

/* 全局单例：优先读取管理后台保存过的配置，否则使用出厂默认值 */
const hasPersistedConfig = readConfig() !== null
const state = reactive<WorkspaceConfig>(readConfig() ?? clone(DEFAULT_CONFIG))

/* 任何配置变更都落盘，管理后台无需显式「保存」按钮 */
watch(state, () => writeConfig(clone(state)), { deep: true, flush: "post" })

export const config = state

/** 从磁盘的 proxy.config.json 配置中初始化模块的 api 字段
 * 这样能确保前端显示的配置和磁盘上的规则一致。
 *
 * 重要：如果用户已经在 localStorage 中有持久化配置，
 * 则不覆盖 enabled 字段，只同步技术参数（path/target/changeOrigin 等），
 * 防止用户显式关闭的代理在页面刷新后被磁盘文件重新启用。
 */
export function initProxyConfigFromDisk(diskRules: Array<{
  path: string
  target: string
  changeOrigin?: boolean
  stripPrefix?: boolean
  ws?: boolean
}>): void {
  // 将磁盘配置映射回模块的 api 字段
  for (const rule of diskRules) {
    const mod = state.modules.find(m => m.api?.path === rule.path)
    if (mod && mod.api) {
      // 有持久化配置时：保留用户对 enabled 的显式选择
      // 无持久化配置时（首次使用）：从磁盘规则推导 enabled = true
      const wasEnabled = hasPersistedConfig ? mod.api.enabled : true
      // 更新模块的 api 配置，与磁盘保持一致
      Object.assign(mod.api, {
        enabled: wasEnabled,
        path: rule.path,
        target: rule.target,
        changeOrigin: rule.changeOrigin ?? true,
        stripPrefix: rule.stripPrefix ?? false,
        ws: rule.ws ?? false,
      })
    }
  }

  // 禁用磁盘上没有的规则
  for (const mod of state.modules) {
    if (!mod.api?.path) continue
    const inDisk = diskRules.some(r => r.path === mod.api?.path)
    if (!inDisk && mod.api.enabled) {
      // 磁盘上已删除，同步这个变化
      mod.api.enabled = false
    }
  }

  console.log("✓ 从磁盘配置初始化完成")
}


export const modules = computed(() => state.modules)
export const combos = computed(() => state.combos)
export const readyModules = computed(() => state.modules.filter((m) => m.status === "ready"))
export const devModules = computed(() => state.modules.filter((m) => m.status === "dev"))
export const combinableModules = computed(() =>
  state.modules.filter((m) => m.status === "ready" && m.combinable),
)

export function getModule(id: string | null | undefined): ModuleConfig | undefined {
  return id ? state.modules.find((m) => m.id === id) : undefined
}

/** 更新某模块的接口代理配置（局部合并） */
export function updateModuleApi(id: string, patch: Partial<ApiProxyConfig>): void {
  const mod = getModule(id)
  if (!mod) return
  mod.api = { ...(mod.api ?? defaultApiProxy()), ...patch }
}

/** 代理规则的精简结构，用于生成 Vite 的 proxy.config.json */
export interface ProxyRule {
  path: string
  target: string
  changeOrigin: boolean
  stripPrefix: boolean
  ws: boolean
}

/** 已启用且填了 path/target 的代理规则（含路径重复冲突检测所需的全量集合另见 proxyPathConflicts） */
export const activeProxyRules = computed<ProxyRule[]>(() =>
  state.modules
    .filter((m) => m.api?.enabled && m.api.path.trim() && m.api.target.trim())
    .map((m) => ({
      path: m.api.path.trim(),
      target: m.api.target.trim(),
      changeOrigin: m.api.changeOrigin,
      stripPrefix: m.api.stripPrefix,
      ws: m.api.ws,
    })),
)

/** 生成写入 proxy.config.json 的内容字符串 */
export function buildProxyConfigJson(): string {
  return JSON.stringify(activeProxyRules.value, null, 2)
}

/** 从磁盘的 proxy.config.json 拉取规则并同步回模块状态（方向：磁盘 → 内存） */
export async function syncConfigFromDisk(): Promise<void> {
  try {
    // 优先使用 Vite 内置同步端点（开发环境），回落到独立同步服务
    const response = await fetch("/api/proxy-config-sync")
    if (!response.ok) {
      console.warn("⚠️  读取磁盘配置失败 (status:", response.status, ")")
      return
    }
    const diskRules: Array<{
      path: string
      target: string
      changeOrigin?: boolean
      stripPrefix?: boolean
      ws?: boolean
    }> = await response.json()
    initProxyConfigFromDisk(diskRules)
  } catch {
    // 同步服务不可用时静默失败
  }
}

/** 自动同步代理规则到磁盘的 proxy.config.json */
export async function syncProxyConfigToDisk(): Promise<void> {
  try {
    // 优先使用 Vite 内置同步端点（开发环境），回落到独立同步服务
    const response = await fetch("/api/proxy-config-sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: buildProxyConfigJson(),
    })
    if (!response.ok) {
      console.warn("⚠️  代理规则同步失败 (status:", response.status, ")")
    }
  } catch {
    // Vite 同步端点不可用（如生产环境），尝试独立同步服务
    try {
      const response = await fetch("http://127.0.0.1:3001/api/proxy-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: buildProxyConfigJson(),
      })
      if (!response.ok) {
        console.warn("⚠️  代理规则同步失败 (status:", response.status, ")")
      }
    } catch {
      // 同步服务不可用时静默失败（可能未启动），不影响前端运行
      // 用户可以通过手动下载 proxy.config.json 并重启 Vite 来生效
    }
  }
}

/** 路径前缀被多个已启用模块重复占用时返回冲突的 path 列表 */
export const proxyPathConflicts = computed<string[]>(() => {
  const seen = new Map<string, number>()
  activeProxyRules.value.forEach((r) => seen.set(r.path, (seen.get(r.path) ?? 0) + 1))
  return [...seen.entries()].filter(([, n]) => n > 1).map(([p]) => p)
})

// 监听 activeProxyRules 变化，自动同步到磁盘
watch(activeProxyRules, () => {
  syncProxyConfigToDisk()
})


export function getCombo(id: string | null | undefined): ComboConfig | undefined {
  return id ? state.combos.find((c) => c.id === id) : undefined
}

/** 按 id 找模块或组合 */
export function getOwner(id: string | null | undefined): LayoutOwner | undefined {
  return getModule(id) ?? getCombo(id)
}

export function isCombo(id: string | null | undefined): boolean {
  return !!getCombo(id)
}

/** 该 id 是否为「结构可编辑」的对象（后台新增的动态模块可增删区块与字段） */
export function canEditStructure(id: string | null | undefined): boolean {
  const mod = getModule(id)
  return !!mod && mod.renderer === "dynamic"
}

/** 组合是否包含某模块 */
export function comboIncludes(comboId: string, moduleId: string): boolean {
  return !!getCombo(comboId)?.members.includes(moduleId)
}

/** 组合成员是否都「已上线且允许组合」 */
function membersUsable(combo: ComboConfig): boolean {
  return combo.members.every((id) => {
    const m = getModule(id)
    return !!m && m.status === "ready" && m.combinable
  })
}

/** 按成员集合精确匹配已启用的组合规则（顺序无关） */
export function findComboByMembers(ids: string[]): ComboConfig | undefined {
  const want = [...new Set(ids)]
  if (want.length < MIN_COMBO_MEMBERS || want.length > MAX_COMBO_MEMBERS) return undefined
  return state.combos.find(
    (c) =>
      c.enabled &&
      c.members.length === want.length &&
      want.every((id) => c.members.includes(id)) &&
      membersUsable(c),
  )
}

/** 查找两个模块之间已启用的组合规则；找不到表示这两个功能不支持组合 */
export function findCombo(a: string, b: string): ComboConfig | undefined {
  return a === b ? undefined : findComboByMembers([a, b])
}

/**
 * 把 addId 叠加到当前载入项上时应触发的组合。
 * current 既可以是单个模块（→ 两元组合），也可以是已有组合（→ 追加为 3 / 4 元组合）。
 */
export function findComboWith(currentId: string, addId: string): ComboConfig | undefined {
  if (currentId === addId) return undefined
  const combo = getCombo(currentId)
  if (!combo) return findComboByMembers([currentId, addId])
  if (combo.members.includes(addId)) return undefined
  return findComboByMembers([...combo.members, addId])
}

/** 组合中除 moduleId 之外的其余成员 */
export function comboMembersWithout(comboId: string, moduleId: string): string[] {
  return getCombo(comboId)?.members.filter((id) => id !== moduleId) ?? []
}

/**
 * 从组合中移除一个成员后应载入的目标：
 * 仅剩一个成员则载入该模块，仍有多个则优先落到对应的子组合规则。
 */
export function dockTargetWithout(comboId: string, moduleId: string): string | null {
  const rest = comboMembersWithout(comboId, moduleId)
  if (!rest.length) return null
  if (rest.length === 1) return rest[0]
  return findComboByMembers(rest)?.id ?? rest[0]
}

/** 主卡片展示用的元数据 */
export function dockedMetaOf(id: string | null): DockedApp | null {
  const owner = getOwner(id)
  if (!owner) return null
  return {
    title: owner.title,
    desc: owner.heroDesc,
    image: owner.image,
    imageAlt: owner.imageAlt,
    tags: owner.tags,
  }
}

/** 弹窗标题栏文案 */
export function windowMetaOf(id: string): { title: string; desc: string } {
  const owner = getOwner(id)
  return { title: owner?.title ?? "功能", desc: owner?.windowDesc ?? "" }
}

export function sectionsOf(id: string): SectionConfig[] {
  return getOwner(id)?.sections ?? []
}

/** 某一列中可见的区块，顺序即后台配置的顺序 */
export function visibleSections(id: string, column: "left" | "right"): SectionConfig[] {
  return sectionsOf(id).filter((s) => s.visible && s.column === column)
}

/* ---------------- 模块维护 ---------------- */

function uid(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export type NewModuleInput = {
  title: string
  desc: string
  windowDesc?: string
  icon?: string
  image?: string
  imageAlt?: string
  status?: ModuleConfig["status"]
  combinable?: boolean
  submitLabel?: string
}

/** 新增模块：默认落为「待开发」，弹窗使用动态表单渲染器 */
export function createModule(input: NewModuleInput): ModuleConfig {
  const id = uid("mod")
  const mod: ModuleConfig = {
  id,
    title: input.title.trim() || "未命名模块",
    desc: input.desc.trim() || "暂无描述",
    heroDesc: input.desc.trim() || "暂无描述",
    windowDesc: input.windowDesc?.trim() || "该模块的表单与布局可在管理后台调整",
    image: input.image ?? "",
    imageAlt: input.imageAlt?.trim() || input.title.trim(),
    tags: ["后台新增", input.status === "ready" ? "已上线" : "待开发"],
    icon: input.icon || "Sparkles",
    status: input.status ?? "dev",
    combinable: input.combinable ?? false,
    renderer: "dynamic",
    builtin: false,
  submitLabel: input.submitLabel?.trim() || "开始生成",
  sections: defaultDynamicSections(),
  api: defaultApiProxy(`/api/${id.replace(/^mod_/, "")}`),
  }
  state.modules.push(mod)
  return mod
  }

export function updateModule(id: string, patch: Partial<ModuleConfig>): void {
  const mod = getModule(id)
  if (!mod) return
  const wasDev = mod.status === "dev"
  Object.assign(mod, patch)
  /*
   * 禁止组合是显式意图变更，直接停用相关规则。
   * 而「撤下为待开发」是可逆操作：不改动 enabled，由 membersUsable 在运行时屏蔽，
   * 模块重新上线后组合规则即自动恢复。
   */
  if (!mod.combinable) {
    state.combos.forEach((c) => {
      if (c.members.includes(id)) c.enabled = false
    })
  }
  /*
   * 从「待开发」重新上线时，将模块插入到最后一个「已上线」模块之后，
   * 确保按重新添加的先后顺序排列：谁先添加谁在前。
   */
  if (wasDev && mod.status === "ready") {
    const idx = state.modules.indexOf(mod)
    if (idx >= 0) {
      state.modules.splice(idx, 1)
      // 找到最后一个已上线模块的位置，插入到它后面
      let insertAt = 0
      for (let i = state.modules.length - 1; i >= 0; i--) {
        if (state.modules[i].status === "ready") {
          insertAt = i + 1
          break
        }
      }
      state.modules.splice(insertAt, 0, mod)
    }
  }
}

/** 删除模块（内置模块不可删），同时清理引用它的组合规则 */
export function deleteModule(id: string): void {
  const mod = getModule(id)
  if (!mod || mod.builtin) return
  state.modules = state.modules.filter((m) => m.id !== id)
  state.combos = state.combos.filter((c) => !c.members.includes(id))
}

/* ---------------- 弹窗区块维护 ---------------- */

export function updateSection(ownerId: string, sectionId: string, patch: Partial<SectionConfig>): void {
  const section = getOwner(ownerId)?.sections.find((s) => s.id === sectionId)
  if (section) Object.assign(section, patch)
}

export function toggleSection(ownerId: string, sectionId: string): void {
  const section = getOwner(ownerId)?.sections.find((s) => s.id === sectionId)
  if (section) section.visible = !section.visible
}

/** 在所属列内上/下移动区块 */
export function moveSection(ownerId: string, sectionId: string, dir: -1 | 1): void {
  const owner = getOwner(ownerId)
  if (!owner) return
  const list = owner.sections
  const index = list.findIndex((s) => s.id === sectionId)
  if (index < 0) return
  const column = list[index].column
  /* 找到同一列中相邻的那个区块并交换位置 */
  let target = -1
  for (let i = index + dir; i >= 0 && i < list.length; i += dir) {
    if (list[i].column === column) {
      target = i
      break
    }
  }
  if (target < 0) return
  const [item] = list.splice(index, 1)
  list.splice(target, 0, item)
}

export function addSection(
  ownerId: string,
  column: "left" | "right" = "left",
  kind: SectionKind = "form",
): void {
  if (!canEditStructure(ownerId)) return
  const base = { id: uid("sec"), column, visible: true, kind }
  if (kind === "upload") {
    getOwner(ownerId)?.sections.push({
      ...base,
      label: "文件上传",
      upload: {
        hint: "点击选择文件",
        formats: "DOCX / PDF / Markdown",
        accept: ".doc,.docx,.pdf,.md",
        multiple: true,
      },
    })
  } else if (kind === "result") {
    getOwner(ownerId)?.sections.push({
      ...base,
      label: "生成结果",
      result: { emptyHint: "填写表单后点击底部按钮生成", minHeight: 220 },
    })
  } else {
    getOwner(ownerId)?.sections.push({ ...base, label: "新区块", fields: [] })
  }
}

export function deleteSection(ownerId: string, sectionId: string): void {
  const owner = getOwner(ownerId)
  if (!owner || !canEditStructure(ownerId)) return
  owner.sections = owner.sections.filter((s) => s.id !== sectionId)
}

/* ---------------- 动态表单字段维护 ---------------- */

export function addField(ownerId: string, sectionId: string): void {
  const section = getOwner(ownerId)?.sections.find((s) => s.id === sectionId)
  if (!section || !canEditStructure(ownerId)) return
  section.fields = [
    ...(section.fields ?? []),
    { id: uid("f"), label: "新字段", type: "text", placeholder: "" },
  ]
}

export function updateField(
  ownerId: string,
  sectionId: string,
  fieldId: string,
  patch: Partial<FieldConfig>,
): void {
  const field = getOwner(ownerId)
    ?.sections.find((s) => s.id === sectionId)
    ?.fields?.find((f) => f.id === fieldId)
  if (field) Object.assign(field, patch)
}

export function deleteField(ownerId: string, sectionId: string, fieldId: string): void {
  const section = getOwner(ownerId)?.sections.find((s) => s.id === sectionId)
  if (!section?.fields) return
  section.fields = section.fields.filter((f) => f.id !== fieldId)
}

/* ---------------- 组合规则维护 ---------------- */

/** 尚未配置组合规则的模块两两组合 */
export const availablePairs = computed(() => {
  const list = combinableModules.value
  const pairs: { a: ModuleConfig; b: ModuleConfig }[] = []
  for (let i = 0; i < list.length; i++) {
    for (let j = i + 1; j < list.length; j++) {
      const exists = state.combos.some(
        (c) => c.members.includes(list[i].id) && c.members.includes(list[j].id),
      )
      if (!exists) pairs.push({ a: list[i], b: list[j] })
    }
  }
  return pairs
})

const ORDINALS = ["一", "二", "三", "四"]

/** 阶段标题里的序号前缀由成员顺序决定，自定义部分（" · " 之后）保留 */
function stageLabel(index: number, name: string) {
  return `阶段${ORDINALS[index] ?? index + 1} · ${name}`
}

function autoTitleOf(ids: string[]) {
  return ids.map((id) => getModule(id)?.title ?? id).join(" × ")
}

function autoSubmitLabelOf(ids: string[]) {
  return `运行组合流水线：${ids.map((id) => getModule(id)?.title ?? id).join(" → ")}`
}

/** 成员变化后同步阶段与自动生成的文案（用户改过的标题/按钮文案不覆盖） */
function syncComboMembers(combo: ComboConfig, prevMembers: string[]): void {
  const titleWasAuto = combo.title === autoTitleOf(prevMembers)
  const submitWasAuto = combo.submitLabel === autoSubmitLabelOf(prevMembers)

  /* 按成员顺序重建阶段列表，已存在的阶段保留其自定义说明与产出文件名 */
  combo.stages = combo.members.map((id, i) => {
    const mod = getModule(id)
    const name = mod?.title ?? id
    const prev = combo.stages.find((s) => s.id === id)
    const customName = prev?.label.includes(" · ") ? prev.label.split(" · ").slice(1).join(" · ") : name
    return {
      id,
      label: stageLabel(i, customName),
      desc: prev?.desc ?? (i === 0 ? `执行${name}` : `基于上一阶段结果执行${name}`),
      icon: mod?.icon ?? "Layers",
      output: prev?.output ?? `${name}.docx`,
    }
  })

  if (titleWasAuto) combo.title = autoTitleOf(combo.members)
  if (submitWasAuto) combo.submitLabel = autoSubmitLabelOf(combo.members)
  combo.tags = ["组合模式", ...combo.members.map((id) => getModule(id)?.title ?? id)]
}

/** 新建组合：支持 2 ~ 4 个模块串联 */
export function createCombo(...memberIds: string[]): ComboConfig | undefined {
  const ids = [...new Set(memberIds)].filter((id) => !!getModule(id))
  if (ids.length < MIN_COMBO_MEMBERS || ids.length > MAX_COMBO_MEMBERS) return undefined
  /* 同一成员集合只允许存在一条规则 */
  if (findComboByMembers(ids) || state.combos.some((c) => c.members.length === ids.length && ids.every((id) => c.members.includes(id)))) {
    return undefined
  }

  const names = ids.map((id) => getModule(id)!.title)
  const combo: ComboConfig = {
    id: uid("combo"),
    members: ids,
    title: autoTitleOf(ids),
    desc: `${names.join("、")}串联执行，一次输入产出 ${ids.length} 份文档`,
    heroDesc: `组合模式：${names.join(" → ")} 依次执行，一次输入产出 ${ids.length} 份文档`,
    windowDesc: `组合模式专属页面：${names.join(" → ")} 依次执行`,
    image: "/images/combo-workflow.png",
    imageAlt: `${autoTitleOf(ids)} 组合工作流`,
    tags: ["组合模式", ...names],
    icon: "Layers",
    enabled: true,
    submitLabel: autoSubmitLabelOf(ids),
    stages: ids.map((id, i) => {
      const mod = getModule(id)!
      return {
        id,
        label: stageLabel(i, mod.title),
        desc: i === 0 ? `执行${mod.title}` : `基于上一阶段结果执行${mod.title}`,
        icon: mod.icon,
        output: `${mod.title}.docx`,
      }
    }),
    sections: [
      { id: "upload", label: "文件上传", column: "left", visible: true },
      { id: "info", label: "项目信息", column: "left", visible: true },
      { id: "pipeline", label: "组合流水线", column: "right", visible: true },
      { id: "outputs", label: "输出文档", column: "right", visible: true },
      { id: "result", label: "组合产出", column: "right", visible: true },
    ],
  }
  state.combos.push(combo)
  return combo
}

/** 可加入某组合的模块：已上线、允许组合、且尚未成为成员 */
export function candidateMembersFor(comboId: string): ModuleConfig[] {
  const combo = getCombo(comboId)
  if (!combo || combo.members.length >= MAX_COMBO_MEMBERS) return []
  return combinableModules.value.filter((m) => !combo.members.includes(m.id))
}

/** 追加成员（最多 4 个），并同步流水线阶段 */
export function addComboMember(comboId: string, moduleId: string): void {
  const combo = getCombo(comboId)
  const mod = getModule(moduleId)
  if (!combo || !mod || combo.members.includes(moduleId)) return
  if (combo.members.length >= MAX_COMBO_MEMBERS) return
  const prev = [...combo.members]
  combo.members = [...combo.members, moduleId]
  syncComboMembers(combo, prev)
}

/** 移除成员（至少保留 2 个），并同步流水线阶段 */
export function removeComboMember(comboId: string, moduleId: string): void {
  const combo = getCombo(comboId)
  if (!combo || combo.members.length <= MIN_COMBO_MEMBERS) return
  const prev = [...combo.members]
  combo.members = combo.members.filter((id) => id !== moduleId)
  syncComboMembers(combo, prev)
}

  /** 调整成员顺序，即调整流水线阶段顺序 */
export function moveComboMember(comboId: string, moduleId: string, dir: -1 | 1): void {
  const combo = getCombo(comboId)
  if (!combo) return
  const index = combo.members.indexOf(moduleId)
  const target = index + dir
  if (index < 0 || target < 0 || target >= combo.members.length) return
  const prev = [...combo.members]
  const next = [...combo.members]
  ;[next[index], next[target]] = [next[target], next[index]]
  combo.members = next
  syncComboMembers(combo, prev)
}

/** 拖拽重排：把 fromIndex 处的成员移动到 toIndex（连线画布用） */
export function reorderComboMembers(comboId: string, fromIndex: number, toIndex: number): void {
  const combo = getCombo(comboId)
  if (!combo) return
  const n = combo.members.length
  if (fromIndex < 0 || fromIndex >= n || toIndex < 0 || toIndex >= n || fromIndex === toIndex) return
  const prev = [...combo.members]
  const next = [...combo.members]
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  combo.members = next
  syncComboMembers(combo, prev)
}

export { MAX_COMBO_MEMBERS, MIN_COMBO_MEMBERS }

export function updateCombo(id: string, patch: Partial<ComboConfig>): void {
  const combo = getCombo(id)
  if (combo) Object.assign(combo, patch)
}

export function updateStage(comboId: string, stageId: string, patch: Partial<StageConfig>): void {
  const stage = getCombo(comboId)?.stages.find((s) => s.id === stageId)
  if (stage) Object.assign(stage, patch)
}

export function deleteCombo(id: string): void {
  state.combos = state.combos.filter((c) => c.id !== id)
}

/** 恢复出厂配置 */
export function resetConfig(): void {
  const fresh = clone(DEFAULT_CONFIG)
  state.version = CONFIG_VERSION
  state.modules = fresh.modules
  state.combos = fresh.combos
  removeConfig()
}
