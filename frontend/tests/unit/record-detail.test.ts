import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { reactive } from 'vue'
import OrganizationPage from '../../app/pages/organizations/[id].vue'
import VenuePage from '../../app/pages/venues/[id].vue'
import SpacePage from '../../app/pages/spaces/[id].vue'
import OrganizationDetailContent from '../../app/components/OrganizationDetailContent.vue'
import VenueDetailContent from '../../app/components/VenueDetailContent.vue'
import SpaceDetailContent from '../../app/components/SpaceDetailContent.vue'
import SpaceDetailContext from '../../app/components/SpaceDetailContext.vue'
import RecordRelations from '../../app/components/RecordRelations.vue'
import RecordWorkflowSummary from '../../app/components/RecordWorkflowSummary.vue'
import RecordLocation from '../../app/components/RecordLocation.vue'
import { placeDetailFixture, placeSections } from '../fixtures/entities'
import EventPage from '../../app/pages/events/[id].vue'
import EntityDetailPage from '../../app/components/EntityDetailPage.vue'
import EntityHero from '../../app/components/EntityHero.vue'
import EventDetailContent from '../../app/components/EventDetailContent.vue'
import EntityTechnicalMetadata from '../../app/components/EntityTechnicalMetadata.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import RecordSection from '../../app/components/RecordSection.vue'
import MarkdownContent from '../../app/components/MarkdownContent.vue'
import RequestState from '../../app/components/RequestState.vue'
import PaginationBar from '../../app/components/PaginationBar.vue'
import { eventDetailFixture, paginatedEventDetailFixture } from '../fixtures/event-detail'
import { recordDateTime } from '../../app/utils/presentation'
import { AdminApiError, failure } from '../../shared/errors'
import type { EntityDetail } from '../../shared/contracts'
enableAutoUnmount(afterEach)
const api = { entity: vi.fn() }
const route = reactive({ params: { id: '' }, query: {} as Record<string, string>, fullPath: '' })
const global = {
  components: {
    OrganizationDetailContent,
    VenueDetailContent,
    SpaceDetailContent,
    SpaceDetailContext,
    RecordRelations,
    RecordWorkflowSummary,
    RecordLocation,
    EntityDetailPage,
    EntityHero,
    EventDetailContent,
    EntityTechnicalMetadata,
    PageHeader,
    RecordSection,
    MarkdownContent,
    RequestState,
    PaginationBar,
  },
  stubs: {
    NuxtLink: { props: ['to'], template: '<a :data-to="JSON.stringify(to)"><slot /></a>' },
    ResultSummary: true,
    ActivityThumbnail: true,
    EntityTypeBadge: true,
    StatusBadge: true,
    InlineAlert: { template: '<div role="alert"><slot /></div>' },
    AppIcon: true,
    EntityTimeline: { template: '<section><h3>Verlauf</h3></section>' },
    ActivityRow: { props: ['item'], template: '<li><h4>{{item.entity_name}}</h4></li>' },
    DataListShell: { template: '<ul><slot /></ul>' },
    EmptyState: { props: ['message'], template: '<p>{{message}}</p>' },
  },
}
beforeEach(() => {
  vi.resetAllMocks()
  const data = eventDetailFixture()
  route.params.id = data.item.entity_key
  route.query = {}
  route.fullPath = `/events/${route.params.id}`
  api.entity.mockResolvedValue(data)
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
})
afterEach(() => vi.unstubAllGlobals())
it('renders one record title, readable Markdown, a generic relation page, then timeline and technical facts', async () => {
  const wrapper = mount(EventPage, { global })
  await flushPromises()
  const data = eventDetailFixture()
  expect(wrapper.findAll('h2').map((h) => h.text())).toEqual([data.item.entity_name])
  expect(wrapper.get('.prose-admin strong').text()).toBe('Kultur und Begegnung')
  expect(wrapper.findAll('h3').map((h) => h.text())).toEqual([
    'Auf einen Blick',
    'Beschreibung',
    'Verknüpfte Datensätze',
    'Qualität & Arbeitsstand',
    'Verlauf',
    'Technische Informationen',
  ])
  const sections = wrapper.findAllComponents(RecordSection)
  expect(sections.at(-1)!.text()).toContain(data.item.entity_key)
  expect(wrapper.get('[data-entity-hero]').text()).not.toContain(data.item.entity_key)
  expect(wrapper.get('[data-entity-hero]').text()).toContain(data.item.subtitle)
  expect(wrapper.get('a.button-primary').attributes('href')).toBe(data.item.public_url)
  wrapper.unmount()
})
it('hides empty descriptions and unavailable facts without inventing zeroes or dates', async () => {
  const data = eventDetailFixture()
  data.item.facts.description = '  '
  data.item.facts.venue_name = data.item.facts.space_name = null
  data.item.facts.event_dates = null
  data.item.finding_count = data.item.mark_count = null
  data.item.created_at = null
  data.item.subtitle = null
  data.item.public_url = null
  data.related.items = []
  data.related.pagination = { page: 1, pages: 0, page_size: 25, total: 0 }
  api.entity.mockResolvedValue(data)
  const wrapper = mount(EventPage, { global })
  await flushPromises()
  expect(wrapper.find('.prose-admin').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('Auf einen Blick')
  expect(wrapper.text()).not.toContain('Quelldatensatz angelegt')
  expect(wrapper.text()).toContain('Der Arbeitsstand ist nicht verfügbar.')
  expect(wrapper.find('.button-primary').exists()).toBe(false)
  wrapper.unmount()
})
it('labels a partial relation page and preserves query parameters for pagination', async () => {
  const data = eventDetailFixture()
  data.related.items = data.related.items.filter((item) => item.entity_type === 'image')
  data.related.pagination = { page: 2, pages: 3, page_size: 25, total: 52 }
  route.query = { related_page: '2', context: 'retained' }
  api.entity.mockResolvedValue(data)
  const wrapper = mount(EventPage, { global })
  await flushPromises()
  expect(wrapper.text()).toContain('1 auf dieser Seite von 52 insgesamt')
  expect(wrapper.text()).toContain('Weitere verknüpfte Datensätze stehen auf anderen Seiten.')
  expect(wrapper.text()).toContain('keine chronologische Terminliste')
  expect(wrapper.findAll('h3').map((heading) => heading.text())).not.toContain('Medien')
  expect(wrapper.text()).not.toContain('Keine Termine')
  expect(
    wrapper
      .findAll('a')
      .find((a) => a.text() === 'Weiter')!
      .attributes('data-to'),
  ).toContain('"context":"retained"')
  wrapper.unmount()
})

it('keeps organizer and standard location independent of a global page containing only 25 of 30 dates', async () => {
  const first = paginatedEventDetailFixture(1)
  api.entity.mockResolvedValueOnce(first)
  const wrapper = mount(EventPage, { global })
  await flushPromises()
  const relations = () => wrapper.get('[data-event-relations]')
  expect(
    relations()
      .findAll('h4')
      .map((heading) => heading.text()),
  ).toEqual(first.related.items.map((item) => item.entity_name))
  expect(relations().text()).toContain('25 auf dieser Seite von 34 insgesamt')
  expect(wrapper.get('[data-entity-hero]').text()).toContain(
    `Veranstalter: ${first.item.organization_name}`,
  )
  const facts = wrapper
    .findAllComponents(RecordSection)
    .find((section) => section.props('title') === 'Auf einen Blick')!
  expect(facts.text()).toContain('Termine insgesamt30')
  expect(facts.text()).toContain(`Standardort${first.item.facts.venue_name}`)
  expect(facts.text()).toContain(`Standardraum${first.item.facts.space_name}`)
  expect(relations().text()).not.toContain('Plakat zur Kulturnacht')
  for (const title of ['Termine', 'Veranstalter', 'Orte & Räume', 'Medien', 'Weitere Beziehungen'])
    expect(wrapper.findAll('h3').map((heading) => heading.text())).not.toContain(title)
  const second = paginatedEventDetailFixture(2)
  api.entity.mockResolvedValueOnce(second)
  route.query = { related_page: '2' }
  route.fullPath += '?related_page=2'
  await flushPromises()
  expect(api.entity).toHaveBeenLastCalledWith('events', first.item.entity_key, 2)
  expect(
    relations()
      .findAll('h4')
      .map((heading) => heading.text()),
  ).toEqual(second.related.items.map((item) => item.entity_name))
  expect(relations().text()).toContain('9 auf dieser Seite von 34 insgesamt')
  expect(relations().text()).toContain('Plakat zur Kulturnacht')
  expect(wrapper.get('[data-entity-hero]').text()).toContain(
    `Veranstalter: ${first.item.organization_name}`,
  )
  wrapper.unmount()
})
it('retains the same record on refresh and failure, clears on identity change, ignores late responses', async () => {
  const wrapper = mount(EventPage, { global })
  await flushPromises()
  let resolve!: (value: EntityDetail) => void
  api.entity.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  route.query = { related_page: '2' }
  route.fullPath += '?related_page=2'
  await flushPromises()
  expect(wrapper.get('h2').text()).toBe('Kulturnacht am Hafen')
  expect(wrapper.text()).toContain('Daten werden aktualisiert')
  api.entity.mockRejectedValueOnce(new Error('private driver'))
  route.fullPath += '&retry=1'
  await flushPromises()
  expect(wrapper.get('h2').text()).toBe('Kulturnacht am Hafen')
  expect(wrapper.text()).toContain('veraltet')
  expect(wrapper.text()).not.toContain('private driver')
  const other = eventDetailFixture()
  other.item.entity_name = 'Anderer Datensatz'
  api.entity.mockResolvedValueOnce(other)
  route.params.id = '20000000-0000-4000-8000-000000000099'
  route.fullPath = `/events/${route.params.id}`
  await flushPromises()
  resolve(eventDetailFixture())
  await flushPromises()
  expect(wrapper.get('h2').text()).toBe('Anderer Datensatz')
  wrapper.unmount()
})
it('offers UUID copy with accessible failure feedback', async () => {
  vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error()) } })
  const wrapper = mount(EntityTechnicalMetadata, { props: { data: eventDetailFixture() }, global })
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role="status"]').text()).toContain('Kopieren nicht verfügbar')
})
it('formats record timestamps in the explicit admin zone across DST', () => {
  expect(recordDateTime('2026-03-29T00:30:00Z')).toBe('29.03.2026 · 01:30')
  expect(recordDateTime('2026-03-29T01:30:00Z')).toBe('29.03.2026 · 03:30')
  expect(recordDateTime('2026-03-29T01:30:00Z', 'UTC')).toBe('29.03.2026 · 01:30')
})

