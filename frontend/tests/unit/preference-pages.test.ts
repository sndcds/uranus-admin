import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { shallowMount, flushPromises } from '@vue/test-utils'
import * as vue from 'vue'
import Dashboard from '../../app/pages/index.vue'
import Activity from '../../app/pages/activity.vue'
import Statistics from '../../app/pages/statistics.vue'
import Graph from '../../app/pages/graph.vue'
import GraphFilters from '../../app/components/GraphFilters.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { useDashboardStore } from '../../app/stores/dashboard'
import { useFindingsStore } from '../../app/stores/findings'
import { summary, findings } from '../fixtures/api'
import { activityFixture } from '../fixtures/activity'
import { statisticsFixture } from '../fixtures/statistics'
import { graphFixture } from '../fixtures/graph'

const route = vue.reactive({ query: {} as Record<string, string> })
const navigate = vi.fn(({ query }) => {
  route.query = Object.fromEntries(
    Object.entries(query)
      .filter(([, value]) => value !== undefined)
      .map(([key, value]) => [key, String(value)]),
  )
  return Promise.resolve()
})
const api = {
  summary: vi.fn(async (period) => ({ ...summary, period })),
  findings: vi.fn(async () => findings),
  activity: vi.fn(async () => activityFixture),
  statistics: vi.fn(async () => statisticsFixture()),
  graph: vi.fn(async () => graphFixture),
  graphSearch: vi.fn(async () => ({ items: [] })),
}
const wrappers: Array<{ unmount: () => void }> = []
function page(component: typeof Activity | typeof Statistics | typeof Dashboard | typeof Graph) {
  const wrapper = shallowMount(component, {
    global: {
      components: { PageHeader, FilterBar, GraphFilters },
      stubs: { PageHeader: false, FilterBar: false, NuxtLink: true },
      mocks: { metric: String, dateTime: String },
    },
  })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  route.query = {}
  for (const key of [
    'ref',
    'shallowRef',
    'computed',
    'watch',
    'onMounted',
    'onBeforeUnmount',
  ] as const)
    vi.stubGlobal(key, vue[key])
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push: navigate, replace: navigate }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useDashboardStore', useDashboardStore)
  vi.stubGlobal('useFindingsStore', useFindingsStore)
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.unstubAllGlobals()
})
it('shares Dashboard choices with Activity and Statistics, while data stays in DashboardStore', async () => {
  const preferences = useFilterPreferencesStore()
  const dashboard = page(Dashboard)
  await flushPromises()
  await dashboard.get('select').setValue('7d')
  await flushPromises()
  expect(preferences.sharedPeriod).toBe('7d')
  expect(api.summary).toHaveBeenLastCalledWith('7d')
  expect(useDashboardStore().data?.period).toBe('7d')
  expect(useDashboardStore().$state).not.toHaveProperty('period')
  dashboard.unmount()
  route.query = {}
  const activity = page(Activity)
  await flushPromises()
  expect(activity.findAll('select')[1]!.element.value).toBe('7d')
  expect(api.activity).toHaveBeenLastCalledWith({ period: '7d' })
  activity.unmount()
  route.query = {}
  const statistics = page(Statistics)
  await flushPromises()
  expect(
    statistics
      .findAll('button')
      .find((button) => button.text() === 'Letzte 7 Tage')!
      .attributes('aria-pressed'),
  ).toBe('true')
})
it('uses unsupported page fallbacks without erasing the shared preference', async () => {
  const preferences = useFilterPreferencesStore()
  preferences.sharedPeriod = '90d'
  const dashboard = page(Dashboard)
  await flushPromises()
  expect(dashboard.get('select').element.value).toBe('24h')
  expect(preferences.sharedPeriod).toBe('90d')
  dashboard.unmount()
  preferences.sharedPeriod = 'today'
  route.query = {}
  const statistics = page(Statistics)
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith({ period: '24h', interval: 'auto' })
  await statistics.get('[role="switch"]').setValue(true)
  await flushPromises()
  expect(preferences.sharedPeriod).toBe('today')
  await statistics
    .findAll('button')
    .find((button) => button.text() === 'Letzte 24 Stunden')!
    .trigger('click')
  expect(preferences.sharedPeriod).toBe('24h')
})
it('synchronizes Activity explicit routes and history without sharing custom/unknown modes', async () => {
  const preferences = useFilterPreferencesStore()
  preferences.sharedPeriod = '7d'
  route.query = { period: '24h', entity_type: 'event', page: '3' }
  const activity = page(Activity)
  await flushPromises()
  expect(preferences.sharedPeriod).toBe('24h')
  await activity.findAll('select')[1]!.setValue('7d')
  await activity.get('form').trigger('submit')
  await flushPromises()
  expect(route.query.page).toBe('1')
  expect(preferences.sharedPeriod).toBe('7d')
  route.query = { period: '24h', entity_type: 'venue' }
  await flushPromises()
  expect(preferences.activity.entityType).toBe('venue')
  expect(preferences.sharedPeriod).toBe('24h')
  route.query = { timestamp_state: 'unknown' }
  await flushPromises()
  expect(activity.findAll('select')[1]!.element.value).toBe('unknown')
  route.query = { from_at: '2026-01-01T00:00:00Z', to_at: '2026-01-02T00:00:00Z' }
  await flushPromises()
  expect(activity.findAll('select')[1]!.element.value).toBe('custom')
  expect(preferences.sharedPeriod).toBe('24h')
})
it('remembers Statistics interval, comparison and selected series, but not custom UI state', async () => {
  const preferences = useFilterPreferencesStore()
  preferences.sharedPeriod = '7d'
  route.query = { period: '30d', interval: '6h', compare: 'previous' }
  const statistics = page(Statistics)
  await flushPromises()
  expect(preferences.sharedPeriod).toBe('30d')
  expect(preferences.statistics.interval).toBe('6h')
  expect(statistics.get('[role="switch"]').element.checked).toBe(true)
  statistics.getComponent({ name: 'EntityTimelineChart' }).vm.$emit('toggle', 'user')
  await flushPromises()
  expect(preferences.statistics.selectedTypes).not.toContain('user')
  route.query = { period: 'custom', from_at: '2026-01-01T00:00:00Z', to_at: '2026-01-02T00:00:00Z' }
  await flushPromises()
  expect(preferences.sharedPeriod).toBe('30d')
  statistics.unmount()
  route.query = {}
  const returning = page(Statistics)
  await flushPromises()
  expect(
    returning.getComponent({ name: 'EntityTimelineChart' }).props('selectedTypes'),
  ).not.toContain('user')
  expect(preferences.statistics).not.toHaveProperty('customFrom')
})
it('restores Graph filters and organization but always uses the explicit root', async () => {
  const preferences = useFilterPreferencesStore()
  preferences.graph = {
    entityType: 'venue',
    relationType: 'venue_has_space',
    organization: 'stored-org',
    depth: 3,
  }
  const graph = page(Graph)
  await flushPromises()
  expect(graph.getComponent({ name: 'GraphFilters' }).props()).toMatchObject({
    entityType: 'venue',
    relationType: 'venue_has_space',
    organization: 'stored-org',
    depth: 3,
  })
  expect(api.graph).not.toHaveBeenCalled()
  graph.unmount()
  route.query = {
    root_type: graphFixture.root.type,
    root_key: graphFixture.root.key,
    depth: '1',
    entity_type: 'user',
  }
  page(Graph)
  await flushPromises()
  expect(api.graph).toHaveBeenLastCalledWith({
    root_type: graphFixture.root.type,
    root_key: graphFixture.root.key,
    depth: 1,
    relation_type: undefined,
  })
  expect(preferences.graph.entityType).toBe('user')
  expect(preferences.graph.depth).toBe(1)
})

it('uses auto when the remembered interval exceeds the new shared period bucket limit', async () => {
  const preferences = useFilterPreferencesStore()
  preferences.statistics.interval = '15m'
  preferences.sharedPeriod = '7d'
  const statistics = page(Statistics)
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith({ period: '7d', interval: 'auto' })
  expect(statistics.get('[aria-label="Intervall"]').element.value).toBe('auto')
  expect(preferences.statistics.interval).toBe('15m')
})
