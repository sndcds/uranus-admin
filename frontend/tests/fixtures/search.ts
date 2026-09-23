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
