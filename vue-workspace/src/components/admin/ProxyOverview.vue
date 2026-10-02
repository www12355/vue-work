<script setup lang="ts">
import { computed, ref } from "vue"
import { Check, Copy, Download, Network } from "lucide-vue-next"
import { activeProxyRules, buildProxyConfigJson, proxyPathConflicts } from "@/stores/registry"

const json = computed(() => buildProxyConfigJson())
const copied = ref(false)

async function copy() {
  try {
    await navigator.clipboard.writeText(json.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1600)
  } catch {
    /* 剪贴板不可用时忽略 */
  }
}

function download() {
  const blob = new Blob([json.value + "\n"], { type: "application/json" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "proxy.config.json"
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <p class="text-xs leading-relaxed text-muted-foreground">
      各模块「接口代理」的规则会汇总为
      <code class="rounded bg-muted px-1 py-0.5 font-mono">proxy.config.json</code>，Vite
      在启动时读取它并按 path 前缀代理到不同后端。修改规则后
      <span class="font-medium text-foreground">下载覆盖项目根目录的该文件并重启开发服务器</span> 即可生效。
    </p>

    <!-- 生效中的规则一览 -->
    <div v-if="activeProxyRules.length" class="flex flex-col gap-2">
      <div
        v-for="r in activeProxyRules"
        :key="r.path"
        class="neu-inset flex flex-wrap items-center gap-2 px-3 py-2 font-mono text-xs"
      >
        <Network class="h-3.5 w-3.5 text-brand" />
        <code class="text-foreground">{{ r.path }}</code>
        <span class="text-muted-foreground">→</span>
        <code class="text-foreground">{{ r.target }}</code>
        <span v-if="r.stripPrefix" class="rounded-full bg-muted px-2 py-0.5 text-[0.65rem]">rewrite</span>
        <span v-if="r.ws" class="rounded-full bg-muted px-2 py-0.5 text-[0.65rem]">ws</span>
      </div>
    </div>
    <p v-else class="rounded-xl border border-dashed border-border bg-muted/30 px-3 py-4 text-center text-xs text-muted-foreground">
      暂无启用的接口代理。在各模块「配置 → 接口代理」中开启并填写后端地址。
    </p>

    <p v-if="proxyPathConflicts.length" class="text-xs font-medium text-destructive">
      存在重复的路径前缀：{{ proxyPathConflicts.join("、") }}，同一路径只会有一条生效。
    </p>

    <!-- 生成的配置文件 -->
    <div class="neu-inset overflow-hidden">
      <div class="flex items-center justify-between border-b border-border px-3 py-2">
        <span class="font-mono text-xs text-muted-foreground">proxy.config.json</span>
        <div class="flex items-center gap-1.5">
          <button
            type="button"
            class="flex items-center gap-1 rounded-xl border border-border px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
            @click="copy"
          >
            <component :is="copied ? Check : Copy" class="h-3 w-3" />
            {{ copied ? "已复制" : "复制" }}
          </button>
          <button
            type="button"
            class="btn btn-primary btn-sm h-7 px-2.5"
            @click="download"
          >
            <Download class="h-3 w-3" />
            下载
          </button>
        </div>
      </div>
      <pre class="max-h-64 overflow-auto p-3 font-mono text-xs leading-relaxed text-foreground">{{ json }}</pre>
    </div>
  </div>
</template>
