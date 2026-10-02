/**
 * 历史记录 composable — session 列表、选择、删除。
 *
 * 用法：
 *   const history = useHistory("tender")
 *   await history.fetchSessions()
 *   history.selectSession(sid)
 */

import { ref, computed } from "vue"
import type { SessionListItem } from "@/services/api/types"

export function useHistory(ownerId: string) {
  const sessions = ref<SessionListItem[]>([])
  const selectedId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const selectedSession = computed(() =>
    selectedId.value
      ? sessions.value.find((s) => s.session_id === selectedId.value) ?? null
      : null,
  )

  const hasSessions = computed(() => sessions.value.length > 0)

  async function fetchSessions(fetchFn: () => Promise<SessionListItem[]>) {
    loading.value = true
    error.value = null
    try {
      sessions.value = await fetchFn()
    } catch (e: any) {
      error.value = e.message || "获取历史记录失败"
      sessions.value = []
    } finally {
      loading.value = false
    }
  }

  async function deleteSession(
    sessionId: string,
    deleteFn: (sid: string) => Promise<void>,
  ) {
    try {
      await deleteFn(sessionId)
      sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
      if (selectedId.value === sessionId) {
        selectedId.value = null
      }
    } catch (e: any) {
      error.value = e.message || "删除失败"
      throw e
    }
  }

  function selectSession(id: string) {
    selectedId.value = id
  }

  function clearSelection() {
    selectedId.value = null
  }

  return {
    sessions,
    selectedId,
    selectedSession,
    loading,
    error,
    hasSessions,
    fetchSessions,
    deleteSession,
    selectSession,
    clearSelection,
  }
}
