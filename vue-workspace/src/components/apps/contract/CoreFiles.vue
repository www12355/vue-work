<script setup lang="ts">
import { ref } from "vue"
import { FileCheck2 } from "lucide-vue-next"
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import { fileNames, type ContractCtx } from "@/components/apps/contract/state"
import { registerFiles } from "@/composables/useUpload"

const props = defineProps<{
  ctx: ContractCtx
  label: string
  uploadProgress?: number
  uploading?: boolean
}>()

const inputRef = ref<HTMLInputElement | null>(null)

function pick(list: FileList | null) {
  const files = Array.from(list ?? [])
  const names = fileNames(list)
  if (names.length) props.ctx.s.coreFiles = names
  if (files.length) registerFiles(files)
  if (props.ctx.onCoreFilesSelected) {
    props.ctx.onCoreFilesSelected(files)
  }
}
</script>

<template>
  <SectionCard :title="label" highlight>
    <input
      ref="inputRef"
      type="file"
      multiple
      class="sr-only"
      :disabled="uploading"
      @change="pick(($event.target as HTMLInputElement).files)"
    />

    <div class="flex items-center gap-3">
      <button
        type="button"
        class="rounded-xl bg-brand px-3 py-2 text-xs font-semibold text-brand-foreground hover:opacity-90 disabled:opacity-50"
        :disabled="uploading"
        @click="inputRef?.click()"
      >
        {{ uploading ? "上传中…" : "选择核心文件" }}
      </button>
      <span class="text-xs text-muted-foreground">需求文档、技术规格书等</span>
    </div>

    <!-- 上传进度条 -->
    <div v-if="uploading && uploadProgress !== undefined" class="mt-3">
      <div class="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          class="h-full rounded-full bg-brand transition-all duration-300"
          :style="{ width: `${uploadProgress}%` }"
        />
      </div>
      <p class="mt-1 text-xs text-muted-foreground">{{ uploadProgress }}%</p>
    </div>

    <ul v-if="ctx.s.coreFiles.length" class="mt-3 flex flex-col gap-1.5">
      <li
        v-for="name in ctx.s.coreFiles"
        :key="name"
        class="flex items-center gap-2 rounded-xl bg-card px-3 py-2 text-xs text-foreground"
      >
        <FileCheck2 class="h-4 w-4 shrink-0 text-brand" />
        <span class="min-w-0 flex-1 truncate">{{ name }}</span>
      </li>
    </ul>
  </SectionCard>
</template>
