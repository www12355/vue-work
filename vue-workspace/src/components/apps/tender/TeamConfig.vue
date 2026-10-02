<script setup lang="ts">
import SectionCard from "@/components/apps/ui/SectionCard.vue"
import { SIZE_OPTIONS, FOCUS_OPTIONS, type TenderCtx } from "@/components/apps/tender/state"

const props = defineProps<{ ctx: TenderCtx; label: string }>()
</script>

<template>
  <SectionCard :title="label || '团队配置'">
    <template #action>
      <span
        class="rounded-xl px-3 py-1.5 text-xs font-bold"
        :class="
          props.ctx.selectedTeamTotal >= 1 && props.ctx.selectedTeamTotal <= 20
            ? 'bg-emerald-500/10 text-emerald-500'
            : 'bg-red-500/10 text-red-500'
        "
      >
        {{ props.ctx.selectedTeamTotal }} 人
      </span>
      <button
        class="rounded-xl border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
        :class="props.ctx.editingTeam && 'bg-brand/10 border-brand text-brand'"
        @click="props.ctx.editingTeam = !props.ctx.editingTeam"
      >
        {{ props.ctx.editingTeam ? "完成编辑" : "编辑团队" }}
      </button>
      <button
        v-if="props.ctx.editingTeam"
        class="rounded-xl border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
        @click="props.ctx.addTeamProfile()"
      >
        新增团队
      </button>
      <button
        v-if="props.ctx.editingTeam"
        class="rounded-xl border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-500 hover:bg-red-500/10"
        @click="props.ctx.deleteTeamProfile()"
      >
        删除当前
      </button>
    </template>

    <!-- 编辑模式：团队 meta -->
    <div v-if="props.ctx.editingTeam && props.ctx.selectedTeamProfile" class="mb-3 grid gap-2 sm:grid-cols-[minmax(160px,0.7fr)_minmax(0,1.3fr)]">
      <input
        :value="props.ctx.selectedTeamProfile.name"
        class="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-brand"
        @input="(props.ctx.selectedTeamProfile as any).name = ($event.target as HTMLInputElement).value"
      />
      <textarea
        :value="props.ctx.selectedTeamProfile.summary"
        rows="2"
        class="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs outline-none resize-none focus:border-brand"
        @input="(props.ctx.selectedTeamProfile as any).summary = ($event.target as HTMLTextAreaElement).value"
      />
    </div>

    <!-- 团队名称（非编辑） -->
    <div v-if="!props.ctx.editingTeam && props.ctx.selectedTeamProfile" class="mb-2">
      <p class="text-sm font-semibold text-card-foreground">{{ props.ctx.selectedTeamProfile.name }}</p>
      <p class="text-xs text-muted-foreground">{{ props.ctx.selectedTeamProfile.summary }}</p>
    </div>

    <!-- 规模选择 -->
    <p class="mb-1.5 text-[11px] font-medium text-muted-foreground">团队规模</p>
    <div class="mb-3 grid grid-cols-3 gap-2">
      <button
        v-for="size in SIZE_OPTIONS"
        :key="size.id"
        class="flex flex-col items-center gap-0.5 rounded-xl border py-2.5 transition-colors"
        :class="
          props.ctx.selectedSize === size.id
            ? 'border-brand bg-brand/10 text-brand'
            : 'border-border text-foreground hover:bg-muted'
        "
        @click="props.ctx.selectSize(size.id)"
      >
        <span class="text-sm font-semibold">{{ size.label }}</span>
        <span class="text-xs opacity-70">{{ size.hint }}</span>
      </button>
    </div>

    <!-- 专业方向 -->
    <p class="mb-1.5 text-[11px] font-medium text-muted-foreground">专业方向</p>
    <div class="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
      <button
        v-for="f in FOCUS_OPTIONS"
        :key="f.id"
        class="flex flex-col items-center gap-0.5 rounded-xl border py-2.5 transition-colors"
        :class="
          props.ctx.selectedFocus === f.id
            ? 'border-brand bg-brand/10 text-brand'
            : 'border-border text-foreground hover:bg-muted'
        "
        @click="props.ctx.selectFocus(f.id)"
      >
        <span class="text-sm font-semibold">{{ f.label }}</span>
        <span class="text-xs opacity-70">{{ f.sub }}</span>
      </button>
    </div>

    <!-- 角色列表 -->
    <div class="flex flex-col gap-2">
      <div
        v-for="(role, index) in props.ctx.selectedTeamRoles"
        :key="`${role.role}-${index}`"
        class="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2"
      >
        <template v-if="props.ctx.editingTeam">
          <input
            :value="role.role"
            class="min-w-[80px] flex-1 rounded border border-border bg-muted/30 px-2 py-1 text-xs outline-none focus:border-brand"
            @input="(role as any).role = ($event.target as HTMLInputElement).value"
          />
          <input
            :value="role.count"
            type="number"
            min="0"
            max="20"
            class="w-[60px] rounded border border-border bg-muted/30 px-2 py-1 text-xs outline-none focus:border-brand"
            @input="(role as any).count = Number(($event.target as HTMLInputElement).value)"
          />
          <input
            :value="role.focus"
            class="min-w-[100px] flex-[1.5] rounded border border-border bg-muted/30 px-2 py-1 text-xs outline-none focus:border-brand"
            @input="(role as any).focus = ($event.target as HTMLInputElement).value"
          />
          <button
            class="shrink-0 text-xs text-red-500 hover:underline"
            :disabled="props.ctx.selectedTeamRoles.length <= 1"
            @click="props.ctx.deleteTeamRole(index)"
          >
            ×
          </button>
        </template>
        <template v-else>
          <span class="min-w-[80px] flex-1 text-xs font-semibold text-card-foreground">{{ role.role }}</span>
          <span class="w-[60px] text-xs text-brand font-medium">{{ role.count }} 人</span>
          <span class="min-w-0 flex-[1.5] text-xs text-muted-foreground truncate">{{ role.focus }}</span>
        </template>
      </div>

      <button
        v-if="props.ctx.editingTeam"
        class="rounded-lg border border-dashed border-border px-3 py-2 text-xs text-muted-foreground hover:bg-muted/50"
        @click="props.ctx.addTeamRole()"
      >
        + 新增角色
      </button>
    </div>
  </SectionCard>
</template>
