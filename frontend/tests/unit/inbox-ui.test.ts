import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, reactive } from 'vue'
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
const route = reactive({ query: {} as Record<string, string> })

const NuxtLink = defineComponent({
  props: ['to'],
  setup:
    (props, { slots }) =>
    () =>
      h('a', { href: typeof props.to === 'string' ? props.to : '' }, slots.default?.()),
})

function page() {
  return mount(Inbox, {
    global: {
      components: {
        AppIcon,
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
    expect(view.findComponent(ResultSummary).text()).toContain('25 nicht zugewiesen')
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
    expect(row.get('a[href="/venues/00000000-0000-4000-8000-000000000020"]').text()).toBe(
      'Ort ansehen',
    )
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
  expect(view.findComponent(ResultSummary).text()).toContain('12 Wiedervorlagen')
  expect(view.get('.data-row').text()).toContain('25.01.2027, 09:00')
  expect(view.get('time').attributes('datetime')).toBe('2027-01-25T08:00:00Z')
})
