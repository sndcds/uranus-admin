import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive, ref, nextTick } from 'vue'
import EntitySearch from '../../app/components/EntitySearch.vue'
import EntityListPage from '../../app/components/EntityListPage.vue'
import EntityDetailPage from '../../app/components/EntityDetailPage.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import PaginationBar from '../../app/components/PaginationBar.vue'
import ResultSummary from '../../app/components/ResultSummary.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import DetailFacts from '../../app/components/DetailFacts.vue'
import { entitySectionSchema, entityPageSchema } from '../../shared/contracts'
import { entityFixture, detailFixture } from '../fixtures/entities'
const api = {
    entities: vi.fn(),
    entity: vi.fn(),
    entitySearch: vi.fn().mockResolvedValue({ items: [] }),
  },
  push = vi.fn(),
  replace = vi.fn()
const route = reactive({
  query: {} as Record<string, string>,
  params: { id: entityFixture('events').items[0]!.entity_key },
  fullPath: '/events',
})
const global = {
  components: { EntitySearch, FilterBar, PaginationBar, ResultSummary, PageHeader },
  stubs: {
    NuxtLink: { props: ['to'], template: '<a :data-to="JSON.stringify(to)"><slot /></a>' },
    DataListShell: { template: '<ul><slot /></ul>' },
    ActivityRow: { props: ['item'], template: '<li>{{item.entity_name}}</li>' },
    RequestState: {
      props: ['loading', 'error'],
      template: '<div>{{loading ? "loading" : error ? "error" : ""}}</div>',
    },
    EmptyState: { props: ['message'], template: '<p>{{message}}</p>' },
  },
}
beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  route.query = {}
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push, replace }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useState', () => ref(0))
})
afterEach(() => vi.unstubAllGlobals())
it.each(entitySectionSchema.options)(
  'renders and filters %s, with a paginated safe detail',
  async (section) => {
    const fixture = entityFixture(section)
    expect(entityPageSchema.safeParse(fixture).success).toBe(true)
    let resolveFirst!: (value: typeof fixture) => void
    api.entities
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve
          }),
      )
      .mockResolvedValue(fixture)
    api.entity.mockResolvedValue(detailFixture(section))
    const list = mount(EntityListPage, { props: { section }, global })
    await nextTick()
    expect(list.text()).toContain('loading')
    resolveFirst(fixture)
    await flushPromises()
    expect(list.text()).toContain(`Fixture ${section}`)
    expect(list.text()).toContain('26 Datensätze insgesamt')
    expect(list.text()).toContain('Seite 1 von 2')
    await list.get('input[type="search"]').setValue('Nord')
    await list.get('form').trigger('submit')
    expect(push).toHaveBeenCalledWith({
      query: {
        q: 'Nord',
        organization_id: undefined,
        status: undefined,
        temporal: undefined,
        period: undefined,
        page: '1',
      },
    })
    route.query = { q: 'Nord', organization_id: 'org', status: 'active', page: '1' }
    await flushPromises()
    const next = list.findAll('a').find((a) => a.attributes('data-to')?.includes('"page":"2"'))!
    expect(JSON.parse(next.attributes('data-to')!)).toEqual({
      query: { ...route.query, page: '2' },
    })
    route.query = { ...route.query, page: '2' }
    await flushPromises()
    expect(api.entities).toHaveBeenLastCalledWith(section, route.query)
    expect((list.get('input[type="search"]').element as HTMLInputElement).value).toBe('Nord')
    api.entities.mockResolvedValue({
      ...fixture,
      items: [],
      pagination: { ...fixture.pagination, total: 0, pages: 0 },
    })
    route.query = { q: 'missing' }
    await flushPromises()
    expect(list.text()).toContain('Keine Datensätze')
    api.entities.mockRejectedValue(new Error('private'))
    route.query = {}
    await flushPromises()
    expect(list.text()).toContain('error')
    expect(list.text()).not.toContain(`Fixture ${section}`)
    list.unmount()
    const detail = mount(EntityDetailPage, { props: { section }, global })
    await flushPromises()
    expect(detail.text()).toContain(`Fixture ${section}`)
    expect(detail.findAllComponents(PageHeader)).toHaveLength(1)
    expect(detail.findAllComponents(DetailFacts)).toHaveLength(1)
    expect(detail.findAll('dl')).toHaveLength(1)
    const header = detail.getComponent(PageHeader)
    expect(header.get('a').text()).toBe('Zur Liste')
    expect(header.get('a').attributes('data-to')).toBe(JSON.stringify(`/${section}`))
    expect(header.text()).toContain('Befunde zu diesem Datensatz')
    expect(header.find('ul').exists()).toBe(false)
    if (section === 'events') {
      expect(detail.text()).toContain('Standardort')
      expect(detail.text()).toContain('Standardraum')
      expect(detail.text()).toContain('Standardbühne')
    }
    expect(detail.findAll('a').some((a) => a.attributes('data-to')?.includes('entity_key'))).toBe(
      true,
    )
    detail.unmount()
  },
)

