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
  permalink.value = window.location.href
  if (!auth.canResearch || route.query.question === undefined) return
  const parsed = researchAnswerQuery(route.query)
  if (!parsed.success) {
    invalid.value = true
    return
  }
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
  const parsed = researchQuestionSchema.safeParse(question.value)
  invalid.value = !parsed.success
  if (!parsed.success) return
  if (route.query.question === parsed.data) return load()
  await navigateTo({ path: '/research/search', query: researchAnswerUrl(parsed.data) })
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
  void load()
})
onBeforeUnmount(() => {
  mounted = false
  clear()
})
</script>
<template>
  <div class="space-y-3">
    <PageHeader
      title="Frage beantworten"
      description="Stelle eine vollständige Frage zu Veranstaltungen, Orten oder Organisationen."
      compact-actions
    >
      <template #actions
        ><CopyValueButton
          :value="permalink"
          label="Frage-Link"
          button-text="Link kopieren"
          variant="button"
      /></template>
    </PageHeader>
    <form class="space-y-2 rounded-lg border border-slate-200 p-3" @submit.prevent="submit">
      <label for="research-question" class="text-sm font-medium">Deine Recherchefrage</label>
      <textarea
        id="research-question"
        ref="input"
        v-model="question"
        class="input min-h-20"
        maxlength="2000"
        required
        placeholder="Wie viele Veranstaltungen gab es in Flensburg im August?"
        :aria-invalid="invalid"
        aria-describedby="research-question-help"
      />
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p id="research-question-help" class="text-xs text-slate-600">
          Bis zu 2.000 Zeichen. Die Frage wird im kopierbaren Link gespeichert.
        </p>
        <button class="button-primary" :disabled="loading || !question.trim()">
          Antwort anzeigen
        </button>
      </div>
    </form>
    <p v-if="invalid" role="alert" class="text-sm text-rose-700">
      Bitte gib eine gültige Frage mit 1 bis 2.000 Zeichen ein.
    </p>
    <RequestState
      :loading="loading"
      loading-message="Frage wird ausgewertet …"
      :error="error"
      @retry="load"
    />
    <ResearchQueryAnswer v-if="data" :response="data" @adjust="adjust" />
  </div>
</template>
