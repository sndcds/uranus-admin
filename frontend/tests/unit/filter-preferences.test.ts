import { beforeEach, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { resolvePeriod, supportsPeriod } from '../../app/utils/periods'

beforeEach(() => setActivePinia(createPinia()))
it('has fresh, scoped defaults and resolves supported page periods', () => {
  const store = useFilterPreferencesStore()
  expect(store.sharedPeriod).toBe('24h')
  expect(store.entities.users).toEqual({ q: '', status: '', period: '' })
  expect(store.entities.images).toEqual({ q: '', period: '' })
  expect(store.statistics.selectedTypes).toHaveLength(7)
  store.setSharedPeriod('7d')
  for (const page of ['dashboard', 'activity', 'statistics'] as const) {
    expect(store.resolvePeriodForPage(page)).toBe('7d')
  }
  store.setSharedPeriod('90d')
  expect(store.resolvePeriodForPage('dashboard')).toBe('24h')
  expect(store.resolvePeriodForPage('activity')).toBe('24h')
  expect(store.sharedPeriod).toBe('90d')
  expect(resolvePeriod('statistics', 'today')).toBe('24h')
  expect(supportsPeriod('statistics', 'today')).toBe(false)
})
it('validates entity scopes, synchronizes URL values and resets only the requested entity', () => {
  const store = useFilterPreferencesStore()
  store.commitEntityFilters('events', {
    q: 'sommer',
    status: 'released',
    temporal: 'upcoming',
    period: '',
  })
  store.commitEntityFilters('users', { q: 'max@example.org', status: 'active', period: '' })
  store.hydrateEntity('events', { status: 'draft', page: '2' })
  expect(store.entities.events).toEqual({ q: '', status: 'draft', temporal: '', period: '' })
  store.hydrateEntity('users', { status: 'released', temporal: 'past' })
  expect(store.entities.users).toEqual({ q: 'max@example.org', status: 'active', period: '' })
  store.setSharedPeriod('90d')
  store.graph.depth = 3
  store.statistics.compare = true
  store.resetEntity('events')
  expect(store.entities.events).toEqual({ q: '', status: '', temporal: '', period: '' })
  expect(store.entities.users.q).toBe('max@example.org')
  expect(store.sharedPeriod).toBe('90d')
  expect(store.graph.depth).toBe(3)
  expect(store.statistics.compare).toBe(true)
  store.resetAll()
  expect(store.entities.users.q).toBe('')
  expect(store.graph.depth).toBe(2)
  expect(store.statistics.compare).toBe(false)
})
it('keeps custom ranges, unknown timestamps and invalid periods out of shared preferences', () => {
  const store = useFilterPreferencesStore()
  store.hydrateActivity({ period: '7d', entity_type: 'user' })
  expect(store.sharedPeriod).toBe('7d')
  expect(store.activity).toEqual({ period: '7d', entityType: 'user' })
  store.hydrateStatistics({ period: '30d', interval: '6h', compare: 'previous' })
  expect(store.sharedPeriod).toBe('30d')
  expect(store.statistics.interval).toBe('6h')
  expect(store.statistics.compare).toBe(true)
  for (const mode of ['custom', 'unknown', 'invalid']) store.setSharedPeriod(mode)
  store.hydrateStatistics({ period: 'custom', from_at: '2026-01-01', to_at: '2026-01-03' })
  store.hydrateActivity({ timestamp_state: 'unknown', period: '7d' })
  store.hydrateActivity({ from_at: '2026-01-01', to_at: '2026-01-03' })
  expect(store.sharedPeriod).toBe('30d')
  expect(store.statistics.period).toBe('30d')
})
it('keeps graph roots out of preferences and validates explicit filters', () => {
  const store = useFilterPreferencesStore()
  store.hydrateGraph({
    entity_type: 'venue',
    relation_type: 'venue_has_space',
    depth: '3',
    root_key: 'private',
  })
  expect(store.graph).toEqual({
    entityType: 'venue',
    relationType: 'venue_has_space',
    depth: 3,
    organization: '',
  })
  store.hydrateGraph({ entity_type: 'user', depth: '1', root_key: 'other' })
  expect(store.graph.entityType).toBe('user')
  expect(store.graph.depth).toBe(1)
  expect(store.graph.relationType).toBe('')
  expect(JSON.stringify(store.$state)).not.toContain('root_key')
})

it('isolates preferences between app/SSR Pinia instances', () => {
  const first = useFilterPreferencesStore(createPinia())
  first.entities.users.q = 'private@example.org'
  first.sharedPeriod = '90d'
  const second = useFilterPreferencesStore(createPinia())
  expect(second.entities.users.q).toBe('')
  expect(second.sharedPeriod).toBe('24h')
})

it('starts with All and inherits shared periods only after a conscious choice', () => {
  const store = useFilterPreferencesStore()
  expect(store.entityDefaults('events').period).toBe('')
  expect(store.sharedPeriodChosen).toBe(false)
  store.hydrateEntity('events', { period: '7d' })
  expect(store.sharedPeriod).toBe('7d')
  expect(store.entityDefaults('venues').period).toBe('7d')
  store.hydrateEntity('venues', { period: '30d' })
  expect(store.entityDefaults('events').period).toBe('7d')
  expect(store.sharedPeriod).toBe('30d')
  expect(store.entityDefaults('spaces').period).toBe('30d')
  store.hydrateEntity('events', { period: '90d' })
  expect(store.entities.events.period).toBe('90d')
  expect(store.sharedPeriod).toBe('90d')
  store.hydrateEntity('events', { period: '' })
  expect(store.sharedPeriod).toBe('90d')
  expect(store.entityDefaults('events').period).toBe('')
  store.resetEntity('venues')
  expect(store.entityDefaults('venues').period).toBe('')
  expect(store.sharedPeriod).toBe('90d')
  store.resetAll()
  expect(store.entityDefaults('events').period).toBe('')
  expect(store.sharedPeriodChosen).toBe(false)
})

it('inherits a conscious Dashboard period but ignores custom and unknown', () => {
  const store = useFilterPreferencesStore()
  store.setSharedPeriod('custom')
  store.setSharedPeriod('unknown')
  expect(store.entityDefaults('users').period).toBe('')
  store.hydratePeriod('dashboard', '7d')
  expect(store.resolvePeriodForPage('entities')).toBe('7d')
  expect(store.entityDefaults('users').period).toBe('7d')
})

it('remembers valid venue scope only for venues and clears it on reset or auth loss', () => {
  const store = useFilterPreferencesStore()
  store.hydrateEntity('venues', { scope: 'organization' })
  expect(store.entityDefaults('venues')).toMatchObject({ scope: 'organization' })
  store.hydrateEntity('venues', { scope: 'foobar' })
  expect(store.entities.venues.scope).toBe('organization')
  store.hydrateEntity('spaces', { scope: 'shared' })
  expect(store.entities.spaces).not.toHaveProperty('scope')
  store.hydrateEntity('venues', { scope: 'shared' })
  expect(store.entities.venues.scope).toBe('shared')
  store.resetEntity('venues')
  expect(store.entities.venues.scope).toBe('')
  store.hydrateEntity('venues', { scope: 'organization' })
  store.resetAll()
  expect(store.entities.venues.scope).toBe('')
})
