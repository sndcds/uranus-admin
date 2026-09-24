import { onBeforeUnmount, ref, shallowRef } from 'vue'
import { asFailure, type ApiFailure } from '#shared/errors'

/** Retain only the last successful response for the same selection/identity. */
export function useOperationsRequest<T>() {
  const data = shallowRef<T | null>(null)
  const error = ref<ApiFailure | null>(null)
  const loading = ref(false)
  let selection: string | undefined
  let generation = 0
  async function load(key: string, request: () => Promise<T>) {
    const current = ++generation
    if (key !== selection) data.value = null
    selection = key
    loading.value = true
    error.value = null
    try {
      const result = await request()
      if (current === generation) data.value = result
    } catch (cause) {
      if (current !== generation) return
      error.value = asFailure(cause)
      if ([401, 403, 404, 422].includes(error.value.status)) data.value = null
    } finally {
      if (current === generation) loading.value = false
    }
  }
  onBeforeUnmount(() => generation++)
  return { data, error, loading, load }
}
