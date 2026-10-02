import { computed, reactive, ref } from "vue"
import type { ComboConfig, StageConfig } from "@/data/registry-defaults"

/** 从输入文本中提炼要点条目 */
function points(text: string, fallback: string) {
  const src = text.trim() || fallback
  return src
    .split(/[\n。；;]/)
    .filter((s) => s.trim())
    .slice(0, 4)
    .map((s, i) => `${i + 1}. ${s.trim()}`)
    .join("\n")
}

/** 按阶段类型生成对应文本；未知类型走通用模板，使后台新建的组合同样可用 */
function renderStage(stage: StageConfig, index: number, ctx: { project: string; notes: string; days: number; files: string[] }) {
  const digest = points(ctx.notes, `依据 ${ctx.files[0] || "上传文件"} 中的内容`)
  const head = `《${ctx.project}》${stage.label.replace(/^阶段[一二三四五] · /, "")}`

  if (stage.id === "minutes") {
    return `${head}

【会议要点】
${digest}

【会议决议】
1. 与会各方确认项目方向与技术路线；
2. 由项目小组按本次结论推进后续文档编制；
3. 风险项纳入实施计划并指定责任人。

【待办事项】
- 完成方案初稿（负责人：技术负责人）
- 汇总报价明细（负责人：商务负责人）
- 组织内部评审（负责人：项目经理）`
  }

  if (stage.id === "tender") {
    return `${head}

一、项目概述
本文档依据"${ctx.project}"的${index === 0 ? "输入材料" : "上一阶段产出"}编制，方向与既有结论保持一致。

二、需求理解
${digest}

三、技术方案
1. 按确认的技术路线进行模块化架构设计；
2. 实施路径：需求调研 → 方案设计 → 开发实施 → 测试验收；
3. 已识别风险已纳入质量保障计划。

四、工期安排（共 ${ctx.days} 天）
调研确认 ${Math.round(ctx.days * 0.15)} 天 / 设计开发 ${Math.round(ctx.days * 0.6)} 天 / 测试交付 ${Math.round(
      ctx.days * 0.25,
    )} 天。

五、报价与服务承诺
报价明细详见附件，提供一年免费质保与 7x24 小时响应服务。`
  }

  if (stage.id === "contract") {
    return `${head}

项目名称：${ctx.project}
依据材料：${index === 0 ? ctx.files.join("、") || "（输入文本）" : "上一阶段产出文档"}

第一条 项目概况
本合同项目为"${ctx.project}"，服务范围以上一阶段确认的方案与承诺为准。

第二条 服务内容与交付
${digest}

第三条 服务期限
自双方签署之日起，服务周期共 ${ctx.days} 天，分阶段验收。

第四条 收费标准及支付方式
合同总金额为人民币【   】元（含税）；签订后 7 个工作日内支付 30% 预付款，验收合格后支付 70% 尾款。

第五条 违约与争议解决
逾期履行按合同总额 0.5‰/日计违约金；争议协商不成的提交项目所在地人民法院诉讼解决。`
  }

  /* 后台新建组合的通用阶段模板 */
  return `${head}

【输入摘要】
${digest}

【阶段产出】
本阶段由管理后台配置的组合规则驱动，产出文件：${stage.output}。
项目名称：${ctx.project}；周期参考：${ctx.days} 天。`
}

/**
 * 组合弹窗的共享状态：阶段列表完全来自管理后台的组合规则配置。
 */
export function createComboState(combo: () => ComboConfig | undefined) {
  const s = reactive({
    files: [] as string[],
    projectName: "",
    notes: "",
    durationDays: 180,
    /** 勾选要导出的阶段产出 */
    outputs: [] as string[],
    /** 0 = 未开始，n = 正在执行第 n 阶段，stages.length + 1 = 全部完成 */
    stage: 0,
    loading: false,
    /** 阶段 id → 生成文本 */
    results: {} as Record<string, string>,
  })

  const tab = ref("")

  const stages = computed<StageConfig[]>(() => combo()?.stages ?? [])

  /* 首次读取时默认全选输出 */
  const selectedOutputs = computed(() =>
    s.outputs.length ? s.outputs : stages.value.map((st) => st.id),
  )

  const disabled = computed(
    () => s.loading || !s.projectName.trim() || (!s.notes.trim() && !s.files.length),
  )

  const hasResult = computed(() => Object.keys(s.results).length > 0)
  const activeText = computed(() => s.results[tab.value] ?? "")

  function toggleOutput(id: string) {
    const list = selectedOutputs.value
    s.outputs = list.includes(id) ? list.filter((k) => k !== id) : [...list, id]
  }

  /** 阶段执行态：done / running / idle */
  function stageState(index: number) {
    if (s.stage > index + 1) return "done"
    if (s.stage === index + 1) return "running"
    return "idle"
  }

  function run() {
    if (disabled.value) return
    const list = stages.value
    if (!list.length) return

    s.loading = true
    s.results = {}
    s.stage = 0
    tab.value = list[0].id

    /* 逐阶段串行执行：每个阶段以上一阶段结果为输入 */
    const step = (index: number) => {
      if (index >= list.length) {
        s.stage = list.length + 1
        s.loading = false
        tab.value = selectedOutputs.value[0] ?? list[0].id
        return
      }
      s.stage = index + 1
      setTimeout(() => {
        const stage = list[index]
        s.results = {
          ...s.results,
          [stage.id]: renderStage(stage, index, {
            project: s.projectName,
            notes: index === 0 ? s.notes : s.results[list[index - 1].id] || s.notes,
            days: s.durationDays,
            files: s.files,
          }),
        }
        tab.value = stage.id
        step(index + 1)
      }, 1300)
    }

    step(0)
  }

  /* 用 reactive 包装：computed / ref 才会在模板中自动解包（普通对象里的 ref 不会） */
  return reactive({
    s,
    tab,
    stages,
    selectedOutputs,
    disabled,
    hasResult,
    activeText,
    toggleOutput,
    stageState,
    run,
  })
}

export type ComboCtx = ReturnType<typeof createComboState>
