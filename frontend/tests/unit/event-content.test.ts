import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, shallowMount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import EventContent from '../../app/components/statistics/EventContentStatistics.vue'
import Ranking from '../../app/components/statistics/RankingBarChart.vue'
import Statistics from '../../app/pages/statistics.vue'
import RequestState from '../../app/components/RequestState.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import { eventContentStatisticsSchema } from '../../shared/contracts'
import { eventContentFixture } from '../fixtures/event-content'
import { statisticsFixture } from '../fixtures/statistics'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { createAdminApi } from '../../app/utils/admin-api'
const route = reactive({ path: '/statistics', query: {} as Record<string, string> })
const push = vi.fn(async ({ query }) => {
  route.query = Object.fromEntries(
    Object.entries(query)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, String(v)]),
  )
})
const api = { eventContent: vi.fn(), statistics: vi.fn() }
const wrappers: { unmount: () => void }[] = []
function content(query: Record<string, string> = {}) {
  const wrapper = mount(EventContent, {
    props: { query },
    global: { components: { RequestState, EmptyState } },
  })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  setActivePinia(createPinia())
  route.query = {}
  vi.clearAllMocks()
  api.eventContent.mockResolvedValue(eventContentFixture())
  api.statistics.mockResolvedValue(statisticsFixture())
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push, replace: push }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
})
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount())
  vi.unstubAllGlobals()
})
it('validates counts, finite shares, All and strict response fields', () => {
  for (const query of [
    '',
    'period=all',
    'period=today&compare=previous',
    'period=30d&status=released',
    'status=cancelled',
  ])
    expect(
      eventContentStatisticsSchema.safeParse(eventContentFixture(new URLSearchParams(query)))
        .success,
    ).toBe(true)
  const data = eventContentFixture()
  data.coverage.categories.events_without_assignment = 100
  expect(eventContentStatisticsSchema.safeParse(data).success).toBe(false)
  data.coverage.categories.events_without_assignment = 2
  data.categories.items[0]!.event_share_percent = Infinity
  expect(eventContentStatisticsSchema.safeParse(data).success).toBe(false)
})
it('renders accessible horizontal rankings, shares, coverage and multi-assignment explanation', async () => {
  const wrapper = content()
  await flushPromises()
  expect(wrapper.text()).toContain('Events erstellt')
  expect(wrapper.text()).toContain('8 von 10 Events')
  expect(wrapper.text()).toContain('2 Events ohne Kategorie')
  expect(wrapper.text()).toContain('4 Events ohne Genre')
  expect(wrapper.text()).toContain('nicht zwingend zu 100 %')
  expect(wrapper.findAll('ol')).toHaveLength(3)
  expect(wrapper.findAll('ol[aria-label] li')).toHaveLength(5)
  expect(wrapper.text()).toContain('6 Events · 60 %')
  expect(wrapper.find('svg').exists()).toBe(false)
  expect(wrapper.findAll('.min-w-0').length).toBeGreaterThan(3)
  const rank = wrapper.getComponent(Ranking)
  expect(rank.text()).toContain('6 von 10 Events')
  expect(rank.find('.break-words').exists()).toBe(true)
})
it('shares periods, scopes status to URL, toggles compare and disables it for All', async () => {
  const preferences = useFilterPreferencesStore()
  preferences.setSharedPeriod('30d')
  preferences.entities.events.status = 'draft'
  const wrapper = content({ view: 'event-content' })
  await flushPromises()
  expect(api.eventContent).toHaveBeenCalledWith({ period: '30d' })
  await wrapper.findAll('select')[0]!.setValue('7d')
  expect(preferences.sharedPeriod).toBe('7d')
  expect(route.query.period).toBe('7d')
  await wrapper.setProps({ query: route.query })
  await wrapper.findAll('select')[1]!.setValue('released')
  expect(preferences.entities.events.status).toBe('draft')
  await wrapper.setProps({ query: route.query })
  await wrapper.get('input[role=switch]').setValue(true)
  await wrapper.setProps({ query: route.query })
  await flushPromises()
  expect(api.eventContent).toHaveBeenLastCalledWith({
    period: '7d',
    status: 'released',
    compare: 'previous',
  })
  await wrapper.findAll('select')[0]!.setValue('all')
  await wrapper.setProps({ query: route.query })
  expect(route.query.compare).toBeUndefined()
  expect(wrapper.get('input').attributes('disabled')).toBeDefined()
  expect(preferences.sharedPeriod).toBe('7d')
})
it('renders previous counts and rank gains without percentage-only deltas', async () => {
  api.eventContent.mockResolvedValue(eventContentFixture(new URLSearchParams('compare=previous')))
  const wrapper = content({ compare: 'previous' })
  await flushPromises()
  expect(wrapper.text()).toContain('Rang ↑ 2')
  expect(wrapper.text()).toContain('+2 Events')
  expect(wrapper.text()).toContain('Prozentpunkte')
  expect(wrapper.text()).toContain('gleichlange Vorperiode')
})
it('handles loading, local errors, retry, empty results and rejects stale responses', async () => {
  let resolve!: (value: ReturnType<typeof eventContentFixture>) => void
  api.eventContent.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r
    }),
  )
  const wrapper = content()
  await wrapper.vm.$nextTick()
  expect(wrapper.text()).toContain('Daten werden geladen')
  api.eventContent.mockResolvedValueOnce(
    eventContentFixture(new URLSearchParams('status=cancelled')),
  )
  await wrapper.setProps({ query: { status: 'cancelled' } })
  await flushPromises()
  expect(wrapper.text()).toContain('Keine Events im gewählten Erstellungszeitraum.')
  resolve(eventContentFixture())
  await flushPromises()
  expect(wrapper.text()).toContain('Keine Events im gewählten Erstellungszeitraum.')
  api.eventContent.mockRejectedValueOnce(new Error('private'))
  await wrapper.setProps({ query: { status: 'draft' } })
  await flushPromises()
  expect(wrapper.getComponent(RequestState).props('error')).toBeTruthy()
  expect(wrapper.text()).not.toContain('private')
  api.eventContent.mockResolvedValue(eventContentFixture())
  wrapper.getComponent(RequestState).vm.$emit('retry')
  await flushPromises()
  expect(wrapper.text()).toContain('8 von 10 Events')
})
it('switches Statistics areas with shared periods and keeps creation API queries unchanged', async () => {
  const preferences = useFilterPreferencesStore()
  preferences.setSharedPeriod('30d')
  const wrapper = shallowMount(Statistics)
  wrappers.push(wrapper)
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith({ period: '30d', interval: 'auto' })
  const switcher = wrapper.findAll('button').find((b) => b.text() === 'Event-Inhalte')!
  await switcher.trigger('click')
  await flushPromises()
  expect(route.query).toMatchObject({ view: 'event-content', period: '30d' })
  expect(wrapper.findComponent(EventContent).exists()).toBe(true)
  const calls = api.statistics.mock.calls.length
  route.query = { view: 'event-content', period: '7d', status: 'released' }
  await flushPromises()
  expect(preferences.sharedPeriod).toBe('7d')
  expect(api.statistics).toHaveBeenCalledTimes(calls)
  await wrapper
    .findAll('button')
    .find((b) => b.text() === 'Erstellung')!
    .trigger('click')
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith({ period: '7d', interval: 'auto' })
  expect(route.query.status).toBeUndefined()
})
it('validates and forwards the dedicated API through the authenticated proxy', async () => {
  const fetcher = vi.fn().mockImplementation(async () => Response.json(eventContentFixture()))
  const apiClient = createAdminApi(fetcher)
  await apiClient.eventContent({ period: '7d', status: 'released', compare: 'previous' })
  expect(String(fetcher.mock.calls[0]![0])).toContain(
    '/statistics/events/content?period=7d&status=released&compare=previous',
  )
  const request = {
    path: '/api/v1/statistics/events/content',
    method: 'GET',
    authorization: 'Bearer fixture',
    query: new URLSearchParams('period=7d&status=released&compare=previous'),
  }
  expect((await forwardAdminRequest(request, 'http://127.0.0.1:8000', fetcher)).status).toBe(200)
  expect(
    (
      await forwardAdminRequest(
        { ...request, authorization: undefined },
        'http://127.0.0.1:8000',
        fetcher,
      )
    ).status,
  ).toBe(401)
  expect(
    (await forwardAdminRequest({ ...request, method: 'POST' }, 'http://127.0.0.1:8000', fetcher))
      .status,
  ).toBe(405)
  expect(
    (
      await forwardAdminRequest(
        { ...request, query: new URLSearchParams('sql=secret') },
        'http://127.0.0.1:8000',
        fetcher,
      )
    ).status,
  ).toBe(422)
})

