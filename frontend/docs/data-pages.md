# Gemeinsame Daten- und Arbeitsseiten

## Informationsarchitektur

Das Dashboard trennt periodengebundene Neuanlagen vom aktuellen Arbeitsbestand:

1. Anmeldung/Zugang (Layout), Dashboard-Header; ein zentraler Zeitraumselector im Layout.
2. **Neu eingegangen**: Gesamtzahl, benannter Zeitraum, `from_at`/`to_at` aus der Antwort,
   neun klickbare Objektarten; die Links verwenden den aktuell gewählten Zeitraum der Dashboard-Seite.
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

### Gemeinsame Entity-Live-Suche

`EntitySearch.vue` ersetzt das einfache Suchfeld auf users, organizations, venues,
spaces, events und images. Das Layout verwendet dieselben Design-Tokens wie GraphFilters
sowie AppIcon und die vorhandenen `entityTypes`; Graph-Verhalten bleibt unverändert.
Der zentrale `$adminApi.entitySearch` verwendet den authentifizierten Proxy und prüft
Antworten samt Action-Links über den gemeinsamen Runtime-Contract.

Ab zwei getrimmten Zeichen startet nach 275 ms die Suche; maximal 20 Treffer sind erlaubt
(Standard im UI/API: 10). Query-, Typ-, Organisations- und Statuswechsel invalidieren
laufende Antworten sofort. Loading-, Fehler- und Leerzustände bleiben im Dropdown.
Es gibt keine clientseitige Vollsuche. Escape leert und schließt, Außenklick/Tab schließen.
ArrowDown/ArrowUp wählen zyklisch, Enter öffnet einen explizit gewählten Treffer über
`action.href`. Ohne Auswahl wendet Enter den q-Filter der Liste an. Combobox, Listbox,
Option, aria-controls/expanded/activedescendant und aria-selected vermitteln den Zustand.
Die Dropdown-Breite folgt dem Eingabefeld, die Höhe ist begrenzt und scrollbar.

Autocomplete-Eingaben ändern die URL nicht. Erst Enter ohne Auswahl oder Anwenden
setzt q/organization_id/status und page=1. Pagination erhält q und die übrigen Filter;
Reload und Browser-Navigation stellen den Zustand aus der URL wieder her.

Durchsuchte Felder (jeweils einschließlich UUID/Teil-UUID):

- Benutzer: username, display_name, email, first_name, last_name.
- Organisationen: name, contact_email, city, postal_code.
- Orte: name, contact_email, street, house_number, postal_code, city.
- Räume: name, venue.name, space_type.
- Veranstaltungen: title, subtitle, external_id; kein unbestätigtes search_text.
- Bilder: tatsächlich vorhandene file_name, alt_text, creator_name, mime_type.

