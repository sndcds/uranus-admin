import previews from './notification-previews.json' with { type: 'json' }
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
  retry_of_delivery_id: null,
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
  summary: {
    active: 1,
    queued: 0,
    sent_today: 0,
    failed: 1,
    temporary_failed: 1,
    permanent_failed: 0,
  },
  health: { delivery_enabled: false, source_capability: true, config_issues: [] },
}
export const notificationDetail = {
  ...notification,
  deliveries: [notificationDelivery],
  delivery_enabled: false,
}
export const notificationDeliveryDetail = {
  ...notificationDelivery,
  notifications: [notification],
  retries: [],
}
export const notificationGuidance = {
  de: 'Melde dich bei Kulturbytes an und öffne den entsprechenden Eintrag in deinem Dashboard.',
  da: 'Log ind på Kulturbytes, og åbn det relevante opslag i dit dashboard.',
  en: 'Sign in to Kulturbytes and open the relevant entry in your dashboard.',
}
export function notificationPreview(locale: 'de' | 'da' | 'en', withAction = true) {
  return previews[locale][withAction ? 'action' : 'guidance']
}

export function notificationDigestPreview(locale: 'de' | 'da' | 'en') {
  return previews[locale].digest
}

export const notificationDeliveryPage = {
  items: [
    {
      ...notificationDelivery,
      organization_name: 'Kulturverein',
      created_at: notification.first_detected_at,
    },
  ],
  pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
  delivery_enabled: false,
}
