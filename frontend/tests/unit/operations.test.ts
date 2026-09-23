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
import { timelineFixture } from '../fixtures/entities'

afterEach(() => vi.unstubAllGlobals())

it('distinguishes zero, false, missing and blank facts and escapes values', () => {
  const view = mount(CompactFacts, {
    props: {
      items: [
        { label: 'Anzahl', value: 0, metadata: 'einschließlich Einladungen' },
        { label: 'Aktiv', value: false },
        { label: 'Unbekannt', value: null },
        { label: 'Leer', value: '  ' },
        { label: 'Name', value: '<img src=x onerror=alert(1)>' },
      ],
    },
  })
  expect(view.findAll('dt').map((el) => el.text())).toEqual([
    'Anzahl',
    'Aktiv',
    'Unbekannt',
    'Leer',
    'Name',
  ])
  expect(view.findAll('dd').map((el) => el.text())).toEqual([
    '0 einschließlich Einladungen',
    'Nein',
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

it('preserves named sections and compact empty-state recovery actions', async () => {
  const view = mount(RecordSection, {
    props: { title: 'Kontext', surface: 'panel' },
    slots: { default: '<p>Fakten</p>', actions: '<button>Öffnen</button>' },
  })
  expect(view.attributes('aria-labelledby')).toBe(view.get('h3').attributes('id'))
  expect(view.get('button').text()).toBe('Öffnen')
  const reset = vi.fn()
  const empty = mount(EmptyState, {
    props: { message: 'Keine Treffer', compact: true },
    slots: { default: () => h('button', { onClick: reset }, 'Filter zurücksetzen') },
  })
  await empty.get('button').trigger('click')
  expect(reset).toHaveBeenCalledOnce()
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
