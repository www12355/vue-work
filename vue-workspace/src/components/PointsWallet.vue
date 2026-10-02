<script setup lang="ts">
import { computed } from "vue"
import { Eye, EyeOff } from "lucide-vue-next"
import { currentUser } from "@/stores/auth"
import { balance, balanceUsd } from "@/stores/points"
import { MODELS, tokensPerDollar } from "@/data/pricing"

/* 卡片持有人：登录用户名，未登录为体验用户 */
const holder = computed(() => currentUser.value?.name ?? "体验用户")

/* 三张卡片对应三个常用计费模型，样式由 variant 决定叠放层级与配色 */
const VARIANTS = ["brand", "accent", "plain"] as const
const cards = computed(() =>
  MODELS.slice(0, 3).map((m, i) => ({
    id: m.id,
    name: m.name,
    variant: VARIANTS[i],
    tokens: tokensPerDollar(m).toLocaleString("en-US"),
    masked: `**** ${String(tokensPerDollar(m)).slice(-4)}`,
  })),
)

const fmtBalance = computed(() => balance.value.toFixed(2))
const fmtUsd = computed(() => `$${balanceUsd.value.toFixed(2)}`)
</script>

<template>
  <div class="wallet-wrap">
    <div class="wallet" role="group" aria-label="积分钱包，悬停查看余额与模型单价">
      <!-- 口袋后壁 -->
      <div class="wallet-back" aria-hidden="true" />

      <!-- 模型计费卡 -->
      <div v-for="c in cards" :key="c.id" class="card" :class="c.variant">
        <div class="card-inner">
          <div class="card-top">
            <span>{{ c.name }}</span>
            <span class="card-chip" aria-hidden="true" />
          </div>
          <div class="card-bottom">
            <div>
              <span class="label">持卡人</span>
              <span class="value">{{ holder }}</span>
            </div>
            <div class="num-wrap">
              <span class="masked">{{ c.masked }}</span>
              <span class="real">{{ c.tokens }}</span>
              <span class="unit">tokens / $1</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 口袋前片 -->
      <div class="pocket">
        <svg class="pocket-svg" viewBox="0 0 280 160" fill="none" aria-hidden="true">
          <path
            d="M 0 20 C 0 10, 5 10, 10 10 C 20 10, 25 25, 40 25 L 240 25 C 255 25, 260 10, 270 10 C 275 10, 280 10, 280 20 L 280 120 C 280 155, 260 160, 240 160 L 40 160 C 20 160, 0 155, 0 120 Z"
            fill="var(--pocket-bg)"
          />
          <path
            d="M 8 22 C 8 16, 12 16, 15 16 C 23 16, 27 29, 40 29 L 240 29 C 253 29, 257 16, 265 16 C 268 16, 272 16, 272 22 L 272 120 C 272 150, 255 152, 240 152 L 40 152 C 25 152, 8 152, 8 120 Z"
            stroke="var(--pocket-stitch)"
            stroke-width="1.5"
            stroke-dasharray="6 4"
          />
        </svg>

        <div class="pocket-content">
          <div class="balance-slot">
            <span class="balance-stars" aria-hidden="true">******</span>
            <span class="balance-real">{{ fmtBalance }}</span>
          </div>
          <span class="pocket-label">积分余额 · {{ fmtUsd }}</span>
          <span class="eye-wrap">
            <EyeOff class="eye eye-slash" aria-hidden="true" />
            <Eye class="eye eye-open" aria-hidden="true" />
          </span>
        </div>
      </div>
    </div>

    <p class="wallet-hint">悬停查看余额与模型单价</p>

    <!-- 屏幕阅读器可直接获取数值，无需依赖悬停 -->
    <p class="sr-only">当前积分余额 {{ fmtBalance }} 积分，约合 {{ fmtUsd }}。</p>
  </div>
</template>

<style scoped>
.wallet-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  /* 悬停时最上层卡片会上移约 75px，预留净空避免溢出容器并遮挡标题 */
  padding-top: 80px;
}

/* 口袋主体：宽度自适应右栏，最大 280px */
.wallet {
  position: relative;
  width: 100%;
  max-width: 280px;
  height: 260px;
  cursor: pointer;
  perspective: 1000px;
  transition: transform 0.4s ease;
  /* 口袋配色：与首页深色主卡同色系的中性深灰 + 虚线缝合线 */
  --pocket-bg: oklch(0.18 0 0);
  --pocket-stitch: oklch(0.38 0 0);
}

.wallet-back {
  position: absolute;
  bottom: 0;
  width: 100%;
  height: 200px;
  background: var(--pocket-bg);
  border-radius: 22px 22px 60px 60px;
  z-index: 5;
  box-shadow:
    inset 0 25px 35px oklch(0 0 0 / 40%),
    inset 0 5px 15px oklch(0 0 0 / 50%);
}

/* 卡片 */
.card {
  position: absolute;
  left: 10px;
  width: calc(100% - 20px);
  height: 140px;
  border-radius: 16px;
  padding: 18px;
  box-shadow:
    inset 0 1px 1px oklch(1 0 0 / 30%),
    0 -4px 15px oklch(0 0 0 / 10%);
  transition: transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
  animation: slideIntoPocket 0.8s cubic-bezier(0.2, 0.8, 0.2, 1) backwards;
}

