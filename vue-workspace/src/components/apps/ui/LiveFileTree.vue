<script setup lang="ts">
/**
 * 实时工作区文件树 — 流水线处理期间每 3 秒轮询 cache-tree，
 * 让用户边生成边查看中间产物（对齐旧版前端 useIDE 的轮询行为）。
 *
 * 点击文件在新标签页打开内容（文本/PDF/图片浏览器可直接渲染，
 * docx 等二进制由浏览器下载），下载按钮由 FileTree 自带。
 */

import { ref, watch, onBeforeUnmount } from "vue"
import { FolderTree, Loader2 } from "lucide-vue-next"
import FileTree from "./FileTree.vue"
import type { FileTreeNode } from "@/services/api/types"

const props = defineProps<{
  sessionId: string | null
  /** 为 true 时启动轮询（流水线处理中） */
  active: boolean
  fetchTree: (sid: string) => Promise<FileTreeNode>
  buildDownloadUrl: (sid: string, file: string) => string
  fileContentUrl: (sid: string, path: string) => string
}>()

const POLL_INTERVAL_MS = 3_000

const tree = ref<FileTreeNode | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const expanded = ref(false)

let timer: ReturnType<typeof setInterval> | null = null

async function refresh() {
  const sid = props.sessionId
  if (!sid) return
  loading.value = true
  try {
    tree.value = await props.fetchTree(sid)
    error.value = null
  } catch (e: any) {
    /* 轮询期间的失败不打断流水线，仅记录最近一次错误 */
    error.value = e?.message || "加载文件树失败"
  } finally {
    loading.value = false
  }
}

function startPolling() {
  stopPolling()
  refresh()
  timer = setInterval(refresh, POLL_INTERVAL_MS)
}

function stopPolling() {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

watch(
  () => props.active,
  (active) => {
    if (active) startPolling()
    else {
      stopPolling()
      /* 结束后补一次最终状态 */
      refresh()
    }
  },
  { immediate: true },
)

onBeforeUnmount(stopPolling)

function onViewFile(node: { path: string }) {
  const sid = props.sessionId
  if (!sid) return
  window.open(props.fileContentUrl(sid, node.path), "_blank")
}
</script>

<template>
  <div class="rounded-2xl border border-border bg-card p-4">
    <button
      class="flex w-full items-center justify-between text-left"
      @click="expanded = !expanded"
    >
      <span class="flex items-center gap-2 text-sm font-bold text-card-foreground">
        <FolderTree class="h-4 w-4 text-muted-foreground" />
        工作区文件
        <Loader2 v-if="loading" class="h-3.5 w-3.5 animate-spin text-muted-foreground" />
        <span v-if="active" class="text-[10px] font-normal text-brand">每 3 秒自动刷新</span>
      </span>
      <span class="text-xs text-muted-foreground">{{ expanded ? "收起" : "展开" }}</span>
    </button>

    <div v-show="expanded" class="mt-3">
      <div v-if="error" class="text-xs text-red-400">{{ error }}</div>
      <div v-else-if="tree" class="max-h-72 overflow-auto rounded-xl border border-border bg-muted/30 p-3">
        <FileTree
          :node="tree"
          :session-id="sessionId ?? ''"
          :build-download-url="(file: string) => buildDownloadUrl(sessionId ?? '', file)"
          @view-file="onViewFile"
        />
      </div>
      <p v-else class="py-4 text-center text-xs text-muted-foreground">暂无文件</p>
    </div>
  </div>
</template>
