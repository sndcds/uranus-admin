import type { EntityStatistics, StatisticsEntity } from '#shared/contracts'
import { metric } from './presentation'

import { entityTypes, invitationPresentation } from './entityPresentation'
function statisticsPresentation(type: {
  label: string
  plural: string
  icon: (typeof entityTypes)[keyof typeof entityTypes]['icon'] | typeof invitationPresentation.icon
  color: string
}) {
  return {
    label: type.plural,
    singular: type.label,
    card: `Neue ${type.plural}`,
    icon: type.icon,
    color: type.color,
  }
}
export const statisticsTypes = {
  user: statisticsPresentation(entityTypes.user),
  organization: statisticsPresentation(entityTypes.organization),
  event: statisticsPresentation(entityTypes.event),
  venue: statisticsPresentation(entityTypes.venue),
  space: statisticsPresentation(entityTypes.space),
  partner_request: statisticsPresentation(entityTypes.partner_request),
  team_invitation: statisticsPresentation(invitationPresentation),
} as const
/** Only Activity understands creation_basis; canonical details and queues remain untouched. */
export function statisticsRecentLink(href: string): string {
  const url = new URL(href, 'https://admin.invalid')
  if (url.pathname !== '/activity') return href
  url.searchParams.set('creation_basis', 'statistics')
  return `${url.pathname}${url.search}${url.hash}`
}
export const statisticsOrder = Object.keys(statisticsTypes) as StatisticsEntity[]
export const statisticsIntervals = {
  '15m': '15 Minuten',
  '1h': 'Stündlich',
  '6h': '6 Stunden',
  '1d': 'Täglich',
} as const
/** Same bucket bound used by the selector, including an inherited interval on entry. */
export function statisticsIntervalAllowed(
  period: string,
  interval: string,
  from?: string,
  to?: string,
) {
  if (interval === 'auto') return true
  const duration =
    period === 'custom' && from && to
      ? Date.parse(to) - Date.parse(from)
      : ({ '24h': 1, '7d': 7, '30d': 30, '90d': 90 }[period] ?? 1) * 86400000
  return (
    Math.ceil(
      duration / ({ '15m': 900000, '1h': 3600000, '6h': 21600000, '1d': 86400000 }[interval] ?? 1),
    ) +
      2 <=
    500
  )
}
export function statisticsDelta(current: number, previous: number) {
  const difference = current - previous
  const sign = difference > 0 ? '+' : difference < 0 ? '−' : ''
  return {
    difference,
    label:
      previous > 0
        ? `${sign}${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 }).format(Math.abs((difference / previous) * 100))} %`
        : difference === 0
          ? '±0'
          : `+${metric(difference)} neu`,
  }
}
export function statisticsDate(
  value: string | number | Date,
  timezone: string,
  mode: 'full' | 'day' | 'time' = 'full',
) {
  return new Intl.DateTimeFormat('de-DE', {
    timeZone: timezone,
    ...(mode === 'time'
      ? ({ hour: '2-digit', minute: '2-digit', timeZoneName: 'short' } as const)
      : mode === 'day'
        ? ({ day: 'numeric', month: 'short' } as const)
        : ({
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          } as const)),
  }).format(new Date(value))
}
export function statisticsActivityLink(data: Pick<EntityStatistics, 'from_at' | 'to_at'>) {
  return {
    path: '/activity',
    query: { from_at: data.from_at, to_at: data.to_at, creation_basis: 'statistics' },
  }
}
/** Date fields describe local calendar days in the server's admin zone, not the browser zone. */
export function statisticsDateBoundary(day: string, timezone: string, followingDay = false) {
  const desired = new Date(`${day}T00:00:00Z`)
  if (!Number.isFinite(desired.getTime())) throw new Error('Invalid date')
  if (followingDay) desired.setUTCDate(desired.getUTCDate() + 1)
  let candidate = desired.getTime()
  const format = new Intl.DateTimeFormat('sv-SE', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  })
  for (let i = 0; i < 3; i++) {
    const parts = format.formatToParts(candidate)
    const part = (type: string) => parts.find((p) => p.type === type)!.value
    const displayed = Date.parse(
      `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}:${part('second')}Z`,
    )
    candidate += desired.getTime() - displayed
  }
  return new Date(candidate).toISOString()
}
