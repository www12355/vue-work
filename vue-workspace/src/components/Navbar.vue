<script setup lang="ts">
import { ChevronDown, ChevronRight } from "lucide-vue-next"
import { goTo, view, type ViewName } from "@/stores/view"
import UserMenu from "@/components/UserMenu.vue"
import NavMenu from "@/components/NavMenu.vue"

/* 主导航：「菜单」为下拉入口（见 NavMenu），其余为独立页面链接 */
const navLinks: { label: string; view: ViewName }[] = [
  { label: "新闻动态", view: "news" },
  { label: "资源中心", view: "resources" },
  { label: "设备工具", view: "devices" },
]

function isActive(v: ViewName) {
  return view.value === v
}
</script>

<template>
  <header
    class="relative z-40 flex w-full flex-wrap items-center justify-between gap-4 border-b border-border/70 bg-background/80 px-5 py-4 backdrop-blur-sm md:px-8 lg:px-12 2xl:px-20"
  >
    <div class="flex items-center gap-8">
      <!-- Logo：点击回到工作台 -->
      <button class="flex items-center gap-3" aria-label="返回工作台首页" @click="goTo('workspace')">
        <div class="relative flex h-12 w-12 items-center justify-center rounded-2xl border-[3px] border-foreground">
          <!-- 对话气泡尾巴 -->
          <span
            class="absolute -bottom-1.5 left-3 h-3 w-3 rotate-45 border-b-[3px] border-l-[3px] border-foreground bg-background"
          />
          <span class="text-xl font-extrabold italic text-brand">X</span>
        </div>
        <div class="text-2xl font-extrabold leading-none tracking-tight text-foreground">AICC</div>
      </button>

      <div class="hidden h-10 w-px bg-border lg:block" />

      <nav class="hidden items-center gap-7 lg:flex">
        <!-- 菜单下拉：首项为工作台 -->
        <NavMenu />

        <button
          v-for="link in navLinks"
          :key="link.view"
          class="flex items-center gap-2 font-medium transition-colors"
          :class="isActive(link.view) ? 'text-brand' : 'text-foreground/80 hover:text-foreground'"
          :aria-current="isActive(link.view) ? 'page' : undefined"
          @click="goTo(link.view)"
        >
          {{ link.label }}
        </button>
      </nav>
    </div>

    <div class="flex items-center gap-4">
      <button class="hidden h-10 items-center gap-1.5 rounded-full border border-border bg-card px-4 sm:flex">
        <span class="text-sm font-medium tracking-wide text-foreground">中文</span>
        <ChevronDown class="h-3.5 w-3.5 text-muted-foreground" />
      </button>

      <button class="hidden h-10 items-center gap-3 rounded-full border-2 border-brand/40 bg-card px-4 md:flex">
        <span class="text-sm font-semibold text-foreground">加入我们</span>
        <span class="flex h-6 w-6 items-center justify-center rounded-full bg-brand text-brand-foreground">
          <ChevronRight class="h-4 w-4" />
        </span>
      </button>

      <!-- 头像下拉菜单：管理后台 / 主题切换 / 退出登录 -->
      <UserMenu />
    </div>
  </header>
</template>
