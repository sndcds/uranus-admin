import { expect, it } from 'vitest'
import { notificationQuery } from '../../app/utils/notification-query'
import { checkDuration } from '../../app/utils/check-runs'
import { deliveryTone, notificationTone } from '../../app/utils/notifications'

it('validates exact URL filters and rejects repeated/invalid filters instead of dropping them', () => {
  expect(
    notificationQuery({
      status: 'active',
      notification_type: 'quality_finding',
      days: '7',
      page: '2',
      page_size: '25',
    }),
  ).toEqual({
    status: 'active',
    notification_type: 'quality_finding',
    days: 7,
    page: 2,
    page_size: 25,
  })
  expect(
    notificationQuery({ status: 'failed', delivery_kind: 'digest', days: '30' }, true),
  ).toEqual({ status: 'failed', delivery_kind: 'digest', days: 30, page: 1 })
  for (const query of [
    { status: ['active', 'resolved'] },
    { status: 'invented' },
    { organization_id: 'invalid' },
    { page: '0' },
    { page_size: '101' },
    { days: '366' },
    { days: null },
    { unknown: 'x' },
  ])
    expect(() => notificationQuery(query)).toThrow()
  expect(() => notificationQuery({ status: 'active' }, true)).toThrow()
  expect(() => notificationQuery({ status: 'sent' })).toThrow()
})
it('only derives elapsed duration from two valid ordered instants, including zero', () => {
  expect(checkDuration('2026-09-24T10:00:00Z', null)).toBeNull()
  expect(checkDuration('invalid', '2026-09-24T10:00:00Z')).toBeNull()
  expect(checkDuration('2026-09-24T10:00:01Z', '2026-09-24T10:00:00Z')).toBeNull()
  expect(checkDuration('2026-09-24T10:00:00Z', '2026-09-24T10:00:00Z')).toBe('0 s')
  expect(checkDuration('2026-09-24T12:00:00+02:00', '2026-09-24T10:02:05Z')).toBe('2 min 5 s')
})
it('distinguishes notification state from delivery outcomes', () => {
  expect(notificationTone('active')).toBe('warning')
  expect(notificationTone('resolved')).toBe('success')
  expect(deliveryTone('failed')).toBe('warning')
  expect(deliveryTone('permanent_failure')).toBe('error')
  expect(deliveryTone('queued')).toBe('neutral')
  expect(deliveryTone('sent')).toBe('success')
})
