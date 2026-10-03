<script setup lang="ts">
import ResearchComposer from './ResearchComposer.vue'
import { researchQuestionSchema, type ResearchExecutionResponse } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import { useResearchLocation } from '~/composables/useResearchLocation'
import { useResearchSuggestions } from '~/composables/useResearchSuggestions'
import { researchAnswerQuery, researchAnswerUrl } from '~/utils/research-answer'
const route = useRoute()
const auth = useAuthStore()
const { $adminApi } = useNuxtApp()
const question = ref('')
const location = useResearchLocation()
const {
  context: locationContext,
  error: locationError,
  pending: locating,
  manual: manualLocation,
} = location
const manualPlace = ref('')
const needsLocation = computed(
  () =>
    data.value?.result.kind === 'needs_clarification' &&
    data.value.result.planner_state === 'needs_location',
)
async function submitManualLocation() {
  if (location.setManual(manualPlace.value)) await load()
}
const autosuggest = useResearchSuggestions(question)
const { result: suggestions, active: activeSuggestion } = autosuggest
let selectionReceipt: string | undefined
const input = useTemplateRef('input')
watch(activeSuggestion, async (index) => {
  if (index < 0) return
  await nextTick()
  document.getElementById(`research-suggestion-${index}`)?.scrollIntoView?.({ block: 'nearest' })
})
const data = shallowRef<ResearchExecutionResponse | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const submitting = ref(false)
const invalid = ref(false)
const permalink = ref<string | null>(null)
const ready = ref(false)
// Onboarding examples, separate from any learned suggestions.
const examples = ['Veranstaltungen am Wochenende', 'Konzerte im Sommer', 'Angebote für Kinder']

