<script setup lang="ts">
import {
  conversationContext,
  MAX_RESEARCH_TURNS,
  type ResearchTurn,
} from '~/utils/research-conversation'
import type { ResearchConversationContext } from '#shared/research-conversation'
import ResearchComposer from './ResearchComposer.vue'
import { researchQuestionSchema } from '#shared/contracts'
import { asFailure } from '#shared/errors'
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
const turns = shallowRef<ResearchTurn[]>([])
const activeId = ref<number | null>(null)
const activeTurn = computed(() => turns.value.find((turn) => turn.id === activeId.value))
const data = computed(() => activeTurn.value?.response ?? null)
const content = useTemplateRef('content')
let nextId = 0
let nearBottom = true
let draftContext: ResearchConversationContext | undefined
function onScroll() {
  const el = content.value
  if (el) nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160
}
async function reveal(id: number, force = false) {
  await nextTick()
  const el = content.value
  const turn = el?.querySelector<HTMLElement>(`[data-turn-id="${id}"]`)
  if (el && turn && (force || nearBottom)) {
    el.scrollTop += turn.getBoundingClientRect().top - el.getBoundingClientRect().top
  }
}
function update(id: number, patch: Partial<ResearchTurn>) {
  turns.value = turns.value.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn))
}
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
  if (activeTurn.value?.state === 'loading') {
    update(activeTurn.value.id, { state: 'cancelled', error: undefined })
  }
  loading.value = false
}
async function load(turn: ResearchTurn | undefined = activeTurn.value) {
  if (!turn || loading.value || !auth.canResearch) return
  autosuggest.close()
  clear()
  activeId.value = turn.id
  const current = generation
  update(turn.id, { state: 'loading', error: undefined })
  controller = new AbortController()
  loading.value = true
  try {
    const receipt = selectionReceipt
    selectionReceipt = undefined
    const response = await $adminApi.researchQuery(
      turn.question,
      controller.signal,
      receipt,
      locationContext.value,
      ...(turn.context ? [turn.context] : []),
    )
    if (mounted && current === generation && auth.canResearch) {
      update(turn.id, {
        response,
        state: response.result.kind === 'needs_clarification' ? 'clarification' : 'success',
      })
      const canonical = response.resolution.find((item) => item.field === 'location_context')
        ?.target.label
      if (canonical && canonical.length <= 160 && locationContext.value?.latitude != null) {
        locationContext.value = { ...locationContext.value, display_name: canonical }
      }
      void reveal(turn.id)
    }
  } catch (cause) {
    if (mounted && current === generation && auth.canResearch)
      update(turn.id, { state: 'error', error: asFailure(cause) })
  } finally {
    if (current === generation) loading.value = false
  }
}
function append(query: string, context?: ResearchConversationContext) {
  const turn: ResearchTurn = { id: ++nextId, question: query, context, state: 'loading' }
  turns.value = [...turns.value, turn].slice(-MAX_RESEARCH_TURNS)
  activeId.value = turn.id
  void reveal(turn.id, true)
  void load(turn)
}
async function newConversation() {
  clear()
  location.cancel()
  locationContext.value = undefined
  turns.value = []
  activeId.value = null
  question.value = ''
  manualPlace.value = ''
  manualLocation.value = false
  draftContext = undefined
  selectionReceipt = undefined
  invalid.value = false
  permalink.value = null
  await navigateTo('/research')
  input.value?.focus()
}
function editDraft() {
  selectionReceipt = undefined
}
let ownNavigation = false
async function submit(receipt?: string) {
  if (!mounted || loading.value || submitting.value || !auth.canResearch) return
  autosuggest.close()
  selectionReceipt = receipt
  const parsed = researchQuestionSchema.safeParse(question.value)
  invalid.value = !parsed.success
  if (!parsed.success) return
  submitting.value = true
  try {
    const context = draftContext ?? conversationContext(turns.value)
    draftContext = undefined
    append(parsed.data, context)
    ownNavigation = true
    await navigateTo({ path: '/research', query: researchAnswerUrl(parsed.data) })
    permalink.value = window.location.href
  } finally {
    ownNavigation = false
    submitting.value = false
  }
}

