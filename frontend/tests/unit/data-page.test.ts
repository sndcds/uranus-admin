import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import DataListShell from '../../app/components/DataListShell.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import ResultSummary from '../../app/components/ResultSummary.vue'
import PaginationBar from '../../app/components/PaginationBar.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import EntityTypeBadge from '../../app/components/EntityTypeBadge.vue'

const NuxtLink = defineComponent({
  props: ['to'],
  setup:
    (props, { slots }) =>
    () =>
      h('a', { href: props.to }, slots.default?.()),
})
describe('shared data-page primitives', () => {
  it('gives page headers a heading, description and actions', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Befunde', description: 'Gespeicherter Bestand', titleId: 'results' },
      slots: { default: '<button>Aktualisieren</button>' },
    })
    expect(wrapper.get('h2').text()).toBe('Befunde')
    expect(wrapper.get('h2').attributes('id')).toBe('results')
    expect(wrapper.text()).toContain('Gespeicherter Bestand')
    expect(wrapper.get('button').text()).toBe('Aktualisieren')
  })
  it('submits filters without navigating and retains labelled controls and help', async () => {
    const wrapper = mount(FilterBar, {
      slots: {
        default:
          '<label>Objektart<select><option>Ort</option></select></label><button>Anwenden</button>',
        help: '<p>Filterhilfe</p>',
      },
    })
    expect(wrapper.attributes('aria-label')).toBe('Filter')
    await wrapper.trigger('submit')
    expect(wrapper.emitted('apply')).toHaveLength(1)
    expect(wrapper.text()).toContain('Filterhilfe')
  })
  it('keeps server totals separate from visible-page counts', () => {
    const wrapper = mount(ResultSummary, {
      props: { total: 298, visible: 25, noun: 'Befunde', description: 'Gespeicherte Befunde' },
      slots: { default: '12 Fehler · auf dieser Seite' },
    })
    expect(wrapper.text()).toContain('298 Befunde insgesamt')
    expect(wrapper.text()).toContain('Auf dieser Seite: 25 Einträge')
    expect(wrapper.text()).toContain('12 Fehler · auf dieser Seite')
    expect(wrapper.text()).not.toContain('Stand:')
  })
  it('emits bounded pagination and disables controls while loading or empty', async () => {
    const wrapper = mount(PaginationBar, {
      props: { pagination: { page: 1, pages: 4 } },
      global: { stubs: { NuxtLink } },
    })
    expect(wrapper.attributes('aria-label')).toBe('Seitennavigation')
    expect(wrapper.text()).toContain('Seite 1 von 4')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('change')).toEqual([[2]])
    await wrapper.setProps({ loading: true })
    expect(
      wrapper.findAll('button').every((button) => button.attributes('disabled') !== undefined),
    ).toBe(true)
    await wrapper.setProps({ loading: false, pagination: { page: 1, pages: 0 } })
    expect(wrapper.text()).toContain('Keine Ergebnisse')
    expect(
      wrapper.findAll('button').every((button) => button.attributes('disabled') !== undefined),
    ).toBe(true)
  })
  it('keeps URL pagination links and disables unavailable directions', () => {
    const wrapper = mount(PaginationBar, {
      props: {
        pagination: { page: 2, pages: 2 },
        to: (page) => `/activity?page=${page}&period=7d`,
      },
      global: { stubs: { NuxtLink } },
    })
    expect(wrapper.get('a').attributes('href')).toBe('/activity?page=1&period=7d')
    expect(wrapper.get('a').attributes('rel')).toBe('prev')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })
  it('preserves list semantics, busy state and labelled grouping in the shared surface', () => {
    const list = mount(DataListShell, {
      props: { as: 'ul' },
      attrs: { 'aria-label': 'Prüfläufe', 'aria-busy': 'true' },
      slots: { default: '<li>Erfolgreich</li>' },
    })
    expect(list.element.tagName).toBe('UL')
    expect(list.get('li').text()).toBe('Erfolgreich')
    expect(list.attributes('aria-busy')).toBe('true')
    expect(list.attributes('aria-label')).toBe('Prüfläufe')
    const groups = mount(DataListShell, {
      slots: { default: '<section><h3>Heute</h3><ul><li>Termin</li></ul></section>' },
    })
    expect(groups.get('section h3').text()).toBe('Heute')
    expect(groups.findAll('li')).toHaveLength(1)
  })
  it('does not claim a visible-page distribution for an aggregate summary', () => {
    const wrapper = mount(ResultSummary, {
      props: { total: 298, noun: 'Befunde' },
      slots: { default: '178 Fehler' },
    })
    expect(wrapper.text()).toContain('298 Befunde insgesamt')
    expect(wrapper.text()).toContain('178 Fehler')
    expect(wrapper.text()).not.toContain('Auf dieser Seite')
  })
  it('shows helpful empty states and readable badge labels independent of color', () => {
    expect(
      mount(EmptyState, { props: { message: 'Keine Befunde. Filter zurücksetzen.' } }).text(),
    ).toContain('Filter zurücksetzen')
    expect(mount(StatusBadge, { props: { label: 'Fehlgeschlagen', tone: 'error' } }).text()).toBe(
      'Fehlgeschlagen',
    )
    expect(mount(EntityTypeBadge, { props: { type: 'event_date' } }).text()).toBe('Termin')
    expect(mount(EntityTypeBadge, { props: { type: 'event_link' } }).text()).toBe(
      'Veranstaltungslink',
    )
    expect(mount(EntityTypeBadge, { props: { type: 'new_kind' } }).text()).toBe('new_kind')
  })
})

it('keeps header badges separate from heading text', () => {
  const view = mount(PageHeader, {
    props: { title: 'Beziehungsgraph' },
    slots: { badge: '<span>Beta</span>' },
  })
  expect(view.get('h2').text()).toBe('Beziehungsgraph')
  expect(view.text()).toContain('Beta')
})
