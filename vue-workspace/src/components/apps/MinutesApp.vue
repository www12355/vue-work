<script setup lang="ts">
import { computed, type Component } from "vue"
import { Loader2, Sparkles } from "lucide-vue-next"
import Topic from "@/components/apps/minutes/Topic.vue"
import Notes from "@/components/apps/minutes/Notes.vue"
import Preview from "@/components/apps/minutes/Preview.vue"
import { createMinutesState } from "@/components/apps/minutes/state"
import { useLayout } from "@/composables/useLayout"

const props = defineProps<{ ownerId: string }>()

const ctx = createMinutesState()
const { left, right, submitLabel } = useLayout(props.ownerId)

/* 区块 id → 组件，顺序与显隐来自管理后台配置 */
const SECTIONS: Record<string, Component> = {
  topic: Topic,
  notes: Notes,
  preview: Preview,
}

const twoColumns = computed(() => left.value.length > 0 && right.value.length > 0)
</script>

<template>
  <div class="flex flex-col gap-4">
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
      class="flex w-full items-center justify-center gap-2 rounded-2xl bg-brand px-4 py-4 text-sm font-semibold text-brand-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      @click="ctx.generate()"
    >
      <Loader2 v-if="ctx.s.loading" class="h-4 w-4 animate-spin" />
      <Sparkles v-else class="h-4 w-4" />
      {{ ctx.s.loading ? "正在生成纪要…" : submitLabel }}
    </button>
  </div>
</template>
