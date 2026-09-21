import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  consoleErrorMessages,
  consolePath,
  consoleServerSchema,
  type ConsoleClientMessage,
  type ConsoleRow,
} from '#shared/sql-console'
import { useAuthStore } from '~/stores/auth'
import { asFailure } from '#shared/errors'

export function useSqlConsole() {
  const auth = useAuthStore()
  const { $adminApi } = useNuxtApp()
  const status = ref<'Idle' | 'Running' | 'Cancelling' | 'Cancelled' | 'Completed' | 'Error'>(
    'Idle',
  )
  const connected = ref(false),
    error = ref(''),
    position = ref<number | null>(null)
  const columns = ref<string[]>([]),
    rows = ref<ConsoleRow[]>([])
  const duration = ref(0),
    truncated = ref(false),
    hasResult = ref(false)
  const busy = computed(() => status.value === 'Running' || status.value === 'Cancelling')
  let socket: WebSocket | undefined,
    requestId = '',
    receivedBytes = 0,
    batch = 0,
    currentLimit = 50
  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  let executing = false
  function send(message: ConsoleClientMessage) {
    socket?.send(JSON.stringify(message))
  }
  function fail(message: string) {
    error.value = message
    status.value = 'Error'
    clearTimeout(timer)
  }
  function disconnect() {
    socket?.close()
    socket = undefined
    connected.value = false
    clearTimeout(timer)
  }
  async function execute(rawSql: string, rowLimit: number) {
    if (busy.value || disposed) return
    if (new TextEncoder().encode(rawSql).length > 32768) {
      fail(consoleErrorMessages.invalid_sql)
      return
    }
    executing = false
    status.value = 'Running'
    const revision = auth.revision
    // Verify auth via the existing HTTP path too: browser WebSocket hides denial status.
    try {
      const identity = await $adminApi.session()
      if (!identity.system_admin) {
        await auth.checkSession(true)
        return
      }
    } catch (cause) {
      const failure = asFailure(cause)
      if (failure.status === 401) {
        auth.clear()
        void navigateTo('/login')
      } else if (failure.status === 403) await auth.checkSession(true)
      else fail(failure.message)
      return
    }
    if (!auth.isAdmin || disposed || revision !== auth.revision || status.value !== 'Running') {
      if (!disposed && status.value === 'Running') status.value = 'Idle'
      return
    }
    status.value = 'Running'
    error.value = ''
    position.value = null
    columns.value = []
    rows.value = []
    duration.value = 0
    truncated.value = false
    hasResult.value = false
    currentLimit = rowLimit
    receivedBytes = 0
    batch = 0
    requestId = crypto.randomUUID()
    const id = requestId
    const run = () => {
      if (disposed || id !== requestId || status.value !== 'Running') return
      executing = true
      send({ v: 1, type: 'execute', request_id: id, sql: rawSql, params: {}, row_limit: rowLimit })
      // Transport watchdog; server's own 8s deadline is the execution authority.
      timer = setTimeout(() => {
        disconnect()
        fail(consoleErrorMessages.timeout)
      }, 11000)
    }
    if (socket?.readyState === WebSocket.OPEN) {
      run()
      return
    }
    disconnect()
    const url = new URL(consolePath, window.location.origin)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    const current = new WebSocket(url)
    socket = current
    timer = setTimeout(() => {
      disconnect()
      fail(consoleErrorMessages.unavailable)
    }, 6000)
    current.onopen = () => {
      clearTimeout(timer)
      connected.value = true
      run()
    }
    current.onmessage = async (event) => {
      if (socket !== current || disposed) return
      try {
        const message = consoleServerSchema.parse(JSON.parse(String(event.data)))
        if (message.request_id !== requestId) return
        if (message.type === 'columns') columns.value = message.columns
        if (message.type === 'rows') {
          receivedBytes += new TextEncoder().encode(String(event.data)).length
          if (
            message.batch !== batch + 1 ||
            rows.value.length + message.rows.length > currentLimit ||
            receivedBytes > 1024 * 1024
          )
            throw new Error('Invalid result')
          batch = message.batch
          if (status.value === 'Running') {
            rows.value.push(...message.rows)
            hasResult.value = true
          }
          await nextTick()
          if (socket === current && busy.value && status.value !== 'Cancelling')
            send({ v: 1, type: 'ack', request_id: requestId, batch })
        }
        if (message.type === 'complete') {
          status.value = 'Completed'
          duration.value = message.duration_ms
          truncated.value = message.truncated
          hasResult.value = true
          clearTimeout(timer)
        }
        if (message.type === 'cancelled') {
          status.value = 'Cancelled'
          duration.value = message.duration_ms
          clearTimeout(timer)
        }
        if (message.type === 'error') {
          position.value = message.position ?? null
          fail(consoleErrorMessages[message.code])
        }
      } catch {
        disconnect()
        fail(consoleErrorMessages.protocol_error)
      }
    }
    current.onclose = (event) => {
      if (socket !== current) return
      connected.value = false
      socket = undefined
      if (busy.value) fail(consoleErrorMessages.unavailable)
      if (event.code === 4401) {
        auth.clear()
        void navigateTo('/login')
      }
      if (event.code === 4403) {
        rows.value = []
        columns.value = []
        hasResult.value = false
        fail('Keine Systemadministrator-Berechtigung.')
        void auth.checkSession(true)
      }
    }
    current.onerror = () => {
      if (socket === current) {
        disconnect()
        fail(consoleErrorMessages.unavailable)
      }
    }
  }
  function cancel() {
    if (!busy.value || status.value === 'Cancelling') return
    status.value = 'Cancelling'
    if (executing && socket?.readyState === WebSocket.OPEN)
      send({ v: 1, type: 'cancel', request_id: requestId })
    else {
      disconnect()
      status.value = 'Cancelled'
    }
  }
  watch(
    () => auth.revision,
    () => {
      disconnect()
      rows.value = []
      columns.value = []
      hasResult.value = false
      status.value = 'Idle'
    },
  )
  onBeforeUnmount(() => {
    disposed = true
    disconnect()
  })
  const result = computed(() =>
    hasResult.value
      ? {
          columns: columns.value,
          rows: rows.value,
          row_count: rows.value.length,
          duration_ms: duration.value,
          observed_at: null,
          truncated: truncated.value,
        }
      : null,
  )
  return { status, connected, error, position, busy, result, execute, cancel }
}