async function useExample(example: string) {
  question.value = example
  invalid.value = false
  await nextTick()
  input.value?.focus()
}
function onKeydown(event: KeyboardEvent) {
  if (!event.shiftKey && !event.ctrlKey && !event.metaKey) autosuggest.keydown(event, submit)
}
let mounted = false
let generation = 0
let controller: AbortController | undefined
function clear() {
  generation++
  controller?.abort()
  data.value = null
  error.value = null
  loading.value = false
}
async function load() {
  autosuggest.close()
  clear()
  const current = generation
  invalid.value = false
  permalink.value = null
  if (!auth.canResearch || route.query.question === undefined) return
  const parsed = researchAnswerQuery(route.query)
  if (!parsed.success) {
    invalid.value = true
    return
  }
  permalink.value = window.location.href
  controller = new AbortController()
  loading.value = true
  try {
    const receipt = selectionReceipt
    selectionReceipt = undefined
    const response = await $adminApi.researchQuery(
      parsed.data,
      controller.signal,
      receipt,
      locationContext.value,
    )
    if (mounted && current === generation && auth.canResearch) {
      data.value = response
      const canonical = response.resolution.find((item) => item.field === 'location_context')
        ?.target.label
      if (canonical && canonical.length <= 160 && locationContext.value?.latitude != null) {
        locationContext.value = { ...locationContext.value, display_name: canonical }
      }
    }
  } catch (cause) {
    if (mounted && current === generation && auth.canResearch) error.value = asFailure(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
async function submit(receipt?: string) {
  if (!mounted || loading.value || submitting.value || !auth.canResearch) return
  autosuggest.close()
  selectionReceipt = receipt
  const parsed = researchQuestionSchema.safeParse(question.value)
  invalid.value = !parsed.success
  if (!parsed.success) return
  submitting.value = true
  try {
    if (route.query.question === parsed.data) await load()
    else await navigateTo({ path: '/research', query: researchAnswerUrl(parsed.data) })
  } finally {
    submitting.value = false
  }
}
async function adjust(candidate?: string) {
  if (
    data.value?.result.kind === 'needs_clarification' &&
    data.value.result.field === 'location_context'
  ) {
    if (candidate && location.setManual(candidate)) {
      await load()
      return
    }
    manualLocation.value = true
    return
  }
  // Candidate labels are editable text, never a browser-submitted execution plan.
  if (candidate) {
    const result = data.value?.result
    const original = data.value?.query ?? question.value
    question.value =
      result?.kind === 'needs_clarification' && result.query && original.includes(result.query)
        ? original.replace(result.query, candidate)
        : `${original}\nGemeint ist: ${candidate}`
  }
  await nextTick()
  input.value?.focus()
}
watch(
  () => route.query.question,
  () => {
    location.cancel()
    manualLocation.value = false
    question.value = typeof route.query.question === 'string' ? route.query.question : ''
    if (mounted) void load()
  },
  { immediate: true },
)
watch(
  () => auth.revision,
  () => {
    clear()
    selectionReceipt = undefined
    question.value = ''
    manualPlace.value = ''
    permalink.value = null
  },
)
onMounted(() => {
  mounted = true
  ready.value = true
  void load()
})
onBeforeUnmount(() => {
  mounted = false
  clear()
})
</script>
<template>
  <div class="research-question-workspace flex min-h-0 min-w-0 flex-1 flex-col">
    <div class="research-question-content min-h-0 flex-1 overflow-y-auto px-1 pb-6 pt-2">
      <template v-if="!route.query.question">
        <slot name="welcome" />
        <div class="mt-4 text-center" role="group" aria-label="Beispiele für Fragen">
          <p class="mb-2 text-sm text-slate-600">Beispiele</p>
          <div
            class="research-examples mx-auto flex max-w-[51rem] flex-wrap justify-center gap-4 sm:gap-8"
          >
            <button
              v-for="example in examples"
              :key="example"
              type="button"
              class="research-example inline-flex min-h-11 max-w-full items-center gap-4 px-4 py-2 text-left text-sm text-slate-700"
              :disabled="!ready || loading"
              @click="useExample(example)"
            >
              {{ example }}
            </button>
          </div>
        </div>
        <slot name="discover" />
      </template>
      <div v-if="loading || error || data" class="mx-auto w-full max-w-5xl space-y-4">
        <RequestState
          :loading="loading"
          loading-message="Frage wird ausgewertet …"
          :error="error"
          @retry="submit()"
        />
        <section
          v-if="needsLocation || manualLocation"
          class="rounded-xl border border-slate-200 bg-white p-4 space-y-3"
          aria-label="Standort benötigt"
        >
          <h2 class="font-semibold">Standort benötigt</h2>
          <p>Nutze deinen Standort oder gib einen Ort für diese Frage an.</p>
          <div class="flex flex-wrap gap-3">
            <button
              type="button"
              class="button-primary"
              :disabled="locating || loading"
              @click="location.locate(load)"
            >
              {{ locating ? 'Standort wird ermittelt …' : 'Standort freigeben' }}
            </button>
            <button type="button" class="button" @click="manualLocation = true">
              Ort manuell eingeben
            </button>
          </div>
          <p v-if="locationError" role="alert">{{ locationError }}</p>
          <form
            v-if="manualLocation"
            class="flex flex-wrap gap-3"
            @submit.prevent="submitManualLocation"
          >
            <label for="research-manual-location">Ort oder Adresse</label>
            <input
              id="research-manual-location"
              v-model="manualPlace"
              maxlength="160"
              required
              class="input"
            />
            <button type="submit" class="button-primary" :disabled="loading || !manualPlace.trim()">
              Ort verwenden
            </button>
          </form>
        </section>
        <ResearchQueryAnswer v-if="data && !needsLocation" :response="data" @adjust="adjust" />
      </div>
      <div class="mx-auto max-w-[51rem]">
        <p
          v-if="invalid"
          id="research-question-error"
          role="alert"
          class="mt-2 text-sm text-rose-700"
        >
          Bitte gib eine gültige Frage mit 1 bis 2.000 Zeichen ein.
        </p>
        <div class="mt-6 flex min-h-8 flex-wrap items-center justify-center gap-x-5 gap-y-1">
          <NuxtLink
            to="/research/search"
            class="inline-flex min-h-8 items-center gap-2 text-xs text-slate-500 underline decoration-slate-300 underline-offset-4 hover:text-blue-700"
          >
            <AppIcon name="search" :size="16" />Klassische Suche
          </NuxtLink>
          <details class="research-input-help text-xs text-slate-500">
            <summary class="flex min-h-8 cursor-pointer items-center hover:text-blue-700">
              Hinweise zur Eingabe
            </summary>
            <p id="research-question-help" class="max-w-sm pb-2 leading-relaxed">
              Bis zu 2.000 Zeichen. Enter zum Absenden, Umschalt + Enter für eine neue Zeile. Die
              Frage wird im kopierbaren Link gespeichert.
            </p>
            <p class="max-w-sm pb-2 leading-relaxed">
              Vorschläge basieren auf häufig erfolgreich verwendeten Recherchefragen.
            </p>
          </details>
          <CopyValueButton
            v-if="permalink"
            :value="permalink"
            label="Frage-Link"
            button-text="Link kopieren"
          />
        </div>
      </div>
    </div>
    <footer class="research-composer-footer shrink-0 px-1 pt-4">
      <div class="research-composer-container relative mx-auto w-full max-w-[51rem]">
        <ul
          v-if="suggestions?.suggestions.length"
          id="research-suggestion-list"
          role="listbox"
          aria-label="Recherchevorschläge"
          class="absolute bottom-full z-20 mb-2 max-h-[min(18rem,40dvh)] w-full overflow-auto rounded-xl border border-slate-200 bg-white shadow-lg"
        >
          <li
            v-for="(suggestion, index) in suggestions.suggestions"
            :id="`research-suggestion-${index}`"
            :key="suggestion.id"
            role="option"
            :aria-selected="activeSuggestion === index"
            class="cursor-pointer px-3 py-2 text-sm hover:bg-slate-100"
            :class="{ 'bg-slate-100': activeSuggestion === index }"
            @pointerdown.prevent
            @click="autosuggest.choose(index, submit)"
          >
            {{ suggestion.query }}
          </li>
        </ul>
        <ResearchComposer
          ref="input"
          v-model="question"
          :disabled="!ready"
          :busy="loading || submitting"
          :invalid="invalid"
          :expanded="!!suggestions?.suggestions.length"
          :active-suggestion="activeSuggestion"
          @submit="submit()"
          @input="selectionReceipt = undefined"
          @focus="autosuggest.focus"
          @blur="autosuggest.blur"
          @keydown="onKeydown"
        />
      </div>
    </footer>
  </div>
</template>
<style scoped>
@reference '../assets/css/main.css';
.research-question-content {
  scrollbar-gutter: stable both-edges;
  overscroll-behavior-y: contain;
}
.research-composer-footer {
  padding-bottom: max(1rem, env(safe-area-inset-bottom));
}
.research-example {
  border: 1px solid var(--color-blue-100);
  border-radius: 0.625rem;
  background: var(--color-blue-50);
  color: var(--color-blue-700);
}
.research-example:hover {
  border-color: var(--color-blue-300);
}
</style>