it.each([401, 403, 404])(
  'discards the last record on access loss or removal (%s)',
  async (status) => {
    const wrapper = mount(EventPage, { global })
    await flushPromises()
    expect(wrapper.get('h2').text()).toBe('Kulturnacht am Hafen')
    api.entity.mockRejectedValueOnce(new AdminApiError(failure(status)))
    route.fullPath += '?related_page=2'
    await flushPromises()
    expect(wrapper.text()).not.toContain('Kulturnacht am Hafen')
    expect(wrapper.find('.prose-admin').exists()).toBe(false)
    wrapper.unmount()
  },
)

const placePages = { organizations: OrganizationPage, venues: VenuePage, spaces: SpacePage }
it.each(placeSections)(
  'renders %s as a record with one title and technical metadata last',
  async (section) => {
    const data = placeDetailFixture(section)
    route.params.id = data.item.entity_key
    route.fullPath = `/${section}/${route.params.id}`
    api.entity.mockResolvedValue(data)
    const wrapper = mount(placePages[section], { global })
    await flushPromises()
    expect(api.entity).toHaveBeenLastCalledWith(section, data.item.entity_key, 1)
    expect(wrapper.findAll('h2').map((heading) => heading.text())).toEqual([data.item.entity_name])
    const hero = wrapper.get('[data-entity-hero]')
    expect(hero.text()).not.toContain(data.item.entity_key)
    expect(hero.find('li').exists()).toBe(false)
    expect(wrapper.find('.prose-admin').exists()).toBe(false)
    expect(
      wrapper
        .findAll('h3')
        .map((heading) => heading.text())
        .slice(-4),
    ).toEqual([
      'Verknüpfte Datensätze',
      'Qualität & Arbeitsstand',
      'Verlauf',
      'Technische Informationen',
    ])
    expect(wrapper.findAllComponents(RecordSection).at(-1)!.text()).toContain(data.item.entity_key)
    const links = hero.findAll('a')
    expect(links.find((link) => link.text() === 'Beziehungen')!.attributes('data-to')).toContain(
      `root_type=${data.item.entity_type}`,
    )
    expect(
      links.find((link) => link.text().includes('Markierungen'))!.attributes('data-to'),
    ).toContain(`"entity_key":"${data.item.entity_key}"`)
    wrapper.unmount()
  },
)

