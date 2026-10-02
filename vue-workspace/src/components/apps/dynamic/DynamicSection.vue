<script setup lang="ts">
import { computed } from "vue"
import { FileCheck2, Sparkles } from "lucide-vue-next"
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import ResultPanel from "@/components/apps/ResultPanel.vue"
import { sectionKind, type SectionConfig } from "@/data/registry-defaults"

const props = defineProps<{
  section: SectionConfig
  /** 表单取值容器，以字段 id 为键 */
  values: Record<string, string>
  files: string[]
  result: string
}>()

const emit = defineEmits<{ pick: [FileList | null] }>()

const kind = computed(() => sectionKind(props.section))
const upload = computed(() => props.section.upload ?? {})
const resultCfg = computed(() => props.section.result ?? {})
</script>

<template>
  <SectionCard :title="section.label">
    <p v-if="section.description" class="-mt-1 mb-3 text-xs leading-relaxed text-muted-foreground">
      {{ section.description }}
    </p>

    <!-- 文件上传区块 -->
    <template v-if="kind === 'upload'">
      <label
        class="flex cursor-pointer flex-col items-center gap-1.5 rounded-2xl border-2 border-dashed border-border px-4 py-6 text-center transition-colors hover:border-brand"
      >
        <input
          type="file"
          :multiple="upload.multiple !== false"
          :accept="upload.accept || undefined"
          class="sr-only"
          @change="emit('pick', ($event.target as HTMLInputElement).files)"
        />
        <span class="text-sm font-semibold text-card-foreground">{{ upload.hint || "点击选择文件" }}</span>
        <span v-if="upload.formats" class="text-xs text-muted-foreground">支持 {{ upload.formats }}</span>
      </label>
      <ul v-if="files.length" class="mt-3 flex flex-col gap-1.5">
        <li
          v-for="name in files"
          :key="name"
          class="flex items-center gap-2 rounded-xl bg-muted px-3 py-2 text-xs text-foreground"
        >
          <FileCheck2 class="h-4 w-4 shrink-0 text-brand" />
          <span class="min-w-0 flex-1 truncate">{{ name }}</span>
        </li>
      </ul>
    </template>

    <!-- 生成结果区块 -->
    <template v-else-if="kind === 'result'">
      <ResultPanel
        label=""
        :result="result"
        :style="{ minHeight: `${resultCfg.minHeight ?? 220}px` }"
      >
        <template #empty>
          <Sparkles class="h-8 w-8 opacity-40" />
          <p class="text-sm">{{ resultCfg.emptyHint || "填写表单后点击底部按钮生成" }}</p>
        </template>
      </ResultPanel>
    </template>

    <!-- 表单字段区块：字段类型与必填由后台配置 -->
    <div v-else class="flex flex-col gap-3">
      <label
        v-for="f in section.fields ?? []"
        :key="f.id"
        class="flex flex-col gap-1 text-xs text-muted-foreground"
      >
        <span>{{ f.label }} <span v-if="f.required" class="text-brand">*</span></span>
        <textarea
          v-if="f.type === 'textarea'"
          v-model="values[f.id]"
          rows="4"
          :placeholder="f.placeholder"
          class="resize-y rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
        />
        <select
          v-else-if="f.type === 'select'"
          v-model="values[f.id]"
          class="rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
        >
          <option value="">请选择</option>
          <option v-for="opt in f.options ?? []" :key="opt" :value="opt">{{ opt }}</option>
        </select>
        <input
          v-else
          v-model="values[f.id]"
          :type="f.type"
          :placeholder="f.placeholder"
          class="rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none ring-ring/50 focus:ring-2"
        />
      </label>
      <p v-if="!(section.fields ?? []).length" class="text-xs text-muted-foreground">
        该区块暂无字段，可在管理后台添加。
      </p>
    </div>
  </SectionCard>
</template>
