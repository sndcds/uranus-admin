import ResearchSqlEditorModal from '../../app/components/sql/ResearchSqlEditorModal.vue'
import SqlCodeEditor from '../../app/components/sql/SqlCodeEditor.vue'
import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  shallowRef,
  useTemplateRef,
  watch,
} from 'vue'
import ResearchNavigation from '../../app/components/ResearchNavigation.vue'
import ResearchHome from '../../app/pages/research/index.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import ResearchQuestion from '../../app/components/ResearchQuestion.vue'
import ResearchSearchPage from '../../app/pages/research/search.vue'
import ResearchQueryAnswer from '../../app/components/ResearchQueryAnswer.vue'
import RequestState from '../../app/components/RequestState.vue'
import { executionResponse, countQuestion } from '../fixtures/research-execution'
import { groupedExecutionResponse } from '../fixtures/research-grouping'
import { createAdminApi } from '../../app/utils/admin-api'
import { AdminApiError, failure } from '../../shared/errors'
import type { ResearchExecutionResponse } from '../../shared/contracts'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
function setup(question: unknown = countQuestion) {
  const route = reactive({
    path: '/research',
    query: { question } as Record<string, unknown>,
  })
  const auth = reactive({ canResearch: true, revision: 0 })
  const api = {
    researchQuery: vi.fn(),
    researchSuggestions: vi.fn(),
    researchSuggestionImpression: vi.fn().mockResolvedValue({ ok: true, receipt: null }),
    researchSuggestionSelect: vi
      .fn()
      .mockResolvedValue({ ok: true, receipt: '00000000-0000-4000-8000-000000000003' }),
  }
  const navigate = vi.fn(
    async (target: { path: string; query?: Record<string, unknown> } | string) => {
      route.path = typeof target === 'string' ? target : target.path
      route.query = typeof target === 'string' ? {} : (target.query ?? {})
    },
  )
  for (const [name, value] of Object.entries({
    computed,
    nextTick,
    onBeforeUnmount,
    onMounted,
    ref,
    shallowRef,
    useTemplateRef,
    watch,
    useRoute: () => route,
    useAuthStore: () => auth,
    useNuxtApp: () => ({ $adminApi: api }),
    navigateTo: navigate,
    definePageMeta: () => {},
    useHead: () => {},
  }))
    vi.stubGlobal(name, value)
  const global = {
    components: { ResearchQuestion, ResearchQueryAnswer, RequestState, EmptyState },
    stubs: {
      PageHeader: true,
      ResearchHeroIllustration: true,
      CopyValueButton: true,
      ResearchResult: true,
      AppIcon: true,
      NuxtLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
    },
  }
  return { route, auth, api, navigate, global }
}
function deferred() {
  let resolve!: (value: ResearchExecutionResponse) => void
  let reject!: (value: unknown) => void
  const promise = new Promise<ResearchExecutionResponse>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
it('loads on URL state, cancels stale work and discards late success/failure', async () => {
  const ctx = setup()
  const first = deferred()
  const second = deferred()
  const third = deferred()
  ctx.api.researchQuery
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise)
    .mockReturnValueOnce(third.promise)
  const view = mount(ResearchQuestion, { global: ctx.global })
  await nextTick()
  expect(view.text()).toContain('Frage wird ausgewertet')
  expect(view.get('button[type=submit]').attributes('disabled')).toBeDefined()
  const signal = ctx.api.researchQuery.mock.calls[0]![1] as AbortSignal
  ctx.route.query.question = 'Zweite Frage'
  await nextTick()
  expect(signal.aborted).toBe(true)
  ctx.route.query.question = 'Dritte Frage'
  await nextTick()
  first.resolve(executionResponse())
  second.reject(new AdminApiError(failure(503)))
  const current = executionResponse()
  current.result = { kind: 'count', metric: 'event_count', value: 7 }
  current.answer_text = 'Für diese Auswahl wurden 7 Veranstaltungen gezählt.'
  third.resolve(current)
  await flushPromises()
  expect(view.text()).toContain('7 Veranstaltungen')
  expect(view.text()).not.toContain('123 Veranstaltungen')
  expect(view.text()).not.toContain('fehlgeschlagen')
  expect(view.text()).not.toContain('Frage wird ausgewertet')
  view.unmount()
  expect((ctx.api.researchQuery.mock.calls[2]![1] as AbortSignal).aborted).toBe(true)
})
it('clears protected answers on auth loss and ignores late responses', async () => {
  const ctx = setup()
  const pending = deferred()
  ctx.api.researchQuery.mockReturnValue(pending.promise)
  const view = mount(ResearchQuestion, { global: ctx.global })
  ctx.auth.canResearch = false
  ctx.auth.revision++
  await nextTick()
  pending.resolve(executionResponse())
  await flushPromises()
  expect(view.find('[data-testid=research-count]').exists()).toBe(false)
  expect(view.get('textarea').element.value).toBe('')
  expect((ctx.api.researchQuery.mock.calls[0]![1] as AbortSignal).aborted).toBe(true)
  view.unmount()
})
it('shows a stable error without fallback and allows an explicit retry', async () => {
  const ctx = setup()
  const retried = executionResponse()
  retried.answer_text = 'Frische Antwort vom Backend nach dem Wiederholen.'
  ctx.api.researchQuery
    .mockRejectedValueOnce(new AdminApiError(failure(422, 'research_execution_unsupported')))
    .mockResolvedValueOnce(retried)
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  expect(view.text()).toContain('Diese Auswertung wird derzeit nicht unterstützt.')
  await view
    .findAll('button')
    .find((button) => button.text() === 'Erneut versuchen')!
    .trigger('click')
  await flushPromises()
  expect(view.text()).toContain('123 Veranstaltungen')
  expect(view.get('[data-testid=research-answer-summary]').text()).toBe(retried.answer_text)
  expect(ctx.api.researchQuery).toHaveBeenCalledTimes(2)
  view.unmount()
})
it('clarification only edits the question until explicitly resubmitted', async () => {
  const response = executionResponse('needs_clarification')
  const ctx = setup(response.query)
  ctx.api.researchQuery.mockResolvedValue(response)
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  await view
    .findAll('button')
    .find((button) => button.text() === 'Neustadt in Holstein')!
    .trigger('click')
  expect(view.get('textarea').element.value).toBe('Neustadt in Holstein')
  expect(ctx.api.researchQuery).toHaveBeenCalledTimes(1)
  await view.get('form').trigger('submit')
  expect(ctx.navigate).toHaveBeenCalledWith({
    path: '/research',
    query: { question: view.get('textarea').element.value },
  })
  view.unmount()
})
it.each([undefined, ['one', 'two'], 'x'.repeat(2001)])(
  'does not execute absent or invalid URL question',
  async (question) => {
    const ctx = setup('placeholder')
    ctx.route.query.question = question
    const view = mount(ResearchQuestion, { global: ctx.global })
    await flushPromises()
    expect(ctx.api.researchQuery).not.toHaveBeenCalled()
    expect(view.find('[role=alert]').exists()).toBe(question !== undefined)
    view.unmount()
  },
)
it('keeps classic and semantic search on their existing page without mode tabs', () => {
  const ctx = setup()
  ctx.route.query = { q: 'Kultur', search_mode: 'semantic' }
  const view = mount(ResearchSearchPage, {
    global: { ...ctx.global, stubs: { ...ctx.global.stubs, ResearchSearch: true } },
  })
  expect(view.find('research-search-stub').exists()).toBe(true)
  expect(view.findComponent(ResearchQuestion).exists()).toBe(false)
  expect(view.text()).not.toContain('Frage beantworten')
  expect(view.get('a').attributes('href')).toBe('/research')
  view.unmount()
})
it('redirects legacy answer links with the original query, leaving other search URLs alone', () => {
  const ctx = setup()
  const meta = vi.fn()
  vi.stubGlobal('definePageMeta', meta)
  const view = mount(ResearchSearchPage, {
    global: { ...ctx.global, stubs: { ...ctx.global.stubs, ResearchSearch: true } },
  })
  const middleware = meta.mock.calls[0]![0].middleware
  for (const query of [
    { mode: 'answer' },
    { question: countQuestion },
    { mode: 'answer', question: ['one', 'two'] },
  ]) {
    middleware({ query })
    expect(ctx.navigate).toHaveBeenLastCalledWith(
      { path: '/research', query },
      { replace: true, redirectCode: 302 },
    )
  }
  ctx.navigate.mockClear()
  middleware({ query: { q: 'Kultur', search_mode: 'semantic' } })
  middleware({ query: {} })
  expect(ctx.navigate).not.toHaveBeenCalled()
  view.unmount()
})
it('opens the homepage composer directly and renders its answer in the same workspace', async () => {
  const ctx = setup()
  ctx.route.query = {}
  ctx.api.researchQuery.mockResolvedValue(executionResponse())
  const view = mount(ResearchHome, { global: ctx.global })
  await flushPromises()
  expect(view.get('h2').text()).toContain('Was möchtest du über Kultur')
  expect(view.text()).not.toContain('Frage beantworten')
  expect(view.findAll('textarea')).toHaveLength(1)
  expect(ctx.api.researchQuery).not.toHaveBeenCalled()
  for (const destination of ['events', 'venues', 'organizations', 'map']) {
    expect(view.find(`a[href="/research/${destination}"]`).exists()).toBe(false)
  }
  await view.get('textarea').setValue(countQuestion)
  await view.get('form').trigger('submit')
  await flushPromises()
  expect(ctx.route.path).toBe('/research')
  expect(ctx.api.researchQuery).toHaveBeenCalledWith(
    countQuestion,
    expect.any(AbortSignal),
    undefined,
    undefined,
  )
  expect(view.text()).toContain('123 Veranstaltungen')
  expect(view.get('a[href="/research/search"]').text()).toBe('Klassische Suche')
  view.unmount()
})
it('examples populate and focus the composer without execution; keyboard submits once', async () => {
  const ctx = setup()
  ctx.route.query = {}
  const pending = deferred()
  ctx.api.researchQuery.mockReturnValue(pending.promise)
  const view = mount(ResearchQuestion, { global: ctx.global, attachTo: document.body })
  await flushPromises()
  const example = view.get('[role="group"] button')
  await example.trigger('click')
  expect(view.get('textarea').element.value).toBe(example.text())
  expect(document.activeElement).toBe(view.get('textarea').element)
  expect(ctx.api.researchQuery).not.toHaveBeenCalled()
  await view.get('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })
  await view.get('textarea').trigger('keydown', { key: 'Enter', ctrlKey: true, isComposing: true })
  expect(ctx.api.researchQuery).not.toHaveBeenCalled()
  await view.get('textarea').trigger('keydown', { key: 'Enter' })
  await flushPromises()
  await view.get('textarea').trigger('keydown', { key: 'Enter', metaKey: true })
  await view.get('form').trigger('submit')
  expect(ctx.api.researchQuery).toHaveBeenCalledTimes(1)
  expect(view.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  expect(view.text()).toContain('Frage wird ausgewertet')
  pending.resolve(executionResponse())
  await flushPromises()
  view.unmount()
})
it('keeps empty records as a successful answer', async () => {
  const ctx = setup()
  const response = executionResponse('records')
  if (response.result.kind !== 'records') throw new Error('fixture')
  response.result.items = []
  response.result.total = 0
  response.answer_text = 'Für diese Frage wurden keine passenden Ergebnisse gefunden.'
  ctx.api.researchQuery.mockResolvedValue(response)
  const view = mount(ResearchHome, { global: ctx.global })
  await flushPromises()
  expect(view.text()).toContain('Keine passenden Datensätze gefunden.')
  expect(view.find('[role="alert"]').exists()).toBe(false)
  expect(view.get('section[aria-label="Antwort"]').exists()).toBe(true)
  view.unmount()
})
it('shows an unavailable API as an error with the question still visible', async () => {
  const ctx = setup()
  ctx.api.researchQuery.mockRejectedValue(new AdminApiError(failure(503)))
  const view = mount(ResearchHome, { global: ctx.global })
  await flushPromises()
  expect(view.get('textarea').element.value).toBe(countQuestion)
  expect(view.findComponent(ResearchQueryAnswer).exists()).toBe(false)
  expect(view.text()).toContain('Erneut versuchen')
  view.unmount()
})

it.each([
  ['/research', '/research'],
  ['/research/search', '/research'],
  ['/research/events', '/research/events'],
  ['/research/venues/venue-id', '/research/venues'],
])('marks only the relevant navigation item active on %s', (path, active) => {
  const ctx = setup()
  ctx.route.path = path
  const view = mount(ResearchNavigation, { global: ctx.global })
  expect(view.findAll('[aria-current="page"]')).toHaveLength(1)
  expect(view.get('[aria-current="page"]').attributes('href')).toBe(active)
  expect(view.get('a').attributes('href')).toBe('/research')
  view.unmount()
})
it('keeps a missing taxonomy match as clarification on the homepage', async () => {
  const ctx = setup()
  const response = executionResponse('needs_clarification')
  if (response.result.kind !== 'needs_clarification') throw new Error('fixture')
  Object.assign(response.result, {
    reason: 'no_match',
    field: 'genre_queries',
    query: 'Jazz',
    candidates: [],
    planner_state: null,
  })
  ctx.api.researchQuery.mockResolvedValue(response)
  const view = mount(ResearchHome, { global: ctx.global })
  await flushPromises()
  expect(view.text()).toContain('Keine eindeutige Zuordnung für „Jazz“')
  expect(view.text()).toContain('Frage präzisieren')
  expect(view.text()).not.toContain('Abruf fehlgeschlagen')
  view.unmount()
})

const learned = {
  request_id: '00000000-0000-4000-8000-000000000001',
  suggestions: [
    {
      id: '00000000-0000-4000-8000-000000000002',
      query: 'Welche Organisation hat die meisten Veranstaltungen?',
      position: 1,
    },
  ],
}
it('debounces, reports rendered impressions once, navigates and selects with Enter', async () => {
  vi.useFakeTimers()
  const ctx = setup(undefined)
  ctx.route.query = {}
  ctx.api.researchSuggestions.mockResolvedValue(learned)
  ctx.api.researchQuery.mockResolvedValue(executionResponse())
  const view = mount(ResearchQuestion, { global: ctx.global })
  const input = view.get('textarea')
  await nextTick() // The homepage enables its composer after hydration.
  await input.trigger('focus')
  await input.setValue('welche org')
  await vi.advanceTimersByTimeAsync(199)
  expect(ctx.api.researchSuggestions).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  await flushPromises()
  expect(view.find('[role=listbox]').exists()).toBe(true)
  expect(input.attributes('aria-expanded')).toBe('true')
  expect(ctx.api.researchSuggestionImpression).toHaveBeenCalledTimes(1)
  await input.trigger('keydown', { key: 'ArrowDown' })
  expect(input.attributes('aria-activedescendant')).toBe('research-suggestion-0')
  await input.trigger('keydown', { key: 'ArrowUp' })
  await input.trigger('keydown', { key: 'Enter', shiftKey: true })
  expect(ctx.api.researchSuggestionSelect).not.toHaveBeenCalled()
  expect(ctx.api.researchQuery).not.toHaveBeenCalled()
  await input.trigger('keydown', { key: 'Enter' })
  await flushPromises()
  expect(ctx.api.researchSuggestionSelect).toHaveBeenCalledTimes(1)
  expect(ctx.api.researchQuery).toHaveBeenCalledWith(
    learned.suggestions[0]!.query,
    expect.any(AbortSignal),
    '00000000-0000-4000-8000-000000000003',
    undefined,
  )
  expect(view.find('[role=listbox]').exists()).toBe(false)
  view.unmount()
})
it('cancels stale responses, Escape closes and auth loss clears suggestions', async () => {
  vi.useFakeTimers()
  const ctx = setup()
  ctx.route.query = {}
  let resolve!: (value: typeof learned) => void
  ctx.api.researchSuggestions
    .mockReturnValueOnce(
      new Promise((r) => {
        resolve = r
      }),
    )
    .mockResolvedValue(learned)
  const view = mount(ResearchQuestion, { global: ctx.global })
  const input = view.get('textarea')
  await nextTick() // The homepage enables its composer after hydration.
  await input.trigger('focus')
  await input.setValue('welche')
  await vi.advanceTimersByTimeAsync(200)
  const signal = ctx.api.researchSuggestions.mock.calls[0]![1] as AbortSignal
  await input.setValue('welche org')
  expect(signal.aborted).toBe(true)
  resolve(learned)
  await flushPromises()
  expect(ctx.api.researchSuggestionImpression).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(200)
  await flushPromises()
  await input.trigger('keydown', { key: 'Escape' })
  expect(view.find('[role=listbox]').exists()).toBe(false)
  expect(ctx.api.researchSuggestionImpression).toHaveBeenCalledTimes(1)
  await input.setValue('welche orga')
  await vi.advanceTimersByTimeAsync(200)
  ctx.auth.canResearch = false
  ctx.auth.revision++
  await nextTick()
  expect(view.find('[role=listbox]').exists()).toBe(false)
  view.unmount()
})
it('mouse selection executes even when telemetry fails and does not select twice', async () => {
  vi.useFakeTimers()
  const ctx = setup()
  ctx.route.query = {}
  ctx.api.researchSuggestions.mockResolvedValue(learned)
  ctx.api.researchSuggestionSelect.mockRejectedValue(new Error('offline'))
  ctx.api.researchQuery.mockResolvedValue(executionResponse())
  const view = mount(ResearchQuestion, { global: ctx.global })
  await nextTick() // The homepage enables its composer after hydration.
  await view.get('textarea').trigger('focus')
  await view.get('textarea').setValue('welche org')
  await vi.advanceTimersByTimeAsync(200)
  await flushPromises()
  const option = view.get('[role=option]')
  await option.trigger('click')
  await flushPromises()
  expect(ctx.api.researchSuggestionSelect).toHaveBeenCalledTimes(1)
  expect(ctx.api.researchQuery).toHaveBeenCalledWith(
    learned.suggestions[0]!.query,
    expect.any(AbortSignal),
    undefined,
    undefined,
  )
  view.unmount()
})

it.each(['ctrlKey', 'metaKey'])(
  'submits the typed homepage question with %s+Enter even when a suggestion is active',
  async (modifier) => {
    vi.useFakeTimers()
    const ctx = setup()
    ctx.route.query = {}
    ctx.api.researchSuggestions.mockResolvedValue(learned)
    ctx.api.researchQuery.mockResolvedValue(executionResponse())
    const view = mount(ResearchHome, { global: ctx.global })
    const input = view.get('textarea')
    await nextTick() // The homepage enables its composer after hydration.
    await input.trigger('focus')
    await input.setValue('welche org')
    await vi.advanceTimersByTimeAsync(200)
    await flushPromises()
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter', [modifier]: true })
    await flushPromises()
    expect(ctx.api.researchSuggestionSelect).not.toHaveBeenCalled()
    expect(ctx.api.researchQuery).toHaveBeenCalledExactlyOnceWith(
      'welche org',
      expect.any(AbortSignal),
      undefined,
      undefined,
    )
    expect(ctx.route.path).toBe('/research')
    expect(view.find('[role=listbox]').exists()).toBe(false)
    view.unmount()
  },
)

function locationClarification() {
  const response = executionResponse()
  response.answer_text = null
  response.result = {
    kind: 'needs_clarification',
    reason: 'planner',
    planner_state: 'needs_location',
    field: null,
    query: null,
    candidates: [],
  }
  return response
}
it('requests browser location only on click, resubmits context and reuses it without URL coordinates', async () => {
  const query = 'Was ist heute in meiner Nähe?'
  const ctx = setup(query)
  const getCurrentPosition = vi.fn()
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
  ctx.api.researchQuery
    .mockResolvedValueOnce(locationClarification())
    .mockResolvedValue(executionResponse())
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  expect(getCurrentPosition).not.toHaveBeenCalled()
  expect(view.text()).toContain('Standort benötigt')
  await view
    .findAll('button')
    .find((b) => b.text() === 'Standort freigeben')!
    .trigger('click')
  expect(getCurrentPosition).toHaveBeenCalledOnce()
  getCurrentPosition.mock.calls[0]![0]({ coords: { latitude: 54.79, longitude: 9.43 } })
  await flushPromises()
  expect(ctx.api.researchQuery).toHaveBeenLastCalledWith(
    query,
    expect.any(AbortSignal),
    undefined,
    { latitude: 54.79, longitude: 9.43, source: 'browser_geolocation' },
  )
  expect(ctx.route.query).toEqual({ question: query })
  expect(ctx.navigate).not.toHaveBeenCalled()
  ctx.route.query.question = 'Welche Veranstaltungen sind bei mir?'
  await flushPromises()
  expect(ctx.api.researchQuery.mock.calls.at(-1)![3]).toEqual({
    latitude: 54.79,
    longitude: 9.43,
    source: 'browser_geolocation',
  })
  expect(getCurrentPosition).toHaveBeenCalledOnce()
  ctx.auth.revision++
  await nextTick()
  ctx.route.query.question = 'Was ist hier los?'
  await flushPromises()
  expect(ctx.api.researchQuery.mock.calls.at(-1)![3]).toBeUndefined()
  view.unmount()
})
it('offers manual fallback on denied location and resubmits the original question', async () => {
  const ctx = setup('Was ist hier los?')
  const getCurrentPosition = vi.fn()
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
  ctx.api.researchQuery
    .mockResolvedValueOnce(locationClarification())
    .mockResolvedValue(executionResponse())
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  await view
    .findAll('button')
    .find((b) => b.text() === 'Standort freigeben')!
    .trigger('click')
  getCurrentPosition.mock.calls[0]![1]({ code: 1 })
  await nextTick()
  expect(view.text()).toContain('Bitte einen Ort manuell eingeben')
  await view.get('#research-manual-location').setValue('Nordermarkt Flensburg')
  await view
    .get('#research-manual-location')
    .element.closest('form')!
    .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(ctx.api.researchQuery).toHaveBeenLastCalledWith(
    'Was ist hier los?',
    expect.any(AbortSignal),
    undefined,
    { source: 'manual', display_name: 'Nordermarkt Flensburg' },
  )
  expect(ctx.route.query).toEqual({ question: 'Was ist hier los?' })
  view.unmount()
})
it('discards late location callbacks after logout', async () => {
  const ctx = setup('Was ist hier los?')
  const getCurrentPosition = vi.fn()
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
  ctx.api.researchQuery.mockResolvedValue(locationClarification())
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  await view
    .findAll('button')
    .find((b) => b.text() === 'Standort freigeben')!
    .trigger('click')
  ctx.auth.canResearch = false
  ctx.auth.revision++
  await nextTick()
  getCurrentPosition.mock.calls[0]![0]({ coords: { latitude: 54.79, longitude: 9.43 } })
  await flushPromises()
  expect(ctx.api.researchQuery).toHaveBeenCalledOnce()
  view.unmount()
})

it('reuses the canonical reverse label on the next nearby query', async () => {
  const ctx = setup('Was ist hier los?')
  const getCurrentPosition = vi.fn()
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
  const resolved = executionResponse()
  resolved.resolution = [
    {
      field: 'location_context',
      query: 'Aktueller Standort',
      target: { entity_type: 'place', id: 'current-location', label: 'Flensburg' },
    },
  ]
  ctx.api.researchQuery.mockResolvedValueOnce(locationClarification()).mockResolvedValue(resolved)
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  await view
    .findAll('button')
    .find((b) => b.text() === 'Standort freigeben')!
    .trigger('click')
  getCurrentPosition.mock.calls[0]![0]({ coords: { latitude: 54.79, longitude: 9.43 } })
  await flushPromises()
  ctx.route.query.question = 'Was gibt es in meiner Nähe?'
  await flushPromises()
  expect(ctx.api.researchQuery.mock.calls.at(-1)![3]).toEqual({
    latitude: 54.79,
    longitude: 9.43,
    source: 'browser_geolocation',
    display_name: 'Flensburg',
  })
  expect(getCurrentPosition).toHaveBeenCalledOnce()
  view.unmount()
})

it('renders multidimensional results through the normal question URL and validated API', async () => {
  const response = groupedExecutionResponse()
  const ctx = setup(response.query)
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(response)))
  const api = createAdminApi(fetcher)
  ctx.api.researchQuery.mockImplementation(api.researchQuery)
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  expect(ctx.api.researchQuery).toHaveBeenCalledOnce()
  expect(fetcher.mock.calls[0]![0]).toBe('/api/admin/api/v1/research/query')
  expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toEqual({ query: response.query })
  expect(api).not.toHaveProperty('researchGroupedQuery')
  const table = view.get('table[aria-label="Mehrdimensionale Auswertung"]')
  expect(table.findAll('thead th').map((cell) => cell.text())).toEqual([
    'Veranstaltungstyp',
    'Monat',
    'Termine',
  ])
  expect(table.findAll('tbody th, tbody td').map((cell) => cell.text())).toEqual([
    'Konzert',
    'September',
    '7',
  ])
  expect(view.text()).toContain('So wurde die Frage verstanden')
  expect(view.text()).toContain('Laufzeit (ms)')
  view.unmount()
})

