<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import type { TenderCtx } from "@/components/apps/tender/state"

const props = defineProps<{ ctx: TenderCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label || '技术栈'">
    <template #action>
      <button
        class="rounded-xl border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
        :class="props.ctx.editingTechStack && 'bg-brand/10 border-brand text-brand'"
        @click="props.ctx.editingTechStack = !props.ctx.editingTechStack"
      >
        {{ props.ctx.editingTechStack ? "完成编辑" : "编辑技术栈" }}
      </button>
      <button
        class="rounded-xl border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
        @click="props.ctx.savePipelineConfig()"
      >
        {{ props.ctx.pipelineCfg.saving ? "保存中" : "保存配置" }}
      </button>
    </template>

    <!-- 状态消息 -->
    <div v-if="props.ctx.pipelineCfg.error" class="mb-2 text-xs text-red-500">
      {{ props.ctx.pipelineCfg.error }}
    </div>
    <div v-else-if="props.ctx.pipelineCfg.message" class="mb-2 text-xs text-brand">
      {{ props.ctx.pipelineCfg.message }}
    </div>

    <!-- 双栏布局 -->
    <div class="grid gap-3 sm:grid-cols-[150px_minmax(0,1fr)]">
      <!-- 左侧：技术栈列表 -->
      <div class="flex flex-col gap-2">
        <button
          v-for="stack in props.ctx.techStackList"
          :key="stack.id"
          class="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs transition-colors"
          :class="
            props.ctx.selectedTechStack?.id === stack.id
              ? 'border-brand bg-brand/10 text-brand'
              : 'border-border text-card-foreground hover:bg-muted'
          "
          @click="props.ctx.selectTechStack(stack.id)"
        >
          <span class="truncate">{{ stack.name }}</span>
          <span class="shrink-0 text-[10px] opacity-60">
            {{ stack.tier === "reference" ? "参考级" : "中标级" }}
          </span>
        </button>
      </div>

      <!-- 右侧：当前技术栈详情 -->
      <div v-if="props.ctx.selectedTechStack" class="flex flex-col gap-2">
        <!-- 编辑模式：新增/删除 -->
        <div v-if="props.ctx.editingTechStack" class="flex gap-2">
          <button
            class="rounded-lg border border-border px-3 py-1.5 text-xs hover:bg-muted"
            @click="props.ctx.addTechStack()"
          >
            新增大方案
          </button>
          <button
            class="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-500 hover:bg-red-500/10"
            @click="props.ctx.deleteTechStack()"
          >
            删除当前
          </button>
        </div>

        <!-- 名称 / tier（编辑模式） -->
        <template v-if="props.ctx.editingTechStack">
          <input
            :value="props.ctx.selectedTechStack.name"
            class="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm font-semibold text-foreground outline-none focus:border-brand"
            @input="(props.ctx.selectedTechStack as any).name = ($event.target as HTMLInputElement).value"
          />
          <select
            :value="props.ctx.selectedTechStack.tier"
            class="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs outline-none"
            @change="(props.ctx.selectedTechStack as any).tier = ($event.target as HTMLSelectElement).value"
          >
            <option value="winning">中标级方案</option>
            <option value="reference">参考级方案</option>
          </select>
          <textarea
            :value="props.ctx.selectedTechStack.summary"
            rows="2"
            class="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs outline-none resize-none focus:border-brand"
            @input="(props.ctx.selectedTechStack as any).summary = ($event.target as HTMLTextAreaElement).value"
          />
        </template>
        <template v-else>
          <div class="text-sm font-bold text-card-foreground">{{ props.ctx.selectedTechStack.name }}</div>
          <div v-if="props.ctx.selectedTechStack.summary" class="text-xs text-muted-foreground">
            {{ props.ctx.selectedTechStack.summary }}
          </div>
        </template>

        <!-- 技术栈 rows -->
        <div class="flex flex-col gap-1.5">
          <div
            v-for="(row, index) in props.ctx.selectedTechStack.rows"
            :key="`${row.key}-${index}`"
            class="flex items-stretch gap-2 rounded-lg border border-border bg-background px-3 py-2"
          >
            <template v-if="props.ctx.editingTechStack">
              <input
                :value="row.key"
                class="w-[80px] shrink-0 rounded border border-border bg-muted/30 px-2 py-1 text-xs outline-none focus:border-brand"
                @input="(row as any).key = ($event.target as HTMLInputElement).value"
              />
              <input
                :value="row.label"
                class="min-w-[100px] flex-1 rounded border border-border bg-muted/30 px-2 py-1 text-xs outline-none focus:border-brand"
                @input="(row as any).label = ($event.target as HTMLInputElement).value"
              />
              <input
                :value="row.value"
                class="min-w-[120px] flex-[2] rounded border border-border bg-muted/30 px-2 py-1 text-xs outline-none focus:border-brand"
                @input="(row as any).value = ($event.target as HTMLInputElement).value"
              />
              <button
                class="shrink-0 text-xs text-red-500 hover:underline"
                :disabled="props.ctx.selectedTechStack.rows.length <= 1"
                @click="props.ctx.deleteTechRow(index)"
              >
                ×
              </button>
            </template>
            <template v-else>
              <span class="shrink-0 text-xs font-medium text-muted-foreground min-w-[80px]">{{ row.label }}</span>
              <span class="text-xs text-card-foreground break-all">{{ row.value }}</span>
            </template>
          </div>
          <button
            v-if="props.ctx.editingTechStack"
            class="rounded-lg border border-dashed border-border px-3 py-2 text-xs text-muted-foreground hover:bg-muted/50"
            @click="props.ctx.addTechRow()"
          >
            + 新增配置项
          </button>
        </div>
      </div>
    </div>
  </SectionCard>
</template>
