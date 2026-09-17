import type { EntityStatistics } from '../../shared/contracts'
import { statisticsTypes, statisticsOrder } from '../../app/utils/statistics'

/** Synthetic records only; no network dependency or production identities. */
export function statisticsFixture(query = new URLSearchParams()): EntityStatistics {
  const period = (query.get('period') ?? '24h') as EntityStatistics['period']
  const days = { '24h': 1, '7d': 7, '30d': 30, '90d': 90, custom: 1 }[period]
  const end = Date.parse(query.get('to_at') ?? '2026-09-16T10:00:00Z')
  const start = query.has('from_at') ? Date.parse(query.get('from_at')!) : end - days * 86400000
  const manual = query.get('interval')
  const interval = (
    manual && manual !== 'auto'
      ? manual
      : { '24h': '15m', '7d': '1h', '30d': '6h', '90d': '1d', custom: '1h' }[period]
  ) as EntityStatistics['interval']
  const step = { '15m': 900000, '1h': 3600000, '6h': 21600000, '1d': 86400000 }[interval]
  const length = Math.ceil((end - start) / step)
  const comparing = query.get('compare') === 'previous'
  const weights = [5, 5, 12, 3, 2, 1, 2]
  const series = statisticsOrder.map((type, index) => {
    const points = Array.from({ length }, (_, n) => ({
      start_at: new Date(start + n * step).toISOString(),
      end_at: new Date(Math.min(end, start + (n + 1) * step)).toISOString(),
      count: Math.max(
        0,
        Math.round(
          weights[index]! * (0.55 + 0.55 * Math.sin(n / 5 + index / 3)) +
            ((n * 13 + index) % 5) / 2,
        ),
      ),
    }))
    const total = points.reduce((sum, point) => sum + point.count, 0)
    return {
      entity_type: type,
      label: statisticsTypes[type].label,
      total,
      previous_total: comparing ? Math.round(total * (type === 'venue' ? 1.1 : 0.78)) : null,
      points,
    }
  })
  const names = [
    'Max Mustermann',
    'Kulturverein Beispielstadt',
    'Jazz im Hof 2027',
    'Kulturhalle Nord',
    'Proberaum 1',
    'Atelier am Hafen → Kulturzentrum Rendsburg',
    'Anna Beispiel',
  ]
  return {
    period,
    from_at: new Date(start).toISOString(),
    to_at: new Date(end).toISOString(),
    observed_at: new Date(end).toISOString(),
    timezone: 'Europe/Berlin',
    interval,
    previous_from_at: comparing ? new Date(start - (end - start)).toISOString() : null,
    previous_to_at: comparing ? new Date(start).toISOString() : null,
    series,
    recent: statisticsOrder.map((type, i) => {
      const activityType = type === 'team_invitation' ? 'team_membership' : type
      const key = `20000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`
      return {
        entity_type: type,
        entity_key: key,
        entity_name: names[i]!,
        organization_name: i === 0 ? null : 'Kulturzentrum Rendsburg e.V.',
        created_at: new Date(end - (i + 1) * 60000).toISOString(),
        action: {
          type: 'view' as const,
          route: 'activity' as const,
          entity_key: key,
          entity_type: activityType,
          href:
            type === 'event'
              ? `/events/${key}`
              : `/activity?entity_key=${key}&entity_type=${activityType}`,
        },
      }
    }),
  }
}
