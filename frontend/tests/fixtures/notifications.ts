import type {
  NotificationSummary,
  NotificationDelivery,
  NotificationPage,
} from '../../shared/contracts'
export const notification: NotificationSummary = {
  id: '10000000-0000-4000-8000-000000000031',
  notification_type: 'unpublished_upcoming_event',
  organization_id: '10000000-0000-4000-8000-000000000010',
  entity_type: 'event',
  entity_key: '10000000-0000-4000-8000-000000000021',
  entity_name: 'Kulturabend',
  finding_id: null,
  rule: null,
  status: 'active',
  payload: {
    organization_name: 'Kulturverein',
    entity_name: 'Kulturabend',
    entity_type: 'event',
    entity_key: '10000000-0000-4000-8000-000000000021',
    internal_action_path: '/events/10000000-0000-4000-8000-000000000021',
    external_action_url:
      'https://app.kulturbytes.de/admin/event/10000000-0000-4000-8000-000000000021',
    event_status: 'draft',
    next_date: '2026-09-30',
    days_until: 12,
    stage: 1,
    episode: 1,
    rule: null,
    finding_id: null,
    severity: null,
    field: null,
    relevance: [],
    priority: 'improvement',
  },
  first_detected_at: '2026-09-18T10:00:00Z',
  last_detected_at: '2026-09-18T10:00:00Z',
  resolved_at: null,
  expired_at: null,
}
export const notificationDelivery: NotificationDelivery = {
  id: '10000000-0000-4000-8000-000000000041',
  organization_id: notification.organization_id,
  recipient: 'recipient@example.test',
  locale: 'da',
  delivery_kind: 'initial',
  status: 'failed',
  subject: 'Dit arrangement finder snart sted',
  message_fingerprint: 'a'.repeat(64),
  attempt_count: 1,
  queued_at: notification.first_detected_at,
  sending_at: notification.first_detected_at,
  sent_at: null,
  next_attempt_at: '2026-09-18T10:05:00Z',
  last_error: 'smtp_451',
  provider_message_id: null,
}
export const notificationPage: NotificationPage = {
  items: [notification],
  pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
  summary: { active: 1, queued: 0, sent_today: 0, failed: 1 },
  health: { delivery_enabled: false, source_capability: true, config_issues: [] },
}
export const notificationDetail = {
  ...notification,
  deliveries: [notificationDelivery],
  delivery_enabled: false,
}
export const notificationDeliveryDetail = { ...notificationDelivery, notifications: [notification] }
export const notificationGuidance = {
  de: 'Melde dich bei Kulturbytes an und öffne den entsprechenden Eintrag in deinem Dashboard.',
  da: 'Log ind på Kulturbytes, og åbn det relevante opslag i dit dashboard.',
  en: 'Sign in to Kulturbytes and open the relevant entry in your dashboard.',
}
export function notificationPreview(locale: 'de' | 'da' | 'en', withAction = true) {
  const subject = {
    de: 'Deine Veranstaltung „Kulturabend“ findet bald statt',
    da: 'Dit arrangement „Kulturabend“ finder snart sted',
    en: 'Your event “Kulturabend” is coming up soon',
  }[locale]
  const url = notification.payload.external_action_url
  const label = { de: 'Veranstaltung bearbeiten', da: 'Rediger arrangementet', en: 'Edit event' }[
    locale
  ]
  const action = withAction ? `<a href="${url}">${label}</a>` : notificationGuidance[locale]
  return {
    subject,
    text: `${subject}\nKulturverein\n${withAction ? `${label}: ${url}` : notificationGuidance[locale]}`,
    html: `<!doctype html><html lang="${locale}"><head></head><body><p>${subject}</p><p>${action}</p></body></html>`,
    locale,
    notification_ids: [notification.id],
    delivery_enabled: false,
  }
}
