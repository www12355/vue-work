<script setup lang="ts">
import { computed, type Component, type CSSProperties } from "vue"
import { Play, Pause, Wrench } from "lucide-vue-next"
import { NOTCH, type AppId, type DragState } from "@/data/apps"
import type { ModuleStatus } from "@/data/registry-defaults"

const props = defineProps<{
  app: AppId
  title: string
  desc: string
  image: string
  imageAlt: string
  icon: Component
  status: ModuleStatus
  docked: boolean
  dragging: DragState
}>()

const emit = defineEmits<{
  (e: "toggleDock", app: AppId): void
  (e: "dragStart", app: AppId, ev: PointerEvent): void
  (e: "cardClick", app: AppId): void
}>()

const isDragging = computed(() => props.dragging?.app === props.app)
/* 待开发模块不可拖拽、不可载入工作区，但可点开查看已配置的弹窗布局 */
const isDev = computed(() => props.status === "dev")

const cardStyle = computed<CSSProperties>(() => {
  const d = props.dragging
  if (!isDragging.value || !d) {
    return { cursor: isDev.value ? "pointer" : "grab", transition: "transform 0.3s ease" }
  }
  return {
    transform: `translate(${d.dx}px, ${d.dy}px) scale(${d.overDrop ? 0.92 : 1.04}) rotate(2deg)`,
    zIndex: 95,
    transition: "box-shadow 0.2s",
    cursor: "grabbing",
  }
})

const notchStyle: CSSProperties = { width: NOTCH, height: NOTCH }
const cornerTopStyle: CSSProperties = {
  bottom: NOTCH,
  background: "radial-gradient(circle at 0% 0%, transparent 23.5px, var(--background) 24px)",
}
const cornerLeftStyle: CSSProperties = {
  right: NOTCH,
  background: "radial-gradient(circle at 0% 0%, transparent 23.5px, var(--background) 24px)",
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault()
    emit("cardClick", props.app)
  }
}

/* 单击卡片（未拖动）直接打开该功能窗口；拖动结束时浏览器仍会派发 click，需忽略 */
function onClick() {
  if (props.dragging) return
  emit("cardClick", props.app)
}
</script>

<template>
  <div
    class="relative min-h-[190px] flex-1 touch-none select-none"
    :class="isDragging ? '' : 'hover:-translate-y-0.5'"
    :style="cardStyle"
    role="button"
    tabindex="0"
    :aria-label="`打开${title}`"
    @pointerdown="!isDev && emit('dragStart', app, $event)"
    @click="onClick"
    @keydown="onKeydown"
  >
    <div
      class="absolute inset-0 overflow-hidden rounded-[1.75rem] bg-neutral-950 text-white"
      :class="[isDragging ? 'shadow-2xl ring-2 ring-brand' : '', isDev ? 'ring-2 ring-dashed ring-white/25' : '']"
    >
      <img
        v-if="image"
        :src="image"
        :alt="imageAlt"
        :draggable="false"
        class="absolute inset-0 h-full w-full object-cover"
        :class="isDev ? 'opacity-30 grayscale' : 'opacity-90'"
      />
      <div class="absolute inset-0 bg-gradient-to-r from-black/85 via-black/45 to-transparent" />
      <div class="relative flex h-full min-h-[170px] flex-col justify-end gap-2 p-5 pb-4">
        <span
          class="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15 text-white backdrop-blur"
        >
          <component :is="icon" class="h-5 w-5" />
        </span>
        <h3 class="text-2xl font-semibold leading-tight">{{ title }}</h3>
        <p class="max-w-[15rem] pr-16 text-xs leading-relaxed text-white/65">{{ desc }}</p>
      </div>

      <!-- 待开发标记 -->
      <span
        v-if="isDev"
        class="absolute right-4 top-4 rounded-full border border-white/40 px-3 py-1 text-xs font-medium text-white/90"
      >
        待开发
      </span>
    </div>

    <!-- 右下角挖角 + 播放/暂停按钮 -->
    <div
      class="absolute bottom-0 right-0 flex items-end justify-end rounded-tl-[1.5rem] bg-background"
      :style="notchStyle"
    >
      <button
        :aria-label="isDev ? `${title}待开发，暂不可载入` : docked ? `暂停${title}` : `载入${title}到工作区`"
        :aria-pressed="docked"
        :disabled="isDev"
        class="flex h-[52px] w-[52px] items-center justify-center rounded-2xl transition-all"
        :class="
          isDev
            ? 'cursor-not-allowed border-2 border-dashed border-foreground/25 text-muted-foreground'
            : docked
              ? 'bg-brand text-brand-foreground hover:scale-105'
              : 'bg-neutral-950 text-white hover:scale-105'
        "
        @pointerdown.stop
        @click.stop="emit('toggleDock', app)"
      >
        <Wrench v-if="isDev" class="h-4 w-4" />
        <Pause v-else-if="docked" class="h-4 w-4 fill-current" />
        <Play v-else class="h-4 w-4 fill-current" />
      </button>
    </div>

    <!-- 挖角处的两个反向圆角 -->
    <div aria-hidden="true" class="absolute right-0 h-6 w-6" :style="cornerTopStyle" />
    <div aria-hidden="true" class="absolute bottom-0 h-6 w-6" :style="cornerLeftStyle" />
  </div>
</template>
