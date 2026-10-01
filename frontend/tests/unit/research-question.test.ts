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
  expect(view.get('button').attributes('disabled')).toBeDefined()
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
  ctx.api.researchQuery
    .mockRejectedValueOnce(new AdminApiError(failure(422, 'research_execution_unsupported')))
    .mockResolvedValueOnce(executionResponse())
  const view = mount(ResearchQuestion, { global: ctx.global })
  await flushPromises()
  expect(view.text()).toContain('Diese Auswertung wird derzeit nicht unterstützt.')
  await view
    .findAll('button')
    .find((button) => button.text() === 'Erneut versuchen')!
    .trigger('click')
  await flushPromises()
  expect(view.text()).toContain('123 Veranstaltungen')
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
  expect(view.get('textarea').element.value).toContain('in Neustadt in Holstein im August')
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
  await view.get('textarea').setValue(countQuestion)
  await view.get('form').trigger('submit')
  await flushPromises()
  expect(ctx.route.path).toBe('/research')
  expect(ctx.api.researchQuery).toHaveBeenCalledWith(
    countQuestion,
    expect.any(AbortSignal),
    undefined,
  )
  expect(view.text()).toContain('123 Veranstaltungen')
  expect(view.get('a[href="/research/search"]').text()).toBe('Klassische Suche')
  for (const destination of ['events', 'venues', 'organizations', 'map']) {
    expect(view.find(`a[href="/research/${destination}"]`).exists()).toBe(true)
  }
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
  await view.get('textarea').trigger('keydown', { key: 'Enter' })
  await view.get('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })
  await view.get('textarea').trigger('keydown', { key: 'Enter', ctrlKey: true, isComposing: true })
  expect(ctx.api.researchQuery).not.toHaveBeenCalled()
  await view.get('textarea').trigger('keydown', { key: 'Enter', ctrlKey: true })
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
    )
    expect(ctx.route.path).toBe('/research')
    expect(view.find('[role=listbox]').exists()).toBe(false)
    view.unmount()
  },
)
