import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import QualityOverview from '../../app/components/QualityOverview.vue'
import DataListShell from '../../app/components/DataListShell.vue'
import SeverityBadge from '../../app/components/SeverityBadge.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import { summary } from '../fixtures/api'
import { summarySchema } from '../../shared/contracts'

const ruleCounts = {
  venue_missing_logo: 12,
  organization_missing_logo: 4,
  logo_unsupported_format: 7,
}
const data = {
  ...summary,
  quality: { ...summary.quality, total: 23, warnings: 16, info: 7, rule_counts: ruleCounts },
}
function render(value: typeof data | typeof summary | null = data, limit?: number) {
  return mount(QualityOverview, {
    props: { data: value, limit },
    global: {
      components: { DataListShell, SeverityBadge, EmptyState },
      stubs: {
        NuxtLink: { name: 'NuxtLink', props: ['to'], template: '<a><slot /></a>' },
        AppIcon: true,
        ResultSummary: true,
        StatusBadge: true,
      },
    },
  })
}

describe('logo quality overview', () => {
  it('groups rules, counts and semantic severity using shared components', () => {
    const view = render()
    const group = view.get('ul[aria-label="Logos & Bilder"]')
    expect(group.findAll('li')).toHaveLength(3)
    const rows = group.findAll('li')
    expect(rows[0]!.text()).toContain('Orte ohne Logo')
    expect(rows[0]!.text()).toContain('12')
    expect(rows[1]!.text()).toContain('Organisationen ohne Logo')
    expect(rows[1]!.text()).toContain('4')
    expect(rows[2]!.text()).toContain('Logos in anderem Format')
    expect(rows[2]!.text()).toContain('7')
    const badges = group.findAllComponents(SeverityBadge)
    expect(badges.map((badge) => badge.props('severity'))).toEqual(['warning', 'warning', 'info'])
    expect(badges[0]!.classes()).toContain('bg-amber-50')
    expect(badges[2]!.classes()).toContain('bg-sky-50')
    expect(group.text()).toContain('Schlechte Datenqualität')
    expect(group.text()).toContain('Hinweis')
  })
  it('links each rule to its exact filters and preserves the source mode', () => {
    const view = render()
    const queries = view
      .findAllComponents({ name: 'NuxtLink' })
      .map((link) => link.props('to'))
      .filter((to) => typeof to === 'object' && to.query.rule in ruleCounts)
    expect(queries).toEqual([
      {
        path: '/findings',
        query: { rule: 'venue_missing_logo', entity_type: 'venue', mode: 'live' },
      },
      {
        path: '/findings',
        query: { rule: 'organization_missing_logo', entity_type: 'organization', mode: 'live' },
      },
      {
        path: '/findings',
        query: { rule: 'logo_unsupported_format', entity_type: undefined, mode: 'live' },
      },
    ])
  })
  it('keeps zero, missing counts and loading distinct', () => {
    const empty = render({
      ...data,
      quality: {
        ...data.quality,
        total: 0,
        rule_counts: Object.fromEntries(Object.keys(ruleCounts).map((key) => [key, 0])),
      },
    })
    expect(empty.text()).toContain('Keine aktuellen Qualitätsbefunde.')
    for (const row of empty.get('ul[aria-label="Logos & Bilder"]').findAll('li'))
      expect(row.text()).toContain('0')
    expect(render(summary).text()).toContain('Nicht verfügbar')
    expect(render(null).find('ul').exists()).toBe(false)
  })
  it('honors dashboard limits without duplicate logo rules', () => {
    expect(render(data, 2).findAll('li')).toHaveLength(2)
    const view = render({ ...data, quality: { ...data.quality, rules: Object.keys(ruleCounts) } })
    expect(view.get('ul[aria-label="Logos & Bilder"]').findAll('li')).toHaveLength(3)
  })
  it('validates additive counts without fabricating old-server metrics', () => {
    expect(summarySchema.parse(data).quality.rule_counts).toEqual(ruleCounts)
    expect(summarySchema.parse(summary).quality.rule_counts).toBeUndefined()
    expect(
      summarySchema.safeParse({
        ...data,
        quality: { ...data.quality, rule_counts: { venue_missing_logo: -1 } },
      }).success,
    ).toBe(false)
  })
})

describe('postal code quality overview', () => {
  it.each(['live', 'persisted'] as const)('links both entity types in %s mode', (mode) => {
    const view = render({
      ...data,
      quality: {
        ...data.quality,
        mode,
        rules: ['postal_code_whitespace'],
        rule_counts: { postal_code_whitespace: 2 },
      },
    })
    const group = view.get('ul[aria-label="Adressqualität"]')
    expect(group.findAll('li')).toHaveLength(1)
    expect(group.text()).toContain('Postleitzahlen mit Leerzeichen')
    expect(group.text()).toContain('Warnung')
    expect(group.text()).toContain('Schlechte Datenqualität')
    expect(group.text()).toContain('2')
    expect(group.text()).not.toContain('postal_code_whitespace')
    expect(group.getComponent({ name: 'NuxtLink' }).props('to')).toEqual({
      path: '/findings',
      query: { rule: 'postal_code_whitespace', entity_type: undefined, mode },
    })
  })
  it('shows zero counts and distinguishes unavailable counts', () => {
    const view = render({
      ...data,
      quality: { ...data.quality, rule_counts: { postal_code_whitespace: 0 } },
    })
    expect(view.get('ul[aria-label="Adressqualität"]').text()).toContain('0')
    expect(render(summary).get('ul[aria-label="Adressqualität"]').text()).toContain(
      'Nicht verfügbar',
    )
  })
})

it('labels both internal missing-location rules and links authoritative owners', () => {
  const view = render()
  const group = view.get('ul[aria-label="Standorte"]')
  expect(group.findAll('li')).toHaveLength(2)
  expect(group.text()).toContain('Organisationen ohne Geoposition')
  expect(group.text()).toContain('Orte ohne Geoposition')
  expect(group.findAllComponents(SeverityBadge).map((badge) => badge.props('severity'))).toEqual([
    'warning',
    'warning',
  ])
  expect(
    group.findAllComponents({ name: 'NuxtLink' }).map((link) => link.props('to').query.entity_type),
  ).toEqual(['organization', 'venue'])
})

describe('quality v2', () => {
  it('separates internal security and links the composite membership filter', () => {
    const view = render({
      ...data,
      quality: {
        ...data.quality,
        mode: 'persisted',
        rule_counts: { membership_joined_accept_token_present: 1 },
      },
    })
    const group = view.get('ul[aria-label="Interne Sicherheit"]')
    expect(group.text()).toContain('Einladungstoken nach Beitritt vorhanden')
    expect(group.getComponent(SeverityBadge).props('severity')).toBe('error')
    expect(group.getComponent({ name: 'NuxtLink' }).props('to')).toEqual({
      path: '/findings',
      query: {
        rule: 'membership_joined_accept_token_present',
        entity_type: 'team_membership',
        mode: 'persisted',
      },
    })
  })
  it('shows all three date checks with their distinct severities', () => {
    const view = render()
    const group = view.get('ul[aria-label="Terminintegrität"]')
    expect(group.findAllComponents(SeverityBadge).map((badge) => badge.props('severity'))).toEqual([
      'error',
      'error',
      'info',
    ])
    expect(group.text()).toContain('Übernachttermin ohne Enddatum')
  })
})
