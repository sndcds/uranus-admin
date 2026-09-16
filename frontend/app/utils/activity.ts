import { activityImageUrlSchema } from '#shared/contracts'
import type { ActivityPage, DashboardSummary } from '#shared/contracts'
import { calendarDay, dayLabel, metric } from './presentation'

export type ActivityItem = ActivityPage['items'][number]
export const activityTypes = {
  organization: {
    label: 'Organisation',
    plural: 'Organisationen',
    icon: 'organization',
    tone: 'bg-indigo-50 text-indigo-700',
  },
  venue: { label: 'Ort', plural: 'Orte', icon: 'pin', tone: 'bg-teal-50 text-teal-700' },
  space: { label: 'Raum', plural: 'Räume', icon: 'space', tone: 'bg-cyan-50 text-cyan-700' },
  event: {
    label: 'Veranstaltung',
    plural: 'Veranstaltungen',
    icon: 'calendar',
    tone: 'bg-fuchsia-50 text-fuchsia-700',
  },
  event_date: {
    label: 'Termin',
    plural: 'Termine',
    icon: 'clock',
    tone: 'bg-violet-50 text-violet-700',
  },
  user: { label: 'Benutzer', plural: 'Benutzer', icon: 'user', tone: 'bg-sky-50 text-sky-700' },
  partner_request: {
    label: 'Partneranfrage',
    plural: 'Partneranfragen',
    icon: 'partner',
    tone: 'bg-amber-50 text-amber-800',
  },
  team_membership: {
    label: 'Teammitgliedschaft',
    plural: 'Teammitgliedschaften',
    icon: 'users',
    tone: 'bg-blue-50 text-blue-700',
  },
  image: { label: 'Bild', plural: 'Bilder', icon: 'image', tone: 'bg-rose-50 text-rose-700' },
} as const satisfies Record<
  ActivityItem['entity_type'],
  { label: string; plural: string; icon: string; tone: string }
>

// Values emitted by repositories/activity.py and the verified source fixtures.
const statusLabels: Record<string, string> = {
  released: 'Veröffentlicht',
  draft: 'Entwurf',
  cancelled: 'Abgesagt',
  pending: 'Ausstehend',
  accepted: 'Angenommen',
  active: 'Aktiv',
  inactive: 'Inaktiv',
  joined: 'Beigetreten',
  invited: 'Eingeladen',
}
export function activityStatus(status: string | null): string | null {
  return status ? (Object.hasOwn(statusLabels, status) ? statusLabels[status]! : status) : null
}
export function activityName(item: ActivityItem): string {
  const name = item.entity_name.trim()
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  const partnerNames = name.split('→').map((part) => part.trim())
  const onlyPartnerIds = partnerNames.length === 2 && partnerNames.every((part) => uuid.test(part))
  return !name || name === item.entity_key || uuid.test(name) || onlyPartnerIds
    ? `${activityTypes[item.entity_type].label} ohne Anzeigenamen`
    : name
}
export function activityGroups(data: ActivityPage) {
  if (data.timestamp_state === 'unknown')
    return [{ key: 'unknown', label: null, items: data.items }]
  const groups = new Map<string, { key: string; label: string; items: ActivityItem[] }>()
  for (const item of data.items) {
    const key = calendarDay(item.created_at) ?? 'unknown'
    if (!groups.has(key))
      groups.set(key, {
        key,
        label:
          key === 'unknown'
            ? 'Ohne belegten Zeitpunkt'
            : dayLabel(item.created_at!, data.observed_at),
        items: [],
      })
    groups.get(key)!.items.push(item)
  }
  // Preserve API order; do not fabricate correlations or reorder records within a day.
  return [...groups.values()]
}
export function activityCounts(items: ActivityItem[]) {
  return (Object.keys(activityTypes) as ActivityItem['entity_type'][])
    .map((type) => ({ type, count: items.filter((item) => item.entity_type === type).length }))
    .filter((item) => item.count > 0)
    .sort((a, b) => b.count - a.count)
}

export function recordRows(data: DashboardSummary | null) {
  const mapping = {
    organizations: 'organization',
    venues: 'venue',
    spaces: 'space',
    events: 'event',
    event_dates: 'event_date',
    users: 'user',
    partner_requests: 'partner_request',
    team_memberships: 'team_membership',
    images: 'image',
  } as const
  return Object.entries(mapping).map(([key, type]) => ({
    key,
    type,
    ...activityTypes[type],
    value: metric(data?.new_records[key as keyof typeof mapping]),
  }))
}

/** Enlarge only a validated public thumbnail, preserving the image's native ratio. */
export function activityImagePreviewUrl(value: string | null | undefined): string | null {
  const validated = activityImageUrlSchema.safeParse(value)
  if (!validated.success) return null
  const url = new URL(validated.data)
  url.search = new URLSearchParams({ width: '1280' }).toString()
  return url.toString()
}

export function entityPresentation(type: string) {
  if (Object.hasOwn(activityTypes, type)) return activityTypes[type as keyof typeof activityTypes]
  const extra: Record<string, string> = {
    event_link: 'Veranstaltungslink',
    license: 'Lizenz',
    image_link: 'Bildverknüpfung',
  }
  return { label: extra[type] ?? type, tone: 'bg-slate-100 text-slate-600' }
}
