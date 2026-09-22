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
