import { describe, expect, it } from 'vitest'
import { findingPageSchema, summarySchema } from '../../shared/contracts'
import { summary, findings } from '../fixtures/api'
import { dateTime, metric, recordRows } from '../../app/utils/presentation'
import { parseFilters } from '../../app/utils/filters'

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
