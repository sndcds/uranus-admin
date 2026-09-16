# Gemeinsame Daten- und Arbeitsseiten

## Informationsarchitektur

Das Dashboard trennt periodengebundene Neuanlagen vom aktuellen Arbeitsbestand:

1. Anmeldung/Zugang (Layout), Dashboard-Header; ein zentraler Zeitraumselector im Layout.
2. **Neu eingegangen**: Gesamtzahl, benannter Zeitraum, `from_at`/`to_at` aus der Antwort,
   neun klickbare Objektarten; die Links verwenden weiterhin `dashboard.period`.
3. **Was braucht Aufmerksamkeit?**: aktueller Bestand, ausdrücklich unabhängig vom Zeitraum.
4. Priorisierte Arbeitsliste und Datenqualität.
5. Offene Vorgänge und Schnellfilter.

Die nicht verfügbare „Nächste Veranstaltung“-Platzhalterkarte entfällt. Bestehende Navigation,
Authentifizierung, serverseitige Sortierung und API-Verträge bleiben erhalten.

### Bedeutung der Kennzahlen

| Kennzahl | Fachliche Basis | Zeitbezug / Ziel |
| --- | --- | --- |
| Neu eingegangen | `period_window` und tatsächliches `created_at` der neun Quelltabellen | `[from_at,to_at)`; Activity mit gewähltem `period` und `entity_type` |
| Dringend | Nicht behobene persistierte Findings mit Priorität ≤ 2 oder `published_soon` | Bestand; gesamte Arbeitsliste, **kein exakt reproduzierbarer Dringlichkeitsfilter** |
| Datenqualität | `persisted_counts`: alle Status außer `resolved`, inklusive Snooze/Ausnahmen | Bestand; echte Gesamtzahlen für Fehler, Warnungen und Hinweise |
| Offene Vorgänge | Eigene paginierte Queues | Bestand; Summary liefert keine Gesamtzahl, daher „Nicht verfügbar“ und Links zu den Queues |
| Prüfstatus | Eigene Prüflaufhistorie | Summary liefert keinen aktuellen Status; Link zu den gespeicherten Prüfläufen |

Quelle: `backend/app/services/dashboard.py`, `repositories/dashboard.py` und
`services/checks.py::persisted_counts`. Der Standard ist persistiert; eine explizite
Live-Diagnose zählt den aktuellen Scan, ebenfalls unabhängig vom Dashboard-Zeitraum.
Die Anzeige benennt die tatsächliche Quelle. Ein GET im Standard löst keinen Vollscan aus.

Bei einem Zeitraumwechsel bleiben vorhandene Zahlen mit dem **Zeitraum ihrer Antwort**
beschriftet, bis neue Daten ankommen. Der bestehende Hinweis auf den vorherigen Zeitraum
bleibt sichtbar. Links öffnen den neu gewählten Zeitraum; auch das wird im Hinweis erklärt.

„Neu aufgetretene Befunde“ wird nicht ergänzt. `first_seen_at` existiert für persistierte
Findings, aber der Summary-Vertrag enthält dafür keine aggregierte Zeitfensterzählung.
Eine aktuelle Findings-Seite darf weder zu einer Gesamtzahl hochgerechnet noch `last_seen_at`
als Erstfund interpretiert werden. Eine zusätzliche Backend-Metrik bleibt Folgearbeit.

## Wiederverwendbare Bausteine

- `PageHeader`: Titel, Beschreibung, optionale Aktionen; einheitliche Heading-Ebene.
- `FilterBar`: semantisches Formular mit kompaktem responsivem Raster und Hilfe-Slot.
  Fachliche Filter, Validierung und URL-Synchronisation bleiben in Seite/FilterForm.
- `ResultSummary`: API-Gesamtzahl, sichtbare Einträge, optional Quelle/Stand und Aufschlüsselung.
  Slot-Zahlen betreffen ausdrücklich die sichtbare Seite. Findings liefern keine aggregierten
  Schweregradzahlen für die vollständige gefilterte Liste.
- `PaginationBar`: „Seite X von Y“, benannte Navigation, deaktivierte Rand-/Ladezustände;
  URL-Links für Activity/Marks/Queues, Change-Events für Findings/Checks, Slot für Seitengröße.
