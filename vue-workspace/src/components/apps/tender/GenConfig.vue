<script setup lang="ts">
import { History, Shuffle } from "lucide-vue-next"
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import { goToHistory } from "@/stores/view"
import type { TenderCtx } from "@/components/apps/tender/state"

const props = defineProps<{ ctx: TenderCtx; label: string }>()

const field = "w-full box-border rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none ring-ring/50 focus:ring-2 focus:border-brand"
</script>

<template>
  <SectionCard :title="label || '生成配置'">
    <template #action>
      <button
        class="flex items-center gap-1 text-xs text-brand underline underline-offset-4"
        @click="goToHistory('tender')"
      >
        <History class="h-3.5 w-3.5" />
        历史记录
      </button>
    </template>

    <div class="flex flex-col gap-3">
      <!-- 多方案 tabs -->
      <div v-if="props.ctx.proposalTabs.length > 1" class="flex gap-1.5 overflow-x-auto pb-1">
        <button
          v-for="tab in props.ctx.proposalTabs"
          :key="tab.slot"
          class="shrink-0 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors"
          :class="
            props.ctx.selectedProposalSlot === tab.slot
              ? 'border-brand bg-brand/10 text-brand'
              : 'border-border text-muted-foreground hover:bg-muted'
          "
          @click="props.ctx.selectProposal(tab.slot)"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- 第一行：参考方案数量 + 方案名称 + 工期 -->
      <div class="grid gap-3 sm:grid-cols-[auto_minmax(0,1fr)_auto]">
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          参考方案数量
          <select
            :value="props.ctx.referenceCount"
            :class="field"
            @change="props.ctx.setReferenceCount(Number(($event.target as HTMLSelectElement).value))"
          >
            <option v-for="n in 11" :key="n - 1" :value="n - 1">{{ n - 1 }} 份</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          方案名称
          <input
            v-if="props.ctx.activeProposal"
            v-model="props.ctx.activeProposal.name"
            :class="field"
            maxlength="40"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          工期天数
          <input
            v-if="props.ctx.activeProposal"
            v-model.number="props.ctx.activeProposal.delivery_days"
            type="number"
            min="1"
            max="2000"
            :class="[field, 'w-24']"
          />
        </label>
      </div>

      <!-- 第二行：当前技术栈 + 当前团队模板 -->
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          当前技术栈
          <select
            v-if="props.ctx.activeProposal"
            :value="props.ctx.activeProposal.tech_stack_id"
            :class="field"
            @change="props.ctx.selectTechStack(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="stack in props.ctx.techStackList" :key="stack.id" :value="stack.id">
              {{ stack.name }}（{{ stack.tier === "reference" ? "参考级" : "中标级" }}）
            </option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          当前团队模板
          <select
            v-if="props.ctx.activeProposal"
            :value="props.ctx.activeProposal.team_profile_id"
            :class="field"
            @change="props.ctx.selectTeamProfile(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="team in props.ctx.teamProfileList" :key="team.id" :value="team.id">
              {{ team.name }}（{{ team.total ?? 0 }} 人）
            </option>
          </select>
        </label>
      </div>

      <!-- 第三行：目标标包 + 会话 ID -->
      <div class="grid gap-3 sm:grid-cols-[minmax(0,0.7fr)_minmax(0,1fr)]">
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          目标标包
          <input
            v-model="props.ctx.s.targetPackage"
            placeholder="输入标包编号"
            :class="field"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          会话 ID
          <span class="flex gap-2">
            <input v-model="props.ctx.s.sessionId" :class="[field, 'min-w-0 flex-1']" />
            <button
              class="flex shrink-0 items-center gap-1 rounded-xl border border-border px-3 py-2 text-xs font-medium text-foreground hover:bg-muted"
              @click="props.ctx.newSession()"
            >
              <Shuffle class="h-3.5 w-3.5" />
              随机
            </button>
          </span>
        </label>
      </div>
    </div>
  </SectionCard>
</template>
