import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AdminApi } from '../utils/admin-api'
import type { DashboardSummary, Period } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'

export const useDashboardStore = defineStore('dashboard', () => {
  const data = ref<DashboardSummary | null>(null)
  const loading = ref(false)
  const error = ref<ApiFailure | null>(null)
  const lastSuccess = ref<string | null>(null)
  let requestId = 0
  async function load(api: AdminApi, requestedPeriod: Period = '24h', geoScopeId?: string) {
    const id = ++requestId
    if ((data.value?.geo_scope_id ?? undefined) !== geoScopeId) data.value = null
    loading.value = true
    error.value = null
    try {
      const result = await (geoScopeId
        ? api.summary(requestedPeriod, geoScopeId)
        : api.summary(requestedPeriod))
      if (id !== requestId) return
      data.value = result
      lastSuccess.value = new Date().toISOString()
    } catch (cause) {
      if (id !== requestId) return
      error.value = asFailure(cause)
      if ([401, 403].includes(error.value.status)) data.value = null
    } finally {
      if (id === requestId) loading.value = false
    }
  }
  function reset() {
    requestId++
    data.value = null
    error.value = null
    loading.value = false
    lastSuccess.value = null
  }
  return { data, loading, error, lastSuccess, load, reset }
})
