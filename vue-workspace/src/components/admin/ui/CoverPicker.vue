<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import { Check, ChevronDown, ImageOff } from "lucide-vue-next"
import { IMAGE_OPTIONS } from "@/data/registry-defaults"

defineProps<{ label: string }>()
const model = defineModel<string>({ default: "" })

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const current = computed(
  () => IMAGE_OPTIONS.find((o) => o.value === model.value) ?? IMAGE_OPTIONS[0],
)

function select(value: string) {
  model.value = value
  open.value = false
}

function toggle() {
  open.value = !open.value
}

/* 点击组件外部时关闭下拉 */
function onDocClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}
document.addEventListener("click", onDocClick)
onBeforeUnmount(() => document.removeEventListener("click", onDocClick))
</script>

<template>
  <div ref="root" class="relative flex flex-col gap-1.5">
    <span class="text-xs font-medium text-muted-foreground">{{ label }}</span>

    <!-- 触发按钮：显示当前封面缩略图 + 名称 -->
    <button
      type="button"
      class="neu-inset flex items-center gap-2.5 px-2.5 py-2 text-left text-sm text-foreground transition-colors"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="toggle"
    >
      <span class="flex h-9 w-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-neutral-900">
        <img
          v-if="current.value"
          :src="current.value"
          :alt="current.label"
          class="h-full w-full object-cover"
          loading="lazy"
          decoding="async"
        />
        <ImageOff v-else class="h-4 w-4 text-neutral-500" />
      </span>
      <span class="min-w-0 flex-1 truncate">{{ current.label }}</span>
      <ChevronDown class="h-4 w-4 shrink-0 text-muted-foreground transition-transform" :class="open && 'rotate-180'" />
    </button>

    <!-- 下拉：懒加载缩略预览网格 -->
    <div
      v-if="open"
      role="listbox"
      class="absolute left-0 right-0 top-full z-30 mt-1.5 max-h-72 overflow-y-auto rounded-xl border border-border bg-popover p-2 shadow-lg"
    >
      <div class="grid grid-cols-2 gap-2">
        <button
          v-for="opt in IMAGE_OPTIONS"
          :key="opt.value"
          type="button"
          role="option"
          :aria-selected="model === opt.value"
          class="group relative overflow-hidden rounded-xl border transition-colors"
          :class="model === opt.value ? 'border-brand ring-1 ring-brand' : 'border-border hover:border-brand/60'"
          @click="select(opt.value)"
        >
          <span class="flex aspect-[16/9] items-center justify-center overflow-hidden bg-neutral-900">
            <img
              v-if="opt.value"
              :src="opt.value"
              :alt="opt.label"
              class="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
              loading="lazy"
              decoding="async"
            />
            <ImageOff v-else class="h-5 w-5 text-neutral-500" />
          </span>
          <span class="flex items-center justify-between gap-1 px-2 py-1.5 text-left text-xs text-foreground">
            <span class="truncate">{{ opt.label }}</span>
            <Check v-if="model === opt.value" class="h-3.5 w-3.5 shrink-0 text-brand" />
          </span>
        </button>
      </div>
    </div>
  </div>
</template>
