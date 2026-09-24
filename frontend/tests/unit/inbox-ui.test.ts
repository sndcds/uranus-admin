import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, reactive } from 'vue'
import TechnicalInfoBar from '../../app/components/TechnicalInfoBar.vue'
import InlineAlert from '../../app/components/InlineAlert.vue'
import { AdminApiError, failure } from '../../shared/errors'
import Inbox from '../../app/pages/inbox.vue'
import InboxRow from '../../app/components/InboxRow.vue'
import AppIcon from '../../app/components/AppIcon.vue'
import DataListShell from '../../app/components/DataListShell.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import EntityTypeBadge from '../../app/components/EntityTypeBadge.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import PaginationBar from '../../app/components/PaginationBar.vue'
import RequestState from '../../app/components/RequestState.vue'
import ResultSummary from '../../app/components/ResultSummary.vue'
import SeverityBadge from '../../app/components/SeverityBadge.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import { inboxFixture } from '../fixtures/inbox'

const push = vi.fn()
const inbox = vi.fn()
const route = reactive({ query: {} as Record<string, unknown> })

const NuxtLink = defineComponent({
  props: ['to'],
  setup:
    (props, { slots }) =>
    () =>
      h('a', { href: typeof props.to === 'string' ? props.to : '' }, slots.default?.()),
})

const views: { unmount: () => void }[] = []
afterEach(() => views.splice(0).forEach((view) => view.unmount()))
function page() {
  const view = mount(Inbox, {
    global: {
      components: {
        AppIcon,
        TechnicalInfoBar,
        InlineAlert,
        DataListShell,
        EmptyState,
        EntityTypeBadge,
        FilterBar,
        InboxRow,
        PageHeader,
        PaginationBar,
        RequestState,
        ResultSummary,
        SeverityBadge,
        StatusBadge,
      },
      stubs: { NuxtLink },
    },
  })
  views.push(view)
  return view
}

beforeEach(() => {
  vi.clearAllMocks()
  route.query = {}
  inbox.mockResolvedValue(structuredClone(inboxFixture))
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: { inbox } }))
})

describe('Inbox shared list page', () => {
  it('uses the shared shell, real result summary and one divided list surface', async () => {
    const view = page()
    await flushPromises()

    expect(view.findComponent(PageHeader).props()).toMatchObject({
      title: 'Inbox',
      description: 'Aktuelle Aufgaben, Zuständigkeiten und Betriebsfälle.',
    })
    expect(view.findComponent(FilterBar).exists()).toBe(true)
    expect(view.findComponent(RequestState).exists()).toBe(true)
    expect(view.findComponent(ResultSummary).text()).toContain('25 Aufgaben insgesamt')
    expect(view.findComponent(ResultSummary).text()).toContain('Auf dieser Seite: 1 Einträge')
    expect(view.get('button[aria-label="25 Nicht zugewiesen"]').text()).toContain('25')
    expect(view.findAllComponents(DataListShell)).toHaveLength(1)
    expect(view.findAll('.data-list')).toHaveLength(1)
    expect(view.find('.data-list').classes()).toContain('divide-y')
    expect(view.findAll('.data-row')).toHaveLength(1)
    expect(view.findAll('.data-row.card')).toHaveLength(0)
    expect(view.classes()).not.toContain('max-w-')
  })

  it('makes the entity primary and renders safe human workflow and assignment context', async () => {
    const view = page()
    await flushPromises()
    const row = view.get('.data-row')

    expect(row.get('h3').text()).toBe('Kühlhaus Flensburg')
    expect(row.text()).toContain('Kühlhaus e.V.')
    expect(row.text()).toContain('Standortvorschlag')
    expect(row.text()).toContain('Mehrere mögliche Standorte · 3 Kandidaten')
    expect(row.text()).toContain('Zuständig: operator')
    expect(row.text()).not.toContain('ambiguous')
    expect(row.get('a[href="/geocoding/076ca10a-459e-4d96-b7cb-35bd5df3b356"]').text()).toContain(
      'Vorschlag prüfen',
    )
    expect(row.get('a[href="/venues/00000000-0000-4000-8000-000000000020"]').text()).toBe('Öffnen')
  })

  it('restores URL filters and writes changed filters and pagination back to the URL', async () => {
    route.query = {
      scope: 'mine',
      attention: 'overdue',
      kind: 'geocode_request',
      entity_type: 'venue',
      page: '2',
      page_size: '10',
    }
    inbox.mockResolvedValue({
      ...structuredClone(inboxFixture),
      pagination: { page: 2, page_size: 10, total: 25, pages: 3 },
    })
    const view = page()
    await flushPromises()

    expect(view.get('select[aria-label="Einträge pro Seite"]').element).toHaveProperty(
      'value',
      '10',
    )
    const selects = view.findAll('form[aria-label="Filter"] select')
    expect(selects.map((select) => (select.element as HTMLSelectElement).value)).toEqual([
      'mine',
      'overdue',
      'geocode_request',
      'venue',
    ])
    await selects[1]!.setValue('critical')
    await view.get('form[aria-label="Filter"]').trigger('submit')
    expect(push).toHaveBeenLastCalledWith({
      query: {
        scope: 'mine',
        attention: 'critical',
        kind: 'geocode_request',
        entity_type: 'venue',
        page_size: 10,
      },
    })
    await view.get('nav[aria-label="Inbox-Seitennavigation"] button:last-child').trigger('click')
    expect(push).toHaveBeenLastCalledWith({
      query: {
        scope: 'mine',
        attention: 'overdue',
        kind: 'geocode_request',
        entity_type: 'venue',
        page: 3,
        page_size: 10,
      },
    })
  })

  it('uses EmptyState when the selected Inbox page has no tasks', async () => {
    inbox.mockResolvedValue({
      ...structuredClone(inboxFixture),
      items: [],
      pagination: { page: 1, page_size: 25, total: 0, pages: 0 },
    })
    const view = page()
    await flushPromises()
    expect(view.findComponent(EmptyState).text()).toContain('keine aktiven Aufgaben')
    expect(view.findAllComponents(DataListShell)).toHaveLength(0)
  })
})

