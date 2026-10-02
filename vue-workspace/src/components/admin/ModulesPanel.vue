<script setup lang="ts">
import { computed, reactive, ref } from "vue"
import { CircleMinus, CirclePlus, Plus, Settings2, Trash2, Wrench, X } from "lucide-vue-next"
import Panel from "@/components/admin/ui/Panel.vue"
import Field from "@/components/admin/ui/Field.vue"
import Toggle from "@/components/admin/ui/Toggle.vue"
import IconPicker from "@/components/admin/ui/IconPicker.vue"
import CoverPicker from "@/components/admin/ui/CoverPicker.vue"
import LayoutEditor from "@/components/admin/LayoutEditor.vue"
import ApiProxyEditor from "@/components/admin/ApiProxyEditor.vue"
import ProxyOverview from "@/components/admin/ProxyOverview.vue"
import WorkspacePreview from "@/components/admin/WorkspacePreview.vue"
import { createModule, deleteModule, modules, updateModule } from "@/stores/registry"
import { type ModuleConfig } from "@/data/registry-defaults"
import { iconOf } from "@/data/icons"

/* 新增模块表单 */
const draft = reactive({
  title: "",
  desc: "",
  windowDesc: "",
  icon: "Sparkles",
  image: "",
  submitLabel: "",
  ready: false,
  combinable: false,
})

const adding = ref(false)
/** 当前展开编辑的模块 id */
const openId = ref<string | null>(null)

const canSubmit = computed(() => !!draft.title.trim())
/** 当前正在配置的模块，配置面板显示在卡片区下方 */
const openMod = computed(() => modules.value.find((m) => m.id === openId.value) ?? null)

function submit() {
  if (!canSubmit.value) return
  const mod = createModule({
    title: draft.title,
    desc: draft.desc,
    windowDesc: draft.windowDesc,
    icon: draft.icon,
    image: draft.image,
    submitLabel: draft.submitLabel,
    status: draft.ready ? "ready" : "dev",
    combinable: draft.combinable,
  })
  Object.assign(draft, {
    title: "",
    desc: "",
    windowDesc: "",
    icon: "Sparkles",
    image: "",
    submitLabel: "",
    ready: false,
    combinable: false,
  })
  adding.value = false
  openId.value = mod.id
}

function patch(id: string, key: keyof ModuleConfig, value: unknown) {
  updateModule(id, { [key]: value } as Partial<ModuleConfig>)
}

function statusLabel(mod: ModuleConfig) {
  return mod.status === "ready" ? "已上线" : "待开发"
}

/** 在「已上线（工作台可用）」与「待开发（已撤下）」之间切换 */
function toggleWorkspace(mod: ModuleConfig) {
  updateModule(mod.id, { status: mod.status === "ready" ? "dev" : "ready" })
}

