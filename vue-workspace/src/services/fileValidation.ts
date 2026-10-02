/**
 * 上传文件预校验 — 规则与后端 routes_upload 保持一致：
 * - 允许的扩展名：docx/doc/pdf/txt/md/pptx/ppt/xlsx/xls/jpg/jpeg/png/bmp
 * - 大小上限：.docx 200MB（核心标书文件），其余 50MB
 * 前端先行校验可以在创建会话前就给出明确提示，避免上传到一半才被后端拒绝。
 */

const ALLOWED_EXTENSIONS = [
  ".docx", ".doc", ".pdf", ".txt", ".md",
  ".pptx", ".ppt", ".xlsx", ".xls",
  ".jpg", ".jpeg", ".png", ".bmp",
]

const MAX_FILE_SIZE = 50 * 1024 * 1024
const MAX_DOCX_SIZE = 200 * 1024 * 1024

/** 返回 null 表示全部合法；否则返回可直接展示的错误信息 */
export function validateUploadFiles(files: File[]): string | null {
  const problems: string[] = []
  for (const f of files) {
    const dot = f.name.lastIndexOf(".")
    const ext = dot >= 0 ? f.name.slice(dot).toLowerCase() : ""
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      problems.push(`${f.name}（不支持的类型 ${ext || "无扩展名"}）`)
      continue
    }
    const limit = ext === ".docx" ? MAX_DOCX_SIZE : MAX_FILE_SIZE
    if (f.size > limit) {
      problems.push(`${f.name}（超过 ${Math.round(limit / 1024 / 1024)}MB 上限）`)
    }
  }
  return problems.length ? `以下文件无法上传：${problems.join("、")}` : null
}
