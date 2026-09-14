export interface ApiFailure {
  status: number
  code: string
  message: string
}

export function failure(status: number, code = 'request_failed'): ApiFailure {
  const messages: Record<number, string> = {
    401: 'Anmeldung erforderlich. Für diesen Zugriff fehlen gültige Zugangsdaten.',
    403: 'Keine Berechtigung. Dein Zugang darf diese Verwaltungsdaten nicht lesen.',
    422: 'Die Filter sind ungültig. Bitte prüfe deine Eingaben.',
    502: 'Die Admin-API ist nicht erreichbar oder hat eine ungültige Antwort geliefert.',
    503: 'Die Admin-API ist derzeit nicht bereit. Bitte später erneut versuchen.',
    504: 'Die Admin-API hat nicht rechtzeitig geantwortet.',
  }
  return { status, code, message: messages[status] ?? 'Die Daten konnten nicht geladen werden.' }
}

export class AdminApiError extends Error {
  constructor(readonly failure: ApiFailure) {
    super(failure.message)
  }
}

export function asFailure(error: unknown): ApiFailure {
  return error instanceof AdminApiError ? error.failure : failure(502)
}
