import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AdminSession } from '#shared/contracts'
import { AdminApiError, asFailure, failure, type ApiFailure } from '#shared/errors'
import { useDashboardStore } from './dashboard'
import { useFindingsStore } from './findings'

export const useAuthStore = defineStore('auth', () => {
  const { $adminApi } = useNuxtApp()
  const dashboard = useDashboardStore()
  const findings = useFindingsStore()
  const status = ref<'unknown' | 'checking' | 'authenticated' | 'anonymous'>('unknown')
  const session = ref<AdminSession | null>(null)
  const error = ref<ApiFailure | null>(null)
  const logoutWarning = ref('')
  const revision = ref(0)
  const isAdmin = computed(
    () => status.value === 'authenticated' && session.value?.system_admin === true,
  )
  // Request coordination stays private to this SSR/app instance, never in the payload.
  let pending: Promise<void> | undefined
  function resetData() {
    revision.value++
    dashboard.reset()
    findings.reset()
  }
  function clear() {
    status.value = 'anonymous'
    session.value = null
    error.value = null
    pending = undefined
    $adminApi.clearCredential()
    resetData()
  }
  function checkSession(force = false): Promise<void> {
    if (pending) return pending
    if (!force && status.value !== 'unknown') return Promise.resolve()
    const current = revision.value
    status.value = 'checking'
    error.value = null
    pending = (async () => {
      try {
        const identity = await $adminApi.session()
        if (current !== revision.value) return
        session.value = identity
        status.value = 'authenticated'
      } catch (cause) {
        if (current !== revision.value) return
        const detail = asFailure(cause)
        session.value = null
        // A denied account is still authenticated; never turn 403 into logout.
        status.value = detail.status === 403 ? 'authenticated' : 'anonymous'
        error.value = detail.status === 401 ? null : detail
      } finally {
        if (current === revision.value) pending = undefined
      }
    })()
    return pending
  }
  async function login(username: string, password: string) {
    clear()
    logoutWarning.value = ''
    const current = revision.value
    const identity = await $adminApi.login(username, password)
    if (current !== revision.value) return
    session.value = identity
    await checkSession(true)
    if (!isAdmin.value)
      throw new AdminApiError(error.value ?? failure(status.value === 'authenticated' ? 403 : 401))
  }
  async function logout() {
    try {
      await $adminApi.logout()
      logoutWarning.value = ''
    } catch {
      logoutWarning.value =
        'Die Serversitzung konnte nicht beendet werden. Bitte erneut anmelden und die Abmeldung wiederholen.'
    } finally {
      clear()
      await navigateTo('/login', { replace: true })
    }
  }
  return {
    status,
    session,
    error,
    logoutWarning,
    revision,
    isAdmin,
    checkSession,
    login,
    logout,
    clear,
  }
})