Autocomplete und paginierte q-Suche haben dieselbe case-insensitive Literal-Substring-
Semantik, auch bei `%`, `_` und `\`. E-Mail-Adressen erscheinen im geschützten
Benutzer-Suchdropdown; Secrets/Tokens werden weder durchsucht noch ausgegeben.
Die Source bleibt read-only. Große ILIKE-Scans können künftig pg_trgm-Indizes im
Uranus-Repo benötigen; dieser Task führt keine Source-Migrationen aus.

### Terminlage in den Entity-Listen

Das sichtbare Eingabefeld „Organisation UUID“ entfällt auf allen sechs Listen.
`organization_id` bleibt für Deep Links, interne Navigation und API-Consumer erhalten;
Anwenden, Live-Suche und Pagination übernehmen den vorhandenen URL-Wert weiterhin.

Auf events, organizations, venues und spaces steht der Filter **Terminlage**:

- Alle: kein temporal-Parameter.
- Mit bevorstehenden Terminen: `temporal=upcoming`.
- Mit vergangenen Terminen: `temporal=past`.

Users und images zeigen keinen Terminlage-Filter und senden ihn nicht im Autocomplete.
Explizite API-Anfragen für diese Typen mit temporal werden mit 422 abgewiesen.
Die Auswahl wendet den Filter sofort an und setzt page=1. Enter/Anwenden kombinieren
q, temporal und Status mit einem bestehenden organization_id. Pagination behält alle
Parameter; Reload und Browser Back/Forward stellen die Steuerelemente wieder her.
Die Ergebnisübersicht zeigt den angewendete Terminlage über das vorhandene
ResultSummary-description-Pattern. Auf kleinen Viewports bricht die Filterleiste um.

EntitySearch reicht temporal an den zentralen Admin-API-Client durch und invalidiert
bei Änderungen alte Antworten. Debounce, Tastaturbedienung und Fehlerzustände bleiben
bestehen; es findet keine lokale zeitliche Filterung statt. Die Proxy-Allowlist umfasst
den neuen Parameter sowohl für Listen als auch für entity-search.

Die zentrale Backend-Semantik verwendet das effektive **Terminende**, nicht created_at.
Ein Event/Organisation/effektiver Ort/effektiver Raum braucht mindestens einen passenden
Termin. Laufende und heute ganztägige Termine sind noch bevorstehend; gemischte Termine
können beide Filter erfüllen. Ohne Termine bleibt ein Event nur unter „Alle“ sichtbar.
Venue-/Space-Vererbung folgt location.py, einschließlich der aufgehobenen Space-Vererbung
bei einem Venue-Override am Termin. Datum/Uhrzeit werden in EVENT_TIMEZONE (Standard
Europe/Berlin) interpretiert und mit einem UTC-Zeitpunkt verglichen. Enddatum ohne
Endzeit und all_day gelten bis Tagesende; Endzeit ohne Enddatum gehört zum Starttag.
Ohne Endangaben zählt der Startzeitpunkt (fehlende Startzeit: Tagesbeginn).
Weitere Details, DST- und Performance-Grenzen stehen im Backend-Contract.

## Filterpräferenzen und Zuständigkeiten

Vor dieser Änderung lagen Entity-, Activity-, Statistics- und Graph-Filter in lokalen
Seiten-Refs bzw. direkt in der Route; Dashboard besaß zusätzlich einen eigenen
`period`-State. Findings hat bereits einen eigenständigen Store für validierte Filter
und Ergebnisdaten. Diese Ownership wird nicht dupliziert: Findings bleibt unverändert.
Checks hat nur Pagination/Polling, Quality zeigt aktuellen Bestand. Die Queue-Filter
(Organisationskontext, Mindestalter und je Queue unterschiedliche Status) bleiben
URL-basiert; sie teilen weder Event-Termine noch Neuanlagen-Zeiträume.

`useFilterPreferencesStore` (`app/stores/filter-preferences.ts`) hält ausschließlich
Präferenzen im anwendungs-/SSR-request-lokalen Pinia-Speicher:

| Bereich | Gemerkte Werte |
| --- | --- |
| `sharedPeriod` | `today`, `24h`, `7d`, `30d`, `90d` |
| `entities.events` | `q`, Event-`status`, `temporal`, `period` |
| `entities.users` | `q`, User-`status`, `period` |
| `entities.organizations/venues/spaces` | `q`, `temporal`, `period` |
| `entities.images` | `q`, `period` |
| `activity` | Objektart und zuletzt explizit gewähltes normales Preset |
| `statistics` | normales Preset, Intervall, Vergleich, ausgewählte Serien |
| `graph` | Entitätstyp, Beziehungstyp, Suchorganisation, Tiefe |

`app/utils/periods.ts` zentralisiert Schema, Labels und Unterstützung. Dashboard und
Activity unterstützen Heute/24 Stunden/7 Tage; Statistics 24 Stunden/7/30/90 Tage.
Ein nicht unterstützter gemeinsamer Zeitraum verwendet lokal `24h` und **ändert die
globale Präferenz nicht**. `custom`, Activity `unknown`, eigene Datumsgrenzen,
Chart-Highlight und geöffnete Dialoge bleiben lokale bzw. explizite URL-Zustände.
Passt ein gemerktes Statistikintervall nach Wechsel des gemeinsamen Zeitraums nicht
mehr in die bestehende 500-Bucket-Grenze, verwendet die Seite lokal `auto`.
Graph speichert weder Suchtext noch Root. Die Suchorganisation bleibt lokal zur
Graph-Präferenz; ein gespeicherter Organisationsfilter wird auch vor Laden des
nächsten Graphs als Auswahl angezeigt.

Es gilt **URL > Store > Default**. Bei Entity-Einstiegen gewinnen explizite Felder
(z. B. `status=draft`); fehlende Felder werden einmal aus der jeweiligen Präferenz
ergänzt. Die vervollständigte Query wird mit `router.replace` einschließlich `page=1`
teilbar gemacht. Bereits angewendete Entity-URLs mit `page` sind vollständige
Snapshots: Fehlende Werte bedeuten dort leere Filter. So reaktiviert insbesondere
Reload oder Zurück/Vorwärts keine zuvor gelöschten Filter.

Activity, Statistics und Graph erhalten ihre bisherigen vollständigen Query-Verträge:
Ein expliziter Query-Link gewinnt insgesamt. Das schützt insbesondere Activity-Links
zu einzelnen Objektschlüsseln oder Custom-Ranges vor zusätzlichen Zeitgrenzen sowie
Graph-Root-Links vor gespeicherten Einschränkungen. Ohne Query werden die
Präferenzen einmal übernommen und in der URL sichtbar gemacht. `usePreferenceQuery`
trennt diese Wiederherstellung von späteren URL-Änderungen. Zurück/Vorwärts liest
ausschließlich den jeweiligen URL-Zustand ein und aktualisiert den scoped Store.
Es gibt keine Rückkopplung vom Store zum Router. Auch ungültige explizite API-Filter
werden nicht durch gespeicherte Werte ersetzt.

Entity-Filter werden bei Anwenden oder Enter gespeichert, mit `page=1` in die URL
übernommen und durch die bestehende API serverseitig angewendet. Pagination erhält
die Query. Nicht angewendete Suchentwürfe werden nicht als letzte Filter gespeichert.
Reset löscht nur die aktuelle Entity und ihren URL-Kontext, keine anderen Bereiche.
`organization_id` bleibt für Deep Links unterstützt, wird aber nicht als globale
Präferenz gespeichert. Die typisierten Entity-Schemas verhindern eine Vermischung
von Event- und User-Status sowie Terminlage-Filter für Users/Images.

DashboardStore besitzt jetzt nur Daten, Lade-/Fehlerzustand, `lastSuccess` und
Request-Koordination. Der zu ladende Zeitraum ist ein Argument, keine zweite
Preference-Quelle. Dashboard-Links übernehmen den auf der Seite gewählten Zeitraum.
Der bereits sichtbare Hinweis bei älteren Daten während eines Zeitraumwechsels bleibt.

Es gibt **kein Persist-Plugin und keine Speicherung in localStorage, sessionStorage,
IndexedDB oder Cookies**. Ein voller Reload rekonstruiert nur den URL-Zustand.
Suchbegriffe können personenbezogene Daten enthalten und bleiben ausschließlich im
Session-Arbeitsspeicher. Der bestehende Auth-Reset löscht mit `resetAll()` alle
Präferenzen bei Logout (auch bei Serverfehler), Session-Verlust und erneutem Login.
Backend, Auth-Grenzen und Source-Read-only-Vertrag bleiben unverändert.


## Erstellt und Terminlage

Alle sechs Entity-Listen unterstützen **Erstellt** (`period`): Alle, Heute,
Letzte 24 Stunden, Letzte 7 Tage, Letzte 30 Tage und Letzte 90 Tage. Die Labels
und Presets stammen aus `pagePeriods.entities` und den gemeinsamen Period-Helpers.
`period` filtert den eigenen `created_at`-Zeitpunkt, nicht Änderungen oder Event-Termine.
Der bisherige `temporal`-Filter heißt jetzt **Terminlage** und bleibt auf Events,
Organisationen, Orte und Räume beschränkt. Beide Filter sind unabhängig und werden
serverseitig mit Suche, Status und Organisationskontext per AND kombiniert.

Ohne bewusste Zeitraumwahl bleiben Entity-Listen zunächst auf **Alle**; das globale
Default-Preset `24h` verkürzt die bisherigen Listen nicht automatisch. Es gilt:
**explizite URL > eigene gemerkte Entity-Auswahl > bewusst gewählte sharedPeriod > Alle**.
`sharedPeriodChosen` unterscheidet einen gewählten globalen Zeitraum vom Initialwert.
`entityPeriodsSet` unterscheidet unbesuchte/unbestimmte Entity-Auswahlen von bewusstem
Alle (`period: ''`). Normale Presets aus Dashboard, Activity, Statistics oder einer
Entity können daher bisher unbestimmte Entity-Seiten vorbelegen. Eine Entity mit eigener
Auswahl behält diese; deren Wiederherstellung überschreibt nicht den zuletzt global
gewählten Zeitraum. Explizite URL-Perioden und spätere Periodenwechsel aktualisieren
dagegen sowohl die Entity-Präferenz als auch `sharedPeriod`.

Alle und Reset löschen nur den Zeitraum der jeweiligen Entity, nicht sharedPeriod.
Alle wird ohne period-Parameter und mit `page=1` als vollständiger URL-Snapshot
serialisiert. Die bestehende `usePreferenceQuery`-Architektur bleibt unverändert;
Pagination, Reload und Browser-Navigation bewahren bzw. rekonstruieren den Filter.
Logout/resetAll löscht auch die beiden Auswahl-Metadaten. Alles bleibt ausschließlich
im request-/session-lokalen Pinia-Speicher; es gibt keine Browser-Persistenz.

EntitySearch erhält denselben period-Filter über den zentralen API-Client. Ein Wechsel
invalidiert noch laufende Antworten; keine lokale Datumsfilterung. ResultSummary zeigt
z. B. „Erstellt: Letzte 7 Tage · Terminlage: Mit bevorstehenden Terminen“.
Backend-Zeitgrenzen sind inklusive Anfang/exklusive Jetzt. Heute beginnt um Mitternacht
in `ADMIN_TIMEZONE` (Standard Europe/Berlin), die anderen Presets sind rollierende
UTC-Dauern. Source-Zeitstempel werden entsprechend `URANUS_TIMESTAMP_TIMEZONE`
interpretiert. Fehlende created_at-Werte sind bei Alle sichtbar, bei period ausgeschlossen.

## Event-Inhalte in Statistics

`/statistics` now offers the keyboard-accessible area buttons **Erstellung** and
**Event-Inhalte**. The latter uses `view=event-content`; existing creation links (including
custom ranges, intervals and comparisons) remain valid. Area switching reuses the page,
its query ownership and shared Pinia period preference. Each panel only loads its own API;
request generations prevent a late response from reviving an inactive panel.

Event content uses `GET /api/v1/statistics/events/content` through the central authenticated
API client/proxy with strict Zod contracts. Filters are Zeitraum (Alle, Heute, 24h, 7d,
30d, 90d), Status and Zeitraum vergleichen. Normal presets update sharedPeriod; All is a
local URL mode and never overwrites that preference. Status is URL-local and does not
change entity-list status preferences. An explicit URL wins; reload and Back/Forward
restore the active view and filters. If creation cannot represent Today, it uses its
24h fallback without overwriting the shared Today preference. Custom creation ranges
remain exclusive to Erstellung; switching to content uses the shared normal preset.

**The cohort is defined solely by event.created_at, not event/occurrence dates.**
Timezones, half-open boundaries and equal-duration predecessor semantics match the
backend period service. All has no predecessor; the compare switch is disabled and a
switch to All removes compare from the URL. Today compares an equal elapsed duration
immediately before midnight, not yesterday's complete calendar day.

Four KPIs show total created events plus category, genre and event-type coverage,
including explicit missing-event counts. Three instances of RankingBarChart render
horizontal bars with visible names/counts/event-share percentages and an accessible
ordered-list text alternative. Labels wrap on mobile, no information requires hovering,
and ranks have no dead drilldown links. Multi-assignment semantics are explicitly
explained: shares divide by all events and need not sum to 100%. Lookup languages never
multiply counts. Genres use composite type/genre identities and exclude the source's
no-genre sentinel 0. Coverage measures assignment presence, including unresolved IDs
with fallback labels, not validity against the taxonomy.

Comparison shows previous totals/coverage, actual previous ranks (including beyond the
old top ten), rank direction, count changes and percentage-point changes. New assignments
have no invented prior rank. Zero events show a clear empty state, zero coverage and empty
stable ranking panels. Loading clears old metrics; API failures stay within the panel
and offer retry. No persist plugin/browser storage, source writes or new public routes.

Follow-ups: read-only Event list facet filters for drilldown, full long-tail lists, exports,
category/genre/type matrices and individual genre timelines. These are deliberately absent
from v1. Browser tests use API fixtures; SQL behavior is tested separately on PostgreSQL.

## Benachrichtigungen

`/notifications` shows authenticated semantic notifications with status/type/organization/time
filters, active/queued/sent-today/failed counts, missing source capability and config errors.
Dry Run is an explicit banner. `/notifications/{id}` shows detection, resolution/expiry,
minimal payload, delivery history and DE/DA/EN HTML/Text previews. `/notifications/deliveries/{id}`
shows recipient PII, attempts, sanitized SMTP errors and contained notifications. All pages use
the existing auth layout, request state, list, empty and pagination components and typed Zod
contracts. GET never schedules/sends mail. Preview uses an opaque-origin sandbox iframe,
restrictive CSP and no v-html. Locale comes from the preview selection or source recipient,
not the admin browser. Source notification configuration cannot be edited here.

Notification HTML/Text previews display the actual external recipient email. CTAs use verified
normal Kulturbytes dashboard edit routes on the configured app origin, including parent-event
routing for dates/links. Missing or unsafe routes show DE/DA/EN text guidance without a link.
`internal_action_path` is separate from `external_action_url`; internal findings/event routes
must never be substituted into the preview. Organization contacts need not have system-admin
accounts.
