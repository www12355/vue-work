import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath, URL } from "node:url"
import { defineConfig, type ProxyOptions } from "vite"
import vue from "@vitejs/plugin-vue"
import tailwindcss from "@tailwindcss/vite"

/**
 * 按路径代理到不同后端：管理后台「接口代理」可视化配置的规则会导出成
 * proxy.config.json（本文件同级目录）。这里在 dev / preview 启动时读取它，
 * 生成 Vite 的 server.proxy 表，实现 path 前缀 → 不同后端的转发。
 */
interface ProxyRuleFile {
  path: string
  target: string
  changeOrigin?: boolean
  stripPrefix?: boolean
  ws?: boolean
}

function loadProxy(): Record<string, ProxyOptions> {
  const file = fileURLToPath(new URL("./proxy.config.json", import.meta.url))
  if (!existsSync(file)) return {}
  try {
    const rules = JSON.parse(readFileSync(file, "utf-8")) as ProxyRuleFile[]
    const proxy: Record<string, ProxyOptions> = {}
    for (const r of rules) {
      if (!r?.path || !r?.target) continue
      proxy[r.path] = {
        target: r.target,
        changeOrigin: r.changeOrigin ?? true,
        ws: r.ws ?? false,
        ...(r.stripPrefix
          ? { rewrite: (p: string) => p.replace(new RegExp(`^${r.path}`), "") }
          : {}),
      }
    }
    return proxy
  } catch {
    return {}
  }
}


export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
    // 代理配置同步插件
    {
      name: "proxy-config-sync",
      configureServer(server) {
        const file = fileURLToPath(new URL("./proxy.config.json", import.meta.url))

        // 内置同步端点：前端直接通过 Vite 开发服务器读写 proxy.config.json，
        // 无需额外启动 scripts/proxy-config-server.js。
        server.middlewares.use("/api/proxy-config-sync", (req, res, next) => {
          if (req.method === "GET") {
            try {
              const content = readFileSync(file, "utf-8")
              res.writeHead(200, { "Content-Type": "application/json" })
              res.end(content)
            } catch {
              res.writeHead(200, { "Content-Type": "application/json" })
              res.end("[]")
            }
            return
          }

          if (req.method === "POST") {
            let body = ""
            req.on("data", (chunk: string) => { body += chunk })
            req.on("end", () => {
              try {
                const config = JSON.parse(body)
                if (!Array.isArray(config)) throw new Error("Config must be an array")
                writeFileSync(file, JSON.stringify(config, null, 2), "utf-8")
                console.log("📝 proxy.config.json 已更新，重启开发服务器后生效")
                res.writeHead(200, { "Content-Type": "application/json" })
                res.end(JSON.stringify({ success: true, message: "Config saved — restart dev server to apply" }))
              } catch (err: any) {
                console.error("✗ 保存 proxy.config.json 失败:", err.message)
                res.writeHead(400, { "Content-Type": "application/json" })
                res.end(JSON.stringify({ error: err.message }))
              }
            })
            return
          }

          if (req.method === "OPTIONS") {
            res.writeHead(204, {
              "Access-Control-Allow-Origin": "*",
              "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
              "Access-Control-Allow-Headers": "Content-Type",
            })
            res.end()
            return
          }

          next()
        })
      },
      // 虚拟模块：将 proxy.config.json 内容导出给前端（仅启动时加载一次）
      resolveId(id) {
        if (id === "virtual:proxy-config") { return id }
      },
      load(id) {
        if (id === "virtual:proxy-config") {
          const file = fileURLToPath(new URL("./proxy.config.json", import.meta.url))
          try {
            const content = readFileSync(file, "utf-8")
            return `export default ${content}`
          } catch {
            return `export default []`
          }
        }
      },
    },
  ],
  css: {
    /**
     * Tailwind 由 @tailwindcss/vite 插件处理，这里显式给出内联 postcss 配置，
     * 阻止 Vite 向上层目录搜索并误加载外部（如 Next 项目）的 postcss.config.*
     */
    postcss: { plugins: [] },
  },
  server: {
    host: true,
    port: 5174,
    strictPort: true,
    allowedHosts: true,
    // 代理规则：优先使用 proxy.config.json（管理后台可视化配置），
    // 同时硬编码内置模块的代理规则作为兜底（参考旧项目 AutoGenUnified 的可靠模式）。
    proxy: {
      // ── 内置模块硬编码代理（兜底，确保不依赖外部文件即可工作）──
      '/api/tender': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api\/tender/, ''),
        ws: true,
      },
      '/api/contract': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api\/contract/, ''),
        ws: true,
      },
      // ── proxy.config.json 中的规则（管理后台可追加自定义代理）──
      ...loadProxy(),
    },
  },
  preview: {
    host: true,
    port: 5174,
    allowedHosts: true,
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
})
