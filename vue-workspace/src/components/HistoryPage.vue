<script setup lang="ts">
/**
 * 历史记录独立页面 — 全屏展示，非弹窗。
 * 通过 view store 中的 historyModule 决定展示标书还是合同的历史记录。
 */

import { ref, computed, watch } from "vue"
import {
  Trash2,
  RefreshCw,
  Clock,
  FolderOpen,
  ArrowLeft,
  Loader2,
  Server,
  FileText,
  History,
} from "lucide-vue-next"
import FileTree from "@/components/apps/ui/FileTree.vue"
import { useHistory } from "@/composables/useHistory"
import { historyModule, goBackToWorkspace } from "@/stores/view"
import {
  fetchBidSessions,
  deleteBidSession,
  fetchBidCacheTree,
  fetchBidFileContent,
  bidDownloadUrl,
} from "@/services/api/bid"
import {
  fetchContractSessions,
  deleteContractSession,
  fetchContractCacheTree,
  fetchContractFileContent,
  contractDownloadUrl,
} from "@/services/api/contract"
import type { SessionListItem, FileTreeNode, DownloadableFile } from "@/services/api/types"

/* 根据 historyModule 选择对应的 API */
const isTender = computed(() => historyModule.value === "tender")
const ownerId = computed(() => historyModule.value)

const api = computed(() => ({
  fetchSessions: isTender.value ? fetchBidSessions : fetchContractSessions,
  deleteSession: isTender.value ? deleteBidSession : deleteContractSession,
  fetchCacheTree: isTender.value ? fetchBidCacheTree : fetchContractCacheTree,
  fetchFileContent: isTender.value ? fetchBidFileContent : fetchContractFileContent,
  buildDownloadUrl: isTender.value ? bidDownloadUrl : contractDownloadUrl,
}))

const pageTitle = computed(() => (isTender.value ? "标书生成 · 历史记录" : "合同生成 · 历史记录"))

const history = useHistory(historyModule.value)

/* 文件树状态 */
const cacheTree = ref<FileTreeNode | null>(null)
const treeLoading = ref(false)
const treeError = ref<string | null>(null)
const viewingFile = ref<{ path: string; content: string } | null>(null)

const sessionsSorted = computed(() =>
  [...history.sessions.value].sort((a, b) => {
    const da = a.created_at ?? ""
    const db = b.created_at ?? ""
    return db.localeCompare(da)
  }),
)

function statusLabel(s: SessionListItem): string {
  switch (s.status) {
    case "completed": return "已完成"
    case "running": return "运行中"
    case "failed": return "失败"
    default: return "空闲"
  }
}

function statusClass(s: SessionListItem): string {
  switch (s.status) {
    case "completed": return "bg-emerald-500/15 text-emerald-500"
    case "running": return "bg-brand/15 text-brand"
    case "failed": return "bg-red-500/15 text-red-500"
    default: return "bg-muted text-muted-foreground"
  }
}

function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id
}

function displayName(s: SessionListItem): string {
  return s.company || s.project || shortId(s.session_id)
}

