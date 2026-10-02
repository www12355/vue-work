/**
 * 计费定价：以「模型 token 单价」为基准，按 1 积分 = 1 美金换算。
 *
 * - 每个模型有一个混合单价（美金 / 每百万 token），$1 能买到的 token 数 = 1,000,000 / 单价。
 * - 每类文档有一个预估 token 消耗（输入 + 输出），生成成本(美金) = tokens / 1e6 × 单价。
 * - 因为 1 积分 = 1 美金，所以「成本积分」= 成本美金。
 * - 组合生成 = 各成员文档成本之和，并给出组合优惠折扣。
 */

export interface ModelPrice {
  id: string
  name: string
  /** 混合单价：美金 / 每百万 token */
  pricePerM: number
  /** 说明标签 */
  note: string
}

/** 可选模型（单价为示意值，接入真实计费时替换即可） */
export const MODELS: ModelPrice[] = [
  { id: "deepseek-v3", name: "DeepSeek-V3", pricePerM: 0.5, note: "高性价比 · 国产" },
  { id: "qwen-max", name: "通义千问 Max", pricePerM: 2, note: "均衡 · 中文优化" },
  { id: "gpt-4o", name: "GPT-4o", pricePerM: 5, note: "通用旗舰" },
  { id: "claude-3-5", name: "Claude 3.5 Sonnet", pricePerM: 6, note: "长文档 · 强推理" },
]

export interface DocPricing {
  id: string
  name: string
  /** 单次生成预估 token 消耗 */
  tokens: number
  /** lucide 图标名 */
  icon: string
}

/** 单文档计费项，token 与工作台模块对应 */
export const DOC_PRICING: DocPricing[] = [
  { id: "minutes", name: "会议纪要", tokens: 25000, icon: "ClipboardList" },
  { id: "contract", name: "合同生成", tokens: 60000, icon: "FileSignature" },
  { id: "tender", name: "标书生成", tokens: 130000, icon: "FileText" },
]

/** 组合生成优惠：成员成本之和 × 该系数（9 折） */
export const COMBO_DISCOUNT = 0.9

/** $1（= 1 积分）能购买的 token 数 */
export function tokensPerDollar(model: ModelPrice): number {
  return Math.round(1_000_000 / model.pricePerM)
}

/** 单次生成成本（美金 = 积分） */
export function docCost(doc: DocPricing, model: ModelPrice): number {
  return (doc.tokens / 1_000_000) * model.pricePerM
}

/** 组合生成成本（会议纪要 + 合同 + 标书，享组合优惠） */
export function comboCost(model: ModelPrice): { original: number; discounted: number } {
  const original = DOC_PRICING.reduce((sum, d) => sum + docCost(d, model), 0)
  return { original, discounted: original * COMBO_DISCOUNT }
}
