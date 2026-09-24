import { entityFixture } from './entities'
import type { EntitySearchType, GlobalSearchResponse } from '../../shared/contracts'
export function globalSearchFixture(query: string): GlobalSearchResponse {
  const types: {
    type: EntitySearchType
    section: 'users' | 'organizations' | 'venues'
    label: string
    subtitle: string | null
  }[] = query.toLowerCase().includes('kühlhaus')
    ? [
        {
          type: 'organization',
          section: 'organizations',
          label: 'Kühlhaus e.V.',
          subtitle: 'Flensburg',
        },
        {
          type: 'venue',
          section: 'venues',
          label: 'Kühlhaus Flensburg',
          subtitle: 'Norderstraße 1 · 24937 Flensburg',
        },
      ]
    : query.includes('@')
      ? [{ type: 'user', section: 'users', label: 'person@example.org', subtitle: null }]
      : []
  return {
    query,
    groups: types.map(({ type, section, label, subtitle }) => {
      const source = entityFixture(section).items[0]!
      return {
        entity_type: type,
        items: [
          {
            entity_type: type,
            entity_key: source.entity_key,
            label,
            subtitle,
            matched_fields: [type === 'user' ? 'email' : 'name'],
            action: source.action!,
          },
        ],
      }
    }),
  }
}

// All nine global types, including composite queue identities and parent-event actions.
export function allGlobalSearchFixture(query = 'alle'): GlobalSearchResponse {
  const id = '20000000-0000-4000-8000-000000000001'
  const other = '20000000-0000-4000-8000-000000000002'
  const specs = [
    ['user', id, 'Max Mustermann', 'max@example.org', 'users'],
    ['organization', id, 'Kulturverein Nord', 'Flensburg', 'organizations'],
    ['venue', id, 'Kulturhaus', 'Flensburg', 'venues'],
    ['space', id, 'Saal', 'Kulturhaus', 'spaces'],
    ['event', id, 'Herbstmarkt', null, 'events'],
    ['event_date', other, 'Herbstmarkt', '12.10.2026 · 19:00', 'events'],
    ['image', id, 'Herbstmarkt Foto', 'image/jpeg', 'images'],
    ['partner_request', `partner-request:${id}:${other}`, 'Nord → Süd', 'Ausstehend', null],
    [
      'team_membership',
      `membership:${id}:${other}`,
      'Max Mustermann',
      'Kulturverein Nord · Beigetreten',
      null,
    ],
  ] as const
  return {
    query,
    groups: specs.map(([entity_type, entity_key, label, subtitle, section]) => {
      const route =
        entity_type === 'partner_request'
          ? 'partner_requests'
          : entity_type === 'team_membership'
            ? 'team_invitations'
            : 'activity'
      const targetType = entity_type === 'event_date' ? 'event' : entity_type
      const targetKey = entity_type === 'event_date' ? id : entity_key
      return {
        entity_type,
        items: [
          {
            entity_type,
            entity_key,
            label,
            subtitle,
            matched_fields: ['uuid'],
            action: {
              type: 'view',
              route,
              entity_type: targetType,
              entity_key: targetKey,
              href: section
                ? `/${section}/${targetKey}`
                : `/queues/${route}?entity_key=${encodeURIComponent(targetKey)}`,
            },
          },
        ],
      }
    }),
  }
}