function remove(mod: ModuleConfig) {
  if (openId.value === mod.id) openId.value = null
  deleteModule(mod.id)
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- 工作台镜像：与前端同布局的缩小版，卡片右上角圆圈减号可把模块撤下 -->
    <Panel
      title="工作台预览"
      desc="这里是前端工作台的缩小版镜像。点击功能卡右上角的减号即可把该模块从工作台撤下（回落为「待开发」）；下方「功能模块」中的待开发卡片点击加号可重新添加回工作台。"
    >
      <WorkspacePreview />
    </Panel>

    <Panel
      title="功能模块"
      desc="工作台右栏的功能卡由此维护。新增模块默认为「待开发」，会以占位样式展示且不可拖入工作区；切换为「已上线」后即可正常使用。"
    >
      <!-- 功能卡网格：列数随窗口宽度自适应 -->
      <div class="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-3">
        <article
          v-for="mod in modules"
          :key="mod.id"
          class="flex flex-col overflow-hidden rounded-2xl border bg-background transition-colors"
          :class="openId === mod.id ? 'border-brand' : 'border-border hover:border-brand/50'"
        >
          <!-- 缩略封面：与工作台功能卡一致的深色样式 -->
          <div class="relative h-24 overflow-hidden bg-neutral-950 text-white">
            <img
              v-if="mod.image"
              :src="mod.image"
              :alt="mod.imageAlt"
              class="absolute inset-0 h-full w-full object-cover"
              :class="mod.status === 'ready' ? 'opacity-90' : 'opacity-30 grayscale'"
            />
            <div class="absolute inset-0 bg-gradient-to-r from-black/85 via-black/45 to-transparent" />
            <div class="relative flex h-full flex-col justify-end gap-1.5 p-3">
              <span class="flex h-7 w-7 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
                <component :is="iconOf(mod.icon)" class="h-3.5 w-3.5" />
              </span>
              <h3 class="truncate text-sm font-semibold leading-tight">{{ mod.title }}</h3>
            </div>
            <div class="absolute right-2 top-2 flex items-center gap-1.5">
              <span
                class="flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.65rem] font-medium"
                :class="
                  mod.status === 'ready'
                    ? 'bg-accent/90 text-neutral-950'
                    : 'border border-white/40 text-white/90'
                "
              >
                <Wrench v-if="mod.status === 'dev'" class="h-2.5 w-2.5" />
                {{ statusLabel(mod) }}
              </span>

              <!-- 待开发 → 加号添加回工作台；已上线 → 减号撤下 -->
              <button
                type="button"
                :aria-label="
                  mod.status === 'ready' ? `从工作台撤下${mod.title}` : `把${mod.title}添加到工作台`
                "
                class="flex h-6 w-6 items-center justify-center rounded-full bg-neutral-950/70 text-white ring-1 ring-white/25 backdrop-blur transition-colors"
                :class="mod.status === 'ready' ? 'hover:bg-destructive' : 'hover:bg-brand'"
                @click="toggleWorkspace(mod)"
              >
                <component :is="mod.status === 'ready' ? CircleMinus : CirclePlus" class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div class="flex flex-1 flex-col gap-2 p-3">
            <p class="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{{ mod.desc }}</p>
            <div class="mt-auto flex items-center gap-2">
              <span v-if="mod.builtin" class="text-[0.65rem] text-muted-foreground">内置</span>
              <span v-if="mod.combinable" class="text-[0.65rem] text-brand">可组合</span>
              <button
                type="button"
                class="ml-auto flex items-center gap-1 rounded-xl border border-border px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
                :aria-expanded="openId === mod.id"
                @click="openId = openId === mod.id ? null : mod.id"
              >
                <Settings2 class="h-3 w-3" />
                配置
              </button>
              <button
                v-if="!mod.builtin"
                type="button"
                :aria-label="`删除${mod.title}`"
                class="flex h-7 w-7 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                @click="remove(mod)"
              >
                <Trash2 class="h-3 w-3" />
              </button>
            </div>
          </div>
        </article>
      </div>

      <!-- 卡片区下方：添加功能卡 -->
      <div class="mt-3 rounded-2xl border border-dashed border-border bg-muted/30 p-4">
        <div v-if="!adding" class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-foreground">添加功能卡</p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              新增的功能卡会出现在工作台右栏，默认以「待开发」占位样式展示。
            </p>
          </div>
          <button
            type="button"
            class="btn btn-primary btn-sm"
            @click="adding = true"
          >
            <Plus class="h-3.5 w-3.5" />
            新增模块
          </button>
        </div>

        <!-- 新增模块表单 -->
        <div v-else class="flex flex-col gap-3">
          <div class="grid gap-3 md:grid-cols-2">
            <Field v-model="draft.title" label="模块名称" placeholder="例如：周报生成" />
            <Field v-model="draft.submitLabel" label="提交按钮文案" placeholder="默认为「开始生成」" />
          </div>
          <Field v-model="draft.desc" label="功能卡描述" type="textarea" :rows="2" placeholder="一句话说明该模块做什么" />
          <Field v-model="draft.windowDesc" label="弹窗副标题" placeholder="弹窗标题下方的说明文字" />

          <div class="grid gap-3 md:grid-cols-2">
            <IconPicker v-model="draft.icon" label="模块图标" />
            <CoverPicker v-model="draft.image" label="功能卡封面" />
          </div>

          <div class="grid gap-2 md:grid-cols-2">
            <Toggle v-model="draft.ready" label="立即上线" hint="关闭则保存为待开发状态" />
            <Toggle v-model="draft.combinable" label="允许参与组合" hint="上线后才能配置组合规则" />
          </div>

          <div class="flex justify-end gap-2">
            <button
              type="button"
              class="rounded-xl border border-border px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
              @click="adding = false"
            >
              取消
            </button>
            <button
              type="button"
              :disabled="!canSubmit"
              class="btn btn-primary btn-sm"
              @click="submit"
            >
              保存模块
            </button>
          </div>
        </div>
      </div>
    </Panel>

    <!-- 选中卡片的详细配置 -->
    <Panel v-if="openMod" :title="`配置：${openMod.title}`" desc="修改后即时生效并自动保存。">
      <template #action>
        <button
          type="button"
          class="flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
          @click="openId = null"
        >
          <X class="h-3.5 w-3.5" />
          收起
        </button>
      </template>

      <div class="flex flex-col gap-4">
        <div class="grid gap-3 md:grid-cols-2">
          <Field
            :model-value="openMod.title"
            label="模块名称"
            @update:model-value="patch(openMod!.id, 'title', $event)"
          />
          <Field
            :model-value="openMod.submitLabel"
            label="提交按钮文案"
            @update:model-value="patch(openMod!.id, 'submitLabel', $event)"
          />
        </div>
        <Field
          :model-value="openMod.desc"
          label="功能卡描述"
          type="textarea"
          :rows="2"
          @update:model-value="patch(openMod!.id, 'desc', $event)"
        />
        <Field
          :model-value="openMod.heroDesc"
          label="工作区主卡片描述"
          type="textarea"
          :rows="2"
          @update:model-value="patch(openMod!.id, 'heroDesc', $event)"
        />
        <Field
          :model-value="openMod.windowDesc"
          label="弹窗副标题"
          @update:model-value="patch(openMod!.id, 'windowDesc', $event)"
        />

        <div class="grid gap-3 md:grid-cols-2">
          <IconPicker
            :model-value="openMod.icon"
            label="模块图标"
            @update:model-value="patch(openMod!.id, 'icon', $event)"
          />
          <CoverPicker
            :model-value="openMod.image"
            label="功能卡封面"
            @update:model-value="patch(openMod!.id, 'image', $event)"
          />
        </div>

        <div class="grid gap-2 md:grid-cols-2">
          <Toggle
            :model-value="openMod.status === 'ready'"
            label="已上线"
            hint="关闭则在工作台显示为待开发占位卡"
            @update:model-value="patch(openMod!.id, 'status', $event ? 'ready' : 'dev')"
          />
          <Toggle
            :model-value="openMod.combinable"
            label="允许参与组合"
            hint="关闭后含该模块的组合规则会自动停用"
            @update:model-value="patch(openMod!.id, 'combinable', $event)"
          />
        </div>

        <div class="neu-inset p-4">
          <h3 class="text-sm font-bold text-card-foreground">弹窗页面布局</h3>
          <div class="mt-3">
            <LayoutEditor :owner-id="openMod.id" />
          </div>
        </div>

        <ApiProxyEditor :module-id="openMod.id" />
      </div>
    </Panel>

    <!-- 接口代理总览：汇总所有模块的代理规则并生成 proxy.config.json -->
    <Panel title="接口代理总览" desc="按路径把请求代理到不同后端。汇总各模块的代理规则并生成 Vite 的 proxy.config.json。">
      <ProxyOverview />
    </Panel>
  </div>
</template>
