import { expect, it } from 'vitest'
import { entityCollectionFacts, collectionContext } from '../../app/utils/collections'
import { clockTime } from '../../app/utils/presentation'
import { entityFixture } from '../fixtures/entities'
import { collectionFixture } from '../fixtures/collections'
import { entitySectionSchema, entityPageSchema } from '../../shared/contracts'
it.each(entitySectionSchema.options)(
  'uses real collection contract fields for %s review fixtures',
  (section) => {
    expect(entityPageSchema.safeParse(collectionFixture(section)).success).toBe(true)
  },
)

it('selects domain facts, preserves zero/false and never promotes a description to a list fact', () => {
  const item = entityFixture('organizations').items[0]!
  item.facts = {
    ...item.facts,
    events: 0,
    venues: 2,
    memberships: 3,
    description: 'Long prose',
    orphan: false,
  }
  expect(entityCollectionFacts('organizations', item)).toEqual([
    { label: 'Veranstaltungen', value: 0 },
    { label: 'Orte', value: 2 },
    { label: 'Teammitgliedschaften (einschließlich Einladungen)', value: 3 },
  ])
  expect(entityCollectionFacts('images', item)).toEqual([
    { label: 'Ohne Verknüpfung', value: false },
  ])
  expect(entityCollectionFacts('spaces', item)).toEqual([])
  expect(entityCollectionFacts('users', entityFixture('users').items[0]!)).toEqual([])
})
it('deduplicates exact identity values without changing the canonical user name', () => {
  const item = entityFixture('users').items[0]!
  item.entity_name = item.email = 'user@example.org'
  item.facts.username = ' user@example.org '
  item.organization_name = null
  expect(collectionContext('users', item)).toEqual([])
  item.facts.username = 'different-username'
  expect(collectionContext('users', item)).toEqual(['different-username'])
})
it('presents the parent venue as context without inferring an identity or link', () => {
  const item = entityFixture('spaces').items[0]!
  item.facts.venue_name = 'Hafenhaus'
  item.organization_name = 'Kulturverein'
  expect(collectionContext('spaces', item)).toEqual(['Hafenhaus', 'Kulturverein'])
})
it('uses Berlin time within a labelled day group without repeating its date', () => {
  expect(clockTime('2026-09-13T16:22:00Z')).toBe('18:22')
  expect(clockTime('2026-01-13T16:22:00Z')).toBe('17:22')
})
