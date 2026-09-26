import type { ResearchQuery, ResearchRecord, ResearchType } from '#shared/contracts'
import { researchQuerySchema } from '#shared/contracts'

export const researchSections = {
  event: 'events',
  venue: 'venues',
  organization: 'organizations',
} as const
export const researchLabels = {
  event: 'Veranstaltung',
  venue: 'Ort',
  organization: 'Organisation',
} as const
export const researchStatuses = {
  released: 'Veröffentlicht',
  cancelled: 'Abgesagt',
  deferred: 'Verschoben',
  rescheduled: 'Neuer Termin',
} as const
export const researchNavigation = [
  { to: '/research/search', label: 'Suche', icon: 'search' },
  { to: '/research/map', label: 'Karte', icon: 'pin' },
  { to: '/research/events', label: 'Veranstaltungen', icon: 'calendar' },
  { to: '/research/venues', label: 'Orte', icon: 'pin' },
  { to: '/research/organizations', label: 'Organisationen', icon: 'organization' },
] as const
export function researchHref(kind: ResearchType, id: string) {
  return `/research/${researchSections[kind]}/${encodeURIComponent(id)}`
}
export function researchKey(item: ResearchRecord) {
  return `${item.entity_type}:${item.entity_key}`
}
export function researchQuery(query: Record<string, unknown>) {
  const { view: _view, ...filters } = query
  return researchQuerySchema.safeParse(filters)
}
export function researchUrlQuery(query: ResearchQuery): Record<string, string> {
  return Object.fromEntries(
    Object.entries(query)
      .filter(([, value]) => value !== undefined && value !== '')
      .map(([key, value]) => [key, String(value)]),
  )
}
export function researchDate(value: string | null) {
  return value
    ? new Intl.DateTimeFormat('de-DE', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        timeZone: 'UTC',
      }).format(new Date(`${value}T12:00:00Z`))
    : 'Termin unbekannt'
}
