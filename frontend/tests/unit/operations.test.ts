import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import CompactFacts from '../../app/components/CompactFacts.vue'
import TechnicalInfoBar from '../../app/components/TechnicalInfoBar.vue'
import DenseTable from '../../app/components/DenseTable.vue'
import RecordSection from '../../app/components/RecordSection.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import EntityTimeline from '../../app/components/EntityTimeline.vue'
import DataListShell from '../../app/components/DataListShell.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import EntityTechnicalMetadata from '../../app/components/EntityTechnicalMetadata.vue'
import { eventDetailFixture } from '../fixtures/event-detail'
import { timelineFixture } from '../fixtures/entities'

afterEach(() => vi.unstubAllGlobals())

it('distinguishes zero, false, missing and blank facts and escapes values', () => {
  const view = mount(CompactFacts, {
    props: {
      items: [
        { label: 'Anzahl', value: 0, description: 'einschließlich Einladungen' },
        { label: 'Aktiv', value: false },
        { label: 'Geprüft', value: true },
        { label: 'Unbekannt', value: null },
        { label: 'Leer', value: '  ' },
        { label: 'Name', value: '<img src=x onerror=alert(1)>' },
      ],
    },
  })
  expect(view.findAll('dt').map((el) => el.text())).toEqual([
    'Anzahl',
    'Aktiv',
    'Geprüft',
    'Unbekannt',
    'Leer',
    'Name',
  ])
  expect(view.findAll('dd').map((el) => el.text())).toEqual([
    '0 einschließlich Einladungen',
    'Nein',
    'Ja',
    'Nicht verfügbar',
    'Nicht verfügbar',
    '<img src=x onerror=alert(1)>',
  ])
  expect(view.find('img').exists()).toBe(false)
})

it('omits only absent values when requested and hides an empty facts grid', async () => {
  const view = mount(CompactFacts, {
    props: {
      missing: 'omit',
      items: [
        { label: 'Null', value: null },
        { label: 'Leer', value: '' },
        { label: 'Anzahl', value: 0 },
        { label: 'Aktiv', value: false },
      ],
    },
  })
  expect(view.findAll('dt').map((el) => el.text())).toEqual(['Anzahl', 'Aktiv'])
  await view.setProps({ items: [] })
  expect(view.find('dl').exists()).toBe(false)
})

it('shows only supplied technical values and reports clipboard success and failure accessibly', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const view = mount(TechnicalInfoBar, {
    props: {
      items: [
        { label: 'UUID', value: 'test-key', mono: true, copyable: true },
        { label: 'Versuche', value: 0 },
        { label: 'Fehlt', value: null },
        { label: 'Unbekannt', value: undefined },
        { label: 'Leer', value: ' ' },
      ],
    },
  })
  expect(view.findAll('dt').map((el) => el.text())).toEqual(['UUID', 'Versuche'])
  expect(view.get('code').text()).toBe('test-key')
  expect(view.attributes('aria-labelledby')).toBe(view.get('h3').attributes('id'))
  await view.get('button').trigger('click')
  await flushPromises()
  expect(writeText).toHaveBeenCalledWith('test-key')
  expect(view.get('[role=status]').text()).toBe('UUID kopiert.')
  writeText.mockRejectedValueOnce(new Error('clipboard unavailable'))
  await view.get('button').trigger('click')
  await flushPromises()
  expect(view.get('[role=status]').text()).toContain('als Text ausgewählt')
  expect(view.get('code').text()).toBe('test-key')
  view.unmount()
})

it('discards copy feedback after technical data changes', async () => {
  let release!: () => void
  vi.stubGlobal('navigator', {
    clipboard: {
      writeText: () =>
        new Promise<void>((resolve) => {
          release = resolve
        }),
    },
  })
  const view = mount(TechnicalInfoBar, {
    props: { items: [{ label: 'UUID', value: 'old', copyable: true }] },
  })
  await view.get('button').trigger('click')
  await view.setProps({ items: [{ label: 'UUID', value: 'new' }] })
  release()
  await flushPromises()
  expect(view.get('[role=status]').text()).toBe('')
  expect(view.text()).toContain('new')
  await view.setProps({ items: [{ label: 'UUID', value: null }] })
  expect(view.find('section').exists()).toBe(false)
  view.unmount()
})