it('restores the reminder filter and shows authoritative reminder counts and time', async () => {
  route.query = { attention: 'snoozed' }
  const fixture = structuredClone(inboxFixture)
  fixture.counts.snoozed = 12
  fixture.items[0]!.snoozed_until = '2027-01-25T08:00:00Z'
  inbox.mockResolvedValue(fixture)
  const view = page()
  await flushPromises()
  expect(inbox).toHaveBeenCalledWith(expect.objectContaining({ attention: 'snoozed' }))
  expect(view.get('button[aria-label="12 Wiedervorlagen"]').attributes('aria-pressed')).toBe('true')
  expect(view.get('.data-row').text()).toContain('25.01.2027, 09:00')
  expect(view.get('time[datetime="2027-01-25T08:00:00Z"]').attributes('datetime')).toBe(
    '2027-01-25T08:00:00Z',
  )
})

it.each([
  ['Kritisch', { attention: 'critical' }],
  ['Meine', { scope: 'mine' }],
  ['Nicht zugewiesen', { scope: 'unassigned' }],
  ['Heute fällig', { attention: 'due_today' }],
  ['Überfällig', { attention: 'overdue' }],
  ['Wiedervorlagen', { attention: 'snoozed' }],
])(
  'writes the %s count shortcut to the URL, preserving unrelated filters',
  async (label, filter) => {
    route.query = { kind: 'finding', entity_type: 'venue', page: '3', page_size: '10' }
    const view = page()
    await flushPromises()
    await view
      .findAll('button[aria-pressed]')
      .find((button) => button.attributes('aria-label')?.endsWith(` ${label}`))!
      .trigger('click')
    expect(push).toHaveBeenLastCalledWith({
      query: { kind: 'finding', entity_type: 'venue', page_size: 10, ...filter },
    })
    route.query = { ...filter }
    await flushPromises()
    expect(view.findAll('button[aria-pressed="true"]')).toHaveLength(1)
  },
)
it.each([{ page: '0' }, { scope: ['mine', 'all'] }, { unknown: 'x' }])(
  'rejects invalid URL %j without an API request',
  async (query) => {
    route.query = query
    const view = page()
    await flushPromises()
    expect(inbox).not.toHaveBeenCalled()
    expect(view.text()).toContain('ungültige Inbox-Filter')
  },
)
it('retains same-query refresh data but clears on query change, stale invalid-query responses and denial', async () => {
  const view = page()
  await flushPromises()
  inbox.mockRejectedValueOnce(new AdminApiError(failure(503)))
  await view
    .findAll('button')
    .find((el) => el.text().includes('Aktualisieren'))!
    .trigger('click')
  await flushPromises()
  expect(view.text()).toContain('Kühlhaus Flensburg')
  expect(view.text()).toContain('veraltet')
  let resolve!: (value: typeof inboxFixture) => void
  inbox.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  route.query = { scope: 'mine' }
  await flushPromises()
  expect(view.text()).not.toContain('Kühlhaus Flensburg')
  route.query = { page: '0' }
  await flushPromises()
  resolve(inboxFixture)
  await flushPromises()
  expect(view.text()).not.toContain('Kühlhaus Flensburg')
  route.query = {}
  await flushPromises()
  inbox.mockRejectedValueOnce(new AdminApiError(failure(403)))
  await view
    .findAll('button')
    .find((el) => el.text().includes('Aktualisieren'))!
    .trigger('click')
  await flushPromises()
  expect(view.text()).not.toContain('Kühlhaus Flensburg')
  expect(view.text()).toContain('Zugriff gesperrt')
})
