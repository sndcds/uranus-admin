import { locationContextSchema, type LocationContext } from '#shared/contracts'

/** In-memory only; auth loss invalidates both context and pending browser callbacks. */
export function useResearchLocation() {
  const auth = useAuthStore()
  const context = ref<LocationContext>()
  const error = ref('')
  const pending = ref(false)
  const manual = ref(false)
  let generation = 0
  watch(
    () => auth.revision,
    () => {
      generation++
      context.value = undefined
      pending.value = false
      error.value = ''
      manual.value = false
    },
  )
  onBeforeUnmount(() => {
    generation++
    context.value = undefined
  })
  function cancel() {
    generation++
    pending.value = false
  }
  function locate(resubmit: () => Promise<void>) {
    if (!auth.canResearch || pending.value) return
    if (context.value) {
      void resubmit()
      return
    }
    if (!navigator.geolocation) {
      error.value = 'Standort nicht verfügbar. Bitte einen Ort manuell eingeben.'
      manual.value = true
      return
    }
    pending.value = true
    error.value = ''
    const current = ++generation
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (current !== generation || !auth.canResearch) return
        pending.value = false
        const parsed = locationContextSchema.safeParse({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          source: 'browser_geolocation',
        })
        if (!parsed.success) {
          manual.value = true
          return
        }
        context.value = parsed.data
        void resubmit()
      },
      () => {
        if (current !== generation || !auth.canResearch) return
        pending.value = false
        error.value =
          'Standort nicht freigegeben oder nicht verfügbar. Bitte einen Ort manuell eingeben.'
        manual.value = true
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    )
  }
  function setManual(displayName: string): boolean {
    const parsed = locationContextSchema.safeParse({ display_name: displayName, source: 'manual' })
    if (!parsed.success) return false
    generation++
    pending.value = false
    context.value = parsed.data
    error.value = ''
    manual.value = false
    return true
  }
  return { context, error, pending, manual, locate, setManual, cancel }
}
