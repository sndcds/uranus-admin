import { activityFixture } from './activity'
import type { EntitySection, EntityPage, EntityDetail } from '../../shared/contracts'
import { entitySections } from '../../app/utils/entities'
export function entityFixture(section: EntitySection): EntityPage {
  const type = entitySections[section].type
  const base = activityFixture.items[0]!
  return {
    items: [
      {
        ...base,
        entity_type: type,
        entity_name: `Fixture ${section}`,
        status: section === 'users' ? 'active' : null,
        action: {
          type: 'view',
          route: 'activity',
          entity_type: type,
          entity_key: base.entity_key,
          href: `/${section}/${base.entity_key}`,
        },
        public_url: null,
        image_url:
          section === 'images'
            ? `https://api.kulturbytes.de/api/image/${base.entity_key}?width=320`
            : null,
        finding_count: 2,
        mark_count: 1,
        facts: {
          username: section === 'users' ? 'fixture-user' : null,
          description: null,
          venue_name: section === 'events' ? 'Standardbühne' : null,
          space_name: section === 'events' ? 'Saal A' : null,
          event_dates: null,
          venues: null,
          spaces: null,
          events: null,
          memberships: null,
          image_links: null,
          orphan: null,
        },
      },
    ],
    pagination: { page: 1, page_size: 25, total: 26, pages: 2 },
    observed_at: activityFixture.observed_at,
  }
}
export function detailFixture(section: EntitySection): EntityDetail {
  const page = entityFixture(section)
  const membership = activityFixture.items.find((item) => item.entity_type === 'team_membership')!
  const related =
    section === 'users'
      ? [
          {
            ...membership,
            created_at: '2026-01-01T00:00:00Z',
            subtitle: 'Eingeladen: 02.02.2026 13:00 (Europe/Berlin)',
            status: 'invited',
          },
        ]
      : []
  return {
    item: page.items[0]!,
    related: {
      items: related,
      pagination: { page: 1, page_size: 25, total: related.length, pages: related.length ? 1 : 0 },
    },
    observed_at: page.observed_at,
  }
}
