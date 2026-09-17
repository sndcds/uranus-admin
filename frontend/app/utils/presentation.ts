import type { Severity } from '#shared/contracts'

export const adminTimeZone = 'Europe/Berlin'
const fullDateTime = new Intl.DateTimeFormat('de-DE', {
  timeZone: adminTimeZone,
  dateStyle: 'medium',
  timeStyle: 'short',
})
const longDay = new Intl.DateTimeFormat('de-DE', {
  timeZone: adminTimeZone,
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})
const shortDay = new Intl.DateTimeFormat('de-DE', {
  timeZone: adminTimeZone,
  day: '2-digit',
  month: '2-digit',
})
const shortTime = new Intl.DateTimeFormat('de-DE', {
  timeZone: adminTimeZone,
  hour: '2-digit',
  minute: '2-digit',
})

export function metric(value: number | null | undefined): string {
  return value == null ? 'Nicht verfügbar' : new Intl.NumberFormat('de-DE').format(value)
}
export function dateTime(value: string | null | undefined): string {
  if (!value) return 'Nicht verfügbar'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return 'Nicht verfügbar'
  return fullDateTime.format(date)
}
export const severityLabels: Record<Severity, string> = {
  error: 'Fehler',
  warning: 'Warnung',
  info: 'Hinweis',
}
// Activity does not expose admin_timezone; use the same zone as all existing date displays.
const dayFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: adminTimeZone,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})
export function calendarDay(value: string | null | undefined): string | null {
  if (!value || !Number.isFinite(new Date(value).getTime())) return null
  const parts = dayFormatter.formatToParts(new Date(value))
  return ['year', 'month', 'day']
    .map((type) => parts.find((part) => part.type === type)!.value)
    .join('-')
}
export function dayLabel(value: string, observedAt: string): string {
  const day = calendarDay(value)
  const today = calendarDay(observedAt)
  if (!day || !today) return 'Ohne belegten Zeitpunkt'
  if (day === today) return 'Heute'
  // Subtract a calendar day, not 24 hours: Berlin days may contain 23 or 25 hours.
  const yesterday = new Date(`${today}T12:00:00Z`)
  yesterday.setUTCDate(yesterday.getUTCDate() - 1)
  if (day === yesterday.toISOString().slice(0, 10)) return 'Gestern'
  return longDay.format(new Date(value))
}
export function activityTime(value: string | null, observedAt: string): string {
  if (!calendarDay(value)) return 'Ohne Zeitstempel'
  const date = new Date(value!)
  const time = shortTime.format(date)
  if (calendarDay(value) === calendarDay(observedAt)) return time
  const day = shortDay.format(date)
  return `${day} · ${time}`
}

export { dashboardPeriods as periodLabels } from './periods'
export const findingStatusLabels: Record<string, string> = {
  open: 'Offen',
  in_progress: 'In Bearbeitung',
  snoozed: 'Zurückgestellt',
  exception: 'Ausnahme',
  reviewed: 'Geprüft',
  ignored: 'Ignoriert',
  resolved: 'Behoben',
}

export const checkStatusLabels = {
  queued: 'Wartet auf Worker',
  running: 'Läuft',
  success: 'Erfolgreich',
  failed: 'Fehlgeschlagen',
}
