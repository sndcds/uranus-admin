const berlinParts = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Berlin',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

function offsetAt(value: Date) {
  const parts = Object.fromEntries(
    berlinParts
      .formatToParts(value)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, Number(part.value)]),
  )
  return (
    Date.UTC(parts.year!, parts.month! - 1, parts.day!, parts.hour!, parts.minute!, parts.second!) -
    value.getTime()
  )
}

/** Convert a Berlin calendar due date to the final second of that local day, including DST. */
export function berlinDueAt(date: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  const [year, month, day] = date.split('-').map(Number)
  if (!year || !month || !day) return null
  const wallClock = Date.UTC(year, month - 1, day, 23, 59, 59)
  let instant = new Date(wallClock)
  instant = new Date(wallClock - offsetAt(instant))
  instant = new Date(wallClock - offsetAt(instant))
  return Number.isNaN(instant.getTime()) ? null : instant.toISOString()
}

export function berlinDate(value: string | null): string {
  if (!value) return ''
  const parts = berlinParts.formatToParts(new Date(value))
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${map.year}-${map.month}-${map.day}`
}

function localParts(value: Date, timezone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(value)
  return Object.fromEntries(parts.map((part) => [part.type, part.value]))
}

export function adminDateTime(value: string, timezone: string): string {
  return new Intl.DateTimeFormat('de-DE', {
    timeZone: timezone,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

/** Resolve a local minute. Reject DST gaps; repeated minutes use the earlier occurrence. */
export function adminLocalInstant(local: string, timezone: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) return null
  const wallClock = Date.parse(`${local}:00Z`)
  if (!Number.isFinite(wallClock)) return null
  const offsets = new Set<number>()
  for (const hours of [-36, 0, 36]) {
    const instant = new Date(wallClock + hours * 3600000)
    const p = localParts(instant, timezone)
    offsets.add(
      Date.parse(`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:00Z`) - instant.getTime(),
    )
  }
  const matches = [...offsets]
    .map((offset) => new Date(wallClock - offset))
    .filter((instant) => {
      const p = localParts(instant, timezone)
      return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}` === local
    })
    .sort((a, b) => a.getTime() - b.getTime())
  return matches[0]?.toISOString() ?? null
}

/** Local calendar days, never elapsed 24-hour blocks. */
export function snoozePreset(days: 1 | 3 | 7, now: Date, timezone: string): string | null {
  const p = localParts(now, timezone)
  const calendar = new Date(Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day) + days))
  return adminLocalInstant(`${calendar.toISOString().slice(0, 10)}T09:00`, timezone)
}
