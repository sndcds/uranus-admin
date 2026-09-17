import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AdminApi } from '../utils/admin-api'
import type { DashboardSummary, Period } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'

export const useDashboardStore = defineStore('dashboard', () => {
  const data = ref<DashboardSummary | null>(null)
  const period = ref<Period>('24h')
  const loading = ref(false)
  const error = ref<ApiFailure | null>(null)
  const lastSuccess = ref<string | null>(null)
  let requestId = 0
  async function load(api: AdminApi) {
    const id = ++requestId
    const requestedPeriod = period.value
    loading.value = true
    error.value = null
    try {
      const result = await api.summary(requestedPeriod)
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
    period.value = '24h'
    requestId++
    data.value = null
    error.value = null
    loading.value = false
    lastSuccess.value = null
  }
  async function setPeriod(value: Period, api: AdminApi) {
    if (value === period.value && data.value) return
    period.value = value
    await load(api)
  }
  return { data, period, loading, error, lastSuccess, load, setPeriod, reset }
})
