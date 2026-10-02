<script setup lang="ts">
import { computed } from "vue"
import { Download, FileDown } from "lucide-vue-next"
import type { DownloadableFile } from "@/services/api/types"

/* 各功能共用的右侧预览面板：标题栏 + 导出按钮 + 结果 / 空状态 */
const props = defineProps<{
  label: string
  result: string
  /** 可下载的输出文件 */
  files?: DownloadableFile[]
}>()

const hasFiles = computed(() => (props.files?.length ?? 0) > 0)
</script>

<template>
  <div class="flex min-h-[240px] flex-1 flex-col rounded-2xl border border-border bg-muted/50">
    <div class="flex items-center justify-between border-b border-border px-4 py-2.5">
      <span class="text-xs font-medium text-muted-foreground">{{ label }}</span>
      <button
        v-if="result"
        class="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-brand hover:bg-brand/10"
      >
        <Download class="h-3.5 w-3.5" />
        导出
      </button>
    </div>

    <div class="flex-1 overflow-auto p-4">
      <!-- 输出文件下载列表（优先显示） -->
      <div v-if="hasFiles" class="flex flex-col gap-2">
        <p class="text-xs font-medium text-muted-foreground mb-1">输出文件</p>
        <a
          v-for="file in files"
          :key="file.path"
          :href="file.url"
          target="_blank"
          class="flex items-center justify-between rounded-xl border border-border bg-card px-3 py-2.5 transition-colors hover:bg-muted"
        >
          <div class="flex items-center gap-2 min-w-0">
            <FileDown class="h-4 w-4 shrink-0 text-brand" />
            <span class="text-sm text-card-foreground truncate">{{ file.name }}</span>
            <span v-if="file.size_kb" class="text-xs text-muted-foreground shrink-0">
              {{ file.size_kb }} KB
            </span>
          </div>
          <Download class="h-3.5 w-3.5 shrink-0 text-brand" />
        </a>
      </div>

      <!-- 文本结果 -->
      <pre
        v-if="result"
        class="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground"
      >{{ result }}</pre>

      <!-- 空状态 -->
      <div v-if="!result && !hasFiles" class="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
        <slot name="empty" />
      </div>
    </div>
  </div>
</template>
