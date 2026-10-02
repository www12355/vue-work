<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { FlaskConical, X } from "lucide-vue-next"
import ProxyOverview from "@/components/admin/ProxyOverview.vue"
import { activeProxyRules } from "@/stores/registry"

const isDev = import.meta.env.DEV
const open = ref(false)
const panelRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLElement | null>(null)
const ruleCount = computed(() => activeProxyRules.value.length)

function toggle() {
  open.value = !open.value
}

function close() {
  open.value = false
}

function onClickOutside(e: MouseEvent) {
  if (!open.value) return
  const target = e.target as Node
  const outsidePanel = !panelRef.value?.contains(target)
  const outsideTrigger = !triggerRef.value?.contains(target)
  if (outsidePanel && outsideTrigger) close()
}

onMounted(() => document.addEventListener("click", onClickOutside))
onBeforeUnmount(() => document.removeEventListener("click", onClickOutside))
</script>

<template>
  <div v-if="isDev" class="fixed bottom-6 right-6 z-[100] flex flex-col items-end gap-3">
    <!-- 可展开面板 -->
    <div
      v-if="open"
      ref="panelRef"
      class="ws-zoom-in w-[380px] max-h-[70vh] overflow-hidden rounded-2xl border border-border bg-card shadow-2xl flex flex-col"
    >
      <!-- 标题栏 -->
      <div class="flex items-center justify-between border-b border-border px-4 py-3">
        <div class="flex items-center gap-2">
          <FlaskConical class="h-4 w-4 text-brand" />
          <span class="text-sm font-semibold text-card-foreground">接口代理测试</span>
          <span
            v-if="ruleCount > 0"
            class="rounded-full bg-accent px-1.5 py-0.5 text-[0.6rem] font-bold text-accent-foreground leading-none"
          >
            {{ ruleCount }}
          </span>
        </div>
        <button
          type="button"
          class="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          @click="close"
        >
          <X class="h-4 w-4" />
        </button>
      </div>

      <!-- 内容 -->
      <div class="overflow-y-auto p-4">
        <ProxyOverview />
      </div>
    </div>

    <!-- 触发器按钮 -->
    <button
      ref="triggerRef"
      type="button"
      class="relative flex h-11 w-11 items-center justify-center rounded-full border border-border bg-card shadow-lg transition-all hover:scale-105 hover:shadow-xl"
      :class="open ? 'ring-2 ring-brand ring-offset-1 ring-offset-background' : ''"
      :aria-label="open ? '关闭测试面板' : '打开测试面板'"
      @click="toggle"
    >
      <FlaskConical class="h-5 w-5 text-brand" />
      <!-- 活跃规则指示点 -->
      <span
        v-if="ruleCount > 0 && !open"
        class="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full border-2 border-card bg-emerald-500"
      />
    </button>
  </div>
</template>