it.each(['count', 'records', 'grouped', 'clarification', 'error', 'unsupported', 'semantic'])(
  'keeps the same single composer through loading and %s',
  async (state) => {
    const ctx = setup()
    ctx.route.query = {}
    const pending = deferred()
    ctx.api.researchQuery.mockReturnValue(pending.promise)
    const view = mount(ResearchHome, { global: ctx.global })
    await flushPromises()
    const input = view.get('textarea').element
    const form = view.get('.research-composer').element
    expect(view.findAll('textarea')).toHaveLength(1)
    await view.get('textarea').setValue(countQuestion)
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(view.get('textarea').element).toBe(input)
    expect(view.get('form').attributes('aria-busy')).toBe('true')
    if (state === 'error' || state === 'unsupported') {
      pending.reject(
        new AdminApiError(
          failure(
            state === 'error' ? 503 : 422,
            state === 'unsupported' ? 'research_execution_unsupported' : undefined,
          ),
        ),
      )
    } else {
      pending.resolve(
        state === 'grouped'
          ? groupedExecutionResponse()
          : executionResponse(
              state === 'clarification'
                ? 'needs_clarification'
                : state === 'count'
                  ? 'count'
                  : 'records',
              state === 'semantic',
            ),
      )
    }
    await flushPromises()
    expect(view.findAll('textarea')).toHaveLength(1)
    expect(view.get('textarea').element).toBe(input)
    expect(view.get('.research-composer').element).toBe(form)
    expect(input.value).toBe(countQuestion)
    expect(view.get('.research-composer-footer textarea').exists()).toBe(true)
    expect(view.find('.research-question-content textarea').exists()).toBe(false)
    expect(view.findAll('input[type=file], nav textarea, aside textarea')).toHaveLength(0)
    expect(view.get('.research-composer-container').classes()).toEqual(
      expect.arrayContaining(['mx-auto', 'w-full', 'research-conversation-width']),
    )
    expect(view.get('.research-question-content').classes()).toContain('pb-6')
    view.unmount()
  },
)

