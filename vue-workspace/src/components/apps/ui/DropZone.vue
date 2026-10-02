<script setup lang="ts">
import { ref } from "vue"
import { FileCheck2, Loader2, AlertCircle } from "lucide-vue-next"
import { registerFiles, unregisterFile } from "@/composables/useUpload"

const props = withDefaults(
  defineProps<{
    /** 主标题，如「拖拽 DOCX 文件到此处」 */
    title: string
    /** 第二行提示 */
    hint?: string
    /** 第三行辅助说明 */
    note?: string
    /** 可接受的文件类型 */
    accept?: string
    /** 是否允许多选 */
    multiple?: boolean
    /** 上传进度 0-100（可选，为 undefined 时不显示进度条） */
    uploadProgress?: number
    /** 是否正在上传 */
    uploading?: boolean
  }>(),
  { hint: "", note: "", accept: ".docx", multiple: false, uploadProgress: undefined, uploading: false },
)

const files = defineModel<string[]>({ default: () => [] })

const emit = defineEmits<{
  /** 文件被选中时发出原始 File 对象，供父组件跟踪 */
  (e: "files-selected", files: File[]): void
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const over = ref(false)

function pick(list: FileList | null) {
  if (!list?.length) return
  const arr = Array.from(list)
  const names = arr.map((f) => f.name)
  files.value = props.multiple ? [...files.value, ...names] : names.slice(0, 1)
  /* 注册到全局 fileMap 供上传时查找 */
  registerFiles(props.multiple ? arr : arr.slice(0, 1))
  emit("files-selected", props.multiple ? arr : arr.slice(0, 1))
}

function onDrop(e: DragEvent) {
  over.value = false
  pick(e.dataTransfer?.files ?? null)
}

function remove(name: string) {
  files.value = files.value.filter((f) => f !== name)
  unregisterFile(name)
}
</script>

<template>
  <div
    class="flex min-h-36 flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed p-6 text-center transition-colors"
    :class="over ? 'border-brand bg-brand/5' : 'border-border bg-card/60'"
    @dragover.prevent="over = true"
    @dragleave="over = false"
    @drop.prevent="onDrop"
  >
    <input
      ref="inputRef"
      type="file"
      class="sr-only"
      :accept="accept"
      :multiple="multiple"
      :disabled="uploading"
      @change="pick(($event.target as HTMLInputElement).files)"
    />

    <template v-if="uploading">
      <Loader2 class="h-6 w-6 animate-spin text-brand" />
      <p class="text-sm font-medium text-card-foreground">正在上传…</p>
      <!-- 进度条 -->
      <div
        v-if="uploadProgress !== undefined"
        class="mt-1 h-1.5 w-48 overflow-hidden rounded-full bg-muted"
      >
        <div
          class="h-full rounded-full bg-brand transition-all duration-300"
          :style="{ width: `${uploadProgress}%` }"
        />
      </div>
      <p v-if="uploadProgress !== undefined" class="text-xs text-muted-foreground">
        {{ uploadProgress }}%
      </p>
    </template>

    <template v-else>
      <p class="text-base font-bold text-card-foreground">{{ title }}</p>
      <button type="button" class="text-xs text-muted-foreground underline-offset-2 hover:underline" @click="inputRef?.click()">
        {{ hint || "或点击选择文件" }}
      </button>
      <p v-if="note" class="text-xs text-muted-foreground/80">{{ note }}</p>
    </template>

    <ul v-if="files.length" class="mt-2 flex w-full flex-col gap-1.5">
      <li
        v-for="name in files"
        :key="name"
        class="flex items-center gap-2 rounded-xl bg-muted px-3 py-2 text-left text-xs text-foreground"
      >
        <FileCheck2 class="h-4 w-4 shrink-0 text-brand" />
        <span class="min-w-0 flex-1 truncate">{{ name }}</span>
        <button
          v-if="!uploading"
          type="button"
          class="shrink-0 text-muted-foreground hover:text-foreground"
          @click="remove(name)"
        >
          移除
        </button>
      </li>
    </ul>
  </div>
</template>
