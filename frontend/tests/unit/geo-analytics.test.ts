import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { shallowMount, mount, flushPromises } from '@vue/test-utils'
import * as vue from 'vue'
import Activity from '../../app/pages/activity.vue'
import Findings from '../../app/pages/findings.vue'
import Dashboard from '../../app/pages/index.vue'
import Statistics from '../../app/pages/statistics.vue'
import Graph from '../../app/pages/graph.vue'
import EventContent from '../../app/components/statistics/EventContentStatistics.vue'
import MetricCard from '../../app/components/statistics/EntityMetricCard.vue'
import GraphFilters from '../../app/components/GraphFilters.vue'
import FilterForm from '../../app/components/FilterForm.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { useFindingsStore } from '../../app/stores/findings'
import { useDashboardStore } from '../../app/stores/dashboard'
import { supportsGeoScope, geoPagination } from '../../app/utils/geo'
import { filtersSchema } from '../../shared/contracts'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { geoArea } from '../fixtures/geo'
import { summary, findings } from '../fixtures/api'
import { activityFixture } from '../fixtures/activity'
import { statisticsFixture } from '../fixtures/statistics'
import { eventContentFixture } from '../fixtures/event-content'
import { graphFixture } from '../fixtures/graph'

const route = vue.reactive({ path: '/activity', query: {} as Record<string, string>, hash: '' })
const push = vi.fn(async ({ query }) => {
  route.query = Object.fromEntries(
    Object.entries(query)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, String(v)]),
  )
})
const api = {
  activity: vi.fn(),
  findings: vi.fn(),
  summary: vi.fn(),
  statistics: vi.fn(),
  eventContent: vi.fn(),
  graph: vi.fn(),
  graphSearch: vi.fn(),
}
const wrappers: { unmount: () => void }[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useFilterPreferencesStore().setGeoScope(geoArea)
  route.query = { geo_scope_id: geoArea.id, period: '7d' }
  api.activity.mockResolvedValue(activityFixture)
  api.findings.mockResolvedValue(findings)
  api.summary.mockResolvedValue({
    ...summary,
    geo_scope_id: geoArea.id,
    scoped_new_records_total: 3,
    global_new_records_total: 7,
  })
  api.statistics.mockResolvedValue(statisticsFixture())
  api.eventContent.mockResolvedValue(eventContentFixture())
  api.graph.mockResolvedValue(graphFixture)
  api.graphSearch.mockResolvedValue({ items: [graphFixture.nodes[0]] })
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
  vi.stubGlobal('useRouter', () => ({ push, replace: push }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useFindingsStore', useFindingsStore)
  vi.stubGlobal('useDashboardStore', useDashboardStore)
})
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount())
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
function page(
  component:
    typeof Activity | typeof Findings | typeof Dashboard | typeof Statistics | typeof Graph,
) {
  const wrapper = shallowMount(component, {
    global: {
      components: { FilterBar, FilterForm, GraphFilters },
      stubs: { FilterBar: false, NuxtLink: { template: '<a><slot /></a>' } },
      mocks: { dateTime: String, metric: String },
    },
  })
  wrappers.push(wrapper)
  return wrapper
}
it('supports only explicit analytics and spatial list routes; adds pagination only to lists', () => {
  for (const path of ['/', '/activity', '/findings', '/statistics', '/graph', '/venues'])
    expect(supportsGeoScope(path)).toBe(true)
  for (const path of [
    '/login',
    '/settings',
    '/users',
    '/images',
    '/venues/id',
    '/notifications',
    '/statistics/id',
  ])
    expect(supportsGeoScope(path)).toBe(false)
  for (const path of ['/', '/statistics', '/graph']) expect(geoPagination(path)).toBe(false)
})
it('scopes Activity requests, excludes nonspatial filter options and preserves geo on reset', async () => {
  const wrapper = page(Activity)
  await flushPromises()
  expect(api.activity).toHaveBeenLastCalledWith(
    expect.objectContaining({ geo_scope_id: geoArea.id, period: '7d' }),
  )
  const options = wrapper
    .findAll('select')[0]!
    .findAll('option')
    .map((o) => o.attributes('value'))
  expect(options).toContain('event_date')
  expect(options).not.toContain('user')
  expect(options).not.toContain('image')
  await wrapper
    .findAll('button')
    .find((b) => b.text() === 'Filter zurücksetzen')!
    .trigger('click')
  await flushPromises()
  expect(route.query.geo_scope_id).toBe(geoArea.id)
})
it('passes geo to Findings and preserves it when local form filters change or reset', async () => {
  route.query = { geo_scope_id: geoArea.id }
  const wrapper = page(Findings)
  await flushPromises()
  expect(api.findings).toHaveBeenLastCalledWith(
    expect.objectContaining({ geo_scope_id: geoArea.id }),
  )
  wrapper.getComponent(FilterForm).vm.$emit('apply', filtersSchema.parse({ severity: 'warning' }))
  await flushPromises()
  expect(route.query.geo_scope_id).toBe(geoArea.id)
  wrapper.getComponent(FilterForm).vm.$emit('reset')
  await flushPromises()
  expect(route.query).toEqual({ geo_scope_id: geoArea.id })
})
it('scopes Dashboard counts and preview, reloads on scope change and renders separate totals', async () => {
  const wrapper = page(Dashboard)
  await flushPromises()
  expect(api.summary).toHaveBeenLastCalledWith('7d', geoArea.id)
  expect(api.findings).toHaveBeenLastCalledWith(
    expect.objectContaining({ geo_scope_id: geoArea.id }),
  )
  expect(wrapper.text()).toContain('Systemweit zusätzlich: 7')
  expect(wrapper.text()).toContain('neue Datensätze im Gebiet')
  route.query = { period: '7d' }
  await flushPromises()
  expect(api.summary).toHaveBeenLastCalledWith('7d')
  expect(api.findings).toHaveBeenLastCalledWith(
    expect.objectContaining({ geo_scope_id: undefined }),
  )
})
it('keeps period and scope when switching Statistics views', async () => {
  const wrapper = page(Statistics)
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith(
    expect.objectContaining({ geo_scope_id: geoArea.id, period: '7d' }),
  )
  await wrapper
    .findAll('button')
    .find((b) => b.text() === 'Event-Inhalte')!
    .trigger('click')
  await flushPromises()
  expect(route.query.geo_scope_id).toBe(geoArea.id)
  expect(route.query.period).toBe('7d')
})
it('sends scope to event content and explains the scoped population', async () => {
  const wrapper = shallowMount(EventContent, { props: { query: route.query } })
  wrappers.push(wrapper)
  await flushPromises()
  expect(api.eventContent).toHaveBeenLastCalledWith({ period: '7d', geo_scope_id: geoArea.id })
  expect(wrapper.text()).toContain('Veranstaltungen im gewählten Gebiet')
})
it.each(['geo', 'global'] as const)('visibly labels %s statistics series', (scope) => {
  const wrapper = mount(MetricCard, {
    props: {
      series: { ...statisticsFixture().series[0]!, scope },
      selected: true,
      showScope: true,
    },
  })
  wrappers.push(wrapper)
  expect(wrapper.text()).toContain(scope === 'geo' ? 'Gebiet' : 'Systemweit')
})
it('scopes Graph discovery, disables user roots, and keeps traversal API unscoped', async () => {
  vi.useFakeTimers()
  route.query = {
    geo_scope_id: geoArea.id,
    root_type: graphFixture.root.type,
    root_key: graphFixture.root.key,
  }
  const wrapper = page(Graph)
  await flushPromises()
  expect(api.graph).toHaveBeenLastCalledWith(
    expect.not.objectContaining({ geo_scope_id: geoArea.id }),
  )
  const filters = wrapper.getComponent(GraphFilters)
  expect(filters.props('geoActive')).toBe(true)
  filters.vm.$emit('update:query', 'Kultur')
  await vi.advanceTimersByTimeAsync(350)
  await flushPromises()
  expect(api.graphSearch).toHaveBeenLastCalledWith(
    expect.objectContaining({ geo_scope_id: geoArea.id }),
  )
  filters.vm.$emit('reset')
  await flushPromises()
  expect(route.query.geo_scope_id).toBe(geoArea.id)
})
it('explicitly allowlists geo on six analytics APIs, never graph traversal', async () => {
  const fetcher = vi.fn(async () => new Response('{}', { status: 200 }))
  for (const path of [
    'dashboard/activity',
    'findings',
    'dashboard/summary',
    'statistics/entities',
    'statistics/events/content',
    'graph/search',
  ]) {
    const response = await forwardAdminRequest(
      {
        path: '/api/v1/' + path,
        method: 'GET',
        query: new URLSearchParams({ geo_scope_id: geoArea.id }),
        authorization: 'Bearer test-token',
      },
      'https://api.test',
      fetcher,
    )
    expect(response.status).toBe(200)
    expect(String(fetcher.mock.calls.at(-1)?.[0])).toContain('geo_scope_id=')
  }
  const response = await forwardAdminRequest(
    {
      path: '/api/v1/graph',
      method: 'GET',
      query: new URLSearchParams({ geo_scope_id: geoArea.id }),
    },
    'https://api.test',
    fetcher,
  )
  expect(response.status).toBe(422)
})

it('a geo-only URL inherits shared period, explicit period still wins', async () => {
  useFilterPreferencesStore().setSharedPeriod('30d')
  route.query = { geo_scope_id: geoArea.id }
  const wrapper = page(Statistics)
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith(
    expect.objectContaining({ period: '30d', geo_scope_id: geoArea.id }),
  )
  expect(route.query.period).toBe('30d')
  wrapper.unmount()
  route.query = { geo_scope_id: geoArea.id, period: '7d' }
  page(Statistics)
  await flushPromises()
  expect(api.statistics).toHaveBeenLastCalledWith(
    expect.objectContaining({ period: '7d', geo_scope_id: geoArea.id }),
  )
})