it('shows organization counts including invitations without repeating its own name or address in the hero', async () => {
  const data = placeDetailFixture('organizations')
  api.entity.mockResolvedValue(data)
  const wrapper = mount(OrganizationPage, { global })
  await flushPromises()
  const hero = wrapper.get('[data-entity-hero]')
  expect(hero.text().split(data.item.entity_name).length - 1).toBe(1)
  expect(hero.text()).toContain('Flensburg')
  expect(hero.text()).not.toContain(data.item.address)
  const facts = wrapper
    .findAllComponents(RecordSection)
    .find((section) => section.props('title') === 'Auf einen Blick')!
  expect(facts.findAll('dt').map((term) => term.text())).toEqual([
    'Veranstaltungen',
    'Orte',
    'Teammitgliedschaften',
  ])
  expect(facts.findAll('dd.font-semibold').map((value) => value.text())).toEqual(['26', '1', '1'])
  expect(facts.text()).toContain('Einschließlich Einladungen')
  expect(wrapper.text()).not.toMatch(/aktive Mitglieder/i)
  expect(wrapper.getComponent(RecordLocation).text()).toContain(data.item.address)
  expect(hero.find('.button-primary').exists()).toBe(false)
  const osm = wrapper.getComponent(RecordLocation).get('a')
  expect(osm.attributes('rel')).toBe('noopener noreferrer')
  expect(osm.attributes('referrerpolicy')).toBe('no-referrer')
  expect(osm.attributes('aria-label')).toContain('(neuer Tab)')
  expect(wrapper.get('[data-record-relations]').text()).toContain(
    '25 auf dieser Seite von 28 insgesamt',
  )
  wrapper.unmount()
})

