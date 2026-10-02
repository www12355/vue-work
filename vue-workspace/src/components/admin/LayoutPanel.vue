<script setup lang="ts">
import { computed, ref } from "vue"
import Panel from "@/components/admin/ui/Panel.vue"
import LayoutEditor from "@/components/admin/LayoutEditor.vue"
import { combos, getOwner, modules } from "@/stores/registry"
import { iconOf } from "@/data/icons"

/** 左侧目标列表：所有模块 + 所有组合，统一编辑其弹窗布局 */
const targets = computed(() => [
  ...modules.value.map((m) => ({
    id: m.id,
    title: m.title,
    icon: m.icon,
    kind: m.status === "ready" ? "模块" : "模块 · 待开发",
  })),
  ...combos.value.map((c) => ({
    id: c.id,
    title: c.title,
    icon: c.icon,
    kind: c.enabled ? "组合" : "组合 · 已停用",
  })),
])

const selected = ref<string>(modules.value[0]?.id ?? "")

const owner = computed(() => getOwner(selected.value))

const visibleCount = computed(() => owner.value?.sections.filter((s) => s.visible).length ?? 0)
</script>

<template>
  <Panel
    title="弹窗布局"
    desc="集中管理所有弹窗页面的功能区块：控制显隐、重命名、切换左右栏与调整顺序。选中左侧对象即可编辑。"
  >
    <div class="grid gap-4 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
      <!-- 对象列表 -->
      <nav class="flex flex-col gap-1.5" aria-label="弹窗页面列表">
        <button
          v-for="t in targets"
          :key="t.id"
          type="button"
          class="flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-colors"
          :class="
            selected === t.id
              ? 'border-brand bg-brand/5'
              : 'border-border hover:bg-muted'
          "
          :aria-current="selected === t.id"
          @click="selected = t.id"
        >
          <component
            :is="iconOf(t.icon)"
            class="h-4 w-4 shrink-0"
            :class="selected === t.id ? 'text-brand' : 'text-muted-foreground'"
          />
          <span class="min-w-0">
            <span class="block truncate text-sm font-medium text-foreground">{{ t.title }}</span>
            <span class="block text-xs text-muted-foreground">{{ t.kind }}</span>
          </span>
        </button>
      </nav>

      <!-- 布局编辑 -->
      <div v-if="owner" class="neu-inset p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-sm font-bold text-foreground">{{ owner.title }} · 弹窗区块</h3>
          <span class="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
            {{ visibleCount }} / {{ owner.sections.length }} 个区块可见
          </span>
        </div>
        <div class="mt-4">
          <LayoutEditor :owner-id="selected" />
        </div>
      </div>
      <p v-else class="text-sm text-muted-foreground">请选择左侧的弹窗页面。</p>
    </div>
  </Panel>
</template>