it('keeps table semantics, row identity, scoped cells and actionable slot content', async () => {
  const selected = vi.fn()
  const Fixture = defineComponent({
    setup: () => () =>
      h(
        DenseTable,
        {
          caption: 'Arbeitsliste',
          columns: [
            { key: 'name', label: 'Name', rowHeader: true },
            { key: 'count', label: 'Anzahl' },
          ],
          rows: [{ id: 'a', name: '<script>unsafe</script>', count: 0 }],
          rowKey: (row) => String(row.id),
        },
        {
          actions: ({ row }: { row: { id: string } }) =>
            h('button', { onClick: () => selected(row.id) }, 'Öffnen'),
        },
      ),
  })
  const view = mount(Fixture)
  expect(view.get('caption').text()).toBe('Arbeitsliste')
  expect(view.get('tbody th').attributes('scope')).toBe('row')
  expect(view.get('tbody th').attributes('headers')).toBe(view.get('thead th').attributes('id'))
  expect(view.get('tbody').text()).toContain('<script>unsafe</script>')
  expect(view.find('script').exists()).toBe(false)
  expect(view.get('tbody').text()).toContain('0')
  await view.get('button').trigger('click')
  expect(selected).toHaveBeenCalledWith('a')
})

it('distinguishes loading from an empty table and labels its optional scroll region', async () => {
  const view = mount(DenseTable, {
    props: {
      caption: 'Ergebnisse',
      columns: [{ key: 'id', label: 'ID' }],
      rows: [],
      rowKey: (row) => String(row.id),
      busy: true,
      mobile: 'scroll',
    },
  })
  expect(view.findComponent(EmptyState).exists()).toBe(false)
  expect(view.attributes('aria-busy')).toBe('true')
  expect(view.get('[role=region]').attributes('aria-label')).toBe('Ergebnisse')
  expect(view.get('[role=region]').attributes('tabindex')).toBe('0')
  await view.setProps({ busy: false })
  expect(view.findComponent(EmptyState).text()).toContain('Keine Ergebnisse')
})

it('preserves panel headings, icons, actions and compact empty-state recovery', async () => {
  const view = mount(RecordSection, {
    props: { title: 'Kontext', surface: 'panel' },
    slots: {
      default: '<p>Fakten</p>',
      icon: '<svg aria-hidden="true" />',
      actions: '<button>Öffnen</button>',
    },
  })
  expect(view.attributes('aria-labelledby')).toBe(view.get('h3').attributes('id'))
  expect(view.get('button').text()).toBe('Öffnen')
  expect(view.get('h3 svg').attributes('aria-hidden')).toBe('true')
  const reset = vi.fn()
  const empty = mount(EmptyState, {
    props: { title: 'Keine Treffer', message: 'Passe die Filter an.', variant: 'compact' },
    slots: { actions: () => h('button', { onClick: reset }, 'Filter zurücksetzen') },
  })
  await empty.get('button').trigger('click')
  expect(reset).toHaveBeenCalledOnce()
  expect(empty.text()).toContain('Keine Treffer')
  expect(empty.text()).toContain('Passe die Filter an.')
})

it('retains PageHeader slots with named actions and compatible default actions', () => {
  const view = mount(PageHeader, {
    props: { title: 'Datensatz', description: 'Kontext' },
    slots: {
      leading: '<span>Icon</span>',
      badge: '<span>Status</span>',
      context: '<p>Organisation</p>',
      actions: '<button>Aktualisieren</button>',
    },
  })
  expect(view.get('h2').text()).toBe('Datensatz')
  for (const text of ['Kontext', 'Icon', 'Status', 'Organisation'])
    expect(view.text()).toContain(text)
  expect(view.get('button').text()).toBe('Aktualisieren')
  expect(
    mount(PageHeader, {
      props: { title: 'Legacy' },
      slots: { default: '<button>Öffnen</button>' },
    })
      .get('button')
      .text(),
  ).toBe('Öffnen')
})

