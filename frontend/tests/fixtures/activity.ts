import type { ActivityPage } from '../../shared/contracts'

export const activityObservedAt = '2026-09-15T10:30:00Z'
const types = [
  'event_date',
  'image',
  'event',
  'venue',
  'organization',
  'space',
  'user',
  'partner_request',
  'team_membership',
] as const
const names = [
  'Lesung am Hafen',
  'Plakat zur Kulturnacht',
  'Offene Ateliers',
  'Hafenbühne',
  'Kulturverein Nord',
  'Werkstattraum',
  'Testkonto',
  'Kulturverein Nord → Bühne West',
  'Testmitglied',
]
export const activityFixture: ActivityPage = {
  items: Array.from({ length: 20 }, (_, index) => {
    const kind = types[index % types.length]!
    const uuid = `20000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`
    const key =
      kind === 'partner_request'
        ? `partner-request:10000000-0000-4000-8000-000000000010:${uuid}`
        : kind === 'team_membership'
          ? `membership:10000000-0000-4000-8000-000000000010:${uuid}`
          : uuid
    const day = index < 12 ? '15' : index < 17 ? '14' : '13'
    const status =
      kind === 'event' || kind === 'event_date'
        ? 'released'
        : kind === 'partner_request'
          ? 'pending'
          : kind === 'user'
            ? 'active'
            : kind === 'team_membership'
              ? 'invited'
              : null
    return {
      entity_type: kind,
      entity_key: key,
      entity_name: `${names[index % names.length]}${index >= types.length ? ` ${index + 1}` : ''}`,
      organization_id:
        kind === 'image' || kind === 'user' ? null : '10000000-0000-4000-8000-000000000010',
      organization_name: kind === 'image' || kind === 'user' ? null : 'Kulturverein Nord',
      created_at: new Date(
        Date.UTC(2026, 8, Number(day), 10, 30) - (index % 12) * 15 * 60_000,
      ).toISOString(),
      status,
      action: {
        type: 'view',
        route: 'activity',
        entity_type: kind,
        entity_key: key,
        href: `/activity?entity_key=${encodeURIComponent(key)}&entity_type=${kind}`,
      },
    }
  }),
  pagination: { page: 1, page_size: 20, total: 80, pages: 4 },
  observed_at: activityObservedAt,
  from_at: '2026-09-08T10:30:00Z',
  to_at: activityObservedAt,
  timestamp_state: 'known',
  unknown_timestamp_count: 15,
}
