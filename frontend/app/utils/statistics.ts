import type { EntityStatistics, StatisticsEntity } from '#shared/contracts'
import { metric } from './presentation'

export const statisticsTypes = {
  user: {
    label: 'Benutzer',
    singular: 'Benutzer',
    card: 'Neue Benutzer',
    icon: 'user',
    color: '#3980ff',
  },
  organization: {
    label: 'Organisationen',
    singular: 'Organisation',
    card: 'Neue Organisationen',
    icon: 'organization',
    color: '#951bff',
  },
  event: {
    label: 'Veranstaltungen',
    singular: 'Veranstaltung',
    card: 'Neue Veranstaltungen',
    icon: 'calendar',
    color: '#ff4081',
  },
  venue: {
    label: 'Veranstaltungsorte',
    singular: 'Veranstaltungsort',
    card: 'Neue Orte',
    icon: 'pin',
    color: '#21c87a',
  },
  space: { label: 'Räume', singular: 'Raum', card: 'Neue Räume', icon: 'space', color: '#10b9d4' },
  partner_request: {
    label: 'Partneranfragen',
    singular: 'Partneranfrage',
    card: 'Neue Partneranfragen',
    icon: 'partner',
    color: '#ffad32',
  },
  team_invitation: {
    label: 'Teameinladungen',
    singular: 'Teameinladung',
    card: 'Neue Teameinladungen',
    icon: 'mail',
    color: '#ac78ff',
  },
} as const
export const statisticsOrder = Object.keys(statisticsTypes) as StatisticsEntity[]
export const statisticsPeriods = {
  '24h': '24 Stunden',
  '7d': '7 Tage',
  '30d': '30 Tage',
  '90d': '90 Tage',
} as const
export const statisticsIntervals = {
  '15m': '15 Minuten',
  '1h': 'Stündlich',
  '6h': '6 Stunden',
  '1d': 'Täglich',
} as const
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
