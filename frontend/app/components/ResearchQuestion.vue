<script setup lang="ts">
import { researchQuestionSchema, type ResearchExecutionResponse } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import { researchAnswerQuery, researchAnswerUrl } from '~/utils/research-answer'
const route = useRoute()
const auth = useAuthStore()
const { $adminApi } = useNuxtApp()
const question = ref('')
const input = useTemplateRef('input')
const data = shallowRef<ResearchExecutionResponse | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const invalid = ref(false)
const permalink = ref<string | null>(null)
const ready = ref(false)
// Onboarding examples, separate from any learned suggestions.
const examples = [
  'Welche Jazz-Konzerte finden heute statt?',
  'Wie viele Veranstaltungen gab es in Flensburg im August?',
  'Wo finden Jazz-Konzerte statt?',
  'Welche Orte sind besonders aktiv?',
]
async function useExample(example: string) {
  question.value = example
  invalid.value = false
  await nextTick()
  input.value?.focus()
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing) {
    event.preventDefault()
    void submit()
  }
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
    const response = await $adminApi.researchQuery(parsed.data, controller.signal)
    if (mounted && current === generation && auth.canResearch) data.value = response
  } catch (cause) {
    if (mounted && current === generation && auth.canResearch) error.value = asFailure(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
async function submit() {
  if (!mounted || loading.value || !auth.canResearch) return
  const parsed = researchQuestionSchema.safeParse(question.value)
  invalid.value = !parsed.success
  if (!parsed.success) return
  if (route.query.question === parsed.data) return load()
  await navigateTo({ path: '/research', query: researchAnswerUrl(parsed.data) })
}
async function adjust(candidate?: string) {
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
    question.value = typeof route.query.question === 'string' ? route.query.question : ''
    if (mounted) void load()
  },
  { immediate: true },
)
watch(
  () => auth.revision,
  () => {
    clear()
    question.value = ''
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
  <div>
    <div class="mx-auto max-w-[51rem]">
      <form
        class="research-composer relative rounded-2xl border border-slate-200 bg-white"
        @submit.prevent="submit"
      >
        <label for="research-question" class="sr-only">Deine Recherchefrage</label>
        <textarea
          id="research-question"
          ref="input"
          v-model="question"
          class="research-composer-input block w-full resize-none border-0 bg-transparent text-base leading-6 text-slate-900 placeholder:text-slate-500"
          rows="2"
          maxlength="2000"
          required
          placeholder="Frage zu Veranstaltungen, Orten oder Organisationen stellen …"
          :disabled="!ready"
          :aria-invalid="invalid"
          :aria-describedby="
            invalid ? 'research-question-help research-question-error' : 'research-question-help'
          "
          @keydown="onKeydown"
        />
        <div class="research-composer-actions absolute flex items-end gap-4">
          <span class="translate-y-2 text-xs tabular-nums text-slate-500" aria-hidden="true"
            >{{ question.length.toLocaleString('de-DE') }}/2.000</span
          >
          <button
            type="submit"
            class="research-send inline-flex h-12 w-12 items-center justify-center rounded-lg bg-blue-700 text-white shadow-soft hover:bg-blue-800 disabled:cursor-not-allowed"
            :disabled="!ready || loading || !question.trim()"
            :aria-busy="loading"
            aria-label="Antwort anzeigen"
          >
            <AppIcon :name="loading ? 'refresh' : 'send'" :size="20" />
            <span class="sr-only">{{ loading ? 'Wird ausgewertet …' : 'Antwort anzeigen' }}</span>
          </button>
        </div>
      </form>
      <p
        v-if="invalid"
        id="research-question-error"
        role="alert"
        class="mt-2 text-sm text-rose-700"
      >
        Bitte gib eine gültige Frage mit 1 bis 2.000 Zeichen ein.
      </p>
      <div
        v-if="!route.query.question"
        class="mt-4 text-center"
        role="group"
        aria-label="Beispiele für Fragen"
      >
        <p class="mb-2 text-sm text-slate-600">Beispiele für Fragen:</p>
        <div class="research-examples flex flex-wrap justify-center gap-x-3 gap-y-1">
          <button
            v-for="example in examples"
            :key="example"
            type="button"
            class="research-example inline-flex min-h-11 max-w-full items-center gap-4 px-4 py-2 text-left text-sm text-slate-700"
            :disabled="!ready || loading"
            @click="useExample(example)"
          >
            {{ example }}<AppIcon name="arrow" :size="16" class="text-blue-700" />
          </button>
        </div>
      </div>
      <div class="mt-1 flex min-h-8 flex-wrap items-center justify-center gap-x-5 gap-y-1">
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
            Bis zu 2.000 Zeichen. Strg/⌘ + Enter zum Absenden. Die Frage wird im kopierbaren Link
            gespeichert.
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
    <div v-if="loading || error || data" class="mx-auto mt-6 max-w-5xl space-y-4">
      <RequestState
        :loading="loading"
        loading-message="Frage wird ausgewertet …"
        :error="error"
        @retry="load"
      />
      <ResearchQueryAnswer v-if="data" :response="data" @adjust="adjust" />
    </div>
  </div>
</template>

<style scoped>
@reference '../assets/css/main.css';
.research-composer {
  min-height: 116px;
  padding: 12px 20px;
  box-shadow: 0 4px 16px color-mix(in srgb, var(--color-blue-200) 22%, transparent);
}
.research-composer-input {
  height: 90px;
  padding-right: 68px;
  padding-bottom: 24px;
}
.research-composer-actions {
  right: 16px;
  bottom: 20px;
}
.research-example {
  position: relative;
  isolation: isolate;
}
.research-example::before {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 4px 0;
  border: 1px solid var(--color-slate-200);
  border-radius: 9999px;
  background: white;
  box-shadow: var(--shadow-soft);
}
.research-example:hover::before {
  background: var(--color-blue-50);
  border-color: var(--color-blue-200);
}
.research-composer:focus-within {
  @apply border-blue-400 ring-2 ring-blue-100;
}
</style>