it('retry submits exactly the failed turn without overwriting an unsubmitted draft', async () => {
  const ctx = setup()
  ctx.api.researchQuery
    .mockRejectedValueOnce(new AdminApiError(failure(503)))
    .mockResolvedValueOnce(executionResponse())
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  const input = view.get('textarea').element
  await view.get('textarea').setValue('Neue Frage')
  await view
    .findAll('button')
    .find((b) => b.text() === 'Erneut versuchen')!
    .trigger('click')
  await flushPromises()
  expect(ctx.api.researchQuery.mock.calls.at(-1)![0]).toBe(countQuestion)
  expect(view.get('textarea').element).toBe(input)
  expect(input.value).toBe('Neue Frage')
  view.unmount()
})

it('retains ordered turns, sends only the opaque token, and preserves an edited draft', async () => {
  const ctx = setup()
  ctx.route.query = {}
  const first = groupedExecutionResponse()
  first.conversation_id = 'a'.repeat(43)
  const pending = deferred()
  ctx.api.researchQuery
    .mockResolvedValueOnce(first)
    .mockReturnValueOnce(pending.promise)
    .mockResolvedValue(executionResponse())
  const view = mount(ResearchHome, { global: ctx.global })
  await flushPromises()
  await view.get('textarea').setValue(first.query)
  await view.get('form').trigger('submit')
  await flushPromises()
  expect(view.text()).not.toContain('Was möchtest du über Kultur')
  expect(view.text()).not.toContain('Kultur entdecken')
  await view.get('textarea').setValue('Und nur sonntags?')
  await view.get('form').trigger('submit')
  await flushPromises()
  expect(view.findAll('article')).toHaveLength(2)
  expect(view.findAllComponents(ResearchQueryAnswer)).toHaveLength(1)
  expect(ctx.api.researchQuery.mock.calls[1]![4]).toBe('a'.repeat(43))
  await view.get('textarea').setValue('Ein noch nicht abgesendeter Entwurf')
  pending.resolve(executionResponse())
  await flushPromises()
  expect(view.get('textarea').element.value).toBe('Ein noch nicht abgesendeter Entwurf')
  await view.get('textarea').setValue('Dritte Frage')
  await view.get('form').trigger('submit')
  await flushPromises()
  expect(view.findAll('[data-testid=research-user-question]').map((v) => v.text())).toEqual([
    first.query,
    'Und nur sonntags?',
    'Dritte Frage',
  ])
  expect(view.findAll('[data-testid=research-answer-summary]').map((item) => item.text())).toEqual([
    first.answer_text,
    executionResponse().answer_text,
    executionResponse().answer_text,
  ])
  expect(view.findAll('textarea')).toHaveLength(1)
  // Back/forward reveals existing history instead of re-executing or appending it.
  ctx.route.query.question = first.query
  await flushPromises()
  ctx.route.query.question = 'Dritte Frage'
  await flushPromises()
  expect(ctx.api.researchQuery).toHaveBeenCalledTimes(3)
  expect(view.findAll('article')).toHaveLength(3)
  await view
    .findAll('button')
    .find((b) => b.text() === 'Neue Recherche')!
    .trigger('click')
  await flushPromises()
  expect(view.findAll('article')).toHaveLength(0)
  expect(view.get('textarea').element.value).toBe('')
  expect(ctx.route.query).toEqual({})
  expect(view.text()).toContain('Was möchtest du über Kultur')
  view.unmount()
})

