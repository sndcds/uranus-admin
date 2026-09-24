import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import * as vue from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import Statistics from '../../app/pages/statistics.vue'
import Content from '../../app/components/statistics/EventContentStatistics.vue'
import Quality from '../../app/pages/quality.vue'
import QualityOverview from '../../app/components/QualityOverview.vue'
import TechnicalInfoBar from '../../app/components/TechnicalInfoBar.vue'
import RequestState from '../../app/components/RequestState.vue'
import EntityTimelineChart from '../../app/components/statistics/EntityTimelineChart.vue'
import { statisticsFixture } from '../fixtures/statistics'
import { eventContentFixture } from '../fixtures/event-content'
import { summary } from '../fixtures/api'
import { useDashboardStore } from '../../app/stores/dashboard'
import { AdminApiError, failure } from '../../shared/errors'

const route = vue.reactive({ path: '/statistics', query: {} as Record<string, string> })
const api = { statistics: vi.fn(), eventContent: vi.fn(), summary: vi.fn() }
let view: ReturnType<typeof shallowMount>
const global = { components: { TechnicalInfoBar, RequestState, QualityOverview } }
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
beforeEach(() => {
  setActivePinia(createPinia())
  route.path = '/statistics'
  route.query = { period: '7d' }
  api.statistics.mockReset().mockResolvedValue(statisticsFixture(new URLSearchParams('period=7d')))
  api.eventContent
    .mockReset()
    .mockResolvedValue(eventContentFixture(new URLSearchParams('period=7d')))
  api.summary
    .mockReset()
    .mockResolvedValue({ ...summary, quality: { ...summary.quality, mode: 'persisted' } })
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push: vi.fn(), replace: vi.fn() }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useDashboardStore', useDashboardStore)
  vi.stubGlobal('computed', vue.computed)
  vi.stubGlobal('onMounted', vue.onMounted)
})
afterEach(() => {
  view?.unmount()
  vi.unstubAllGlobals()
})

for (const kind of ['creation', 'content'] as const)
  describe(`${kind} analytics request lifecycle`, () => {
    const response = () => (kind === 'creation' ? statisticsFixture() : eventContentFixture())
    const mock = () => (kind === 'creation' ? api.statistics : api.eventContent)
    function mountView() {
      view =
        kind === 'creation'
          ? shallowMount(Statistics, { global })
          : shallowMount(Content, { props: { query: { period: '7d' } }, global })
    }
    async function change(query: Record<string, string>) {
      if (kind === 'creation') route.query = query
      else await view.setProps({ query })
      await flushPromises()
    }
    const hasData = () => view.getComponent(RequestState).props('hasData')
    const refresh = () => view.getComponent(RequestState).vm.$emit('retry')
    it('keeps same-query values during refresh and marks transient errors stale', async () => {
      mountView()
      await flushPromises()
      const pending = deferred<ReturnType<typeof response>>()
      mock().mockReturnValueOnce(pending.promise)
      refresh()
      await flushPromises()
      expect(hasData()).toBe(true)
      expect(view.getComponent(RequestState).props('loading')).toBe(true)
      pending.reject(new AdminApiError(failure(503)))
      await flushPromises()
      expect(hasData()).toBe(true)
      expect(view.getComponent(RequestState).props('error').status).toBe(503)
      expect(view.getComponent(TechnicalInfoBar).props('showTitle')).toBe(false)
    })
    it.each([401, 403, 404, 422])('clears protected values on %s', async (status) => {
      mountView()
      await flushPromises()
      mock().mockRejectedValueOnce(new AdminApiError(failure(status)))
      refresh()
      await flushPromises()
      expect(hasData()).toBe(false)
      expect(view.findComponent(TechnicalInfoBar).exists()).toBe(false)
    })
    it('clears a changed query immediately and ignores a late failure', async () => {
      mountView()
      await flushPromises()
      const stale = deferred<ReturnType<typeof response>>()
      mock().mockReturnValueOnce(stale.promise)
      refresh()
      await flushPromises()
      if (kind === 'creation') view.getComponent(EntityTimelineChart).vm.$emit('highlight', 'user')
      const current = deferred<ReturnType<typeof response>>()
      mock().mockReturnValueOnce(current.promise)
      await change({ period: '30d', geo_scope_id: '00000000-0000-4000-8000-000000000800' })
      expect(hasData()).toBe(false)
      stale.reject(new AdminApiError(failure(403)))
      await flushPromises()
      expect(view.getComponent(RequestState).props('error')).toBeNull()
      current.resolve(response())
      await flushPromises()
      expect(hasData()).toBe(true)
      expect(mock().mock.lastCall?.[0].geo_scope_id).toBe('00000000-0000-4000-8000-000000000800')
      if (kind === 'creation')
        expect(view.getComponent(EntityTimelineChart).props('highlighted')).toBeNull()
    })
  })

it('switching to content invalidates a pending creation response without an extra creation request', async () => {
  const pending = deferred<ReturnType<typeof statisticsFixture>>()
  api.statistics.mockReturnValueOnce(pending.promise)
  view = shallowMount(Statistics, { global })
  await flushPromises()
  route.query = { view: 'event-content', period: '7d' }
  await flushPromises()
  pending.resolve(statisticsFixture())
  await flushPromises()
  expect(view.findComponent(EntityTimelineChart).exists()).toBe(false)
  expect(view.findComponent(Content).exists()).toBe(true)
  expect(api.statistics).toHaveBeenCalledTimes(1)
})

it('Quality reloads scoped dashboard data globally and never labels client retrieval time as observation', async () => {
  route.path = '/quality'
  const store = useDashboardStore()
  store.data = { ...summary, geo_scope_id: '00000000-0000-4000-8000-000000000800' }
  const pending = deferred<typeof summary>()
  api.summary.mockReturnValueOnce(pending.promise)
  view = shallowMount(Quality, { global })
  expect(view.getComponent(QualityOverview).props('data')).toBeNull()
  expect(api.summary).toHaveBeenCalledExactlyOnceWith('24h')
  pending.resolve({ ...summary, quality: { ...summary.quality, mode: 'persisted' } })
  await flushPromises()
  expect(view.text()).toContain('Persistierter Bestand · Systemweit')
  expect(view.getComponent(TechnicalInfoBar).props('items')).not.toEqual(
    expect.arrayContaining([expect.objectContaining({ datetime: expect.any(String) })]),
  )
  api.summary.mockRejectedValueOnce(new AdminApiError(failure(503)))
  view.getComponent(RequestState).vm.$emit('retry')
  await flushPromises()
  expect(view.getComponent(RequestState).props('hasData')).toBe(true)
  expect(view.getComponent(RequestState).props('error').status).toBe(503)
  api.summary.mockRejectedValueOnce(new AdminApiError(failure(403)))
  view.getComponent(RequestState).vm.$emit('retry')
  await flushPromises()
  expect(view.getComponent(QualityOverview).props('data')).toBeNull()
})
