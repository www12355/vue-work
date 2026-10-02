/**
 * WebSocket 客户端 — 自动重连 + 消息路由。
 *
 * 用法：
 *   const ws = useWebSocket()
 *   ws.connect("ws://localhost:8001/ws/session-id", (msg) => { ... })
 *
 * 重连策略：指数退避 1s/2s/4s/8s → 上限 30s 轮询。
 * 组件卸载时自动断开。
 */

import { ref, onBeforeUnmount } from "vue"
import type { WSMessage } from "@/services/api/types"

/** 最大重连延迟（ms） */
const MAX_RECONNECT_DELAY = 30_000
/** 初始重连延迟（ms） */
const INITIAL_RECONNECT_DELAY = 1_000

export function useWebSocket() {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const reconnecting = ref(false)
  const lastMessage = ref<WSMessage | null>(null)
  const error = ref<string | null>(null)

  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let pingTimer: ReturnType<typeof setInterval> | null = null
  let reconnectDelay = INITIAL_RECONNECT_DELAY
  let shouldReconnect = false
  let currentUrl: string | null = null
  let messageHandler: ((msg: WSMessage) => void) | null = null

  /** 后端主动关闭且不应重连的码：1000 正常关闭、4004 无效 session */
  const TERMINAL_CLOSE_CODES = new Set([1000, 4004])
  /** ping 心跳间隔（ms） */
  const PING_INTERVAL = 30_000

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function clearPingTimer() {
    if (pingTimer !== null) {
      clearInterval(pingTimer)
      pingTimer = null
    }
  }

  function startPing() {
    clearPingTimer()
    pingTimer = setInterval(() => {
      if (ws.value?.readyState === WebSocket.OPEN) {
        try {
          ws.value.send(JSON.stringify({ type: "ping" }))
        } catch { /* ignore */ }
      }
    }, PING_INTERVAL)
  }

  /** 断开当前连接并停止重连 */
  function disconnect() {
    shouldReconnect = false
    clearReconnectTimer()
    clearPingTimer()
    if (ws.value) {
      ws.value.onopen = null
      ws.value.onmessage = null
      ws.value.onerror = null
      ws.value.onclose = null
      ws.value.close()
      ws.value = null
    }
    connected.value = false
    reconnecting.value = false
    reconnectDelay = INITIAL_RECONNECT_DELAY
    currentUrl = null
    messageHandler = null
  }

  /** 建立连接（自动处理重连） */
  function connect(url: string, onMessage: (msg: WSMessage) => void) {
    // 先断开旧连接
    disconnect()

    currentUrl = url
    messageHandler = onMessage
    shouldReconnect = true
    reconnectDelay = INITIAL_RECONNECT_DELAY

    doConnect()
  }

  function doConnect() {
    if (!currentUrl) return

    try {
      ws.value = new WebSocket(currentUrl)

      ws.value.onopen = () => {
        connected.value = true
        reconnecting.value = false
        reconnectDelay = INITIAL_RECONNECT_DELAY
        error.value = null
        startPing()
      }

      ws.value.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as WSMessage
          lastMessage.value = msg

          /* 心跳 / pong 忽略 */
          if (msg.type === "heartbeat" || msg.type === "pong") return

          messageHandler?.(msg)
        } catch {
          /* 非 JSON 消息忽略 */
        }
      }

      ws.value.onerror = () => {
        connected.value = false
        error.value = "WebSocket 连接错误"
        console.error("[WS] onerror fired, readyState:", ws.value?.readyState)
      }

      ws.value.onclose = (ev) => {
        connected.value = false
        clearPingTimer()
        /* 正常关闭 / 无效 session：不重连 */
        if (TERMINAL_CLOSE_CODES.has(ev.code)) {
          shouldReconnect = false
          return
        }
        if (shouldReconnect) {
          scheduleReconnect()
        }
      }
    } catch (e: any) {
      connected.value = false
      error.value = e.message || "WebSocket 初始化失败"
      if (shouldReconnect) {
        scheduleReconnect()
      }
    }
  }

  function scheduleReconnect() {
    clearReconnectTimer()
    reconnecting.value = true
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY)
      doConnect()
    }, reconnectDelay)
  }

  onBeforeUnmount(() => {
    disconnect()
  })

  return {
    ws,
    connected,
    reconnecting,
    lastMessage,
    error,
    connect,
    disconnect,
  }
}