it('keeps Today as the shared preference when creation needs its supported fallback', async () => {
  route.query = { view: 'event-content', period: 'today' }
  const wrapper = shallowMount(Statistics)
  wrappers.push(wrapper)
  await flushPromises()
  expect(useFilterPreferencesStore().sharedPeriod).toBe('today')
  await wrapper
    .findAll('button')
    .find((b) => b.text() === 'Erstellung')!
    .trigger('click')
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith({ interval: 'auto' })
  expect(useFilterPreferencesStore().sharedPeriod).toBe('today')
})
it('renders ten long names as semantic list rows and rejects an unbounded response', () => {
  const data = eventContentFixture()
  const first = data.genres.items[0]!
  data.genres.items = Array.from({ length: 10 }, (_, i) => ({
    ...first,
    id: `1:${i + 1}`,
    rank: i + 1,
    name: 'Sehr langer Genre-Name mit verständlicher Typzuordnung '.repeat(4),
  }))
  data.genres.distinct_assignment_count = 28
  const wrapper = mount(Ranking, {
    props: { title: 'Top 10 Genres', ranking: data.genres, totalEvents: 10 },
  })
  wrappers.push(wrapper)
  expect(wrapper.findAll('ol li')).toHaveLength(10)
  expect(wrapper.text()).toContain('28 verschiedene Zuordnungen · 10 davon angezeigt')
  expect(eventContentStatisticsSchema.safeParse(data).success).toBe(true)
  data.genres.items.push({ ...first, id: 'extra', rank: 11 })
  expect(eventContentStatisticsSchema.safeParse(data).success).toBe(false)
})

it('restores the remembered creation interval when switching back from content', async () => {
  const preferences = useFilterPreferencesStore()
  preferences.setSharedPeriod('30d')
  preferences.statistics.interval = '6h'
  const wrapper = shallowMount(Statistics)
  wrappers.push(wrapper)
  await flushPromises()
  await wrapper
    .findAll('button')
    .find((b) => b.text() === 'Event-Inhalte')!
    .trigger('click')
  await flushPromises()
  await wrapper
    .findAll('button')
    .find((b) => b.text() === 'Erstellung')!
    .trigger('click')
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith({ period: '30d', interval: '6h' })
  expect(preferences.statistics.interval).toBe('6h')
})
