<script setup lang="ts">
import DropZone from "@/components/apps/ui/DropZone.vue"
import type { ComboCtx } from "@/components/apps/combo/state"

const props = defineProps<{ ctx: ComboCtx; label: string }>()
</script>

<template>
  <DropZone
    v-model="props.ctx.s.files"
    :title="label"
    hint="或点击选择文件"
    note="支持 .docx / .txt / .md，最大 200 MB"
    accept=".docx,.txt,.md"
    multiple
  />
</template>
