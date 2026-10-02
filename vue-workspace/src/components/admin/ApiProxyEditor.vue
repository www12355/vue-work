<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, Server } from "lucide-vue-next"
import Field from "@/components/admin/ui/Field.vue"
import Toggle from "@/components/admin/ui/Toggle.vue"
import { getModule, proxyPathConflicts, updateModuleApi } from "@/stores/registry"
import { defaultApiProxy } from "@/data/registry-defaults"

const props = defineProps<{ moduleId: string }>()

const api = computed(() => getModule(props.moduleId)?.api ?? defaultApiProxy())

function set<K extends keyof ReturnType<typeof defaultApiProxy>>(
  key: K,
  value: ReturnType<typeof defaultApiProxy>[K],
) {
  updateModuleApi(props.moduleId, { [key]: value })
}

/** 请求路径归一：确保以 / 开头 */
function normalizePath(v: string) {
  const t = v.trim()
  if (!t) return ""
  return t.startsWith("/") ? t : `/${t}`
}

/** 转发预览：把 path 前缀映射到目标后端 */
const forwardPreview = computed(() => {
  const path = api.value.path.trim() || "/api/xxx"
  const target = api.value.target.trim() || "http://localhost:PORT"
  const to = api.value.stripPrefix ? `${target}/…` : `${target}${path}/…`
  return { from: `${path}/…`, to }
})

const pathTaken = computed(
  () => api.value.enabled && proxyPathConflicts.value.includes(api.value.path.trim()),
)
</script>

<template>
  <div class="neu-inset p-4">
    <div class="flex items-center gap-2">
      <span class="flex h-7 w-7 items-center justify-center rounded-xl bg-brand/10 text-brand">
        <Server class="h-4 w-4" />
      </span>
      <div>
        <h3 class="text-sm font-bold text-card-foreground">接口代理（Vite 按路径代理到后端）</h3>
        <p class="text-xs text-muted-foreground">
          前端对该 path 前缀的请求会被 Vite 转发到指定后端，实现「按路径代理到不同后端」。
        </p>
      </div>
    </div>

    <div class="mt-3 flex flex-col gap-3">
      <Toggle
        :model-value="api.enabled"
        label="启用该模块的接口代理"
        hint="关闭后此规则不会写入 proxy.config.json"
        @update:model-value="set('enabled', $event)"
      />

      <div class="grid gap-3 md:grid-cols-2">
        <Field
          :model-value="api.path"
          label="请求路径前缀"
          placeholder="/api/tender"
          @update:model-value="set('path', normalizePath($event as string))"
        />
        <Field
          :model-value="api.target"
          label="后端目标地址"
          placeholder="http://localhost:4001"
          @update:model-value="set('target', ($event as string).trim())"
        />
      </div>

      <div class="grid gap-2 md:grid-cols-2">
        <Toggle
          :model-value="api.changeOrigin"
          label="changeOrigin"
          hint="改写 Host 头为目标地址"
          @update:model-value="set('changeOrigin', $event)"
        />
        <Toggle
          :model-value="api.stripPrefix"
          label="去掉路径前缀（rewrite）"
          hint="转发前剥离 path 前缀"
          @update:model-value="set('stripPrefix', $event)"
        />
      </div>

      <Toggle
        :model-value="api.ws"
        label="代理 WebSocket"
        hint="该后端需要 WebSocket 时开启"
        @update:model-value="set('ws', $event)"
      />

      <!-- 转发预览 -->
      <div class="rounded-xl border border-dashed border-border bg-muted/30 p-3">
        <p class="mb-1.5 text-xs font-medium text-muted-foreground">转发预览</p>
        <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
          <code class="rounded-xl bg-background px-2 py-1 text-foreground">{{ forwardPreview.from }}</code>
          <ArrowRight class="h-3.5 w-3.5 text-brand" />
          <code class="rounded-xl bg-background px-2 py-1 text-foreground">{{ forwardPreview.to }}</code>
        </div>
      </div>

      <p v-if="pathTaken" class="text-xs font-medium text-destructive">
        路径前缀 {{ api.path }} 已被其他已启用模块占用，请改用不同的前缀。
      </p>
    </div>
  </div>
</template>
