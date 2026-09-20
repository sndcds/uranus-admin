import { describe, expect, it } from 'vitest'
import { findingPageSchema, summarySchema } from '../../shared/contracts'
import { summary, findings } from '../fixtures/api'
import { recordRows } from '../../app/utils/activity'
import { dateTime, metric } from '../../app/utils/presentation'
import { parseFilters, filterQuery } from '../../app/utils/filters'

describe('actual response contract', () => {
  it('maps a real-shaped response and retains unknown history', () => {
    expect(findingPageSchema.parse(findings).items[0]?.first_seen_at).toBeNull()
    expect(summarySchema.parse(summary).new_records.event_dates).toBe(0)
    expect(recordRows(summary).find((row) => row.key === 'event_dates')?.value).toBe('0')
  })
  it('distinguishes missing metrics from zero and rejects incomplete required data', () => {
    expect(metric(0)).toBe('0')
    expect(metric(undefined)).toBe('Nicht verfügbar')
    expect(metric(null)).toBe('Nicht verfügbar')
    expect(recordRows(null)[0]?.value).toBe('Nicht verfügbar')
    expect(summarySchema.safeParse({ ...summary, new_records: {} }).success).toBe(false)
    expect(
      summarySchema.parse({ ...summary, quality: { total: 0, warnings: 0 } }).quality.errors,
    ).toBeUndefined()
  })
  it('uses explicit Berlin time, including daylight-saving time', () => {
    expect(dateTime('2026-09-14T12:00:00Z')).toContain('14:00')
    expect(dateTime(null)).toBe('Nicht verfügbar')
  })
  it('validates deep-link filters without silently accepting arrays or invalid pages', () => {
    expect(parseFilters({ severity: 'warning', page: '2' })?.page).toBe(2)
    for (const query of [
      { severity: 'fatal' },
      { page: '0' },
      { page_size: '101' },
      { organization_id: 'wrong' },
      { page: ['1', '2'] },
      { arbitrary: 'x' },
    ]) {
      expect(parseFilters(query)).toBeNull()
    }
  })
})

it('accepts stable composite finding keys and rejects empty keys', () => {
  for (const entity_key of ['partner-request:org-a:org-b', 'membership:org:user']) {
    const page = { ...findings, items: [{ ...findings.items[0], entity_key, entity_id: null }] }
    expect(findingPageSchema.parse(page).items[0]?.entity_key).toBe(entity_key)
  }
  expect(
    findingPageSchema.safeParse({ ...findings, items: [{ ...findings.items[0], entity_key: '' }] })
      .success,
  ).toBe(false)
})

it('validates internal action routes and encoded keys', async () => {
  const { actionSchema } = await import('../../shared/contracts')
  const action = {
    type: 'view',
    route: 'partner_requests',
    entity_key: 'a:b',
    href: '/queues/partner_requests?entity_key=a%3Ab',
  }
  expect(actionSchema.safeParse(action).success).toBe(true)
  for (const href of [
    'https://evil.invalid',
    '//evil.invalid',
    '/venues/a',
    '/queues/partner_requests?entity_key=a%3Ab&url=evil',
  ])
    expect(actionSchema.safeParse({ ...action, href }).success).toBe(false)
})

it('defaults normal finding lists to persisted and requires explicit live diagnosis', () => {
  expect(parseFilters({})?.mode).toBe('persisted')
  expect(parseFilters({ mode: 'live' })?.mode).toBe('live')
})

it('round-trips active-only booleans without interpreting false as truthy', () => {
  expect(parseFilters({})?.active_only).toBe(false)
  for (const active of [true, false]) {
    const parsed = parseFilters({ active_only: String(active), severity: 'error' })!
    expect(parsed.active_only).toBe(active)
    expect(parseFilters(filterQuery(parsed))).toEqual(parsed)
  }
  for (const active_only of ['yes', '', 'anything', ['true', 'false'], 1]) {
    expect(parseFilters({ active_only })).toBeNull()
  }
})
