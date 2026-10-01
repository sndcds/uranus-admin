import type { ResearchSuggestions } from '#shared/contracts'
import type { Ref } from 'vue'

export function useResearchSuggestions(question: Ref<string>) {
  const { $adminApi } = useNuxtApp()
  const auth = useAuthStore()
  const result = shallowRef<ResearchSuggestions | null>(null)
  const active = ref(-1)
  const focused = ref(false)
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  let generation = 0
  let impressions: Promise<unknown> | undefined
  let choosing = false
  let disposed = false
  function close() {
    generation++
    clearTimeout(timer)
    controller?.abort()
    result.value = null
    active.value = -1
  }
  function changed() {
    close()
    const q = question.value.trim()
    if (!focused.value || !auth.canResearch || q.length < 2 || q.length > 120) return
    const current = generation
    timer = setTimeout(async () => {
      controller = new AbortController()
      try {
        const response = await $adminApi.researchSuggestions(q, controller.signal)
        if (current !== generation || !auth.canResearch || !focused.value) return
        result.value = response
        await nextTick()
        if (current !== generation || !response.suggestions.length || !focused.value) return
        impressions = $adminApi
          .researchSuggestionImpression({
            request_id: response.request_id,
            prefix: q,
            suggestions: response.suggestions.map(({ id, position }) => ({ id, position })),
          })
          .catch(() => {})
      } catch {
        /* Suggestions are optional; keep the editable question usable. */
      }
    }, 200)
  }
  async function choose(index: number, submit: (receipt?: string) => Promise<void>) {
    const response = result.value
    const suggestion = response?.suggestions[index]
    if (!response || !suggestion || choosing) return
    choosing = true
    const pendingImpression = impressions
    close()
    const selectedGeneration = generation
    question.value = suggestion.query
    const selectedQuery = suggestion.query
    const revision = auth.revision
    let receipt: string | undefined
    try {
      await pendingImpression
      const event = await $adminApi.researchSuggestionSelect({
        request_id: response.request_id,
        suggestion_id: suggestion.id,
        position: suggestion.position,
      })
      receipt = event.receipt ?? undefined
    } catch {
      /* Selection telemetry must not block question execution. */
    } finally {
      choosing = false
    }
    if (
      !disposed &&
      selectedGeneration === generation &&
      auth.canResearch &&
      revision === auth.revision &&
      question.value === selectedQuery
    ) {
      close()
      await submit(receipt)
    }
  }
  function keydown(event: KeyboardEvent, submit: (receipt?: string) => Promise<void>) {
    if (event.isComposing) return
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
      return
    }
    const count = result.value?.suggestions.length ?? 0
    if (!count) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      active.value =
        active.value < 0
          ? event.key === 'ArrowDown'
            ? 0
            : count - 1
          : (active.value + (event.key === 'ArrowDown' ? 1 : count - 1)) % count
    } else if (event.key === 'Enter' && active.value >= 0) {
      event.preventDefault()
      void choose(active.value, submit)
    }
  }
  watch(question, () => {
    if (!choosing) changed()
  })
  watch(() => auth.revision, close)
  onBeforeUnmount(() => {
    disposed = true
    close()
  })
  function focus() {
    focused.value = true
    changed()
  }
  function blur() {
    focused.value = false
    close()
  }
  return { result, active, close, changed, choose, keydown, focus, blur }
}
