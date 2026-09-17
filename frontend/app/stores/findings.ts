import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AdminApi } from '../utils/admin-api'
import type { FindingFilters, FindingPage } from '#shared/contracts'
import { filtersSchema } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'

export const useFindingsStore = defineStore('findings', () => {
  const data = ref<FindingPage | null>(null)
  const filters = ref<FindingFilters>(filtersSchema.parse({}))
  const loading = ref(false)
  const error = ref<ApiFailure | null>(null)
  const lastSuccess = ref<string | null>(null)
  let requestId = 0
  async function load(api: AdminApi) {
    const id = ++requestId
    loading.value = true
    error.value = null
    try {
      const result = await api.findings({ ...filters.value })
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
  function setFilters(value: Partial<FindingFilters>) {
    filters.value = filtersSchema.parse({ ...filters.value, ...value, page: 1 })
    requestId++
    data.value = null
  }
  function syncQuery(value: FindingFilters) {
    filters.value = value
    requestId++
    data.value = null
  }
  function reset() {
    filters.value = filtersSchema.parse({})
    requestId++
    data.value = null
    error.value = null
    loading.value = false
    lastSuccess.value = null
  }
  return { data, filters, loading, error, lastSuccess, load, setFilters, syncQuery, reset }
})
