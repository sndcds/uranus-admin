import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SectionHeader from '../../app/components/SectionHeader.vue'
import InlineAlert from '../../app/components/InlineAlert.vue'
import DetailFacts from '../../app/components/DetailFacts.vue'
import { isNavigationActive } from '../../app/utils/navigation'
import { statisticsRecentLink, statisticsTypes } from '../../app/utils/statistics'
import { entityTypes, invitationPresentation } from '../../app/utils/entityPresentation'

it('uses semantic section headings and preserves actions and descriptions', () => {
  const view = mount(SectionHeader, {
    props: { title: 'Verknüpfungen', titleId: 'related', description: 'Belegte Beziehungen' },
    slots: { default: '<button>Öffnen</button>' },
  })
  expect(view.get('h3').attributes('id')).toBe('related')
  expect(view.text()).toContain('Belegte Beziehungen')
  expect(view.get('button').text()).toBe('Öffnen')
})
it('announces errors and information with appropriate live-region semantics', () => {
  expect(
    mount(InlineAlert, {
      props: { tone: 'error' },
      slots: { default: 'Fehlgeschlagen' },
    }).attributes('role'),
  ).toBe('alert')
  expect(mount(InlineAlert, { slots: { default: 'Aktualisiert' } }).attributes('role')).toBe(
    'status',
  )
})
it('keeps zero and false facts, omits null and escapes source text', () => {
  const view = mount(DetailFacts, {
    props: {
      items: [
        { label: 'Anzahl', value: 0 },
        { label: 'Aktiv', value: false },
        { label: 'Fehlt', value: null },
        { label: 'Name', value: '<script>unsafe</script>' },
      ],
    },
  })
  expect(view.findAll('dt').map((node) => node.text())).toEqual(['Anzahl', 'Aktiv', 'Name'])
  expect(view.findAll('dd').map((node) => node.text())).toEqual([
    '0',
    'Nein',
    '<script>unsafe</script>',
  ])
  expect(view.find('script').exists()).toBe(false)
})
it.each([
  ['/events', '/events', true],
  ['/events/id', '/events', true],
  ['/events-other', '/events', false],
  ['/spaces/id', '/venues', true],
  ['/venues/id', '/venues', true],
  ['/statistics', '/statistics', true],
  ['/graph', '/graph', true],
  ['/events', '/', false],
  ['/', '/', true],
])('navigation %s belongs to %s: %s', (path, target, active) => {
  expect(isNavigationActive(path, target)).toBe(active)
})
it('preserves canonical and queue hrefs and adds the statistics basis only to Activity', () => {
  for (const href of [
    '/events/uuid',
    '/venues/uuid?tab=dates',
    '/queues/team_invitations?entity_key=membership:x:y',
  ])
    expect(statisticsRecentLink(href)).toBe(href)
  expect(statisticsRecentLink('/activity')).toBe('/activity?creation_basis=statistics')
  expect(statisticsRecentLink('/activity?entity_key=x&creation_basis=other#row')).toBe(
    '/activity?entity_key=x&creation_basis=statistics#row',
  )
})
it('shares entity identity without conflating invitations with memberships', () => {
  expect(statisticsTypes.event.singular).toBe(entityTypes.event.label)
  expect(statisticsTypes.event.color).toBe(entityTypes.event.color)
  expect(statisticsTypes.team_invitation.singular).toBe(invitationPresentation.label)
  expect(statisticsTypes.team_invitation.singular).not.toBe(entityTypes.team_membership.label)
})
