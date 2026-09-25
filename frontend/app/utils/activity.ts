import { entityTypes as activityTypes } from './entityPresentation'
import { activityImageUrlSchema, activityLocationSchema } from '#shared/contracts'
import type { ActivityPage, DashboardSummary } from '#shared/contracts'
import { eventStatusLabels } from './entities'
import { calendarDay, dayLabel, metric } from './presentation'

export type ActivityItem = ActivityPage['items'][number]
export type ActivityIdentity = Pick<ActivityItem, 'entity_key' | 'entity_name'> & {
  entity_type: string
}
export { entityTypes as activityTypes } from './entityPresentation'

// Values emitted by repositories/activity.py and the verified source fixtures.
const statusLabels: Record<string, string> = {
  ...eventStatusLabels,
  pending: 'Ausstehend',
  accepted: 'Angenommen',
  active: 'Aktiv',
  inactive: 'Nicht aktiv',
  joined: 'Beigetreten',
  invited: 'Eingeladen',
}
export function activityStatus(status: string | null): string | null {
  return status ? (Object.hasOwn(statusLabels, status) ? statusLabels[status]! : status) : null
}
export function activityName(item: ActivityIdentity): string {
  // The backend owns Uranus user presentation, including the final UUID fallback.
  if (item.entity_type === 'user' || item.entity_type === 'team_membership') return item.entity_name
  const name = item.entity_name.trim()
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  const partnerNames = name.split('→').map((part) => part.trim())
  const onlyPartnerIds = partnerNames.length === 2 && partnerNames.every((part) => uuid.test(part))
  return !name || name === item.entity_key || uuid.test(name) || onlyPartnerIds
    ? `${entityPresentation(item.entity_type).label} ohne Anzeigenamen`
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

/** Enlarge only a validated public thumbnail, preserving permitted query parameters. */
export function activityImagePreviewUrl(value: string | null | undefined): string | null {
  const validated = activityImageUrlSchema.safeParse(value)
  if (!validated.success) return null
  const url = new URL(validated.data)
  if (url.pathname.endsWith('/avatar/128')) url.pathname = url.pathname.replace(/128$/, '512')
  else if (/^\/api\/image\//i.test(url.pathname)) {
    url.searchParams.set('width', '1280')
    url.searchParams.set('type', 'png')
  }
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

/** Validated source coordinates only; no geocoding or requests to map services. */
export function activityMapUrl(value: ActivityItem['location']): string | null {
  const parsed = activityLocationSchema.safeParse(value)
  if (!parsed.success) return null
  const { latitude, longitude } = parsed.data
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`
}
