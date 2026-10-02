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
  if (names.length) props.ctx.s.refFiles = names
  if (files.length) registerFiles(files)
  if (props.ctx.onRefFilesSelected) {
    props.ctx.onRefFilesSelected(files)
  }
}
</script>

<template>
  <SectionCard :title="label">
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
        class="rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50"
        :disabled="uploading"
        @click="inputRef?.click()"
      >
        {{ uploading ? "上传中…" : "选择参考文件" }}
      </button>
      <span class="text-xs text-muted-foreground">合同案例、模板文档等</span>
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

    <ul v-if="ctx.s.refFiles.length" class="mt-3 flex flex-col gap-1.5">
      <li
        v-for="name in ctx.s.refFiles"
        :key="name"
        class="flex items-center gap-2 rounded-xl bg-muted px-3 py-2 text-xs text-foreground"
      >
        <FileCheck2 class="h-4 w-4 shrink-0 text-muted-foreground" />
        <span class="min-w-0 flex-1 truncate">{{ name }}</span>
      </li>
    </ul>
  </SectionCard>
</template>