async function adjust(turn: ResearchTurn, candidate?: string) {
  activeId.value = turn.id
  draftContext = turn.context
  question.value = turn.question
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
    const original = turn.question
    question.value =
      result?.kind === 'needs_clarification' && result.query && original.includes(result.query)
        ? original.replace(result.query, candidate)
        : `${original}\nGemeint ist: ${candidate}`
  }
  await nextTick()
  input.value?.focus()
}
function readRoute() {
  if (ownNavigation) return
  clear()
  location.cancel()
  manualLocation.value = false
  const parsed = researchAnswerQuery(route.query)
  invalid.value = route.query.question !== undefined && !parsed.success
  permalink.value = parsed.success ? window.location.href : null
  if (!parsed.success) return
  draftContext = undefined
  const existing = [...turns.value].reverse().find((turn) => turn.question === parsed.data)
  if (existing) {
    activeId.value = existing.id
    void reveal(existing.id, true)
    return
  }
  question.value = parsed.data
  permalink.value = window.location.href
  // Direct URL navigation is independent; never manufacture lost chat context.
  append(parsed.data)
}
watch(
  () => route.query.question,
  () => {
    if (mounted) readRoute()
  },
)
watch(
  () => auth.revision,
  () => {
    clear()
    selectionReceipt = undefined
    turns.value = []
    activeId.value = null
    draftContext = undefined
    question.value = ''
    manualPlace.value = ''
    permalink.value = null
  },
)
onMounted(() => {
  mounted = true
  ready.value = true
  readRoute()
})
onBeforeUnmount(() => {
  mounted = false
  clear()
})
</script>
<template>
  <div
    ref="content"
    class="research-question-workspace flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto"
    @scroll="onScroll"
  >
    <div class="research-question-content flex-1 px-1 pb-6 pt-2">
      <template v-if="!turns.length">
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
      </template>
      <div v-if="turns.length" class="research-conversation-width mx-auto w-full space-y-6">
        <div class="flex items-center justify-between gap-4">
          <p class="text-xs text-slate-500">
            Nur diese Sitzung · höchstens {{ MAX_RESEARCH_TURNS }} Beiträge
          </p>
          <button type="button" class="button" @click="newConversation">Neue Recherche</button>
        </div>
        <article
          v-for="turn in turns"
          :key="turn.id"
          :data-turn-id="turn.id"
          class="space-y-4"
          :aria-label="`Recherche ${turn.id}`"
        >
          <div class="flex justify-end">
            <p
              class="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-blue-50 px-4 py-3 text-slate-900"
              data-testid="research-user-question"
            >
              {{ turn.question }}
            </p>
          </div>
          <RequestState
            :loading="turn.state === 'loading'"
            loading-message="Frage wird ausgewertet …"
            :error="turn.error ?? null"
            @retry="load(turn)"
          />
          <ResearchQueryAnswer
            v-if="turn.response && !(turn.id === activeId && needsLocation)"
            :response="turn.response"
            @adjust="adjust(turn, $event)"
          />
          <p v-if="turn.state === 'cancelled'" class="text-sm text-slate-500">
            Auswertung abgebrochen.
          </p>
          <button
            v-if="turn.state === 'error' || turn.state === 'cancelled'"
            class="action-link"
            @click="adjust(turn)"
          >
            Frage bearbeiten
          </button>
          <section
            v-if="turn.id === activeId && (needsLocation || manualLocation)"
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
                @click="location.locate(() => load())"
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
              <button
                type="submit"
                class="button-primary"
                :disabled="loading || !manualPlace.trim()"
              >
                Ort verwenden
              </button>
            </form>
          </section>
        </article>
      </div>
      <div class="research-conversation-width mx-auto w-full">
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
    <footer class="research-composer-footer sticky bottom-0 z-20 mt-auto shrink-0 px-1 pt-4">
      <div class="research-composer-container research-conversation-width relative mx-auto w-full">
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
          @input="editDraft"
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
.research-conversation-width {
  max-width: var(--research-conversation-width, 64rem);
}
.research-question-workspace {
  scrollbar-gutter: stable both-edges;
  scrollbar-width: thin;
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
