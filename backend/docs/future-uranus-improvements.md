# Spätere Uranus-Verbesserungen — keine Umsetzung in Meilenstein 1

Diese Punkte stammen aus der Analyse des Commits `7feb47e319145b383d46616026f27fe9d6626d63`.
Sie sind Vorschläge, keine durchgeführten Schemaänderungen. Vor Änderungen Live-Schema,
fachliche Semantik und bestehende Daten prüfen.

## Identität und Rechte

- Explizite serverseitige Systemadmin-Berechtigung samt sicherem Token-Verifikationsvertrag.
  Org-Teamverwaltung ist keine globale Berechtigung. Deaktivierung/Widerruf definieren.
- Membership-Prüfung in Org-/Venue-/Event-Rechtepfaden vereinheitlichen; direkte Objektberechtigungen
  fachlich abgrenzen. Doppelte `user_*_link`-Paare bereinigen und geeignete UNIQUE-Constraints prüfen.
- Permission-TODOs in Partner- und Pluto-Handlern schließen, bevor neue Admin-Aktionen sie nutzen.
- Registrierte ältere Event-/Terminhandler mit `id`/`event_id` statt UUID-Spalten korrigieren
  und mit aktuellen Schreibverträgen testen. Validation und Projektionsrefresh pro Pfad absichern.

## Belastbare Zeitpunkte

- UTC-Speicherung wurde durch den Betreiber für den Backup bestätigt. Diesen Vertrag für
  alle Writer verbindlich dokumentieren. `SHOW timezone` allein wäre kein historischer Beleg.
- Neue Auditdaten als timestamptz. Altdaten nicht ohne Migrationsstrategie umdeuten; Zeitpunkte
  in der DST-Doppelstunde sind ohne Zusatzdaten nicht eindeutig wiederherstellbar.
- Membership: `joined_at`/`accepted_at` für künftige Annahmen; keine Rückdatierung aus created_at.
- Partneranfrage: stabile ID, `decision_at`, Entscheider und Entscheidung statt Löschhistorie zu erfinden.
- User: `activated_at` und bei fachlichem Bedarf echtes `last_login_at`; nicht modified_at umbenennen.
- Bildverknüpfung: Zeitpunkt für neue Verwendung und ggf. Akteur.
- Auditlog für Neuanlage/Änderung/Löschung/Einladung/Annahme/Partnerentscheidung; Umfang und
  datensparsame Aufbewahrung festlegen. Erst ab Einführung belastbar.

## Domain-Verträge und Constraints

- Effektiven Space zwischen öffentlicher Projektionsliste und Termindetail vereinheitlichen.
- Öffentliche Status, Absagen/Verschiebungen, release_date und Termin-Overrides definieren.
- URL-Prüfung konsistent in Uranus-Schreibpfaden verwenden; Groß-/Kleinschreibung, Whitespace
  und optionale Leerwerte fachlich klären. Wiki-Felder nicht ungeprüft als URLs interpretieren.
- `venue.scope` Default `'standard'` widerspricht CHECK `'organization'/'shared'`; auch im Live-Backup bestätigt.
- Partneranfrage-FKs, Self-Request-Verbot und definierte Statuswerte prüfen.
- `event_date.event_uuid` ist nullable; Bedarf klären.
- `space_feature_link.space_id` Integer gegenüber `space.uuid` UUID klären.
- Pluto-Kontext/Identifier und polymorphe Ziele absichern; Metadatenpflichten nach Kontext definieren.
- Die vollständigen Enums/Funktionen/Trigger sind im nachgereichten Backup enthalten. Diese
  Definitionen ohne Produktivdaten versionieren, einschließlich Abhängigkeiten außerhalb `uranus`.
  Repository-DDL und Backup unterscheiden sich bei `organization.member_of_orgs`; Schemaquelle vereinheitlichen.
  Projektionszeitstempel nicht als Domain-Neuanlage zählen.

## Indexkandidaten — zuerst EXPLAIN

| Query | Zu prüfende Indexrichtung |
| --- | --- |
| Neue Datensätze | created_at der neun Quelltabellen; UTC-Vertrag ermöglicht indexfreundliche Parametergrenzen |
| Kommende Termine | event_date(start_date, event_uuid), abhängig von Selektivität und realem Plan |
| Org-Listen/Joins | venue(org_uuid), event(org_uuid), space(venue_uuid) |
| Offene Vorgänge | partielle Indizes auf pending und nicht beigetretene Memberships samt Altersfeld |
| Fehlende Geoposition | ggf. partieller Index für NULL/EMPTY, erst nach Plan/Selektivitätsmessung |

Vorhanden sind bereits Event-Venue-, Event-Date-Event-/Venue-Indizes sowie Venue-GiST(point).
Ein Ausdruck über Event und Event Date (`COALESCE`) lässt sich nicht durch einen einfachen
tabellenübergreifenden Index lösen; ggf. disjunkte Query-Zweige testen. Ausdrucksindizes für
Zeitzonenfilter erst nach festem Speichervertrag prüfen. Keine dieser Änderungen wurde ausgeführt.
