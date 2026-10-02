<script setup lang="ts">
/**
 * 递归文件树组件 — 展示 session 工作空间的目录结构。
 * 目录可折叠/展开，文件可点击查看。
 */

import { ref } from "vue"
import {
  Folder,
  FolderOpen,
  File,
  FileText,
  FileCode,
  Image,
  ChevronRight,
  Download,
} from "lucide-vue-next"
import type { FileTreeNode } from "@/services/api/types"

const props = defineProps<{
  node: FileTreeNode
  sessionId: string
  buildDownloadUrl: (file: string) => string
}>()

const emit = defineEmits<{
  (e: "viewFile", node: { path: string; name: string }): void
}>()

const expanded = ref(props.node.type === "directory" && (props.node.children?.length ?? 0) <= 5)

function toggle() {
  if (props.node.type === "directory") {
    expanded.value = !expanded.value
  }
}

function iconFor(name: string) {
  const ext = name.split(".").pop()?.toLowerCase()
  switch (ext) {
    case "md": return FileCode
    case "txt": return FileText
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "svg": return Image
    default: return File
  }
}

function downloadUrl(): string {
  return props.buildDownloadUrl(props.node.path)
}
</script>

<template>
  <div>
    <!-- 目录节点 -->
    <div
      v-if="node.type === 'directory'"
      class="cursor-pointer select-none rounded-lg py-0.5 transition-colors hover:bg-muted/50"
      @click="toggle"
    >
      <div class="flex items-center gap-1 px-1">
        <ChevronRight
          class="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform"
          :class="expanded && 'rotate-90'"
        />
        <component
          :is="expanded ? FolderOpen : Folder"
          class="h-3.5 w-3.5 shrink-0 text-muted-foreground/70"
        />
        <span class="text-xs text-card-foreground truncate">{{ node.name }}</span>
        <span class="text-[10px] text-muted-foreground/50">
          {{ node.children?.length ?? 0 }}
        </span>
      </div>
    </div>

    <!-- 文件节点 -->
    <div
      v-else
      class="flex items-center gap-1 rounded-lg px-1 py-0.5 transition-colors hover:bg-muted/50"
    >
      <span class="w-3.5 shrink-0" />
      <component
        :is="iconFor(node.name)"
        class="h-3.5 w-3.5 shrink-0 text-muted-foreground/70"
      />
      <button
        class="text-xs text-card-foreground truncate text-left hover:text-brand"
        @click="emit('viewFile', { path: node.path, name: node.name })"
      >
        {{ node.name }}
      </button>
      <span v-if="node.size_kb" class="text-[10px] text-muted-foreground/50 shrink-0 ml-auto">
        {{ node.size_kb }}KB
      </span>
      <a
        :href="downloadUrl()"
        target="_blank"
        class="shrink-0 rounded p-0.5 text-muted-foreground/50 transition-colors hover:text-brand"
        title="下载"
      >
        <Download class="h-3 w-3" />
      </a>
    </div>

    <!-- 子目录（折叠展开） -->
    <div
      v-if="node.type === 'directory' && expanded && node.children?.length"
      class="ml-3.5 border-l border-border/50 pl-2"
    >
      <FileTree
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :session-id="sessionId"
        :build-download-url="buildDownloadUrl"
        @view-file="emit('viewFile', $event)"
      />
    </div>
  </div>
</template>
