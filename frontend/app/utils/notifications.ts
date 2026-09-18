import type {
  NotificationStatus,
  NotificationType,
  NotificationDeliveryStatus,
  NotificationDeliveryKind,
} from '#shared/contracts'
export const notificationStatuses: Record<NotificationStatus, string> = {
  pending: 'In Bewertung',
  active: 'Aktiv',
  resolved: 'Gelöst',
  suppressed: 'Unterdrückt',
  expired: 'Abgelaufen',
}
export const notificationTypes: Record<NotificationType, string> = {
  unpublished_upcoming_event: 'Unveröffentlichte Veranstaltung',
  quality_finding: 'Qualitätshinweis',
}
export const deliveryStatuses: Record<NotificationDeliveryStatus, string> = {
  queued: 'Ausstehend',
  sending: 'Wird gesendet',
  sent: 'Gesendet',
  failed: 'Fehlgeschlagen',
  permanent_failure: 'Dauerhaft fehlgeschlagen',
  cancelled: 'Abgebrochen',
}
export const deliveryKinds: Record<NotificationDeliveryKind, string> = {
  initial: 'Erster Hinweis',
  reminder: 'Erinnerung',
  escalation: 'Dringlicher Hinweis',
  digest: 'Zusammenfassung',
  test: 'Test',
}