it('keeps dense list semantics, complete long content and actionable rows', async () => {
  const longValue = 'LangerDatensatzname'.repeat(30)
  const open = vi.fn()
  const view = mount(DataListShell, {
    props: { as: 'ul', dense: true },
    attrs: { 'aria-label': 'Datensätze', 'aria-busy': true },
    slots: {
      default: () =>
        h('li', { class: 'data-row' }, [longValue, h('button', { onClick: open }, 'Öffnen')]),
    },
  })
  expect(view.element.tagName).toBe('UL')
  expect(view.attributes('aria-label')).toBe('Datensätze')
  expect(view.attributes('aria-busy')).toBe('true')
  expect(view.get('li').text()).toContain(longValue)
  await view.get('button').trigger('click')
  expect(open).toHaveBeenCalledOnce()
  expect(
    mount(CompactFacts, { props: { items: [{ label: 'Lang', value: longValue }] } })
      .get('dd')
      .text(),
  ).toBe(longValue)
})

it('can hide the technical heading while preserving a named region and time semantics', () => {
  const view = mount(TechnicalInfoBar, {
    props: {
      showTitle: false,
      items: [
        {
          label: 'Stand',
          value: '29.03.2026 · 03:30',
          datetime: '2026-03-29T01:30:00Z',
          timezone: 'Europe/Berlin',
        },
      ],
    },
  })
  expect(view.find('h3').exists()).toBe(false)
  expect(view.attributes('aria-label')).toBe('Technische Informationen')
  expect(view.get('time').attributes('datetime')).toBe('2026-03-29T01:30:00Z')
  expect(view.get('time').attributes('title')).toBe('Europe/Berlin')
})

it('adapts verified record metadata to the shared bar without inventing creation times', async () => {
  const data = eventDetailFixture()
  data.item.created_at = '2026-03-29T01:30:00Z'
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const view = mount(EntityTechnicalMetadata, { props: { data } })
  expect(view.findAll('dt').map((el) => el.text())).toEqual([
    'UUID',
    'Quelldatensatz angelegt',
    'Datenstand des Abrufs',
  ])
  expect(view.findAll('time').map((el) => el.attributes('datetime'))).toEqual([
    data.item.created_at,
    data.observed_at,
  ])
  expect(view.text()).toContain('29.03.2026 · 03:30')
  expect(view.text()).toContain('Europe/Berlin')
  await view.get('button[aria-label="UUID kopieren"]').trigger('click')
  await flushPromises()
  expect(writeText).toHaveBeenCalledWith(data.item.entity_key)
  expect(view.get('[role=status]').text()).toBe('UUID kopiert.')
  await view.setProps({ data: { ...data, item: { ...data.item, created_at: null } } })
  expect(view.text()).not.toContain('Quelldatensatz angelegt')
  expect(view.findAll('time')).toHaveLength(1)
  expect(view.get('[role=status]').text()).toBe('')
})

it('compact timeline retains evidence, timestamps, links and pagination', async () => {
  const data = timelineFixture('user')
  const timeline = vi
    .fn()
    .mockResolvedValueOnce({ ...data, cursor_pagination: { next_cursor: 'next', has_more: true } })
    .mockResolvedValueOnce(data)
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: { timeline } }))
  const view = mount(EntityTimeline, {
    props: { entityType: 'user', entityKey: 'key', compact: true },
    global: {
      components: { DataListShell, EmptyState },
      stubs: {
        AppIcon: true,
        SectionHeader: true,
        RequestState: true,
        SeverityBadge: true,
        NuxtLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
      },
    },
  })
  await flushPromises()
  expect(view.findAll('li')).toHaveLength(data.items.length)
  expect(view.text()).toContain(data.items[0]!.title)
  expect(view.get('time').attributes('datetime')).toBe(data.items[0]!.occurred_at)
  await view.get('button').trigger('click')
  await flushPromises()
  expect(timeline).toHaveBeenLastCalledWith('user', 'key', 'next')
  expect(view.findAll('li')).toHaveLength(data.items.length)
  view.unmount()
})
