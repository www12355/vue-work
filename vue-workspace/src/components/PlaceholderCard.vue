<script setup lang="ts">
import { Plus } from "lucide-vue-next"

/*
 * 虚框占位卡（纯展示，不可点击、不跳转）：
 * - trailing（默认）：右栏末尾的「待开发」入口
 * - slot：某个模块被后台撤下后原位保留的空位
 * 两种变体外观完全一致：大圆角虚线外框 + 虚线圆圈加号 + 「待开发」文字
 */
withDefaults(
  defineProps<{
    variant?: "trailing" | "slot"
    name?: string
  }>(),
  { variant: "trailing" },
)
</script>

<template>
  <div
    class="relative flex min-h-[190px] flex-1 items-center justify-center rounded-[1.75rem] border-2 border-dashed border-foreground/20 bg-transparent"
    role="note"
    :aria-label="name ? `${name} · 待开发` : '待开发'"
  >
    <div class="flex flex-col items-center justify-center gap-3">
      <!-- 虚线圆形加号图标，与设计截图一致 -->
      <span
        class="flex h-11 w-11 items-center justify-center rounded-full border-2 border-dashed border-foreground/30 text-foreground/40"
      >
        <Plus class="h-5 w-5 stroke-[1.5]" />
      </span>
      <span class="text-sm font-medium text-foreground/60">待开发</span>
    </div>
  </div>
</template>
