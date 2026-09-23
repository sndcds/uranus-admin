import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
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
const api = { entity: vi.fn() }
const route = reactive({ params: { id: '' }, query: {} as Record<string, string>, fullPath: '' })
const global = {
  components: {
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
  vi.clearAllMocks()
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
  expect(wrapper.text()).toContain(
    'Weitere Termine, Orte oder Medien können auf anderen Seiten stehen.',
  )
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
