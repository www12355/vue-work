import { computed, reactive } from "vue"

/** 从会议记录原文中提炼要点条目 */
function extractPoints(text: string, max: number) {
  return text
    .split(/[\n。；;]/)
    .filter((s) => s.trim())
    .slice(0, max)
    .map((s, i) => `${i + 1}. ${s.trim()}`)
    .join("\n")
}

/**
 * 会议纪要弹窗的共享状态。区块拆分后由管理后台决定顺序与显隐。
 */
export function createMinutesState() {
  const s = reactive({
    topic: "",
    notes: "",
    loading: false,
    result: "",
  })

  const disabled = computed(() => s.loading || !s.notes.trim())

  function generate() {
    if (disabled.value) return
    s.loading = true
    s.result = ""
    setTimeout(() => {
      s.result = `${s.topic || "会议"}纪要

【会议要点】
${extractPoints(s.notes, 4)}

【会议决议】
1. 与会各方就核心议题达成一致意见；
2. 相关方案按讨论结果修订后执行。

【待办事项】
1. 各负责人于本周内提交细化执行计划；
2. 下次例会跟进本次决议落实情况。`
      s.loading = false
    }, 1400)
  }

  /* 用 reactive 包装：computed 才会在模板中自动解包（普通对象里的 ref 不会） */
  return reactive({ s, disabled, generate })
}

export type MinutesCtx = ReturnType<typeof createMinutesState>