@keyframes slideIntoPocket {
  0% {
    transform: translateY(-100px);
    opacity: 0;
  }
  100% {
    transform: translateY(0);
    opacity: 1;
  }
}

.card-inner {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 100%;
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.card-chip {
  width: 32px;
  height: 24px;
  border-radius: 4px;
  background: oklch(1 0 0 / 20%);
  border: 1px solid oklch(1 0 0 / 10%);
}

.card-bottom {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 8px;
}

.label {
  display: block;
  font-size: 8px;
  opacity: 0.7;
  margin-bottom: 2px;
}

.value {
  font-size: 11px;
  font-weight: 500;
}

.num-wrap {
  text-align: right;
  min-width: 0;
}

.masked {
  font-size: 15px;
  letter-spacing: 2px;
}

.real,
.unit {
  display: none;
}

.real {
  font-size: 14px;
  font-weight: 600;
  font-family: var(--font-mono, monospace);
}

.unit {
  font-size: 8px;
  opacity: 0.75;
}

/* 卡片配色：品牌紫 / 青色强调 / 浅色卡面，共三色 + 中性口袋 */
.brand {
  background: var(--brand);
  color: var(--brand-foreground);
  bottom: 115px;
  z-index: 10;
  animation-delay: 0.1s;
}

.accent {
  background: var(--accent);
  color: oklch(0.2 0.02 200);
  bottom: 78px;
  z-index: 20;
  animation-delay: 0.2s;
}

.plain {
  background: var(--card);
  color: var(--card-foreground);
  bottom: 40px;
  z-index: 30;
  animation-delay: 0.3s;
}

.plain .card-chip,
.accent .card-chip {
  background: oklch(0 0 0 / 6%);
  border-color: oklch(0 0 0 / 8%);
}

/* 口袋前片 */
.pocket {
  position: absolute;
  bottom: 0;
  width: 100%;
  height: 160px;
  z-index: 40;
  filter: drop-shadow(0 15px 25px oklch(0.2 0.02 275 / 40%));
}

.pocket-svg {
  width: 100%;
  height: 100%;
}

.pocket-content {
  position: absolute;
  top: 45px;
  width: 100%;
  z-index: 50;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.balance-slot {
  position: relative;
  height: 26px;
  width: 100%;
  display: flex;
  justify-content: center;
}

.balance-stars {
  color: oklch(0.7 0 0);
  font-size: 24px;
  letter-spacing: 4px;
  transition: opacity 0.3s ease;
}

.balance-real {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translate(-50%, 10px);
  opacity: 0;
  color: oklch(0.97 0 0);
  font-size: 22px;
  font-weight: 700;
  transition:
    opacity 0.3s ease,
    transform 0.3s ease;
}

.pocket-label {
  color: oklch(0.68 0 0);
  font-size: 12px;
  font-weight: 500;
}

.eye-wrap {
  position: relative;
  margin-top: 4px;
  height: 20px;
  width: 20px;
  opacity: 0.35;
  transition: opacity 0.3s ease;
}

.eye {
  position: absolute;
  inset: 0;
  height: 20px;
  width: 20px;
  color: oklch(0.78 0 0);
  transition:
    opacity 0.3s ease,
    transform 0.3s ease;
}

.eye-open {
  opacity: 0;
}

.wallet-hint {
  margin-top: 12px;
  font-size: 12px;
  font-weight: 600;
  font-style: italic;
  color: var(--muted-foreground);
  text-decoration: underline;
}

/* ---------- 悬停：卡片抽出、余额显形 ---------- */
.wallet:hover {
  transform: translateY(-5px);
}
.wallet:hover .brand {
  transform: translateY(-75px) rotate(-3deg);
}
.wallet:hover .accent {
  transform: translateY(-45px) rotate(2deg);
}
.wallet:hover .plain {
  transform: translateY(-10px);
}

/* 单卡再悬停：置顶放平并展示完整单价 */
.card:hover {
  z-index: 100 !important;
}
.wallet:hover .brand:hover,
.wallet:hover .plain:hover {
  transform: translateY(-60px) scale(1.05) rotate(0);
}
.wallet:hover .accent:hover {
  transform: translateY(-70px) scale(1.05) rotate(0);
}
.card:hover .masked {
  display: none;
}
.card:hover .real,
.card:hover .unit {
  display: block;
}

.wallet:hover .balance-stars {
  opacity: 0;
}
.wallet:hover .balance-real {
  opacity: 1;
  transform: translate(-50%, 0);
}
.wallet:hover .eye-wrap {
  opacity: 1;
}
.wallet:hover .eye-slash {
  opacity: 0;
  transform: scale(0.5);
}
.wallet:hover .eye-open {
  opacity: 1;
  transform: scale(1.1);
}

@media (prefers-reduced-motion: reduce) {
  .wallet,
  .card,
  .balance-stars,
  .balance-real,
  .eye,
  .eye-wrap {
    transition: none;
  }
  .card {
    animation: none;
  }
}
</style>