it('navigates to the selected result using its validated action href', async () => {
  const fixture = entityFixture('users')
  api.entities.mockResolvedValue(fixture)
  const item = fixture.items[0]!
  api.entitySearch.mockResolvedValue({
    items: [
      {
        entity_type: 'user',
        entity_key: item.entity_key,
        label: 'Max Mustermann',
        subtitle: '@max · max@example.org',
        status: 'active',
        action: item.action,
      },
    ],
  })
  vi.useFakeTimers()
  const list = mount(EntityListPage, { props: { section: 'users' }, global })
  try {
    await flushPromises()
    await list.get('input[type="search"]').trigger('focus')
    await list.get('input[type="search"]').setValue('max')
    await vi.advanceTimersByTimeAsync(275)
    await list.get('[role="option"]').trigger('click')
    expect(push).toHaveBeenCalledExactlyOnceWith(item.action!.href)
  } finally {
    list.unmount()
    vi.useRealTimers()
  }
})

it.each(entitySectionSchema.options)(
  'simplifies the filter bar for %s and retains organization deep links',
  async (section) => {
    const org = entityFixture(section).items[0]!.entity_key
    route.query = { organization_id: org }
    api.entities.mockResolvedValue(entityFixture(section))
    const list = mount(EntityListPage, { props: { section }, global })
    await flushPromises()
    expect(list.text()).not.toContain('Organisation UUID')
    expect(list.find('input:not([type="search"])').exists()).toBe(false)
    const supported = !['users', 'images'].includes(section)
    expect(list.findAll('label').some((label) => label.text().startsWith('Terminlage'))).toBe(
      supported,
    )
    expect(list.getComponent(EntitySearch).props('organizationId')).toBe(org)
    expect(api.entities).toHaveBeenCalledWith(section, { organization_id: org })
    await list.get('form').trigger('submit')
    expect(push).toHaveBeenLastCalledWith({
      query: {
        q: undefined,
        organization_id: org,
        status: undefined,
        temporal: undefined,
        period: undefined,
        page: '1',
      },
    })
    list.unmount()
  },
)

it.each(['events', 'organizations', 'venues', 'spaces'] as const)(
  '%s restores temporal, combines filters, resets the page and preserves URL state',
  async (section) => {
    const org = entityFixture(section).items[0]!.entity_key
    const initial = {
      q: 'hacks',
      temporal: 'past',
      status: 'released',
      organization_id: org,
      page: '2',
    }
    route.query = { ...initial }
    api.entities.mockResolvedValue(entityFixture(section))
    const list = mount(EntityListPage, { props: { section }, global })
    await flushPromises()
    const select = list
      .findAll('label')
      .find((label) => label.text().startsWith('Terminlage'))!
      .get('select')
    expect(select.findAll('option').map((o) => o.text())).toEqual([
      'Alle',
      'Mit bevorstehenden Terminen',
      'Mit vergangenen Terminen',
    ])
    expect((select.element as HTMLSelectElement).value).toBe('past')
    expect(list.getComponent(EntitySearch).props('temporal')).toBe('past')
    expect(list.text()).toContain('Terminlage: Mit vergangenen Terminen')
    for (const temporal of ['upcoming', 'past', '']) {
      await select.setValue(temporal)
      expect(push).toHaveBeenLastCalledWith({
        query: { ...initial, temporal: temporal || undefined, period: undefined, page: '1' },
      })
      route.query = { ...initial, page: '1', ...(temporal ? { temporal } : {}) }
      if (!temporal) delete route.query.temporal
      await flushPromises()
      expect(api.entities).toHaveBeenLastCalledWith(section, route.query)
    }
    // Browser Back/Forward restores the applied controls from route state.
    route.query = { ...initial, temporal: 'upcoming', page: '1' }
    await flushPromises()
    expect((select.element as HTMLSelectElement).value).toBe('upcoming')
    const next = list.findAll('a').find((a) => a.attributes('data-to')?.includes('"page":"2"'))!
    expect(JSON.parse(next.attributes('data-to')!)).toEqual({
      query: { ...route.query, page: '2' },
    })
    route.query = { ...initial }
    await flushPromises()
    expect((select.element as HTMLSelectElement).value).toBe('past')
    expect(list.getComponent(EntitySearch).props('temporal')).toBe('past')
    list.unmount()
  },
)