it.each([null, 0])('preserves unknown versus zero domain counts (%s)', (value) => {
  for (const section of ['organizations', 'venues'] as const) {
    const data = placeDetailFixture(section)
    data.item.facts = { events: value, venues: value, memberships: value, spaces: value }
    const wrapper = mount(
      section === 'organizations' ? OrganizationDetailContent : VenueDetailContent,
      { props: { data, loading: false }, global },
    )
    expect(
      wrapper
        .findAllComponents(RecordSection)[0]!
        .findAll('dd.font-semibold')
        .map((entry) => entry.text()),
    ).toEqual(
      Array(section === 'organizations' ? 3 : 1).fill(value === null ? 'Nicht verfügbar' : '0'),
    )
    wrapper.unmount()
  }
})

it('shows venue organization and address, uses only the provided public URL and has no invented location', async () => {
  const data = placeDetailFixture('venues')
  api.entity.mockResolvedValue(data)
  const wrapper = mount(VenuePage, { global })
  await flushPromises()
  expect(wrapper.get('[data-entity-hero]').text()).toContain(
    `Organisation: ${data.item.organization_name}`,
  )
  expect(wrapper.getComponent(RecordLocation).text()).toContain(data.item.address)
  expect(wrapper.get('a.button-primary').attributes('href')).toBe(data.item.public_url)
  expect(wrapper.getComponent(RecordLocation).find('a').exists()).toBe(false)
  expect(wrapper.text()).toContain('Räume insgesamt1')
  const updated = structuredClone(data)
  updated.item.public_url = null
  api.entity.mockResolvedValueOnce(updated)
  route.fullPath += '?refresh=1'
  await flushPromises()
  expect(wrapper.find('.button-primary').exists()).toBe(false)
  wrapper.unmount()
})

