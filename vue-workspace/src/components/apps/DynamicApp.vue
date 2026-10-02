<script setup lang="ts">
import { computed, reactive, ref } from "vue"
import { Loader2, Sparkles, Wrench } from "lucide-vue-next"
import DynamicSection from "@/components/apps/dynamic/DynamicSection.vue"
import { getModule } from "@/stores/registry"
import { useLayout } from "@/composables/useLayout"
import type { FieldConfig } from "@/data/registry-defaults"

const props = defineProps<{ ownerId: string }>()

const mod = computed(() => getModule(props.ownerId))
const { left, right, submitLabel } = useLayout(props.ownerId)

/** 表单取值：以字段 id 为键，后台增删字段后自动生效 */
const values = reactive<Record<string, string>>({})
const files = ref<string[]>([])
const loading = ref(false)
const result = ref("")

const isDev = computed(() => mod.value?.status === "dev")

/** 可见区块中的必填字段 */
const requiredFields = computed<FieldConfig[]>(() =>
  (mod.value?.sections ?? [])
    .filter((s) => s.visible)
    .flatMap((s) => s.fields ?? [])
    .filter((f) => f.required),
)

const disabled = computed(
  () => loading.value || isDev.value || requiredFields.value.some((f) => !values[f.id]?.trim()),
)

const twoColumns = computed(() => left.value.length > 0 && right.value.length > 0)

function pick(list: FileList | null) {
  if (list?.length) files.value = Array.from(list).map((f) => f.name)
}

function generate() {
  if (disabled.value) return
  loading.value = true
  result.value = ""
  setTimeout(() => {
    const rows = (mod.value?.sections ?? [])
      .filter((s) => s.visible)
      .flatMap((s) => s.fields ?? [])
      .map((f) => `- ${f.label}：${values[f.id]?.trim() || "（未填写）"}`)

    result.value = `${mod.value?.title ?? "文档"} 生成结果

【输入信息】
${rows.length ? rows.join("\n") : "- 该模块暂未配置表单字段"}

【上传文件】
${files.value.length ? files.value.map((n) => `- ${n}`).join("\n") : "- 无"}

【生成正文】
本文档由管理后台配置的「${mod.value?.title}」模块生成，区块顺序、字段与布局均可在后台调整。`
    loading.value = false
  }, 1200)
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- 待开发模块给出明确提示，避免误认为功能故障 -->
    <div
      v-if="isDev"
      class="flex items-start gap-3 rounded-2xl border border-dashed border-border bg-muted/60 px-4 py-3"
    >
      <Wrench class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <p class="text-xs leading-relaxed text-muted-foreground">
        该模块处于「待开发」状态，页面结构可在管理后台预先配置；状态切换为「已上线」后即可正式生成文档。
      </p>
    </div>

    <div class="grid gap-4" :class="twoColumns ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]' : ''">
      <div v-if="left.length" class="flex flex-col gap-4">
        <DynamicSection
          v-for="s in left"
          :key="s.id"
          :section="s"
          :values="values"
          :files="files"
          :result="result"
          @pick="pick"
        />
      </div>

      <div v-if="right.length" class="flex flex-col gap-4">
        <DynamicSection
          v-for="s in right"
          :key="s.id"
          :section="s"
          :values="values"
          :files="files"
          :result="result"
          @pick="pick"
        />
      </div>
    </div>

    <button
      :disabled="disabled"
      class="flex w-full items-center justify-center gap-2 rounded-2xl bg-brand px-4 py-4 text-sm font-semibold text-brand-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      @click="generate"
    >
      <Loader2 v-if="loading" class="h-4 w-4 animate-spin" />
      <Sparkles v-else class="h-4 w-4" />
      {{ isDev ? "该模块待开发，暂不可生成" : loading ? "正在生成…" : submitLabel }}
    </button>
  </div>
</template>
