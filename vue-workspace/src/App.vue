<script setup lang="ts">
import { watchEffect } from "vue"
import { Newspaper, FolderOpen, Wrench, MessageSquarePlus, Zap, Wand2 } from "lucide-vue-next"
import Sidebar from "@/components/Sidebar.vue"
import Workspace from "@/components/Workspace.vue"
import BottomHero from "@/components/BottomHero.vue"
import AdminPage from "@/components/AdminPage.vue"
import LoginPage from "@/components/LoginPage.vue"
import UnderDevelopmentPage from "@/components/UnderDevelopmentPage.vue"
import PersonalCenter from "@/components/PersonalCenter.vue"
import HistoryPage from "@/components/HistoryPage.vue"
import { view } from "@/stores/view"
import { isAdmin } from "@/stores/auth"

/* 后台门控：未以管理员身份登录时访问后台，一律跳转到登录页 */
watchEffect(() => {
  if (view.value === "admin" && !isAdmin.value) view.value = "login"
})

/* 待开发页面文案配置：新增此类页面时在此登记即可，不影响工作台逻辑 */
const PLACEHOLDER = {
  news: {
    icon: Newspaper,
    title: "新闻动态",
    subtitle: "第一时间了解平台的功能更新、行业资讯与最佳实践分享。",
    features: ["平台版本更新与功能公告", "行业趋势与政策解读", "优秀案例与使用技巧"],
  },
  resources: {
    icon: FolderOpen,
    title: "资源中心",
    subtitle: "汇聚模板、示例文档与操作指南，帮助你更快上手每一项功能。",
    features: ["投标 / 合同 / 纪要模板库", "操作视频与图文教程", "常见问题与帮助文档"],
  },
  devices: {
    icon: Wrench,
    title: "设备工具",
    subtitle: "管理与调试接入平台的终端设备，统一维护工具与运行状态。",
    features: ["设备接入与状态监控", "工具集中管理与配置", "运行日志与故障排查"],
  },
  chat: {
    icon: MessageSquarePlus,
    title: "新建对话",
    subtitle: "开启全新的 AI 对话，探索智能问答与内容生成。",
    features: ["多轮对话交互", "上下文理解与记忆", "文档 / 标书 / 合同辅助生成"],
  },
  tasks: {
    icon: Zap,
    title: "自动任务",
    subtitle: "创建自动化工作流，让 AI 替你完成重复性任务。",
    features: ["定时任务调度", "批量文档处理", "流程化审批与通知"],
  },
  skills: {
    icon: Wand2,
    title: "技能广场",
    subtitle: "发现和安装 AI 技能插件，扩展平台的无限可能。",
    features: ["技能市场浏览", "一键安装与启用", "自定义技能开发"],
  },
} as const
</script>

<template>
  <!-- 管理后台：独立全屏布局，自带左侧可收纳导航栏，不显示前台顶部导航 -->
  <AdminPage v-if="view === 'admin' && isAdmin" />

  <!-- 前台：顶部导航 + 内容区 -->
  <main v-else class="relative min-h-screen bg-background">

    <!-- 侧边导航栏 -->
    <Sidebar />

    <!-- 内容区：为侧边栏留出左边距；工作台视图下作为纵向 flex 容器，供工作区拉伸填满视口高度 -->
    <div
      class="relative z-10 w-full pl-0 pr-5 py-6 md:px-8 lg:min-h-screen lg:pl-52 lg:pr-12 2xl:pl-60 2xl:pr-20"
      :class="view === 'workspace' ? 'flex flex-col' : ''"
    >
      <Workspace v-if="view === 'workspace'">
        <template #bottom>
          <BottomHero />
        </template>
      </Workspace>
      <LoginPage v-else-if="view === 'login'" />
      <PersonalCenter v-else-if="view === 'profile'" />
      <HistoryPage v-else-if="view === 'history'" />
      <UnderDevelopmentPage
        v-else-if="view === 'news' || view === 'resources' || view === 'devices' || view === 'chat' || view === 'tasks' || view === 'skills'"
        :icon="PLACEHOLDER[view].icon"
        :title="PLACEHOLDER[view].title"
        :subtitle="PLACEHOLDER[view].subtitle"
        :features="[...PLACEHOLDER[view].features]"
      />
    </div>
  </main>
</template>
