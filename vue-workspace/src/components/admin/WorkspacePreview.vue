<script setup lang="ts">
import { computed } from "vue"
import { CircleMinus, Play, Plus } from "lucide-vue-next"
import { modules, updateModule } from "@/stores/registry"
import type { ModuleConfig } from "@/data/registry-defaults"
import { iconOf } from "@/data/icons"

/*
 * 与前端右栏一致的槽位：已上线 → 功能卡；已撤下 → 原位虚框。
 * 撤下不会减少槽位数量，位置保持不变。
 */
const slots = computed(() => modules.value.map((m) => ({ mod: m, ready: m.status === "ready" })))

/** 圆圈减号：从前端撤下该模块，原位变为虚框 */
function removeFromWorkspace(mod: ModuleConfig) {
  updateModule(mod.id, { status: "dev" })
}

/** 虚框中的加号：把模块重新添加回工作台 */
function addToWorkspace(mod: ModuleConfig) {
  updateModule(mod.id, { status: "ready" })
}
</script>

<template>
  <!--
    工作台等比镜像：容器宽度即缩放基准（1em = 1% 容器宽度），
    所有尺寸与字号都用 em 表达，窗口变化时整体等比放大/缩小。
  -->
  <div class="preview">
    <!-- 左侧：主卡片 / 放置区 -->
    <div class="col-main">
      <div class="hero">
        <div class="hero-drop">
          <p>将右侧功能卡拖动到此处</p>
        </div>
      </div>

      <div class="hero-foot">
        <div>
          <p class="eyebrow">打造最佳项目</p>
          <h3 class="headline">
            智能办公<span class="badge">创造力</span>
            <br />
            功能工作台
          </h3>
        </div>
        <dl class="stats">
          <div>
            <dt class="sr-only">任务完成率</dt>
            <dd class="stat-num">99%</dd>
            <p class="stat-label">任务完成率</p>
          </div>
          <div>
            <dt class="sr-only">已生成文档</dt>
            <dd class="stat-num">150+</dd>
            <p class="stat-label">已生成文档</p>
          </div>
        </dl>
      </div>
    </div>

    <!-- 右栏：功能卡槽位，减号撤下 / 加号添加回 -->
    <div class="col-side">
      <template v-for="slot in slots" :key="slot.mod.id">
        <!-- 已上线：功能卡 -->
        <article v-if="slot.ready" class="card">
          <img v-if="slot.mod.image" :src="slot.mod.image" :alt="slot.mod.imageAlt" class="card-bg" />
          <div class="card-scrim" />

          <div class="card-body">
            <span class="card-icon">
              <component :is="iconOf(slot.mod.icon)" class="ico" />
            </span>
            <h4 class="card-title">{{ slot.mod.title }}</h4>
            <p class="card-desc">{{ slot.mod.desc }}</p>
          </div>

          <!-- 前端功能卡右下角的播放键，仅作示意 -->
          <span aria-hidden="true" class="card-play"><Play class="ico" /></span>

          <button
            type="button"
            :aria-label="`从工作台撤下${slot.mod.title}，改为待开发`"
            class="btn-minus"
            @click="removeFromWorkspace(slot.mod)"
          >
            <CircleMinus class="ico" />
          </button>
        </article>

        <!-- 已撤下：原位虚框，加号可添加回（圆形加号，与设计稿一致） -->
        <button
          v-else
          type="button"
          :aria-label="`把${slot.mod.title}添加回工作台`"
          class="slot-empty"
          @click="addToWorkspace(slot.mod)"
        >
          <span class="slot-mark"><Plus class="ico" /></span>
          <span class="slot-label">待开发</span>
        </button>
      </template>

      <!-- 前端末尾的「待开发」入口（纯展示，圆形加号） -->
      <div class="slot-empty slot-static">
        <span class="slot-mark"><Plus class="ico" /></span>
        <p class="slot-label">待开发</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/*
 * 缩放基准：容器宽度的 1% 作为 1em，参考前端满宽 1230px 换算各尺寸。
 * 极窄窗口下用 max() 兜底，避免文字小到不可读。
 */
.preview {
  container-type: inline-size;
  /* 0.62 = 缩小版比例；乘在基准上，各处尺寸随窗口等比缩放 */
  font-size: max(0.62cqw, 3px);
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 1.63em;
  align-items: stretch;
}

@container (max-width: 520px) {
  .preview {
    grid-template-columns: 1fr;
  }
}

.col-main,
.col-side {
  display: flex;
  flex-direction: column;
  gap: 1.63em;
  min-width: 0;
}

/* 左侧放置区 */
.hero {
  display: flex;
  flex: 1;
  border-radius: 2.6em;
  background: var(--color-neutral-950, #0a0a0a);
  padding: 1.63em;
}

.hero-drop {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  border: 0.08em dashed rgb(255 255 255 / 0.25);
  border-radius: 2em;
  text-align: center;
}

.hero-drop p {
  color: rgb(255 255 255 / 0.45);
  font-size: 1.14em;
}

.hero-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1.63em;
  padding-inline: 0.4em;
}

