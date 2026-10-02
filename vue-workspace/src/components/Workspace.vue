<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from "vue"
import HeroCard from "@/components/HeroCard.vue"
import FunctionCard from "@/components/FunctionCard.vue"
import PlaceholderCard from "@/components/PlaceholderCard.vue"
import AppWindow from "@/components/AppWindow.vue"
import { COMBO_HOLD_MS, type AppId, type DragState } from "@/data/apps"
import { iconOf } from "@/data/icons"
import {
  comboIncludes,
  dockTargetWithout,
  dockedMetaOf,
  findComboWith,
  getCombo,
  getModule,
  isCombo,
  MAX_COMBO_MEMBERS,
  modules,
} from "@/stores/registry"

const activeApp = ref<AppId | null>(null)
const dockedApp = ref<AppId | null>(null)
const drag = ref<DragState>(null)
const comboProgress = ref<number | null>(null)

const dropRef = ref<HTMLElement | null>(null)
const startPos = { x: 0, y: 0 }
let dragMoved = false
let comboRaf: number | null = null
let comboStart: number | null = null

/*
 * 右栏槽位：按模块配置顺序逐个占位。
 * 已上线 → 功能卡；在管理后台被撤下（回落为待开发）→ 原位保留虚框「添加模块」，
 * 位置不会被后面的卡片挤掉。
 */
const slots = computed(() =>
  modules.value.map((m) =>
    m.status === "ready"
      ? {
          kind: "card" as const,
          id: m.id,
          title: m.title,
          desc: m.desc,
          image: m.image,
          imageAlt: m.imageAlt,
          icon: iconOf(m.icon),
          status: m.status,
        }
      : { kind: "empty" as const, id: m.id, title: m.title },
  ),
)

const dockedMeta = computed(() => dockedMetaOf(dockedApp.value))

/* 拖到工作区但未配置（或已停用）对应组合规则时给出提示 */
const comboBlocked = computed(() => {
  const d = drag.value
  if (!d || !d.overDrop) return false
  const cur = dockedApp.value
  if (!cur || cur === d.app) return false
  /* 已是该组合成员，或组合成员已达上限，都不再叠加 */
  if (isCombo(cur) && comboIncludes(cur, d.app)) return false
  return !findComboWith(cur, d.app)
})

/** 当前载入项已包含的模块数量，用于提示成员上限 */
const dockedMemberCount = computed(() => {
  const cur = dockedApp.value
  if (!cur) return 0
  return getCombo(cur)?.members.length ?? 1
})

const comboFull = computed(() => dockedMemberCount.value >= MAX_COMBO_MEMBERS)

const CIRCUMFERENCE = 2 * Math.PI * 27
const dashOffset = computed(() => CIRCUMFERENCE * (1 - (comboProgress.value ?? 0)))

/** 功能卡是否处于「播放中」：组合停靠时其成员模块同时点亮 */
function isDocked(app: AppId) {
  const cur = dockedApp.value
  if (!cur) return false
  return cur === app || (isCombo(cur) && comboIncludes(cur, app))
}

function isAvailable(app: AppId) {
  return getModule(app)?.status === "ready"
}

/** 播放/暂停：从组合中移除某个成员时，其余成员尽量落到对应的子组合 */
function toggleDock(app: AppId) {
  if (!isAvailable(app)) return
  const cur = dockedApp.value
  if (cur && isCombo(cur)) {
    dockedApp.value = comboIncludes(cur, app) ? dockTargetWithout(cur, app) : app
    return
  }
  dockedApp.value = cur === app ? null : app
}

function stopComboTimer() {
  if (comboRaf !== null) cancelAnimationFrame(comboRaf)
  comboRaf = null
  comboStart = null
  comboProgress.value = null
}

function isOverDrop(x: number, y: number) {
  const rect = dropRef.value?.getBoundingClientRect()
  if (!rect) return false
  return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
}