it('restores scoped preferences on entry and updates both memory and route on apply/reset', async () => {
  const store = useFilterPreferencesStore()
  store.entities.events = { q: 'sommer', status: 'released', temporal: 'upcoming', period: '' }
  store.entities.users = { q: 'max', status: 'active', period: '' }
  store.sharedPeriod = '90d'
  store.statistics.compare = true
  api.entities.mockResolvedValue(entityFixture('events'))
  const list = mount(EntityListPage, { props: { section: 'events' }, global })
  await flushPromises()
  expect(replace).toHaveBeenCalledWith({
    query: { q: 'sommer', status: 'released', temporal: 'upcoming', page: '1' },
  })
  expect(list.getComponent(EntitySearch).props('modelValue')).toBe('sommer')
  expect(api.entities).toHaveBeenCalledWith('events', {
    q: 'sommer',
    status: 'released',
    temporal: 'upcoming',
    page: '1',
  })
  await list.get('input[type="search"]').setValue('neu')
  await list.get('form').trigger('submit')
  expect(store.entities.events.q).toBe('neu')
  await list
    .findAll('button')
    .find((b) => b.text() === 'Filter zurücksetzen')!
    .trigger('click')
  expect(store.entities.events).toEqual({ q: '', status: '', temporal: '', period: '' })
  expect(store.entities.users).toEqual({ q: 'max', status: 'active', period: '' })
  expect(store.sharedPeriod).toBe('90d')
  expect(store.statistics.compare).toBe(true)
  list.unmount()
})

it('gives explicit fields priority, fills missing entry fields, and restores complete history snapshots', async () => {
  const store = useFilterPreferencesStore()
  store.entities.events = { q: 'stored', status: 'released', temporal: 'upcoming', period: '' }
  route.query = { status: 'draft' }
  api.entities.mockResolvedValue(entityFixture('events'))
  const list = mount(EntityListPage, { props: { section: 'events' }, global })
  await flushPromises()
  expect(replace).toHaveBeenCalledWith({
    query: { q: 'stored', status: 'draft', temporal: 'upcoming', page: '1' },
  })
  expect(store.entities.events).toEqual({
    q: 'stored',
    status: 'draft',
    temporal: 'upcoming',
    period: '',
  })
  for (const status of ['released', 'draft', '']) {
    route.query = status ? { status, page: '1' } : { page: '1' }
    await flushPromises()
    expect(store.entities.events.status).toBe(status)
    expect((list.findAll('select')[2]!.element as HTMLSelectElement).value).toBe(status)
  }
  list.unmount()
})

it.each(entitySectionSchema.options)(
  'restores only supported %s preferences on re-entry',
  async (section) => {
    const preferences = useFilterPreferencesStore()
    preferences.hydrateEntity(section, {
      q: 'remembered',
      status: section === 'users' ? 'active' : 'released',
      temporal: 'upcoming',
    })
    api.entities.mockResolvedValue(entityFixture(section))
    const list = mount(EntityListPage, { props: { section }, global })
    await flushPromises()
    expect(api.entities).toHaveBeenLastCalledWith(section, {
      ...Object.fromEntries(
        Object.entries(preferences.entities[section]).filter(([, value]) => value !== ''),
      ),
      page: '1',
    })
    expect(list.getComponent(EntitySearch).props('modelValue')).toBe('remembered')
    if (section === 'users' || section === 'images')
      expect(preferences.entities[section]).not.toHaveProperty('temporal')
    if (!['events', 'users'].includes(section))
      expect(preferences.entities[section]).not.toHaveProperty('status')
    list.unmount()
  },
)

it.each(entitySectionSchema.options)(
  '%s exposes all creation presets independently of Terminlage',
  async (section) => {
    api.entities.mockResolvedValue(entityFixture(section))
    const list = mount(EntityListPage, { props: { section }, global })
    await flushPromises()
    const created = list
      .findAll('label')
      .find((label) => label.text().startsWith('Erstellt'))!
      .get('select')
    expect(created.findAll('option').map((option) => option.text())).toEqual([
      'Alle',
      'Heute',
      'Letzte 24 Stunden',
      'Letzte 7 Tage',
      'Letzte 30 Tage',
      'Letzte 90 Tage',
    ])
    expect((created.element as HTMLSelectElement).value).toBe('')
    await created.setValue('7d')
    expect(push).toHaveBeenLastCalledWith({
      query: expect.objectContaining({ period: '7d', page: '1' }),
    })
    const store = useFilterPreferencesStore()
    expect(store.entities[section].period).toBe('7d')
    expect(store.sharedPeriod).toBe('7d')
    route.query = { period: '30d', q: 'fixture', page: '2' }
    await flushPromises()
    expect(store.entities[section].period).toBe('30d')
    expect(store.sharedPeriod).toBe('30d')
    expect(list.getComponent(EntitySearch).props('period')).toBe('30d')
    expect(list.text()).toContain('Erstellt: Letzte 30 Tage')
    const next = list.findAll('a').find((a) => a.text() === 'Weiter')!
    expect(JSON.parse(next.attributes('data-to')!)).toEqual({
      query: { period: '30d', q: 'fixture', page: '2' },
    })
    route.query = { period: '7d', page: '1' }
    await flushPromises()
    expect((created.element as HTMLSelectElement).value).toBe('7d')
    expect(store.sharedPeriod).toBe('7d')
    await created.setValue('')
    expect(store.entityDefaults(section).period).toBe('')
    expect(store.sharedPeriod).toBe('7d')
    expect(push).toHaveBeenLastCalledWith({
      query: expect.objectContaining({ period: undefined, page: '1' }),
    })
    list.unmount()
  },
)