it('uses the central OSM helper only for valid provided locations and omits empty address sections', async () => {
  const item = placeDetailFixture('venues').item
  const wrapper = mount(RecordLocation, { props: { item }, global })
  expect(wrapper.find('a').exists()).toBe(false)
  await wrapper.setProps({ item: { ...item, location: { latitude: 0, longitude: 0 } } })
  expect(wrapper.get('a').attributes('href')).toBe(
    'https://www.openstreetmap.org/?mlat=0&mlon=0#map=17/0/0',
  )
  await wrapper.setProps({ item: { ...item, address: null, location: null } })
  expect(wrapper.find('section').exists()).toBe(false)
  await wrapper.setProps({
    item: { ...item, address: '  ', location: { latitude: 91, longitude: 0 } },
  })
  expect(wrapper.find('section').exists()).toBe(false)
  wrapper.unmount()
})

it('shows space venue and organization once and links only through a supplied canonical venue relation', async () => {
  const data = placeDetailFixture('spaces')
  api.entity.mockResolvedValue(data)
  const wrapper = mount(SpacePage, { global })
  await flushPromises()
  const context = wrapper.getComponent(SpaceDetailContext)
  expect(context.findAll('dt').map((term) => term.text())).toEqual([
    'Zugehöriger Ort',
    'Organisation',
  ])
  expect(context.text().split(data.item.facts.venue_name!).length - 1).toBe(1)
  expect(context.text()).toContain(data.item.organization_name)
  expect(context.get('a').attributes('data-to')).toBe(
    JSON.stringify(data.related.items[0]!.action!.href),
  )
  expect(
    wrapper.get('[data-entity-hero]').text().split(data.item.facts.venue_name!).length - 1,
  ).toBe(1)
  expect(wrapper.find('.button-primary').exists()).toBe(false)
  const updated = structuredClone(data)
  updated.related.items = []
  api.entity.mockResolvedValueOnce(updated)
  route.fullPath += '?related_page=2'
  await flushPromises()
  expect(context.find('a').exists()).toBe(false)
  expect(context.text()).toContain(data.item.facts.venue_name)
  wrapper.unmount()
})

it('keeps the event hero default context and allows domains to replace it without duplicate fallback content', () => {
  const item = eventDetailFixture().item
  const normal = mount(EntityHero, {
    props: { item, section: 'events', organizationLabel: 'Veranstalter' },
    global,
  })
  expect(normal.text()).toContain(`Veranstalter: ${item.organization_name}`)
  expect(normal.text()).toContain(item.subtitle)
  const custom = mount(EntityHero, {
    props: { item, section: 'events' },
    slots: { context: '<p>Fachlicher Kontext</p>' },
    global,
  })
  expect(custom.text()).toContain('Fachlicher Kontext')
  expect(custom.text()).not.toContain(item.organization_name)
  expect(custom.text()).not.toContain(item.subtitle)
  normal.unmount()
  custom.unmount()
})

it.each([
  [null, null],
  [0, 0],
  [null, 3],
  [2, null],
])('preserves workflow count semantics (%s, %s)', (findings, marks) => {
  const item = placeDetailFixture('organizations').item
  item.finding_count = findings
  item.mark_count = marks
  const wrapper = mount(RecordWorkflowSummary, { props: { item }, global })
  expect(wrapper.findAll('dd').map((entry) => entry.text())).toEqual(
    [findings, marks].filter((value) => value !== null).map(String),
  )
  expect(wrapper.text().includes('Der Arbeitsstand ist nicht verfügbar.')).toBe(
    findings === null && marks === null,
  )
  const link = wrapper.get('a').attributes('data-to')
  expect(link).toContain(`"entity_type":"${item.entity_type}"`)
  expect(link).toContain(`"entity_key":"${item.entity_key}"`)
  wrapper.unmount()
})

