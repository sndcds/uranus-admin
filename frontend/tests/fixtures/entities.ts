import { activityFixture } from './activity'
import type {
  EntitySection,
  EntityPage,
  EntityDetail,
  TimelineEntityType,
  TimelinePage,
} from '../../shared/contracts'
import { entitySections } from '../../app/utils/entities'
export function entityFixture(section: EntitySection): EntityPage {
  const type = entitySections[section].type
  const base = activityFixture.items[0]!
  return {
    items: [
      {
        ...base,
        entity_type: type,
        venue_scope: type === 'venue' ? 'shared' : null,
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
            ? `https://api.kulturbytes.de/api/image/${base.entity_key}?width=320&type=png`
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

export function timelineFixture(entityType: TimelineEntityType): TimelinePage {
  return {
    entity_type: entityType,
    entity_key: activityFixture.items[0]!.entity_key,
    items: [
      {
        id: 'finding:10000000-0000-4000-8000-000000000070',
        kind: 'finding_detected',
        occurred_at: '2026-02-03T10:15:00Z',
        title: 'Qualitätsproblem erkannt',
        summary: 'Beschreibung fehlt.',
        actor: null,
        href: `/findings?mode=persisted&entity_type=${entityType}&entity_key=${activityFixture.items[0]!.entity_key}&rule=missing_description`,
        metadata: {
          status: 'open',
          severity: 'warning',
          rule: 'missing_description',
          field: 'description',
          resource_id: 'missing-description',
          generation: null,
          score: null,
          http_status: null,
        },
      },
    ],
    cursor_pagination: { page_size: 25, next_cursor: null, has_more: false },
    observed_at: '2026-02-03T10:16:00Z',
  }
}

export const placeSections = ['organizations', 'venues', 'spaces'] as const
export type PlaceSection = (typeof placeSections)[number]

/** Synthetic, contract-shaped detail examples. No new source fields or venue coordinates. */
export function placeDetailFixture(section: PlaceSection, page = 1): EntityDetail {
  const data = detailFixture(section)
  const organization = 'Kulturverein für Begegnung und zeitgenössische Kunst am Hafen'
  const venue = 'Kulturhaus an der alten Hafenpromenade'
  data.item.organization_name = organization
  data.item.organization_id = data.item.entity_key
  data.item.entity_name =
    section === 'organizations'
      ? organization
      : section === 'venues'
        ? venue
        : 'Werkstattraum für Musik und gemeinsame Projekte'
  data.item.subtitle =
    section === 'organizations' ? 'Flensburg' : section === 'spaces' ? venue : null
  data.item.address =
    section === 'spaces'
      ? null
      : 'An der alten Hafenpromenade 128, Hinterhaus am Innenhof, 24937 Flensburg'
  data.item.location = section === 'organizations' ? { latitude: 54.793, longitude: 9.446 } : null
  data.item.image_url =
    section === 'spaces'
      ? null
      : `https://api.kulturbytes.de/api/image/${data.item.entity_key}?width=320&type=png`
  data.item.public_url =
    section === 'venues' ? 'https://kulturbytes.de/de/ort/kulturhaus-hafen' : null
  if (section === 'organizations') {
    data.item.facts.events = 26
    data.item.facts.venues = 1
    data.item.facts.memberships = 1
  } else if (section === 'venues') data.item.facts.spaces = 1
  else data.item.facts.venue_name = venue
  const related = (
    type: 'event' | 'venue' | 'space' | 'organization',
    index: number,
    name: string,
  ) => {
    const item = { ...activityFixture.items.find((item) => item.entity_type === type)! }
    const key =
      type === 'event'
        ? `30000000-0000-4000-8000-${String(index).padStart(12, '0')}`
        : data.item.entity_key
    const section = {
      event: 'events',
      venue: 'venues',
      space: 'spaces',
      organization: 'organizations',
    }[type]
    return {
      ...item,
      entity_key: key,
      entity_name: name,
      organization_id: data.item.organization_id,
      organization_name: organization,
      action: {
        type: 'view' as const,
        route: 'activity' as const,
        entity_type: type,
        entity_key: key,
        href: `/${section}/${key}`,
      },
    }
  }
  const items =
    section === 'organizations'
      ? [
          ...Array.from({ length: 26 }, (_, i) =>
            related('event', i + 1, `Hafenprogramm ${String(i + 1).padStart(2, '0')}`),
          ),
          {
            ...activityFixture.items.find((item) => item.entity_type === 'team_membership')!,
            organization_name: organization,
          },
          related('venue', 28, venue),
        ]
      : section === 'venues'
        ? [related('organization', 29, organization), related('space', 30, 'Werkstattraum')]
        : [related('venue', 28, venue)]
  data.related.items = items.slice((page - 1) * 25, page * 25)
  data.related.pagination = {
    page,
    page_size: 25,
    total: items.length,
    pages: Math.ceil(items.length / 25),
  }
  return data
}

export const identitySections = ['users', 'images'] as const
export type IdentitySection = (typeof identitySections)[number]

/** Synthetic domain records using only the existing, globally paginated contract. */
export function identityDetailFixture(section: IdentitySection, page = 1): EntityDetail {
  const data = detailFixture(section)
  data.item.entity_name =
    section === 'users'
      ? 'Alexandra Beispiel'
      : 'Abstrakte Hafenlandschaft in Violett – Plakat für die gemeinsame Kulturnacht'
  data.item.organization_id = data.item.organization_name = data.item.subtitle = null
  data.item.email =
    section === 'users'
      ? 'alexandra.beispiel.kulturprogramm-und-teamkoordination@example.org'
      : null
  data.item.image_url =
    section === 'users'
      ? `https://api.kulturbytes.de/api/user/${data.item.entity_key}/avatar/128`
      : data.item.image_url
  data.item.facts =
    section === 'users'
      ? { ...data.item.facts, username: 'alexandra-beispiel', memberships: 13 }
      : { ...data.item.facts, image_links: 27, orphan: false }
  const organization = activityFixture.items.find((item) => item.entity_type === 'organization')!
  const membership = activityFixture.items.find((item) => item.entity_type === 'team_membership')!
  const items =
    section === 'users'
      ? [
          ...Array.from({ length: 13 }, (_, index) => {
            const key = `40000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`
            return {
              ...organization,
              entity_key: key,
              entity_name: `Kulturteam ${index + 1}`,
              action: {
                type: 'view' as const,
                route: 'activity' as const,
                entity_type: 'organization' as const,
                entity_key: key,
                href: `/organizations/${key}`,
              },
            }
          }),
          ...Array.from({ length: 13 }, (_, index) => {
            const org = `40000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`
            const key = `membership:${org}:${data.item.entity_key}`
            return {
              ...membership,
              entity_key: key,
              entity_name: data.item.entity_name,
              organization_id: org,
              organization_name: `Kulturteam ${index + 1}`,
              status: index % 2 ? 'joined' : 'invited',
              subtitle: 'Eingeladen: 02.02.2026 13:00 (Europe/Berlin)',
              action: {
                type: 'view' as const,
                route: 'team_invitations' as const,
                entity_type: 'team_membership' as const,
                entity_key: key,
                href: `/queues/team_invitations?entity_key=${encodeURIComponent(key)}`,
              },
            }
          }),
        ]
      : Array.from({ length: 27 }, (_, index) => {
          const type = index < 9 ? 'event' : index < 18 ? 'organization' : 'venue'
          const related = activityFixture.items.find((item) => item.entity_type === type)!
          const key = `50000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`
          const path = { event: 'events', organization: 'organizations', venue: 'venues' }[type]
          return {
            ...related,
            entity_key: key,
            entity_name: `Bildkontext ${index + 1}`,
            action: {
              type: 'view' as const,
              route: 'activity' as const,
              entity_type: type,
              entity_key: key,
              href: `/${path}/${key}`,
            },
          }
        })
  data.related = {
    items: items.slice((page - 1) * 25, page * 25),
    pagination: { page, page_size: 25, total: items.length, pages: Math.ceil(items.length / 25) },
  }
  return data
}
