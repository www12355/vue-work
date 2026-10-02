import { ref, watchEffect } from "vue"

export type ThemeName = "light" | "dark"

const STORAGE_KEY = "aicc.theme"

function readTheme(): ThemeName {
  if (typeof window === "undefined") return "light"
  const saved = window.localStorage.getItem(STORAGE_KEY)
  return saved === "dark" ? "dark" : "light"
}

/** 全局主题状态：任意组件（如头像菜单）都可读写，切换即持久化 */
export const theme = ref<ThemeName>(readTheme())

/* 同步 <html> 上的 dark 类并写入本地存储 */
watchEffect(() => {
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("dark", theme.value === "dark")
  }
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, theme.value)
  }
})

export function toggleTheme() {
  theme.value = theme.value === "light" ? "dark" : "light"
}

export function setTheme(next: ThemeName) {
  theme.value = next
}
