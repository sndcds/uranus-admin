import type { Severity } from '#shared/contracts'

export const qualityRules: Record<
  string,
  { label: string; severity: Severity; group: string; entityType?: string }
> = {
  organization_missing_location: {
    label: 'Organisationen ohne Geoposition',
    severity: 'warning',
    group: 'Standorte',
    entityType: 'organization',
  },
  venue_missing_location: {
    label: 'Orte ohne Geoposition',
    severity: 'warning',
    group: 'Standorte',
    entityType: 'venue',
  },
  venue_missing_logo: {
    label: 'Orte ohne Logo',
    severity: 'warning',
    group: 'Logos & Bilder',
    entityType: 'venue',
  },
  organization_missing_logo: {
    label: 'Organisationen ohne Logo',
    severity: 'warning',
    group: 'Logos & Bilder',
    entityType: 'organization',
  },
  logo_unsupported_format: {
    label: 'Logos in anderem Format',
    severity: 'info',
    group: 'Logos & Bilder',
  },
  postal_code_whitespace: {
    label: 'Postleitzahlen mit Leerzeichen',
    severity: 'warning',
    group: 'Adressqualität',
  },
  event_date_end_before_start: {
    label: 'Enddatum liegt vor Startdatum',
    severity: 'error',
    group: 'Terminintegrität',
    entityType: 'event_date',
  },
  event_date_same_day_end_before_start: {
    label: 'Endzeit liegt am selben Tag vor Startzeit',
    severity: 'error',
    group: 'Terminintegrität',
    entityType: 'event_date',
  },
  event_date_overnight_without_end_date: {
    label: 'Übernachttermin ohne Enddatum',
    severity: 'info',
    group: 'Terminintegrität',
    entityType: 'event_date',
  },
  event_price_without_currency: {
    label: 'Preis ohne Währung',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  event_price_range_invalid: {
    label: 'Ungültiger Preisbereich',
    severity: 'error',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  event_free_with_price: {
    label: 'Kostenlose Veranstaltung mit Preis',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  event_link_empty: {
    label: 'Veranstaltungslink ohne URL',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event_link',
  },
  event_link_missing_type: {
    label: 'Veranstaltungslink ohne Typ',
    severity: 'info',
    group: 'Veranstaltungsqualität',
    entityType: 'event_link',
  },
  event_link_unknown_type: {
    label: 'Unbekannter Linktyp',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event_link',
  },
  email_syntax: {
    label: 'Ungültige E-Mail-Syntax',
    severity: 'warning',
    group: 'Kontakt & Adressen',
  },
  postal_code_syntax: {
    label: 'Ungültiges Postleitzahlenformat',
    severity: 'warning',
    group: 'Kontakt & Adressen',
  },
  text_surrounding_whitespace: {
    label: 'Leerzeichen in strukturierten Feldern',
    severity: 'info',
    group: 'Kontakt & Adressen',
  },
  space_capacity_inconsistent: {
    label: 'Sitzplätze über Gesamtkapazität',
    severity: 'warning',
    group: 'Raumkapazität',
    entityType: 'space',
  },
  space_capacity_invalid: {
    label: 'Ungültige Kapazität oder Fläche',
    severity: 'error',
    group: 'Raumkapazität',
    entityType: 'space',
  },
  released_event_without_description: {
    label: 'Veröffentlichte Veranstaltung ohne Beschreibung',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  released_event_without_categories: {
    label: 'Veröffentlichte Veranstaltung ohne Kategorie',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  released_event_without_type: {
    label: 'Veröffentlichte Veranstaltung ohne Typ',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  membership_joined_accept_token_present: {
    label: 'Einladungstoken nach Beitritt vorhanden',
    severity: 'error',
    group: 'Interne Sicherheit',
    entityType: 'team_membership',
  },
  event_unknown_category: {
    label: 'Unbekannte Veranstaltungskategorie',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  event_type_link_unknown_type: {
    label: 'Unbekannter Veranstaltungstyp',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  event_type_link_unknown_genre: {
    label: 'Unbekanntes Genre',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
  event_unknown_language: {
    label: 'Unbekannter Sprachcode',
    severity: 'warning',
    group: 'Veranstaltungsqualität',
    entityType: 'event',
  },
}