/* 拖拽：指针事件跟随 + 悬停 5 秒按后台配置的组合规则触发组合 */
function onDragStart(app: AppId, e: PointerEvent) {
  if (e.button !== 0 && e.pointerType === "mouse") return
  if (!isAvailable(app)) return
  startPos.x = e.clientX
  startPos.y = e.clientY
  dragMoved = false

  /* 目标组合：当前载入的是单模块则两两组合，已是组合则尝试追加为 3 / 4 元组合 */
  const cur = dockedApp.value
  const pairCombo = cur ? findComboWith(cur, app) : undefined
  let comboDone = false

  const cleanup = () => {
    window.removeEventListener("pointermove", onMove)
    window.removeEventListener("pointerup", onUp)
    stopComboTimer()
    drag.value = null
  }

  const startComboTimer = () => {
    if (comboStart !== null || comboDone || !pairCombo) return
    comboStart = performance.now()
    const tick = (now: number) => {
      if (comboStart === null) return
      const progress = Math.min((now - comboStart) / COMBO_HOLD_MS, 1)
      comboProgress.value = progress
      if (progress >= 1) {
        comboDone = true
        dockedApp.value = pairCombo.id
        cleanup()
        return
      }
      comboRaf = requestAnimationFrame(tick)
    }
    comboRaf = requestAnimationFrame(tick)
  }

  const onMove = (ev: PointerEvent) => {
    if (comboDone) return
    const dx = ev.clientX - startPos.x
    const dy = ev.clientY - startPos.y
    if (!dragMoved && Math.hypot(dx, dy) < 8) return
    dragMoved = true
    const over = isOverDrop(ev.clientX, ev.clientY)
    drag.value = { app, dx, dy, overDrop: over }
    /* 悬停在工作区上开始计时；移出则取消 */
    if (over && pairCombo) startComboTimer()
    else stopComboTimer()
  }

  const onUp = (ev: PointerEvent) => {
    const shouldDock = !comboDone && dragMoved && isOverDrop(ev.clientX, ev.clientY)
    cleanup()
    if (shouldDock) dockedApp.value = app
  }

  window.addEventListener("pointermove", onMove)
  window.addEventListener("pointerup", onUp)
}

onBeforeUnmount(stopComboTimer)

function openWindow() {
  if (dockedApp.value) activeApp.value = dockedApp.value
}

/* 单击功能卡：直接打开该功能窗口（待开发模块会在窗口内提示） */
function onCardClick(app: AppId) {
  activeApp.value = app
}
</script>

<template>
  <div class="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
    <!-- 左侧内容：主卡片即放置区 -->
    <div class="flex flex-col gap-8 lg:col-span-2">
      <div ref="dropRef" class="relative">
        <HeroCard :docked="dockedMeta" @open="openWindow" />

        <!-- 拖拽时覆盖在主卡片上的放置提示 -->
        <div
          v-if="drag"
          class="pointer-events-none absolute inset-0 z-[80] flex items-center justify-center rounded-[2rem] border-2 border-dashed backdrop-blur-[2px] transition-all duration-200"
          :class="drag.overDrop ? 'border-brand bg-brand/15' : 'border-white/40 bg-neutral-950/50'"
        >
          <!-- 悬停组合进度 -->
          <div v-if="comboProgress !== null" class="flex flex-col items-center gap-3">
            <div class="relative h-16 w-16">
              <svg viewBox="0 0 64 64" class="h-16 w-16 -rotate-90">
                <circle cx="32" cy="32" r="27" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="5" />
                <circle
                  cx="32"
                  cy="32"
                  r="27"
                  fill="none"
                  stroke="var(--brand)"
                  stroke-width="5"
                  stroke-linecap="round"
                  :stroke-dasharray="CIRCUMFERENCE"
                  :stroke-dashoffset="dashOffset"
                />
              </svg>
              <span class="absolute inset-0 flex items-center justify-center text-sm font-bold text-white">
                {{ Math.round(comboProgress * 100) }}%
              </span>
            </div>
            <p class="rounded-full bg-brand px-6 py-3 text-lg font-semibold text-brand-foreground backdrop-blur">
              保持悬停，即将组合功能…
            </p>
          </div>

          <div v-else class="flex flex-col items-center gap-2">
            <p
              class="rounded-full px-6 py-3 text-lg font-semibold backdrop-blur"
              :class="drag.overDrop ? 'bg-brand text-brand-foreground' : 'bg-white/10 text-white'"
            >
              {{ drag.overDrop ? "松开以载入功能" : "拖动到此处载入" }}
            </p>
            <p v-if="comboBlocked" class="rounded-full bg-neutral-950/70 px-4 py-2 text-xs font-medium text-white">
              {{
                comboFull
                  ? `组合最多 ${MAX_COMBO_MEMBERS} 个功能，松开将替换当前组合`
                  : "这些功能未配置组合规则，松开将替换当前功能"
              }}
            </p>
          </div>
        </div>
      </div>

      <div class="transition-opacity duration-200" :class="drag ? 'opacity-40' : ''">
        <slot name="bottom" />
      </div>
    </div>

    <!-- 右栏：已上线功能卡；被撤下的模块原位显示虚框「添加模块」 -->
    <div class="flex flex-col gap-5 lg:col-span-1">
      <template v-for="slot in slots" :key="slot.id">
        <FunctionCard
          v-if="slot.kind === 'card'"
          :app="slot.id"
          :title="slot.title"
          :desc="slot.desc"
          :image="slot.image"
          :image-alt="slot.imageAlt"
          :icon="slot.icon"
          :status="slot.status"
          :docked="isDocked(slot.id)"
          :dragging="drag"
          @toggle-dock="toggleDock"
          @drag-start="onDragStart"
          @card-click="onCardClick"
        />
        <PlaceholderCard v-else variant="slot" :name="slot.title" />
      </template>
      <PlaceholderCard />
    </div>
  </div>

  <!-- 中心功能窗口 -->
  <AppWindow v-if="activeApp" :app="activeApp" @close="activeApp = null" />
</template>