it('preserves the server relation order, query context, busy state and honest empty state', async () => {
  const data = placeDetailFixture('organizations')
  route.query = { context: 'retained', geo_scope: 'selected', related_page: '1' }
  const wrapper = mount(RecordRelations, { props: { data, loading: false }, global })
  expect(wrapper.findAll('h4').map((heading) => heading.text())).toEqual(
    data.related.items.map((item) => item.entity_name),
  )
  const next = wrapper.findAll('a').find((link) => link.text() === 'Weiter')!
  expect(JSON.parse(next.attributes('data-to'))).toEqual({
    query: { ...route.query, related_page: '2' },
  })
  await wrapper.setProps({ loading: true })
  expect(wrapper.get('section').attributes('aria-busy')).toBe('true')
  await wrapper.setProps({
    loading: false,
    data: {
      ...data,
      related: { items: [], pagination: { page: 1, pages: 0, page_size: 25, total: 0 } },
    },
  })
  expect(wrapper.text()).toContain('Keine belegten Verknüpfungen auf dieser Seite vorhanden.')
  expect(wrapper.find('nav').exists()).toBe(false)
  wrapper.unmount()
})

it('retains organization refresh data, marks stale failures, immediately clears a changed identity and ignores late responses', async () => {
  const data = placeDetailFixture('organizations')
  api.entity.mockResolvedValue(data)
  const wrapper = mount(OrganizationPage, { global })
  await flushPromises()
  let oldResponse!: (value: EntityDetail) => void
  api.entity.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        oldResponse = resolve
      }),
  )
  route.fullPath += '?related_page=2'
  await flushPromises()
  expect(wrapper.get('h2').text()).toBe(data.item.entity_name)
  expect(wrapper.text()).toContain('Daten werden aktualisiert')
  api.entity.mockRejectedValueOnce(new Error('private driver'))
  route.fullPath += '&retry=1'
  await flushPromises()
  expect(wrapper.get('h2').text()).toBe(data.item.entity_name)
  expect(wrapper.text()).toContain('veraltet')
  expect(wrapper.text()).not.toContain('private driver')
  let newResponse!: (value: EntityDetail) => void
  api.entity.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        newResponse = resolve
      }),
  )
  route.params.id = '20000000-0000-4000-8000-000000000099'
  route.fullPath = `/organizations/${route.params.id}`
  await flushPromises()
  expect(wrapper.find('[data-entity-hero]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain(data.item.entity_name)
  oldResponse(data)
  await flushPromises()
  expect(wrapper.find('[data-entity-hero]').exists()).toBe(false)
  const next = placeDetailFixture('organizations')
  next.item.entity_key = route.params.id
  next.item.entity_name = 'Neue Organisation'
  newResponse(next)
  await flushPromises()
  expect(wrapper.get('h2').text()).toBe('Neue Organisation')
  wrapper.unmount()
})

it.each([401, 403, 404])(
  'discards organization data on access loss or removal (%s)',
  async (status) => {
    const data = placeDetailFixture('organizations')
    api.entity.mockResolvedValue(data)
    const wrapper = mount(OrganizationPage, { global })
    await flushPromises()
    expect(wrapper.get('h2').text()).toBe(data.item.entity_name)
    api.entity.mockRejectedValueOnce(new AdminApiError(failure(status)))
    route.fullPath += '?related_page=2'
    await flushPromises()
    expect(wrapper.find('[data-entity-hero]').exists()).toBe(false)
    expect(wrapper.find('[data-record-relations]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(data.item.entity_name)
    wrapper.unmount()
  },
)
