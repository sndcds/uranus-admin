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
import ResearchQuestion from '../../app/components/ResearchQuestion.vue'
import ResearchSearchPage from '../../app/pages/research/search.vue'
import ResearchQueryAnswer from '../../app/components/ResearchQueryAnswer.vue'
import RequestState from '../../app/components/RequestState.vue'
import { executionResponse, countQuestion } from '../fixtures/research-execution'
import { AdminApiError, failure } from '../../shared/errors'
import type { ResearchExecutionResponse } from '../../shared/contracts'

afterEach(() => vi.unstubAllGlobals())
function setup(question: unknown = countQuestion) {
  const route = reactive({
    path: '/research/search',
    query: { mode: 'answer', question } as Record<string, unknown>,
  })
  const auth = reactive({ canResearch: true, revision: 0 })
  const api = { researchQuery: vi.fn() }
  const navigate = vi.fn(
    async (target: { path: string; query?: Record<string, unknown> } | string) => {
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
    components: { ResearchQueryAnswer, RequestState },
    stubs: { PageHeader: true, CopyValueButton: true, EmptyState: true, ResearchResult: true },
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
    path: '/research/search',
    query: { mode: 'answer', question: view.get('textarea').element.value },
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
it('mode switching mounts exactly one path and preserves legacy semantic URLs', async () => {
  const ctx = setup()
  const view = mount(ResearchSearchPage, {
    global: {
      mocks: { navigateTo: ctx.navigate },
      stubs: { ResearchQuestion: true, ResearchSearch: true },
    },
  })
  expect(view.find('research-question-stub').exists()).toBe(true)
  expect(view.find('research-search-stub').exists()).toBe(false)
  await view.findAll('button')[1]!.trigger('click')
  await nextTick()
  expect(view.find('research-question-stub').exists()).toBe(false)
  expect(view.find('research-search-stub').exists()).toBe(true)
  ctx.route.query = { q: 'Kultur', search_mode: 'semantic' }
  await nextTick()
  expect(view.find('research-search-stub').exists()).toBe(true)
  await view.findAll('button')[0]!.trigger('click')
  await nextTick()
  expect(ctx.route.query).toEqual({ mode: 'answer' })
  expect(view.find('research-question-stub').exists()).toBe(true)
  view.unmount()
})