it('limits transcript memory to 20 and reloads only the URL question without context', async () => {
  const ctx = setup()
  ctx.api.researchQuery.mockResolvedValue(executionResponse())
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  for (let i = 1; i <= 21; i++) {
    await view.get('textarea').setValue(`Frage ${i}`)
    await view.get('form').trigger('submit')
    await flushPromises()
  }
  expect(view.findAll('article')).toHaveLength(20)
  expect(view.findAll('[data-testid=research-user-question]')[0]!.text()).toBe('Frage 2')
  view.unmount()
  const fresh = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  expect(fresh.findAll('article')).toHaveLength(1)
  expect(ctx.api.researchQuery.mock.calls.at(-1)![4]).toBeUndefined()
  fresh.unmount()
})

it('keeps clarification and historical SQL attached to their own immutable responses', async () => {
  const ctx = setup()
  const first = executionResponse()
  first.answer_text = 'Historische Backend-Antwort.'
  const second = executionResponse('needs_clarification')
  ctx.api.researchQuery.mockResolvedValueOnce(first).mockResolvedValueOnce(second)
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function () {
    this.open = true
  })
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  await view.get('textarea').setValue(second.query)
  await view.get('form').trigger('submit')
  await flushPromises()
  expect(view.findAll('article')).toHaveLength(2)
  const answers = view.findAllComponents(ResearchQueryAnswer)
  expect(answers[0]!.get('[data-testid=research-answer-summary]').text()).toBe(first.answer_text)
  expect(answers[1]!.find('[data-testid=research-answer-summary]').exists()).toBe(false)
  expect(answers[1]!.text()).toContain('Neustadt')
  await answers[0]!.get('button[aria-label="SQL Editor"]').trigger('click')
  await flushPromises()
  const editor = answers[0]!.getComponent(ResearchSqlEditorModal).getComponent(SqlCodeEditor)
  expect(editor.props('sql')).toBe(first.sql_provenance[0]!.sql)
  expect(editor.props('readonly')).toBe(true)
  expect(answers[1]!.findComponent(ResearchSqlEditorModal).exists()).toBe(false)
  view.unmount()
  vi.restoreAllMocks()
})

