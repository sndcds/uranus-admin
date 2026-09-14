import type { DashboardSummary, Severity } from '#shared/contracts'

export function metric(value: number | null | undefined): string {
  return value == null ? 'Nicht verfügbar' : new Intl.NumberFormat('de-DE').format(value)
}
export function dateTime(value: string | null | undefined): string {
  if (!value) return 'Nicht verfügbar'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return 'Nicht verfügbar'
  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Berlin',
  }).format(date)
}
export const severityLabels: Record<Severity, string> = {
  error: 'Fehler',
  warning: 'Warnung',
  info: 'Hinweis',
}
export function recordRows(data: DashboardSummary | null) {
  const labels = {
    organizations: 'Organisationen',
    venues: 'Orte',
    spaces: 'Räume',
    events: 'Events',
    event_dates: 'Termine',
    users: 'Benutzer',
    partner_requests: 'Partneranfragen',
    team_memberships: 'Teammitgliedschaften',
    images: 'Bilder',
  }
  return Object.entries(labels).map(([key, label]) => {
    const entries = data ? Object.entries(data.new_records) : []
    return { key, label, value: metric(entries.find(([name]) => name === key)?.[1]) }
  })
}
