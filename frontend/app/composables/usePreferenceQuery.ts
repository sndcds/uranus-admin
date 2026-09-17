import { onMounted, shallowRef, watch } from 'vue'
import type { LocationQuery, LocationQueryRaw } from 'vue-router'

/** Restore on entry only. Subsequent history entries are complete URL snapshots. */
export function usePreferenceQuery(
  defaults: LocationQueryRaw,
  hydrate: (query: LocationQuery, previous?: LocationQuery) => void,
  mergeMissing = false,
) {
  const route = useRoute()
  const router = useRouter()
  const entryPath = route.path
  const explicit = Object.keys(route.query).length > 0
  const restored: LocationQuery = {}
  for (const [key, value] of Object.entries(defaults)) {
    if (value !== undefined && value !== null && value !== '') restored[key] = String(value)
  }
  const initial = explicit && !mergeMissing ? route.query : { ...restored, ...route.query }
  const query = shallowRef<LocationQuery>(initial)
  if (explicit) hydrate(initial)
  watch(
    () => route.query,
    (value) => {
      if (route.path !== entryPath) return
      // Our one-time replace serializes the already applied preference; it is not user input.
      if (JSON.stringify(value) === JSON.stringify(query.value)) return
      const previous = query.value
      query.value = value
      hydrate(value, previous)
    },
  )
  onMounted(() => {
    if (JSON.stringify(initial) !== JSON.stringify(route.query))
      void router.replace({ query: initial })
  })
  return query
}
