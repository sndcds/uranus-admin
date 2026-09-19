export interface ApiFailure {
  status: number
  code: string
  message: string
}

export function failure(status: number, code = 'request_failed'): ApiFailure {
  const retryMessages: Record<string, string> = {
    geocode_request_not_found: 'Dieser Standortvorschlag wurde nicht gefunden.',
    geocode_retry_not_allowed: 'Eine Standortprüfung ist bereits eingeplant.',
    geocode_no_longer_needed:
      'Die Position ist bereits vorhanden oder der Datensatz wurde entfernt.',
    geo_scope_not_found: 'Dieses Gebiet ist nicht verfügbar. Der Gebietsfilter wurde entfernt.',
    geo_provider_unavailable:
      'Die Gebietssuche ist derzeit nicht verfügbar. Gespeicherte Gebiete bleiben nutzbar.',
    geo_area_not_eligible: 'Dieser Treffer kann nicht als administratives Gebiet verwendet werden.',
    geo_area_geometry_invalid: 'Die Grenze dieses Gebiets konnte nicht verarbeitet werden.',
    notification_delivery_not_found: 'Dieser E-Mail-Versand wurde nicht gefunden.',
    notification_retry_not_allowed:
      'Dieser Versand kann nicht erneut gestartet werden. Prüfe den neuesten Versuch in der Versandhistorie.',
    notification_retry_obsolete:
      'Empfänger oder Hinweis sind nicht mehr aktiv konfiguriert, oder die Quelldaten sind nicht verfügbar. Kein neuer Versand wurde erstellt.',
    notification_retry_already_queued: 'Für diesen Versand läuft bereits ein erneuter Versuch.',
  }
  const messages: Record<number, string> = {
    401: 'Anmeldung erforderlich. Für diesen Zugriff fehlen gültige Zugangsdaten.',
    403: 'Keine Berechtigung. Dein Zugang darf diese Verwaltungsdaten nicht lesen.',
    404: 'Der Datensatz oder die Markierung wurde nicht gefunden.',
    409: 'Die Markierung wurde zwischenzeitlich geändert. Bitte neu laden und die Eingaben prüfen.',
    413: 'Die Anfrage ist zu groß.',
    429: 'Zu viele Anmeldeversuche. Bitte in fünf Minuten erneut versuchen.',
    422: 'Bitte prüfe deine Eingaben und Filter.',
    502: 'Die Admin-API ist nicht erreichbar oder hat eine ungültige Antwort geliefert.',
    503: 'Die Admin-API ist derzeit nicht bereit. Bitte später erneut versuchen.',
    504: 'Die Admin-API hat nicht rechtzeitig geantwortet.',
  }
  return {
    status,
    code,
    message: retryMessages[code] ?? messages[status] ?? 'Die Daten konnten nicht geladen werden.',
  }
}

export class AdminApiError extends Error {
  constructor(readonly failure: ApiFailure) {
    super(failure.message)
  }
}

export function asFailure(error: unknown): ApiFailure {
  return error instanceof AdminApiError ? error.failure : failure(502)
}
