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
  failed: 'Temporär fehlgeschlagen',
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

export function smtpErrorLabel(code: string): string {
  const labels: Record<string, string> = {
    smtp_553: 'SMTP-Server hat den Versand dauerhaft abgelehnt.',
    smtp_550: 'Empfänger oder Versand wurde dauerhaft abgelehnt.',
    smtp_timeout: 'SMTP-Verbindung hat das Zeitlimit überschritten.',
    smtp_connection_failure: 'SMTP-Verbindung konnte nicht hergestellt werden.',
    attempt_limit: 'Die maximale Anzahl automatischer Versuche wurde erreicht.',
  }
  return (
    labels[code] ??
    'Der Versand konnte nicht abgeschlossen werden. Bitte SMTP-Konfiguration und Anbieter prüfen.'
  )
}