it('renders v12 district clarification labels without internal identities', async () => {
  const { modernPlanResponseSchema } = await import('../../shared/research-grouping')
  const { default: cases } = await import('../fixtures/research-modern-v12.json', {
    with: { type: 'json' },
  })
  const item = cases.find((c) => c.name === 'informal-district')!
  const response = executionResponse('needs_clarification')
  response.query = item.query
  response.plan = modernPlanResponseSchema.parse({
    kind: 'plan',
    schema_version: 'research-query-plan-v12',
    prompt_version: 'research-planner-v18',
    model: 'fixture',
    plan: item.plan,
    reference_date: '2026-10-03',
    timezone: 'Europe/Berlin',
    diagnostics: {
      request_id: 'a'.repeat(32),
      planner_intent: 'list',
      planner_model: 'fixture',
      planner_prompt_version: 'research-planner-v18',
      planner_ms: 1,
      total_ms: 1,
    },
  })
  response.result = {
    kind: 'needs_clarification',
    reason: 'ambiguous',
    field: 'area_query',
    query: 'Schleswig',
    planner_state: null,
    candidates: [
      {
        entity_type: 'area',
        id: '00000000-0000-4000-8000-000000000991',
        label: 'Kreis Schleswig-Flensburg',
      },
      {
        entity_type: 'area',
        id: '00000000-0000-4000-8000-000000000992',
        label: 'Kreis Schleswig (historisch)',
      },
    ],
  }
  const ctx = setup(response.query)
  ctx.api.researchQuery.mockResolvedValue(response)
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  expect(view.text()).toContain('Kreis Schleswig-Flensburg')
  expect(view.text()).toContain('Kreis Schleswig (historisch)')
  expect(view.text()).not.toMatch(
    /Ahneby|Arnis|Ausacker|Bollingstedt|Boren|00000000-0000|expected_level|area_level/,
  )
  view.unmount()
})

it('renders social replies as ordinary text and preserves the opaque conversation handle', async () => {
  const ctx = setup()
  ctx.route.query = {}
  const token = 'b'.repeat(43)
  ctx.api.researchQuery.mockResolvedValue({
    kind: 'conversation',
    answer_text: 'Gerne.',
    language: 'de',
    conversation_id: token,
    interaction: { kind: 'acknowledgement', conversation: { act: 'acknowledge', reason: null } },
  })
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  await view.get('textarea').setValue('danke')
  await view.get('form').trigger('submit')
  await flushPromises()
  expect(view.get('[data-testid=research-conversation-answer]').text()).toBe('Gerne.')
  expect(view.findComponent(ResearchQueryAnswer).exists()).toBe(false)
  expect(view.text()).not.toContain('Frage präzisieren')
  await view.get('textarea').setValue('und morgen?')
  await view.get('form').trigger('submit')
  await flushPromises()
  expect(ctx.api.researchQuery.mock.calls[1]![4]).toBe(token)
  ctx.auth.revision++
  await nextTick()
  expect(view.find('[data-testid=research-conversation-answer]').exists()).toBe(false)
  view.unmount()
})