- `EmptyState`: kurzer hilfreicher Text in derselben Listenfläche.
- `EntityTypeBadge`: Activity-Typdefinition plus Veranstaltungslink, Lizenz und Bildverknüpfung;
  unbekannte Typen bleiben lesbar. `StatusBadge` und `SeverityBadge`: Text plus Farbe.
- `data-list` / `data-row`: gemeinsame Tailwind-Muster für weiße Listenflächen und kompakte
  Zeilen. Keine universelle Komponente, die fachlich unterschiedliche Datenfelder vermischt.

Die Hauptseiten nutzen `space-y-4/5`, Filter `p-4`, Zeilen `px-4/5 py-3`, slate-Neutralfarben
und fuchsia-Akzente. Filter und Aktionen umbrechen mobil. Fokusmarkierungen, Skip-Link,
`aria-busy`, native Formulare, semantische Listen und Modal-Tastatursteuerung bleiben erhalten.

## Seiten-Audit

| Seite | Umsetzung / fachliche Besonderheit |
| --- | --- |
| `/` | Zeitraum-Primärbereich vor Bestands-KPIs; serverseitig priorisierte Vorschau |
| `/activity` | Referenzstil auf gemeinsame Header/Filter/Summary/Pagination/EmptyState umgestellt; Tagesgruppen, unknown timestamps, Bilder/Modal und Actions unverändert |
| `/findings` | Kompakte Filter ohne zusätzliche Filterüberschrift; Gesamtzahl/Seitencounts; kompakte Rows mit Severity-, Entity- und Status-Badges, Details, Action und Markierungen; alle Filter und page_size bleiben |
| `/quality` | Gemeinsamer Header, belegte Bestandszahlen und kompakte Regelzeilen; keine künstliche Pagination |
| `/checks` | Kompakte Historie mit Start/Ende, Regeln, Befunden und deutschen Status-Badges; gemeinsame Pagination |
| `/marks` | Gemeinsame Filter, Summary, Badges, Rows und Pagination; Filter-Reset behält einen gezielt gewählten Datensatz bei |
| `/marks/:id` | Gemeinsamer Header und Badges; Bearbeitungsformular und chronologischer Audit-Verlauf bleiben absichtlich Detailansichten |
| `/queues/:kind` | Gemeinsame Shell mit echten fachlichen Unterschieden: gerichtete Partneranfragen, Einladungsalter aus `invited_at`, Aktivierungsalter aus `created_at`; keine letzte Aktivität abgeleitet. URL-Filter werden bei Navigation ins Formular zurückgespiegelt |

Alle existierenden Seiten sind berücksichtigt. Größere bewusst eigenständige Bereiche sind
Login/Access, Navigation und die Bearbeitungsformulare/Modals: sie sind keine paginierten
Datenlisten und behalten ihre funktionsgerechte Struktur. Keine neuen Backend-Felder,
Migrationen oder Live-Server-Einstellungen werden benötigt.

## Verifikation

`tests/unit/data-page.test.ts` prüft die gemeinsamen Bausteine; `tests/e2e/unified-ui.spec.ts`
prüft Zeitraum-/Bestandssemantik, Stale-Daten, Findings-Filter und Zusammenfassungen sowie
Prüflaufhistorie. Bestehende E2E-Tests decken alle neun Activity-Drill-downs, Unknown-Zeitpunkte,
Thumbnails/Modal, Auth-Verlust, Reviews, Markierungshistorie und Queue-Altersbasis weiterhin ab.

### Zeitstempel in den Listen

`observed_at` in der Ergebnisübersicht bezeichnet den Stand der Antwort, nicht automatisch
einen neuen Prüflauf. Findings zeigen zusätzlich `last_seen_at` als letzte Beobachtung.
Activity gruppiert nur belegtes `created_at`; fehlende Zeitstempel bleiben außerhalb einer
Chronologie. Prüfläufe zeigen tatsächlichen Start und Abschluss. Markierungen zeigen
Erstellung/Erledigung sowie die unveränderten Zeitpunkte ihrer Historie. Einladungen verwenden
`invited_at` für ihr Alter; Benutzeraktivierung und Partneranfragen `created_at`.
