import type { Component } from "vue"
import {
  FileText,
  ClipboardList,
  FileSignature,
  Layers,
  Sparkles,
  PenLine,
  ScrollText,
  BarChart3,
  Mail,
  Bot,
  Presentation,
  Table,
  CheckCircle2,
  Gift,
  Trophy,
  Rocket,
  Star,
  Users,
} from "lucide-vue-next"

/**
 * 图标白名单：配置中心只存图标名称（字符串），
 * 渲染时通过这里换成组件，避免把组件对象写进可持久化的配置里。
 */
export const ICONS: Record<string, Component> = {
  FileText,
  ClipboardList,
  FileSignature,
  Layers,
  Sparkles,
  PenLine,
  ScrollText,
  BarChart3,
  Mail,
  Bot,
  Presentation,
  Table,
  CheckCircle2,
  Gift,
  Trophy,
  Rocket,
  Star,
  Users,
}

export const ICON_OPTIONS = Object.keys(ICONS)

export function iconOf(name: string | undefined): Component {
  return (name && ICONS[name]) || Sparkles
}
