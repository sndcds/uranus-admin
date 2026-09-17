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

## Activity als Gestaltungsreferenz

Das Muster lautet **Page Header → Filter Bar → Result Summary → Data List → Pagination**.
Kurze Titel und Beschreibungen führen in die Aufgabe; Filter bleiben flache Formulare.
API-Gesamtzahlen und sichtbare Seitencounts werden getrennt benannt. Farbige Chips ergänzen
lesbare Labels, ersetzen sie aber nicht. Pro Liste gibt es eine weiße, umrandete Fläche;
Gruppenheader und `divide-y` gliedern sie ohne verschachtelte Karten. Titel stehen vor
sekundären Metadaten, Aktionen bleiben am Datensatz. Nur Activity bekommt Tagesgruppen:
Finding-Beobachtungszeiten, Einladungsalter und Prüflaufhistorie haben andere Semantik.

Das Dashboard wendet dasselbe Muster auf Abschnitte an. Die Neuanlagen verwenden kleine
Icon-/Zahl-Kacheln ohne zusätzliche äußere Karte. Bestands-KPIs stehen als kompakte
Summary-Kacheln darunter. Vorgänge sind Linkzeilen; die Schnellfilter nutzen direkt die
FilterBar. Die Datenqualitätsvorschau zeigt höchstens fünf Regeln und verlinkt bei weiteren
Regeln auf `/quality`, wo alle vom API gelieferten Regeln angezeigt werden. Es handelt sich
um eine Vorschau, nicht um eine neue Regelpriorisierung oder clientseitige Pagination.

## Wiederverwendbare Bausteine

- `PageHeader`: Titel, Beschreibung, optionale Aktionen; einheitliche Heading-Ebene.
- `FilterBar`: semantisches Formular mit kompaktem responsivem Raster und Hilfe-Slot.
  Fachliche Filter, Validierung und URL-Synchronisation bleiben in Seite/FilterForm.
- `ResultSummary`: API-Gesamtzahl, sichtbare Einträge, optional Quelle/Stand und Aufschlüsselung.
  Mit `visible` betreffen Slot-Zahlen ausdrücklich die sichtbare Seite. Für echte aggregierte
  Qualitätszahlen entfällt `visible`, damit keine Seitenverteilung behauptet wird. Findings liefern keine aggregierten
  Schweregradzahlen für die vollständige gefilterte Liste.
- `PaginationBar`: „Seite X von Y“, benannte Navigation, deaktivierte Rand-/Ladezustände;
  URL-Links für Activity/Marks/Queues, Change-Events für Findings/Checks, Slot für Seitengröße.
- `EmptyState`: kurzer hilfreicher Text in derselben Listenfläche.
- `EntityTypeBadge`: Activity-Typdefinition plus Veranstaltungslink, Lizenz und Bildverknüpfung;
  unbekannte Typen bleiben lesbar. `StatusBadge` und `SeverityBadge`: Text plus Farbe.
- `DataListShell`: gemeinsame Listenfläche mit semantischem `div`, `ul` oder `section`;
  Datenfelder, Gruppen und Aktionen bleiben in fachlichen Komponenten. `aria-busy` und
  Beschriftungen werden an das Root-Element weitergereicht.
- `data-list` / `data-row` und `list-group-header`: gemeinsame Tailwind-Muster für weiße Listenflächen und kompakte
  Zeilen. Keine universelle Komponente, die fachlich unterschiedliche Datenfelder vermischt.

Die Hauptseiten nutzen `space-y-4/5`, Filter `p-4`, Zeilen `px-4/5 py-3`, slate-Neutralfarben
und fuchsia-Akzente. Filter und Aktionen umbrechen mobil. Fokusmarkierungen, Skip-Link,
`aria-busy`, native Formulare, semantische Listen und Modal-Tastatursteuerung bleiben erhalten.

## Seiten-Audit

| Seite | Umsetzung / fachliche Besonderheit |
| --- | --- |
| `/` | Kompakter Zeitraum-Primärbereich vor Bestands-KPIs; serverseitig priorisierte Vorschau, begrenzte Regelvorschau, Vorgangszeilen und flache Schnellfilter |
| `/activity` | Referenzstil auf gemeinsame Header/Filter/Summary/Pagination/EmptyState umgestellt; Tagesgruppen, unknown timestamps, Bilder/Modal und Actions unverändert |
| `/findings` | Kompakte Filter ohne zusätzliche Filterüberschrift; Gesamtzahl/Seitencounts; kompakte Rows mit Severity-, Entity- und Status-Badges, Details, Action und Markierungen; alle Filter und page_size bleiben |
| `/quality` | Header, echte aggregierte ResultSummary mit Severity-Chips, vollständige Regelzeilen in DataListShell; keine Filter oder Pagination ohne API-Unterstützung |
| `/checks` | Kompakte Historie mit Start/Ende, Regeln, Befunden und deutschen Status-Badges; gemeinsame Pagination |
| `/marks` | Gemeinsame Filter, Summary, Badges, Rows und Pagination; Filter-Reset behält einen gezielt gewählten Datensatz bei |
| `/marks/:id` | Gemeinsamer Header und Badges; Bearbeitungsformular und chronologischer Audit-Verlauf bleiben absichtlich Detailansichten |
| `/queues/:kind` | Gemeinsame Shell mit echten fachlichen Unterschieden: gerichtete Partneranfragen, Einladungsalter aus `invited_at`, Aktivierungsalter aus `created_at`; keine letzte Aktivität abgeleitet. URL-Filter werden bei Navigation ins Formular zurückgespiegelt |