.eyebrow {
  color: var(--muted-foreground);
  font-size: 1.14em;
}

.headline {
  margin-top: 0.15em;
  color: var(--foreground);
  font-size: 3.1em;
  font-weight: 900;
  line-height: 1.05;
  letter-spacing: -0.02em;
}

.badge {
  margin-left: 0.3em;
  border: 0.05em solid color-mix(in oklab, var(--brand) 40%, transparent);
  border-radius: 999px;
  padding: 0.1em 0.4em;
  color: var(--brand);
  font-size: 0.42em;
  font-weight: 700;
  vertical-align: middle;
}

.stats {
  display: flex;
  gap: 2.4em;
}

.stat-num {
  color: var(--foreground);
  font-size: 3.1em;
  font-weight: 900;
  line-height: 1;
}

.stat-label {
  margin-top: 0.2em;
  color: var(--muted-foreground);
  font-size: 1.05em;
}

/* 右栏功能卡：190/1230 ≈ 15.45em 高，圆角 1.75rem */
.card {
  position: relative;
  height: 15.45em;
  overflow: hidden;
  border-radius: 2.28em;
  background: var(--color-neutral-950, #0a0a0a);
  color: #fff;
}

.card-bg {
  position: absolute;
  inset: 0;
  height: 100%;
  width: 100%;
  object-fit: cover;
  opacity: 0.9;
}

.card-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(to right, rgb(0 0 0 / 0.85), rgb(0 0 0 / 0.45), transparent);
}

.card-body {
  position: relative;
  display: flex;
  height: 100%;
  flex-direction: column;
  justify-content: flex-end;
  gap: 0.65em;
  padding: 1.63em;
  padding-right: 5.5em;
}

.card-icon {
  display: flex;
  height: 3.25em;
  width: 3.25em;
  align-items: center;
  justify-content: center;
  border-radius: 0.98em;
  background: rgb(255 255 255 / 0.15);
  backdrop-filter: blur(4px);
}

.card-icon .ico {
  height: 1.63em;
  width: 1.63em;
}

.card-title {
  font-size: 1.95em;
  font-weight: 600;
  line-height: 1.15;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  color: rgb(255 255 255 / 0.65);
  font-size: 0.98em;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

/* 右下角播放键（示意），对应前端 52px 按钮 */
.card-play {
  position: absolute;
  right: 0.9em;
  bottom: 0.9em;
  display: flex;
  height: 4.23em;
  width: 4.23em;
  align-items: center;
  justify-content: center;
  border-radius: 1.3em;
  background: var(--color-neutral-900, #171717);
  color: rgb(255 255 255 / 0.75);
  box-shadow: inset 0 0 0 0.08em rgb(255 255 255 / 0.15);
}

.card-play .ico {
  height: 1.3em;
  width: 1.3em;
  fill: currentColor;
}

.btn-minus {
  position: absolute;
  right: 1.1em;
  top: 1.1em;
  display: flex;
  height: 2.6em;
  width: 2.6em;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgb(10 10 10 / 0.7);
  color: rgb(255 255 255 / 0.85);
  box-shadow: inset 0 0 0 0.08em rgb(255 255 255 / 0.2);
  backdrop-filter: blur(4px);
  transition: background-color 0.2s;
}

.btn-minus:hover {
  background: var(--destructive);
  color: #fff;
}

.btn-minus .ico {
  height: 1.6em;
  width: 1.6em;
}

/* 空槽虚框：与功能卡等高，保持位置不变 */
.slot-empty {
  display: flex;
  height: 15.45em;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5em;
  border: 0.16em dashed color-mix(in oklab, var(--foreground) 20%, transparent);
  border-radius: 2.28em;
  padding-inline: 1.2em;
  text-align: center;
  transition:
    border-color 0.2s,
    background-color 0.2s;
}

.slot-empty:not(.slot-static):hover {
  border-color: color-mix(in oklab, var(--brand) 60%, transparent);
  background: color-mix(in oklab, var(--brand) 5%, transparent);
}

.slot-mark {
  display: flex;
  height: 3.9em;
  width: 3.9em;
  align-items: center;
  justify-content: center;
  /* 圆形，与设计截图一致 */
  border-radius: 50%;
  border: 0.16em dashed color-mix(in oklab, var(--foreground) 28%, transparent);
  color: color-mix(in oklab, var(--foreground) 38%, transparent);
}

.slot-mark .ico {
  height: 1.95em;
  width: 1.95em;
}

.slot-label {
  color: var(--foreground);
  font-size: 1.14em;
  font-weight: 500;
}

.slot-hint {
  color: var(--muted-foreground);
  font-size: 0.98em;
}
</style>
