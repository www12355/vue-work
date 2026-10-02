<script setup lang="ts">
import { computed, type Component } from "vue"
import { Layers, Loader2, Sparkles } from "lucide-vue-next"
import Upload from "@/components/apps/combo/Upload.vue"
import Info from "@/components/apps/combo/Info.vue"
import Pipeline from "@/components/apps/combo/Pipeline.vue"
import Outputs from "@/components/apps/combo/Outputs.vue"
import Result from "@/components/apps/combo/Result.vue"
import { createComboState } from "@/components/apps/combo/state"
import { getCombo, getModule } from "@/stores/registry"
import { useLayout } from "@/composables/useLayout"

const props = defineProps<{ ownerId: string }>()

const combo = computed(() => getCombo(props.ownerId))
const ctx = createComboState(() => combo.value)
const { left, right, submitLabel } = useLayout(props.ownerId)

/* 区块 id → 组件，阶段与布局均由管理后台的组合规则决定 */
const SECTIONS: Record<string, Component> = {
  upload: Upload,
  info: Info,
  pipeline: Pipeline,
  outputs: Outputs,
  result: Result,
}

const twoColumns = computed(() => left.value.length > 0 && right.value.length > 0)
const stageCount = computed(() => ctx.stages.length)
const memberNames = computed(() => (combo.value?.members ?? []).map((id) => getModule(id)?.title ?? id))
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- 组合构成：成员模块由后台的组合规则决定（说明文案已在窗口标题下展示，此处不重复） -->
    <div class="flex flex-wrap items-center gap-2 rounded-2xl border border-brand/40 bg-brand/5 px-4 py-3">
      <Layers class="h-4 w-4 shrink-0 text-brand" />
      <span class="text-xs font-medium text-muted-foreground">组合构成</span>
      <span
        v-for="(name, i) in memberNames"
        :key="name"
        class="flex items-center gap-2 text-xs font-semibold text-foreground"
      >
        <span v-if="i > 0" aria-hidden="true" class="text-brand">+</span>
        {{ name }}
      </span>
      <span class="ml-auto text-xs text-muted-foreground">共 {{ stageCount }} 个阶段</span>
    </div>

    <div class="grid gap-4" :class="twoColumns ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]' : ''">
      <div v-if="left.length" class="flex flex-col gap-4">
        <component
          v-for="s in left"
          :key="s.id"
          :is="SECTIONS[s.id]"
          v-bind="SECTIONS[s.id] ? { ctx, label: s.label } : {}"
        />
      </div>

      <div v-if="right.length" class="flex flex-col gap-4">
        <component
          v-for="s in right"
          :key="s.id"
          :is="SECTIONS[s.id]"
          v-bind="SECTIONS[s.id] ? { ctx, label: s.label } : {}"
        />
      </div>
    </div>

    <button
      :disabled="ctx.disabled"
      class="flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-brand via-brand/85 to-brand/55 px-4 py-4 text-sm font-semibold text-brand-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      @click="ctx.run()"
    >
      <Loader2 v-if="ctx.s.loading" class="h-4 w-4 animate-spin" />
      <Sparkles v-else class="h-4 w-4" />
      {{ ctx.s.loading ? `正在执行阶段 ${ctx.s.stage} / ${stageCount}…` : submitLabel }}
    </button>
  </div>
</template>
