<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, type Component } from "vue"
import { X } from "lucide-vue-next"
import TenderApp from "@/components/apps/TenderApp.vue"
import MinutesApp from "@/components/apps/MinutesApp.vue"
import ComboApp from "@/components/apps/ComboApp.vue"
import ContractApp from "@/components/apps/ContractApp.vue"
import DynamicApp from "@/components/apps/DynamicApp.vue"
import { getCombo, getModule, windowMetaOf } from "@/stores/registry"
import type { AppId } from "@/data/apps"

const props = defineProps<{ app: AppId }>()
const emit = defineEmits<{ (e: "close"): void }>()

const dialogRef = ref<HTMLElement | null>(null)
const meta = computed(() => windowMetaOf(props.app))

/* 渲染器：内置模块用专属实现，后台新增模块统一走 dynamic，组合走 ComboApp */
const RENDERERS: Record<string, Component> = {
  tender: TenderApp,
  minutes: MinutesApp,
  contract: ContractApp,
  dynamic: DynamicApp,
}

const renderer = computed<Component | null>(() => {
  if (getCombo(props.app)) return ComboApp
  const mod = getModule(props.app)
  return mod ? (RENDERERS[mod.renderer] ?? DynamicApp) : null
})

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close")
}

onMounted(() => {
  window.addEventListener("keydown", onKey)
  document.body.style.overflow = "hidden"
  dialogRef.value?.focus()
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey)
  document.body.style.overflow = ""
})
</script>

<template>
  <!-- 传送到 body：避免被页面内 z-index 较低的父级堆叠上下文（如导航栏所在层）遮挡 -->
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-8"
      role="dialog"
      aria-modal="true"
      :aria-label="meta.title"
    >
      <!-- 遮罩 -->
      <button
        aria-label="关闭窗口"
        class="ws-fade-in absolute inset-0 cursor-default bg-neutral-950/50 backdrop-blur-sm"
        @click="emit('close')"
      />

      <!-- 窗口 -->
      <div
        ref="dialogRef"
        tabindex="-1"
        class="ws-zoom-in relative flex h-full w-full max-w-6xl flex-col overflow-hidden rounded-[1.75rem] bg-card shadow-2xl outline-none"
      >
        <div class="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          <div class="min-w-0">
            <h2 class="text-xl font-bold text-card-foreground">{{ meta.title }}</h2>
            <p class="mt-0.5 text-sm text-muted-foreground">{{ meta.desc }}</p>
          </div>
          <button
            aria-label="关闭"
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground transition-colors hover:bg-border"
            @click="emit('close')"
          >
            <X class="h-5 w-5" />
          </button>
        </div>

        <div class="flex-1 overflow-auto p-5 md:p-6">
          <component :is="renderer" v-if="renderer" :owner-id="app" />
          <p v-else class="py-12 text-center text-sm text-muted-foreground">该功能配置已被删除。</p>
        </div>
      </div>
    </div>
  </Teleport>
</template>
