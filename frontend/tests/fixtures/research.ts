import type {
  ResearchDetail,
  ResearchPage,
  ResearchRecord,
  ResearchType,
} from '../../shared/contracts'
export const researchCategories = [
  { id: 1, name: 'Kultur' },
  { id: 2, name: 'Bildung' },
  { id: 3, name: 'Sport' },
  { id: 4, name: 'Freizeit' },
  { id: 5, name: 'Familie' },
  { id: 6, name: 'Gesellschaft' },
]
export const researchEvent: ResearchRecord = {
  entity_type: 'event',
  entity_key: '20000000-0000-4000-8000-000000000001',
  name: 'Jazzabend im Kühlhaus',
  description:
    'Ein besonderer **Jazzabend** mit regionalen Künstlerinnen und Künstlern.\n\nKultur gemeinsam entdecken.',
  status: 'released',
  categories: researchCategories.slice(0, 2),
  language: 'de',
  start_date: '2026-01-12',
  start_time: '20:00:00',
  end_date: null,
  end_time: '23:00:00',
  all_day: false,
  organization_id: '30000000-0000-4000-8000-000000000001',
  organization_name: 'Kühlhaus Flensburg e.V.',
  venue_id: '40000000-0000-4000-8000-000000000001',
  venue_name: 'Kühlhaus Flensburg',
  space_id: '50000000-0000-4000-8000-000000000001',
  space_name: 'Großer Saal',
  city: 'Flensburg',
  address: 'Mühlendamm 25, 24937 Flensburg',
  location: { latitude: 54.773, longitude: 9.432 },
  event_count: null,
  source_url: 'https://example.invalid/kulturprogramm',
  image_url: null,
  created_at: '2025-11-10T12:00:00Z',
  modified_at: '2026-01-10T15:00:00Z',
}
export const researchVenue: ResearchRecord = {
  ...researchEvent,
  entity_type: 'venue',
  entity_key: researchEvent.venue_id!,
  name: researchEvent.venue_name!,
  status: null,
  organization_id: null,
  organization_name: null,
  venue_id: null,
  venue_name: null,
  space_id: null,
  space_name: null,
  categories: [],
  event_count: 3,
  start_date: null,
  start_time: null,
  end_time: null,
}
export const researchOrganization: ResearchRecord = {
  ...researchVenue,
  entity_type: 'organization',
  entity_key: researchEvent.organization_id!,
  name: researchEvent.organization_name!,
  location: { latitude: 54.789, longitude: 9.43 },
}
export const researchItems = [
  researchEvent,
  {
    ...researchEvent,
    entity_key: '20000000-0000-4000-8000-000000000002',
    name: 'Flensburger Klassiktage',
    categories: researchCategories.slice(2, 4),
    start_date: '2026-01-23',
    location: { latitude: 54.786, longitude: 9.437 },
  },
  {
    ...researchEvent,
    entity_key: '20000000-0000-4000-8000-000000000003',
    name: 'Indie Night',
    categories: researchCategories.slice(4, 6),
    status: 'cancelled' as const,
    start_date: '2026-02-14',
    location: { latitude: 54.791, longitude: 9.439 },
  },
]
export function researchPage(items = researchItems): ResearchPage {
  return {
    items,
    pagination: { page: 1, page_size: 25, total: items.length, pages: items.length ? 1 : 0 },
    observed_at: '2026-09-26T10:00:00Z',
    timezone: 'Europe/Berlin',
  }
}
export function researchDetail(kind: ResearchType = 'event'): ResearchDetail {
  return {
    item:
      kind === 'event' ? researchEvent : kind === 'venue' ? researchVenue : researchOrganization,
    events: researchPage(kind === 'event' ? [] : researchItems),
    dates: {
      items:
        kind === 'event'
          ? [
              {
                id: '60000000-0000-4000-8000-000000000001',
                start_date: researchEvent.start_date!,
                start_time: researchEvent.start_time,
                end_date: null,
                end_time: researchEvent.end_time,
                all_day: false,
                status: 'released',
                venue_id: researchEvent.venue_id,
                venue_name: researchEvent.venue_name,
                space_id: researchEvent.space_id,
                space_name: researchEvent.space_name,
                city: researchEvent.city,
                address: researchEvent.address,
                location: researchEvent.location,
              },
            ]
          : [],
      pagination: {
        page: 1,
        page_size: 25,
        total: kind === 'event' ? 1 : 0,
        pages: kind === 'event' ? 1 : 0,
      },
    },
    usage:
      kind === 'event'
        ? []
        : [
            {
              kind: 'venue',
              key: researchVenue.entity_key,
              name: researchVenue.name,
              event_count: 3,
            },
            {
              kind: 'organization',
              key: researchOrganization.entity_key,
              name: researchOrganization.name,
              event_count: 3,
            },
            { kind: 'category', key: '1', name: 'Kultur', event_count: 1 },
          ],
    months:
      kind === 'event'
        ? []
        : [
            { month: '2026-01-01', event_count: 2 },
            { month: '2026-02-01', event_count: 1 },
          ],
    observed_at: '2026-09-26T10:00:00Z',
  }
}
