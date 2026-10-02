<script setup lang="ts">
import { ref } from "vue"
import { ArrowLeft, Eye, EyeOff, Loader2, Lock, ShieldCheck, User } from "lucide-vue-next"
import { login } from "@/stores/auth"
import { goTo } from "@/stores/view"

const username = ref("")
const password = ref("")
const showPwd = ref(false)
const error = ref("")
const loading = ref(false)

function submit() {
  if (loading.value) return
  error.value = ""
  loading.value = true
  /* 原型：本地校验；模拟一点延迟让交互更自然 */
  window.setTimeout(() => {
    const res = login(username.value, password.value)
    loading.value = false
    if (res.ok) {
      goTo("admin")
    } else {
      error.value = res.error ?? "登录失败"
    }
  }, 320)
}

/* 登录页左侧的能力亮点，纯展示 */
const highlights = [
  "投标文件、会议纪要、合同一键智能生成",
  "模块自由拖拽组合，沉淀专属工作流",
  "全流程可视化配置，管理后台集中维护",
]
</script>

<template>
  <div class="flex min-h-[calc(100vh-8rem)] items-center justify-center py-4">
    <div class="ios-card grid w-full max-w-5xl overflow-hidden lg:grid-cols-2">
      <!-- 左侧：品牌配图 + 文案（移动端隐藏） -->
      <aside class="relative hidden lg:block">
        <img
          src="/images/login-hero.png"
          alt="AICC 智能内容平台"
          class="absolute inset-0 h-full w-full object-cover"
        />
        <!-- 深色遮罩保证文字可读 -->
        <div class="absolute inset-0 bg-gradient-to-t from-neutral-950/85 via-neutral-950/35 to-neutral-950/20" />
        <div class="relative flex h-full flex-col justify-between p-10">
          <!-- 品牌标识 -->
          <div class="flex items-center gap-3">
            <div class="relative flex h-11 w-11 items-center justify-center rounded-2xl border-[3px] border-white">
              <span
                class="absolute -bottom-1.5 left-3 h-3 w-3 rotate-45 border-b-[3px] border-l-[3px] border-white bg-transparent"
              />
              <span class="text-lg font-extrabold italic text-white">X</span>
            </div>
            <span class="text-xl font-extrabold tracking-tight text-white">AICC</span>
          </div>

          <div>
            <h2 class="text-3xl font-bold leading-tight text-balance text-white">
              智能内容协作平台
            </h2>
            <p class="mt-3 max-w-sm text-sm leading-relaxed text-white/75">
              登录后进入管理后台，集中维护功能模块、组合规则与页面布局。
            </p>
            <ul class="mt-6 flex flex-col gap-3">
              <li v-for="item in highlights" :key="item" class="flex items-center gap-2.5 text-sm text-white/90">
                <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand">
                  <ShieldCheck class="h-3 w-3 text-brand-foreground" />
                </span>
                {{ item }}
              </li>
            </ul>
          </div>
        </div>
      </aside>

      <!-- 右侧：登录卡 -->
      <div class="flex flex-col justify-center p-8 sm:p-12">
        <!-- 返回 -->
        <button
          type="button"
          class="mb-8 flex items-center gap-1.5 self-start text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          @click="goTo('workspace')"
        >
          <ArrowLeft class="h-4 w-4" />
          返回工作台
        </button>

        <div>
          <h1 class="text-2xl font-bold text-card-foreground">管理员登录</h1>
          <p class="mt-1.5 text-sm text-muted-foreground">请输入管理员账号以进入管理后台</p>
        </div>

        <!-- 表单 -->
        <form class="mt-8 flex flex-col gap-4" @submit.prevent="submit">
          <label class="flex flex-col gap-1.5">
            <span class="text-xs font-medium text-muted-foreground">用户名</span>
            <div class="relative">
              <User class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                v-model="username"
                type="text"
                autocomplete="username"
                placeholder="请输入用户名"
                class="field pl-10"
              />
            </div>
          </label>

          <label class="flex flex-col gap-1.5">
            <span class="text-xs font-medium text-muted-foreground">密码</span>
            <div class="relative">
              <Lock class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                v-model="password"
                :type="showPwd ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="请输入密码"
                class="field pl-10 pr-10"
              />
              <button
                type="button"
                :aria-label="showPwd ? '隐藏密码' : '显示密码'"
                class="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted"
                @click="showPwd = !showPwd"
              >
                <EyeOff v-if="showPwd" class="h-4 w-4" />
                <Eye v-else class="h-4 w-4" />
              </button>
            </div>
          </label>

          <p v-if="error" class="rounded-xl bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive">
            {{ error }}
          </p>

          <button
            type="submit"
            :disabled="loading"
            class="btn btn-primary mt-2 w-full"
          >
            <Loader2 v-if="loading" class="h-4 w-4 animate-spin" />
            <ShieldCheck v-else class="h-4 w-4" />
            {{ loading ? "登录中…" : "登录后台" }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
