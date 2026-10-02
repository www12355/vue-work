<script setup lang="ts">
import { ref } from "vue"
import { Plus, X } from "lucide-vue-next"
import {
  addComboMember,
  candidateMembersFor,
  getModule,
  removeComboMember,
  reorderComboMembers,
} from "@/stores/registry"
import { MAX_COMBO_MEMBERS, MIN_COMBO_MEMBERS, type ComboConfig } from "@/data/registry-defaults"
import { iconOf } from "@/data/icons"

const props = defineProps<{ combo: ComboConfig }>()

/** 拖拽重排状态：记录当前被拖动的成员索引 */
const dragIndex = ref<number | null>(null)
/** 追加成员下拉的开合 */
const adding = ref(false)

function memberTitle(id: string) {
  return getModule(id)?.title ?? "（已删除模块）"
}
function memberIcon(id: string) {
  return getModule(id)?.icon ?? "Layers"
}

function onDragStart(index: number, e: DragEvent) {
  dragIndex.value = index
  if (e.dataTransfer) e.dataTransfer.effectAllowed = "move"
}
function onDragOver(index: number) {
  if (dragIndex.value === null || dragIndex.value === index) return
  reorderComboMembers(props.combo.id, dragIndex.value, index)
  dragIndex.value = index
}
function onDragEnd() {
  dragIndex.value = null
}

function pick(moduleId: string) {
  addComboMember(props.combo.id, moduleId)
  adding.value = false
}
</script>

<template>
  <!-- 连线式流程画布：模块节点由箭头串联，拖动节点即可调整流水线顺序 -->
  <div class="neu-inset combo-canvas overflow-x-auto p-5">
    <div class="flex min-w-min items-stretch gap-0" @dragover.prevent>
      <template v-for="(id, i) in combo.members" :key="id">
        <!-- 连接线（第一个节点前不画） -->
        <div v-if="i > 0" class="flex w-11 shrink-0 items-center justify-center" aria-hidden="true">
          <svg width="44" height="24" viewBox="0 0 44 24" fill="none">
            <path d="M2 12 H33" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="text-brand/45" />
            <path
              d="M32 6 L42 12 L32 18"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              fill="none"
              class="text-brand"
            />
          </svg>
        </div>

        <!-- 模块节点 -->
        <div
          class="group relative flex w-44 shrink-0 cursor-grab flex-col gap-2 rounded-2xl border bg-card p-3 shadow-sm transition-colors active:cursor-grabbing"
          :class="dragIndex === i ? 'border-brand ring-2 ring-brand/30' : 'border-border hover:border-brand/50'"
          draggable="true"
          @dragstart="onDragStart(i, $event)"
          @dragover.prevent="onDragOver(i)"
          @dragend="onDragEnd"
        >
          <div class="flex items-center justify-between">
            <span class="flex h-6 w-6 items-center justify-center rounded-xl bg-brand/10 text-xs font-bold text-brand">
              {{ i + 1 }}
            </span>
            <button
              type="button"
              :disabled="combo.members.length <= MIN_COMBO_MEMBERS"
              :aria-label="`移出成员：${memberTitle(id)}`"
              class="flex h-6 w-6 items-center justify-center rounded-xl text-muted-foreground opacity-0 transition-colors hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-0"
              @click="removeComboMember(combo.id, id)"
              @dragstart.prevent.stop
            >
              <X class="h-3.5 w-3.5" />
            </button>
          </div>
          <div class="flex items-center gap-2">
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground">
              <component :is="iconOf(memberIcon(id))" class="h-4.5 w-4.5" />
            </span>
            <span class="min-w-0 flex-1 truncate text-sm font-semibold text-card-foreground">{{ memberTitle(id) }}</span>
          </div>
          <span class="text-[0.65rem] text-muted-foreground">{{ i === 0 ? "起始阶段" : `第 ${i + 1} 阶段` }}</span>
        </div>
      </template>

      <!-- 追加节点 -->
      <template v-if="combo.members.length < MAX_COMBO_MEMBERS">
        <div class="flex w-11 shrink-0 items-center justify-center" aria-hidden="true">
          <svg width="44" height="24" viewBox="0 0 44 24" fill="none">
            <path
              d="M2 12 H40"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-dasharray="4 4"
              class="text-border"
            />
          </svg>
        </div>
        <div class="relative w-44 shrink-0">
          <button
            type="button"
            :disabled="!candidateMembersFor(combo.id).length"
            class="flex h-full min-h-[6.5rem] w-full flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed border-border text-muted-foreground transition-colors hover:border-brand hover:bg-brand/5 hover:text-brand disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border disabled:hover:bg-transparent disabled:hover:text-muted-foreground"
            :aria-expanded="adding"
            @click="adding = !adding"
          >
            <Plus class="h-5 w-5" />
            <span class="text-xs font-medium">添加节点</span>
          </button>

          <!-- 候选模块下拉 -->
          <div
            v-if="adding && candidateMembersFor(combo.id).length"
            class="absolute left-0 top-full z-10 mt-2 w-full overflow-hidden rounded-xl border border-border bg-popover shadow-lg"
          >
            <button
              v-for="mod in candidateMembersFor(combo.id)"
              :key="mod.id"
              type="button"
              class="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted"
              @click="pick(mod.id)"
            >
              <component :is="iconOf(mod.icon)" class="h-4 w-4 shrink-0 text-muted-foreground" />
              <span class="min-w-0 flex-1 truncate">{{ mod.title }}</span>
            </button>
          </div>
        </div>
      </template>
    </div>

    <p class="mt-3 text-[0.7rem] text-muted-foreground">
      拖动节点可调整流水线顺序（{{ MIN_COMBO_MEMBERS }} ~ {{ MAX_COMBO_MEMBERS }} 个模块），箭头方向即执行方向。
    </p>
  </div>
</template>

<style scoped>
/* 点状网格背景，营造工作流画布质感 */
.combo-canvas {
  background-image: radial-gradient(color-mix(in oklab, var(--foreground) 12%, transparent) 1px, transparent 1px);
  background-size: 18px 18px;
}
</style>