Alle existierenden Seiten sind berücksichtigt. Größere bewusst eigenständige Bereiche sind
Navigation und die Bearbeitungsformulare/Modals: sie sind keine paginierten
Datenlisten und behalten ihre funktionsgerechte Struktur. Der Markierungsverlauf nutzt trotzdem
die gemeinsame Listenfläche; das Editierformular bleibt eine eigene Fläche. Das Loginpanel
zeigt nach erfolgreicher Anmeldung nur eine kompakte Status-/Abmelden-Zeile, bei fehlender
Identität weiterhin das vollständige Formular. Der lokale Entwicklungszugang bleibt geschlossen.
Der globale Header zeigt nur die App-Identität, Seitentitel stehen im PageHeader.
Keine datenorientierte Route bleibt bei einer separaten Kartensprache. Keine neuen Backend-Felder,
Migrationen oder Live-Server-Einstellungen werden benötigt.

## Verifikation

`tests/unit/data-page.test.ts` prüft die gemeinsamen Bausteine; `tests/e2e/unified-ui.spec.ts`
prüft Zeitraum-/Bestandssemantik, Stale-Daten, Findings-Filter, Zusammenfassungen,
Prüflaufhistorie, begrenzte Regelvorschau, vollständige Qualitätsliste und Tablet-Layout.
Die bestehenden Playwright-Ausgaben enthalten Screenshots für Dashboard, Activity, Findings,
Quality, Checks, Marks und Queues auf Desktop und Mobile (synthetische Testdaten).
Bestehende E2E-Tests decken alle neun Activity-Drill-downs, Unknown-Zeitpunkte,
Thumbnails/Modal, Auth-Verlust, Reviews, Markierungshistorie und Queue-Altersbasis weiterhin ab.

### Zeitstempel in den Listen

`observed_at` in der Ergebnisübersicht bezeichnet den Stand der Antwort, nicht automatisch
einen neuen Prüflauf. Findings zeigen zusätzlich `last_seen_at` als letzte Beobachtung.
Activity gruppiert nur belegtes `created_at`; fehlende Zeitstempel bleiben außerhalb einer
Chronologie. Prüfläufe zeigen tatsächlichen Start und Abschluss. Markierungen zeigen
Erstellung/Erledigung sowie die unveränderten Zeitpunkte ihrer Historie. Einladungen verwenden
`invited_at` für ihr Alter; Benutzeraktivierung und Partneranfragen `created_at`.

### Logo quality

`/quality` uses `QualityOverview` for a “Logos & Bilder” group with “Orte ohne Logo”,
“Organisationen ohne Logo” and “Logos in anderem Format”. Shared list rows and
SeverityBadge distinguish warning (schlechte Datenqualität) from info (Hinweis).
The additive `quality.rule_counts` map supplies counts, including zero; missing metrics
remain “Nicht verfügbar”. Each row links to the corresponding finding rule and, for
missing logos, the venue/organization entity filter, preserving the source mode.
Finding Actions and entity details use the existing canonical routes. Core policy,
identity and scan coverage are documented in [contracts](../../backend/docs/contracts.md).

### Adressqualität

| rule | entity | severity | Bedeutung |
| --- | --- | --- | --- |
| postal_code_whitespace | organization/venue | warning | Führende oder abschließende Whitespaces in postal_code |

`/quality` zeigt unter „Adressqualität“ den Eintrag „Postleitzahlen mit Leerzeichen“,
den Badge „Warnung“ und „Schlechte Datenqualität“. Die zentrale Präsentation in
`app/utils/quality.ts` liefert Label, Gruppe und Severity. Der Count kommt aus
`quality.rule_counts["postal_code_whitespace"]`; fehlende Counts bleiben „Nicht verfügbar“.
Der Drilldown `/findings?rule=postal_code_whitespace` erhält den Live-/Persisted-Modus
und setzt keinen Entity-Filter, da Organisationen und Orte betroffen sein können.

Finding-Zeilen zeigen Entity-Typ, Name, `Feld: postal_code`, Warnung und die Meldung
„Postleitzahl enthält führende oder abschließende Leerzeichen.“ Die bestehende Action
führt auf `/organizations/<uuid>` bzw. `/venues/<uuid>`.

Nur autoritative Organization-/Venue-Werte zählen. Projektionen werden nicht separat
gezählt. Interne Spaces bleiben erlaubt, weil internationale Postleitzahlen sie benötigen
können; kein landesspezifisches PLZ-Format wird validiert. Rand-Tabs und -Zeilenumbrüche
werden ebenfalls erkannt. Die Prüfung bleibt lesend und korrigiert keine Quelldaten.
`tests/e2e/postal-code-quality.spec.ts` prüft Gruppe, Count, Severity, beide Entity-Actions
und den gemeinsamen Rule-Drilldown in Live- und Persisted-Modus auf Desktop und Mobile.
