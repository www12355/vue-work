/**
 * 文件上传 composable — XHR 上传 + 真实进度 + session 生命周期。
 *
 * 三阶段流程：createSession → uploadFiles → startPipeline
 * 后端不可达时所有操作 reject，调用方可 catch 后降级。
 */

import { ref, computed, onBeforeUnmount } from "vue"
import type { ApiClient } from "@/services/api/client"

export interface FileItem {
  name: string
  size: number
  status: "pending" | "uploading" | "done" | "error"
  progress: number // 0–100
  error?: string
}

export interface UploadSlot {
  type: "uploads" | "profile"
  label: string
  accept: string
  multiple: boolean
  files: FileItem[]
}

export function useUpload(
  api: () => ApiClient,
  createSessionFn: () => Promise<{ session_id: string }>,
  startPipelineFn: (sid: string) => Promise<any>,
) {
  const sessionId = ref<string | null>(null)
  const phase = ref<"idle" | "uploading" | "starting" | "done" | "error">("idle")
  const error = ref<string | null>(null)

  /* 文件槽位 */
  const coreSlot = ref<UploadSlot>({
    type: "uploads",
    label: "主文件",
    accept: ".doc,.docx,.pdf,.md,.txt",
    multiple: false,
    files: [],
  })

  const refSlot = ref<UploadSlot>({
    type: "profile",
    label: "参考文件",
    accept: ".doc,.docx,.pdf,.md,.txt,.xlsx,.pptx",
    multiple: true,
    files: [],
  })

  /** 上传队列是否全部完成 */
  const allUploaded = computed(() => {
    const all = [...coreSlot.value.files, ...refSlot.value.files]
    return all.length > 0 && all.every((f) => f.status === "done")
  })

  /** 是否有文件在上传中 */
  const uploading = computed(() => phase.value === "uploading")

  /** 总上传进度 */
  const totalProgress = computed(() => {
    const all = [...coreSlot.value.files, ...refSlot.value.files]
    if (!all.length) return 0
    const sum = all.reduce((acc, f) => acc + f.progress, 0)
    return Math.round(sum / all.length)
  })

  /* 单个文件 XHR 上传使用模块级 xhrUploadFile（见文件底部），此处不再重复实现 */

  /** 添加文件到指定槽位 */
  function addFiles(slot: "core" | "ref", fileList: FileList | File[]) {
    const slotRef = slot === "core" ? coreSlot : refSlot
    const arr = Array.from(fileList)

    if (!slotRef.value.multiple) {
      slotRef.value.files = arr.slice(0, 1).map((f) => ({
        name: f.name,
        size: f.size,
        status: "pending" as const,
        progress: 0,
      }))
    } else {
      const names = new Set(slotRef.value.files.map((f) => f.name))
      const newFiles = arr
        .filter((f) => !names.has(f.name))
        .map((f) => ({
          name: f.name,
          size: f.size,
          status: "pending" as const,
          progress: 0,
        }))
      slotRef.value.files = [...slotRef.value.files, ...newFiles]
    }
  }

  /** 移除文件 */
  function removeFile(slot: "core" | "ref", index: number) {
    const slotRef = slot === "core" ? coreSlot : refSlot
    slotRef.value.files.splice(index, 1)
  }

  /** 上传指定槽位所有 pending 文件 */
  async function uploadSlot(slot: UploadSlot): Promise<void> {
    if (!sessionId.value) throw new Error("Session 尚未创建")

    const pending = slot.files.filter((f) => f.status === "pending")
    if (!pending.length) return

    const baseUrl = api().resolveUrl(
      `/api/session/${sessionId.value}/upload?type=${slot.type}`,
    )

    for (const item of pending) {
      item.status = "uploading"
      try {
        // 需要原始 File 对象 —— 从全局 fileMap 查找
        const fileObj = fileMap.get(item.name)
        if (!fileObj) throw new Error(`找不到文件: ${item.name}`)

        await xhrUploadFile(fileObj, baseUrl, (pct) => {
          item.progress = pct
        })
        item.status = "done"
        item.progress = 100
      } catch (e: any) {
        item.status = "error"
        item.error = e.message || "上传失败"
        throw e
      }
    }
  }

  /** 执行完整三阶段提交流程 */
  async function startPipeline(): Promise<string> {
    try {
      phase.value = "uploading"
      error.value = null

      // Step 1: 创建 session
      const session = await createSessionFn()
      sessionId.value = session.session_id

      // Step 2: 上传所有文件
      if (coreSlot.value.files.length) {
        await uploadSlot(coreSlot.value)
      }
      if (refSlot.value.files.length) {
        await uploadSlot(refSlot.value)
      }

      // Step 3: 启动 pipeline
      phase.value = "starting"
      await startPipelineFn(session.session_id)

      phase.value = "done"
      return session.session_id
    } catch (e: any) {
      phase.value = "error"
      error.value = e.message || "流水线启动失败"
      throw e
    }
  }

  /** 重置为初始状态 */
  function clear() {
    sessionId.value = null
    phase.value = "idle"
    error.value = null
    coreSlot.value.files = []
    refSlot.value.files = []
    fileMap.clear()
  }

  onBeforeUnmount(() => {
    fileMap.clear()
  })

  return {
    sessionId,
    phase,
    error,
    coreSlot,
    refSlot,
    allUploaded,
    uploading,
    totalProgress,
    addFiles,
    removeFile,
    startPipeline,
    clear,
  }
}

/**
 * 全局 File name → File 对象映射。
 * DropZone / FileUpload 等组件的 v-model 可能是字符串数组，
 * 我们需要通过 name 找回原始 File 用于 XHR 上传。
 */
export const fileMap = new Map<string, File>()

/** 注册 File 到全局映射（组件中在 @change / @drop 时调用） */
export function registerFiles(files: FileList | File[]) {
  Array.from(files).forEach((f) => fileMap.set(f.name, f))
}

/** 注销单个文件 */
export function unregisterFile(name: string) {
  fileMap.delete(name)
}

/**
 * XHR 上传单个文件（multipart 字段名 files，与后端一致），带字节级进度回调。
 * 供各 App 的 generate 流程与 useUpload 内部共用。
 */
export function xhrUploadFile(
  file: File,
  url: string,
  onProgress?: (pct: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append("files", file)

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100))
    })

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve()
      } else {
        let detail = `HTTP ${xhr.status}`
        try {
          const body = JSON.parse(xhr.responseText)
          detail = body.detail || body.message || detail
        } catch { /* ignore */ }
        reject(new Error(detail))
      }
    })

    xhr.addEventListener("error", () => reject(new Error("上传失败：网络错误")))
    xhr.addEventListener("abort", () => reject(new Error("上传已取消")))

    if (signal) {
      signal.addEventListener("abort", () => xhr.abort())
    }

    xhr.open("POST", url)
    xhr.send(formData)
  })
}
