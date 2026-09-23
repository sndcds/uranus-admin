import type { GeocodeStatus } from '#shared/contracts'

export const geocodeStatuses: Record<GeocodeStatus, string> = {
  pending: 'Prüfung vorgemerkt',
  checking: 'Prüfung läuft',
  candidate: 'Standortvorschlag vorhanden',
  ambiguous: 'Mehrere mögliche Standorte',
  not_found: 'Kein passender Standort gefunden',
  insufficient_input: 'Zu wenig Adressdaten',
  failed: 'Standortprüfung fehlgeschlagen',
  stale: 'Vorschlag veraltet',
}
export const geocodeMessages: Record<GeocodeStatus, string> = {
  pending: 'Die eingeplante Prüfung ist noch nicht abgeschlossen.',
  checking: 'Das Ergebnis steht nach Abschluss der Prüfung bereit.',
  candidate: 'Der Vorschlag verändert die gespeicherte Geoposition nicht.',
  ambiguous: 'Bitte die Kandidaten vergleichen. Die gespeicherte Geoposition bleibt unverändert.',
  not_found: 'Bitte die Quelladresse prüfen, bevor eine neue Prüfung eingeplant wird.',
  insufficient_input: 'Für eine zuverlässige Standortsuche fehlen ausreichende Adressdaten.',
  failed: 'Die Prüfung kann unter „Weitere Aktionen“ erneut eingeplant werden.',
  stale:
    'Dieser Vorschlag ist nicht mehr aktuell. Die Adresse oder Position hat sich geändert oder der Datensatz wurde entfernt.',
}
export const matchReasonLabels: Record<string, string> = {
  country_exact: 'Land stimmt überein',
  country_mismatch: 'Land weicht ab',
  country_unknown: 'Land nicht sicher zugeordnet',
  postal_code_exact: 'PLZ stimmt überein',
  postal_code_mismatch: 'PLZ weicht ab',
  postal_code_missing: 'PLZ fehlt für den Vergleich',
  city_exact: 'Ort stimmt überein',
  city_mismatch: 'Ort weicht ab',
  city_missing: 'Ort fehlt für den Vergleich',
  street_exact: 'Straße stimmt überein',
  street_mismatch: 'Straße weicht ab',
  street_missing: 'Straße fehlt für den Vergleich',
  house_number_exact: 'Hausnummer stimmt überein',
  house_number_mismatch: 'Hausnummer weicht ab',
  house_number_missing: 'Hausnummer fehlt für den Vergleich',
}
