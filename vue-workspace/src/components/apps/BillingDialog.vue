<script setup lang="ts">
import { Coins, Layers, Sparkles, Wallet, X } from "lucide-vue-next"
import type { BillingCtl } from "@/composables/useBilling"

const props = defineProps<{ ctl: BillingCtl }>()

/** 积分保留 2 位，末尾去零 */
function fmt(n: number): string {
  return Number(n.toFixed(2)).toString()
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.ctl.open"
      class="fixed inset-0 z-[110] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="生成计费说明"
    >
      <button
        aria-label="取消"
        class="ws-fade-in absolute inset-0 cursor-default bg-neutral-950/55 backdrop-blur-sm"
        @click="props.ctl.cancel()"
      />

      <!-- iOS 风格实心卡片 -->
      <div class="ws-zoom-in ios-card relative flex w-full max-w-md flex-col overflow-hidden">
        <!-- 头部 -->
        <div class="flex items-start justify-between gap-3 px-6 pt-6">
          <div class="flex items-center gap-3">
            <span class="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand/12 text-brand">
              <Coins class="h-5 w-5" />
            </span>
            <div>
              <h2 class="text-lg font-bold text-card-foreground">生成计费说明</h2>
              <p class="text-xs text-muted-foreground">确认后将从积分账户扣除</p>
            </div>
          </div>
          <button
            aria-label="关闭"
            class="flex h-9 w-9 items-center justify-center rounded-xl bg-muted text-foreground transition-colors hover:bg-border"
            @click="props.ctl.cancel()"
          >
            <X class="h-4.5 w-4.5" />
          </button>
        </div>

        <div class="flex flex-col gap-4 p-6">
          <!-- 计费模型选择 -->
          <label class="flex flex-col gap-1.5">
            <span class="text-xs font-medium text-muted-foreground">计费模型</span>
            <select
              v-model="props.ctl.modelId"
              class="field h-11 font-medium"
            >
              <option v-for="m in props.ctl.models" :key="m.id" :value="m.id">
                {{ m.name }} · {{ m.note }}
              </option>
            </select>
            <span class="text-[11px] text-muted-foreground">
              当前模型 $1 ≈ {{ props.ctl.tokensPerDollar.toLocaleString() }} tokens，1 积分 = 1 美金
            </span>
          </label>

          <!-- 计费明细 -->
          <div class="overflow-hidden rounded-2xl border border-border">
            <div
              class="flex items-center gap-2 border-b border-border bg-muted px-4 py-2.5 text-xs font-semibold text-muted-foreground"
            >
              <Layers v-if="props.ctl.isCombo" class="h-3.5 w-3.5" />
              <Sparkles v-else class="h-3.5 w-3.5" />
              {{ props.ctl.isCombo ? "组合生成 · 含各文档" : props.ctl.title }}
            </div>
            <ul class="divide-y divide-border">
              <li
                v-for="line in props.ctl.lines"
                :key="line.name"
                class="flex items-center justify-between px-4 py-2.5 text-sm"
              >
                <span class="text-card-foreground">{{ line.name }}</span>
                <span class="text-right">
                  <span class="text-muted-foreground">{{ line.tokens.toLocaleString() }} tokens</span>
                  <span class="ml-3 font-semibold text-card-foreground">{{ fmt(line.cost) }} 积分</span>
                </span>
              </li>
            </ul>

            <!-- 组合折扣 -->
            <div
              v-if="props.ctl.isCombo"
              class="flex items-center justify-between border-t border-border bg-brand/5 px-4 py-2.5 text-xs"
            >
              <span class="text-muted-foreground">小计 {{ fmt(props.ctl.subtotal) }} 积分</span>
              <span class="font-semibold text-brand">
                组合优惠 {{ Math.round((1 - props.ctl.comboDiscount) * 100) }}% off
              </span>
            </div>
          </div>

          <!-- 合计 -->
          <div class="flex items-end justify-between rounded-2xl bg-brand/8 px-4 py-3">
            <div>
              <p class="text-xs text-muted-foreground">本次消耗（约 {{ props.ctl.totalTokens.toLocaleString() }} tokens）</p>
              <p class="text-2xl font-bold text-brand">{{ fmt(props.ctl.cost) }} <span class="text-sm font-medium">积分</span></p>
            </div>
            <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Wallet class="h-3.5 w-3.5" />
              余额 {{ fmt(props.ctl.balance) }}
            </div>
          </div>

          <!-- 余额不足 / 错误提示 -->
          <p
            v-if="!props.ctl.enough || props.ctl.error"
            class="rounded-xl bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive"
          >
            {{ props.ctl.error || "积分余额不足，请前往个人中心充值后再生成" }}
          </p>

          <!-- 操作 -->
          <div class="flex gap-3">
            <button
              class="h-11 flex-1 rounded-xl bg-muted text-sm font-semibold text-foreground transition-colors hover:bg-border"
              @click="props.ctl.cancel()"
            >
              取消
            </button>
            <button
              :disabled="!props.ctl.enough"
              class="btn btn-primary flex-[1.4]"
              @click="props.ctl.confirm()"
            >
              <Sparkles class="h-4 w-4" />
              确认并生成
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
