<script setup lang="ts">
import type { Component } from "vue"
import { ArrowLeft, Hammer } from "lucide-vue-next"
import { goTo } from "@/stores/view"

defineProps<{
  /** 页面主图标 */
  icon: Component
  /** 页面标题 */
  title: string
  /** 一句话说明 */
  subtitle: string
  /** 规划中的能力清单 */
  features: string[]
}>()
</script>

<template>
  <div class="mx-auto flex min-h-[calc(100vh-14rem)] max-w-2xl flex-col items-center justify-center py-10 text-center">
    <!-- 主图标 -->
    <div class="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-brand/10">
      <component :is="icon" class="h-9 w-9 text-brand" />
      <span
        class="absolute -bottom-2 -right-2 flex h-8 w-8 items-center justify-center rounded-full border-4 border-background bg-brand text-brand-foreground"
      >
        <Hammer class="h-3.5 w-3.5" />
      </span>
    </div>

    <!-- 待开发徽标 -->
    <span
      class="chip mt-6"
    >
      <span class="h-1.5 w-1.5 rounded-full bg-brand" />
      功能开发中
    </span>

    <h1 class="mt-4 text-3xl font-bold text-balance text-foreground">{{ title }}</h1>
    <p class="mt-3 max-w-md text-pretty leading-relaxed text-muted-foreground">{{ subtitle }}</p>

    <!-- 规划能力清单 -->
    <div class="ios-card ios-hover relative mt-8 w-full max-w-md overflow-hidden p-5 text-left">
      <span class="ios-sheen" aria-hidden="true" />
      <p class="relative text-sm font-semibold text-card-foreground">即将上线</p>
      <ul class="relative mt-3 flex flex-col gap-2.5">
        <li v-for="item in features" :key="item" class="flex items-start gap-2.5 text-sm text-muted-foreground">
          <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand/60" />
          {{ item }}
        </li>
      </ul>
    </div>

    <button
      type="button"
      class="btn btn-primary mt-8"
      @click="goTo('workspace')"
    >
      <ArrowLeft class="h-4 w-4" />
      返回工作台
    </button>
  </div>
</template>
