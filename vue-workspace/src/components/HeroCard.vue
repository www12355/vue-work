<script setup lang="ts">
import type { CSSProperties } from "vue"
import { Play } from "lucide-vue-next"
import type { DockedApp } from "@/data/apps"

/* 左下角挖角尺寸 */
const NOTCH_H = "72px"
const NOTCH_W = "36%"

defineProps<{ docked: DockedApp | null }>()
const emit = defineEmits<{ (e: "open"): void }>()

const emptyStyle: CSSProperties = { bottom: `calc(${NOTCH_H} + 16px)` }
const readMoreStyle: CSSProperties = { bottom: `calc(${NOTCH_H} + 20px)` }
const tagsStyle: CSSProperties = { left: NOTCH_W, height: NOTCH_H }
const notchStyle: CSSProperties = { width: NOTCH_W, height: NOTCH_H }
const cornerLeftStyle: CSSProperties = {
  bottom: NOTCH_H,
  background: "radial-gradient(circle at 100% 0%, transparent 31.5px, var(--background) 32px)",
}
const cornerBottomStyle: CSSProperties = {
  left: NOTCH_W,
  background: "radial-gradient(circle at 100% 0%, transparent 31.5px, var(--background) 32px)",
}
</script>

<template>
  <div class="relative h-[560px]">
    <!-- 深色主卡片（含右下延伸区） -->
    <div class="absolute inset-0 overflow-hidden rounded-[2rem] bg-neutral-950 text-white">
      <template v-if="docked">
        <!-- 停靠功能的背景图：铺满整卡 -->
        <img :src="docked.image" :alt="docked.imageAlt" class="absolute inset-0 h-full w-full object-cover" />
        <div
          class="absolute inset-0 bg-gradient-to-r from-neutral-950/90 via-neutral-950/40 to-neutral-950/10"
        />

        <!-- 顶部：标题 + 播放按钮 -->
        <div class="absolute inset-x-0 top-0 flex items-start justify-between gap-4 p-7">
          <div class="max-w-sm">
            <h2 class="text-balance text-4xl font-bold md:text-5xl">{{ docked.title }}</h2>
            <p class="mt-5 max-w-xs text-pretty text-sm leading-relaxed text-white/80">{{ docked.desc }}</p>
          </div>
          <button
            :aria-label="`打开${docked.title}窗口`"
            class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-white text-brand transition-transform hover:scale-110"
            @click="emit('open')"
          >
            <Play class="h-5 w-5 fill-current" />
          </button>
        </div>

        <!-- 进入功能：左列底部、挖角之上 -->
        <button
          class="absolute left-7 rounded-full bg-white px-7 py-3.5 text-sm font-medium text-neutral-950 transition-transform hover:scale-105"
          :style="readMoreStyle"
          @click="emit('open')"
        >
          进入功能
        </button>

        <!-- 标签：位于右下延伸区内 -->
        <div
          class="absolute bottom-0 right-0 flex items-center justify-between gap-4 pb-4 pl-6 pr-5"
          :style="tagsStyle"
        >
          <div class="flex flex-col items-start gap-2">
            <span
              v-if="docked.tags[0]"
              class="rounded-full border border-white/60 px-4 py-1.5 text-xs font-medium tracking-wide text-white"
            >
              {{ docked.tags[0] }}
            </span>
            <div class="flex items-center gap-3">
              <span
                v-for="tag in docked.tags.slice(1, 3)"
                :key="tag"
                class="rounded-full border border-white/60 px-4 py-1.5 text-xs font-medium tracking-wide text-white"
              >
                {{ tag }}
              </span>
            </div>
          </div>
        </div>
      </template>

      <!-- 空状态：仅显示虚线拖放提示区 -->
      <div
        v-else
        class="absolute left-6 right-6 top-6 flex items-center justify-center rounded-[1.5rem] border-2 border-dashed border-white/15"
        :style="emptyStyle"
      >
        <p class="max-w-[18rem] text-balance text-center text-sm leading-relaxed text-white/40">
          将右侧功能卡拖动到此处
        </p>
      </div>
    </div>

    <!-- 左下角挖角 -->
    <div
      class="absolute bottom-0 left-0 flex items-end rounded-tr-[2rem] bg-background pb-1 pl-2"
      :style="notchStyle"
    >
      <p class="text-xl font-medium text-foreground/70">打造最佳项目</p>
    </div>

    <!-- 挖角处的两个反向圆角 -->
    <div aria-hidden="true" class="absolute left-0 h-8 w-8" :style="cornerLeftStyle" />
    <div aria-hidden="true" class="absolute bottom-0 h-8 w-8" :style="cornerBottomStyle" />
  </div>
</template>
