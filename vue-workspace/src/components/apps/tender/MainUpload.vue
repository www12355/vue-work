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
  /* ctx 中已有 mainFiles 名称列表（v-model），这里只做额外处理 */
  if (props.ctx.onMainFilesSelected) {
    props.ctx.onMainFilesSelected(files)
  }
}
</script>

<template>
  <DropZone
    v-model="props.ctx.s.mainFiles"
    :title="label || '拖拽 DOCX 文件到此处'"
    hint="或点击选择文件"
    note="支持 .docx 格式，最大 200 MB"
    :upload-progress="uploadProgress"
    :uploading="uploading"
    @files-selected="onFilesSelected"
  />
</template>
