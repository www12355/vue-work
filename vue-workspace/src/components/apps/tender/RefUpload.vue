<script setup lang="ts">
import DropZone from "@/components/apps/ui/DropZone.vue"
import type { TenderCtx } from "@/components/apps/tender/state"

const props = defineProps<{
  ctx: TenderCtx
  label: string
  uploadProgress?: number
  uploading?: boolean
}>()

function onFilesSelected(files: File[]) {
  if (props.ctx.onRefFilesSelected) {
    props.ctx.onRefFilesSelected(files)
  }
}
</script>

<template>
  <DropZone
    v-model="props.ctx.s.refFiles"
    :title="label || '参考文件（可选）'"
    hint="拖拽或点击上传格式、风格或内容参考"
    accept=".docx,.pdf,.md"
    multiple
    :upload-progress="uploadProgress"
    :uploading="uploading"
    @files-selected="onFilesSelected"
  />
</template>