function formatDate(d: string): string {
  if (!d) return ""
  try {
    const date = new Date(d)
    return date.toLocaleString("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return d
  }
}

async function loadSession(session: SessionListItem) {
  history.selectSession(session.session_id)

  treeLoading.value = true
  treeError.value = null
  cacheTree.value = null
  viewingFile.value = null
  try {
    cacheTree.value = await api.value.fetchCacheTree(session.session_id)
  } catch (e: any) {
    treeError.value = e.message || "无法加载文件树"
  } finally {
    treeLoading.value = false
  }
}

async function onDelete(session: SessionListItem) {
  if (!confirm(`确认删除会话 ${shortId(session.session_id)}？此操作不可撤销。`)) return
  try {
    await history.deleteSession(session.session_id, api.value.deleteSession)
    if (history.selectedId.value === session.session_id) {
      cacheTree.value = null
      viewingFile.value = null
    }
  } catch {
    /* 错误已在 composable 中设置 */
  }
}

async function onViewFile(node: { path: string; name: string }) {
  if (!history.selectedId.value) return
  try {
    viewingFile.value = {
      path: node.path,
      content: await api.value.fetchFileContent(history.selectedId.value, node.path),
    }
  } catch (e: any) {
    viewingFile.value = {
      path: node.path,
      content: `[读取失败] ${e.message || "未知错误"}`,
    }
  }
}

function downloadUrl(file: string): string {
  if (!history.selectedId.value) return "#"
  return api.value.buildDownloadUrl(history.selectedId.value, file)
}

const selectedFileNode = computed<DownloadableFile | null>(() => {
  if (!viewingFile.value) return null
  return {
    name: viewingFile.value.path.split("/").pop() || viewingFile.value.path,
    path: viewingFile.value.path,
    url: downloadUrl(viewingFile.value.path),
  }
})

/* 模块切换时重新加载 */
watch(historyModule, (mod) => {
  history.sessions.value = []
  history.selectedId.value = null
  cacheTree.value = null
  viewingFile.value = null
  history.fetchSessions(
    mod === "tender" ? fetchBidSessions : fetchContractSessions,
  )
})

/* 初次进入时自动加载 */
history.fetchSessions(
  historyModule.value === "tender" ? fetchBidSessions : fetchContractSessions,
)
</script>

<template>
  <div class="flex flex-col gap-6">
    <!-- 顶部：标题 + 返回按钮 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <button
          class="flex items-center gap-1.5 rounded-xl bg-muted px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/80 hover:text-foreground"
          @click="goBackToWorkspace"
        >
          <ArrowLeft class="h-4 w-4" />
          返回工作台
        </button>
        <div class="flex items-center gap-2">
          <History class="h-5 w-5 text-brand" />
          <h1 class="text-lg font-semibold text-card-foreground">{{ pageTitle }}</h1>
        </div>
      </div>
      <button
        class="flex items-center gap-1.5 rounded-xl bg-muted px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
        :disabled="history.loading.value"
        @click="history.fetchSessions(api.fetchSessions)"
      >
        <RefreshCw class="h-4 w-4" :class="history.loading.value && 'animate-spin'" />
        刷新
      </button>
    </div>

    <!-- 错误提示 -->
    <div
      v-if="history.error.value"
      class="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3"
    >
      <Server class="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
      <div>
        <p class="text-sm text-red-400">{{ history.error.value }}</p>
        <p class="mt-1 text-xs text-red-400/70">后端服务未连接或地址配置不正确</p>
      </div>
    </div>

    <!-- 主体：两栏布局 — 左侧 session 列表 + 右侧文件树 / 预览 -->
    <div class="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <!-- 左侧：session 列表 -->
      <div class="flex max-h-[calc(100vh-180px)] flex-col gap-2 overflow-auto rounded-2xl border border-border bg-card p-4">
        <p class="px-2 text-xs font-medium text-muted-foreground">
          {{ sessionsSorted.length ? `共 ${sessionsSorted.length} 条记录` : "暂无历史记录" }}
        </p>

        <div v-if="history.loading.value" class="flex items-center justify-center py-8">
          <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
        </div>

        <template v-else-if="sessionsSorted.length">
          <button
            v-for="s in sessionsSorted"
            :key="s.session_id"
            class="flex flex-col gap-1 rounded-xl border px-3 py-2.5 text-left transition-colors hover:bg-muted/50"
            :class="[
              history.selectedId.value === s.session_id
                ? 'border-brand bg-brand/5'
                : 'border-transparent',
            ]"
            @click="loadSession(s)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-medium text-card-foreground truncate">
                {{ displayName(s) }}
              </span>
              <span class="shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium" :class="statusClass(s)">
                {{ statusLabel(s) }}
              </span>
            </div>
            <div class="flex items-center justify-between gap-2">
              <span class="flex items-center gap-1 text-[11px] text-muted-foreground">
                <Clock class="h-3 w-3" />
                {{ formatDate(s.created_at) }}
              </span>
              <span class="text-[11px] text-muted-foreground">
                {{ s.completed_stages ?? s.current_stage }}/{{ s.total_stages }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-[10px] text-muted-foreground/60 font-mono">
                {{ shortId(s.session_id) }}
              </span>
              <button
                class="flex h-6 w-6 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-red-500/10 hover:text-red-500"
                title="删除此会话"
                @click.stop="onDelete(s)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </button>
            </div>
          </button>
        </template>

        <div v-else class="flex flex-col items-center gap-2 py-8 text-center">
          <FolderOpen class="h-6 w-6 text-muted-foreground/40" />
          <p class="text-xs text-muted-foreground">暂无生成记录</p>
        </div>
      </div>

      <!-- 右侧：文件树 + 预览 -->
      <div class="min-h-[calc(100vh-240px)] rounded-2xl border border-border bg-card p-6">
        <!-- 未选择 session -->
        <div
          v-if="!history.selectedId.value"
          class="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground"
        >
          <FolderOpen class="h-10 w-10 opacity-30" />
          <p class="text-sm">选择左侧会话以浏览文件</p>
        </div>

        <!-- 加载中 -->
        <div v-else-if="treeLoading" class="flex items-center justify-center py-12">
          <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
        </div>

        <!-- 文件预览 + 文件树 -->
        <template v-else>
          <div class="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <!-- 文件预览 -->
            <div>
              <p class="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                文件预览
              </p>
              <div
                v-if="viewingFile"
                class="rounded-xl border border-border bg-muted/30 p-4"
              >
                <div class="mb-3 flex items-center justify-between">
                  <span class="text-sm font-mono text-card-foreground truncate">
                    <FileText class="mr-1.5 inline-block h-3.5 w-3.5 text-muted-foreground" />
                    {{ viewingFile.path.split("/").pop() }}
                  </span>
                  <a
                    v-if="selectedFileNode"
                    :href="selectedFileNode.url"
                    target="_blank"
                    class="rounded-lg bg-brand/10 px-3 py-1 text-xs font-medium text-brand transition-colors hover:bg-brand/20"
                  >
                    下载
                  </a>
                </div>
                <pre class="max-h-[calc(100vh-420px)] overflow-auto whitespace-pre-wrap rounded-lg bg-background p-3 text-[12px] leading-relaxed text-card-foreground">{{ viewingFile.content }}</pre>
              </div>
              <div v-else class="flex items-center justify-center py-12">
                <p class="text-xs text-muted-foreground/60">点击右侧文件树中的文件查看预览</p>
              </div>
            </div>

            <!-- 文件树 -->
            <div>
              <p class="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                工作空间
              </p>
              <div v-if="treeError" class="text-xs text-red-400">
                {{ treeError }}
              </div>
              <div
                v-else-if="cacheTree"
                class="rounded-xl border border-border bg-muted/30 p-3"
              >
                <FileTree
                  :node="cacheTree"
                  :session-id="history.selectedId.value"
                  :build-download-url="downloadUrl"
                  @view-file="onViewFile"
                />
              </div>
              <p v-else class="text-xs text-muted-foreground">文件树为空</p>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
