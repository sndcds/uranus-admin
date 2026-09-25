import { findings } from './api'

// Synthetic data matching the reported live response; no copied source records.
const eventDate = {
  ...findings.items[0]!,
  id: 'event_date_end_before_start:event_date:00000000-0000-4000-8000-000000000040:end_date',
  rule: 'event_date_end_before_start',
  entity_type: 'event_date',
  entity_key: '00000000-0000-4000-8000-000000000040',
  entity_id: '00000000-0000-4000-8000-000000000040',
  entity_name: 'Synthetischer Veranstaltungstermin',
  severity: 'error',
  priority: 1,
  priority_score: 6700,
  field: 'end_date',
  message: 'Enddatum liegt vor Startdatum.',
  metadata: { source_fingerprint: 'a'.repeat(64), category: 'integrity' },
  action: {
    type: 'view',
    route: 'activity',
    entity_type: 'event_date',
    entity_key: '00000000-0000-4000-8000-000000000040',
    href: '/activity?entity_key=00000000-0000-4000-8000-000000000040&entity_type=event_date',
  },
  image_url:
    'https://api.kulturbytes.de/api/image/00000000-0000-4000-8000-000000000050?width=320&type=png',
}
const imageLink = {
  ...eventDate,
  id: 'image_link_unknown_context:image_link:synthetic:context',
  rule: 'image_link_unknown_context',
  entity_type: 'image_link',
  entity_key: 'image-link:unknown:00000000-0000-4000-8000-000000000030:main',
  entity_id: null,
  entity_name: 'Synthetische Bildverknüpfung',
  action: null,
  image_url: null,
}
export const liveFindings = {
  ...findings,
  mode: 'live',
  cursor_pagination: null,
  pagination: { page: 1, page_size: 50, total: 932, pages: 19 },
  items: Array.from({ length: 50 }, (_, index) => ({
    ...(index % 2 ? imageLink : eventDate),
    id: `${index % 2 ? imageLink.id : eventDate.id}:${index}`,
  })),
}
