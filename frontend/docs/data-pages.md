# Gemeinsame Daten- und Arbeitsseiten

## Operations-Center-Foundations v2.1

Der [Design Guide v2.1](design-system.md) konsolidiert Dichte und Arbeitsflächen bei
unveränderten fünf Seitenmustern. `DataListShell dense` ist optional; fachliche Zeilen
und Pagination bleiben Sache der aufrufenden Komponente. `RecordSection surface="panel"`
mit Icon-/Actions-Slots ist das gemeinsame OperationsPanel-Pattern. Die technische
Schlusssektion aller sechs Record-Typen verwendet über `EntityTechnicalMetadata` jetzt
`TechnicalInfoBar`, weiterhin mit UUID, belegtem created_at und observed_at in Europe/Berlin.
Fehlende Quellzeitpunkte werden ausgelassen, Copy und `<time datetime>` bleiben erhalten.
Weitere Seiten erhalten technische Informationen nur aus verifizierten vorhandenen Daten.

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

| Kennzahl        | Fachliche Basis                                                              | Zeitbezug / Ziel                                                                           |
| --------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Neu eingegangen | `period_window` und tatsächliches `created_at` der neun Quelltabellen        | `[from_at,to_at)`; Activity mit gewähltem `period` und `entity_type`                       |
| Dringend        | Nicht behobene persistierte Findings mit Priorität ≤ 2 oder `published_soon` | Bestand; gesamte Arbeitsliste, **kein exakt reproduzierbarer Dringlichkeitsfilter**        |
| Datenqualität   | `persisted_counts`: alle Status außer `resolved`, inklusive Snooze/Ausnahmen | Bestand; echte Gesamtzahlen für Fehler, Warnungen und Hinweise                             |
| Offene Vorgänge | Eigene paginierte Queues                                                     | Bestand; Summary liefert keine Gesamtzahl, daher „Nicht verfügbar“ und Links zu den Queues |
| Prüfstatus      | Eigene Prüflaufhistorie                                                      | Summary liefert keinen aktuellen Status; Link zu den gespeicherten Prüfläufen              |

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

## Bisherige Collection-Konventionen

| Seite           | Umsetzung / fachliche Besonderheit                                                                                                                                                                                                                        |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/`             | Kompakter Zeitraum-Primärbereich vor Bestands-KPIs; serverseitig priorisierte Vorschau, begrenzte Regelvorschau, Vorgangszeilen und flache Schnellfilter                                                                                                  |
| `/activity`     | Referenzstil auf gemeinsame Header/Filter/Summary/Pagination/EmptyState umgestellt; Tagesgruppen, unknown timestamps, Bilder/Modal und Actions unverändert                                                                                                |
| `/findings`     | Kompakte Filter ohne zusätzliche Filterüberschrift; Gesamtzahl/Seitencounts; kompakte Rows mit Severity-, Entity- und Status-Badges, Details, Action und Markierungen; alle Filter und page_size bleiben                                                  |
| `/quality`      | Header, echte aggregierte ResultSummary mit Severity-Chips, vollständige Regelzeilen in DataListShell; keine Filter oder Pagination ohne API-Unterstützung                                                                                                |
| `/checks`       | Kompakte Historie mit Start/Ende, Regeln, Befunden und deutschen Status-Badges; gemeinsame Pagination                                                                                                                                                     |
| `/marks`        | Gemeinsame Filter, Summary, Badges, Rows und Pagination; Filter-Reset behält einen gezielt gewählten Datensatz bei                                                                                                                                        |
| `/marks/:id`    | Gemeinsamer Header und Badges; Bearbeitungsformular und chronologischer Audit-Verlauf bleiben absichtlich Detailansichten                                                                                                                                 |
| `/queues/:kind` | Gemeinsame Shell mit echten fachlichen Unterschieden: gerichtete Partneranfragen, Einladungsalter aus `invited_at`, Aktivierungsalter aus `created_at`; keine letzte Aktivität abgeleitet. URL-Filter werden bei Navigation ins Formular zurückgespiegelt |

Diese Tabelle beschreibt die frühere Collection-Vereinheitlichung, keinen vollständigen
aktuellen Frontend-Audit. Der vollständige [UI/UX-Audit](ui-ux-audit.md) erfasst alle Routen
und ihren Migrationsbedarf. Der [Design Guide v2](design-system.md) ist der kanonische
Gestaltungsvertrag mit fünf eigenständigen Seitenmustern. Login ist eine eigene Route;
geschützte Seiten zeigen keine zusätzliche Login-Leiste.

## Record Detail v2: alle sechs Entity-Detailtypen

`/events/:id` verwendet `EntityDetailPage` als Abruf-/Fehler-/Timeline-Shell mit den Slots
`header`, `content` und `after-timeline`. `EntityHero` integriert den gemeinsamen PageHeader
und zeigt den Record-Titel genau einmal. `EventDetailContent` ordnet primäre Fakten,
Beschreibung, verknüpfte Datensätze und Arbeitsstand.
`EntityTechnicalMetadata` folgt nach der unveränderten Timeline. Organisationen, Orte und
Räume, Benutzer und Bilder verwenden dieselben Shell-Slots mit eigenen Presentern.
Alle sechs Entity-Detailtypen sind migriert.

- `/organizations/:id`: Hero mit Logo und Stadt-Subtitle ohne eigenen Namen als
  Organisationskontext zu wiederholen. `facts.events`, `facts.venues`, `facts.memberships`
  werden als Veranstaltungen, Orte und Teammitgliedschaften gezeigt. Mitgliedschaften
  schließen Einladungen ein; keine Aussage über aktive Mitglieder. Danach Adresse/Standort.
- `/venues/:id`: Hero mit Organisation, optionaler öffentlicher Primary Action aus
  `public_url`; Raumzahl aus `facts.spaces`, danach vorhandene Adresse.
- `/spaces/:id`: Zugehöriger Ort aus `facts.venue_name` als Hauptkontext im Hero,
  Organisation darunter. Der Venue-Subtitle wird nicht dupliziert. Diese einzigen
  belegten Fakten brauchen keinen zweiten Faktenkasten. Nur eine gelieferte kanonische
  Ortsrelation erlaubt einen Link; sonst bleibt der Ortsname Text.

- `/users/:id` → **RECORD DETAIL v2**: kanonischer Servername, Avatar, Aktiv/Nicht aktiv,
  E-Mail/Username ohne identische Wiederholung im Hero. Benutzerinformationen (Kontostatus),
  Teamkontext mit `facts.memberships` **einschließlich Einladungen**, danach globale
  Beziehungen, Arbeitsstand, Timeline und Technik. Mitgliedsstatus ist Eingeladen/Beigetreten;
  Einladungszeit ist kein Join-Zeitpunkt. Kein Profil-/Auth-Vertrag wird erweitert.
- `/images/:id` → **RECORD DETAIL v2**: Hero und große sichere Vorschau, Bildinformationen
  mit `facts.image_links` und `facts.orphan` (Ja/Nein; null unbekannt), danach Beziehungen,
  Arbeitsstand, Timeline und Technik. Der UUID-Fallback bekommt keinen erfundenen Bildtitel.
  Die `record`-Variante von ActivityThumbnail teilt URL-Validierung und AppModal,
  reserviert Vorschauhöhe und erhält das Bildverhältnis. Fehler entfernen das defekte Bild
  und zeigen „Bildvorschau konnte nicht geladen werden.“ Keine Retry-/Provider-Schleife.

Alle sechs Presenter verwenden `RecordRelations` und `RecordWorkflowSummary`. Null-Zähler
sind unbekannt, 0 bleibt 0. Der Hero-`context`-Slot ersetzt ausschließlich Kontext;
der Event-Default bleibt erhalten. `RecordLocation` verwendet vorhandene Adresse und
`activityMapUrl` für eine optional gelieferte gültige Location. Der aktuelle Backend-Preview
liefert Koordinaten nur für Organisationen, nicht für Orte. Keine neue Karte, Geocodierung,
Kontaktfelder oder Markdown-Felder. Organisation/Ort/Raum bleiben Plaintext.

`facts.description` stammt unverändert aus `event.description`. Der Markdown-Vertrag ist
im Quell-Editor nachgewiesen (Commit/Dateien im Audit), nicht aus dem Text erraten.
`MarkdownContent` verwendet markdown-it als Tokenparser und einen geschlossenen Vue-Renderer:
kein v-html, kein Raw-HTML, keine Bilder/Plugins. Links erlauben nur validiertes http/https,
einfache mailto-Adressen. Alle relativen Admin-Links (auch Record-, Query- und Fragmentlinks)
bleiben Text; Source-Inhalte bestimmen keine interne Workflow-Navigation. Sonstige unsichere
Links bleiben ebenfalls Text;
externe Links haben neuen Tab, noopener/noreferrer und no-referrer. Große Texte über
100.000 Zeichen bleiben vollständig als Plaintext erhalten. `.prose-admin` begrenzt auf 72ch.
Softbreak wird als Leerzeichen gerendert, Hardbreak als `<br>`; Leerzeilen trennen Absätze.

Der serverseitige Subtitle einschließlich eines ggf. nächsten Termins bleibt unverändert.
Kein Datum wird aus einer paginierten Relation abgeleitet. Standardort/-raum bleiben
Standardwerte, nicht Behauptungen über jeden Termin. Veranstalter im Hero, diese Standardwerte
und die Termin-Gesamtzahl sind unabhängig von der Relationspagination verfügbar.

„Verknüpfte Datensätze“ bleibt bewusst eine allgemeine Liste: maximal 25 Einträge pro Seite,
Sortierung nach Typ/Name/Schlüssel, keine chronologische Terminliste. Seitenumfang und
Gesamtzahl sind sichtbar; gemeinsame Pagination erhält weitere Query-Parameter. Bei 30
Terminen liegen Medien und weitere Beziehungen gegebenenfalls erst auf Seite 2. Das gilt genauso für Organisationen, Orte und Räume: eine Organisation mit 26 Veranstaltungen
kann ihre Orts-/Teamrelation erst auf Seite 2 zeigen. Die sichtbare
Seite ist kein vollständiger fachlicher Abschnitt; fehlende Elemente sind nicht nachweislich
abwesend. Typisierte Termin-/Veranstalter-/Orts-/Medienbereiche benötigen einen Folge-PR mit
unabhängigen begrenzten Abfragen, Counts und eigener Termin-/Medienpagination. Der Pilot
ändert den Backend-Vertrag nicht. Qualitätszähler schließen behobene Befunde aus,
Markierungszahlen schließen erledigte Markierungen ein; null ist nicht verfügbar.

Bei Refresh derselben Identität bleibt der letzte erfolgreiche Detailstand mit Lade-/Fehlerhinweis
sichtbar. Beim Identitätswechsel sowie bei 401/403/404 wird er verworfen; Generation-Guards und Layout-Auth-Cleanup
bleiben erhalten. Keine API-/Backend-/Quellschreibänderung, keine neuen Remote-Requests.

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

Entity-Details verwenden `EntityTimeline` für die vom Backend zusammengeführte Chronologie.
Sie sortiert oder kombiniert keine separaten Client-APIs. „Mehr laden“ folgt dem opaken Cursor;
bereits geladene IDs werden defensiv nicht dupliziert. Titel, Summary und Actor werden als Text
gerendert, und nur Zod-validierte interne Finding-, Mark-, Notification-, Geocoding- und
Queue-Ziele werden verlinkt.

## Admin Inbox und Zuständigkeiten

`/inbox` folgt demselben PageHeader/FilterBar/RequestState/ResultSummary/DataListShell/
PaginationBar-Aufbau wie andere wachsende Datenlisten. `scope`, `attention`, `kind`,
`entity_type`, `page` und `page_size` kommen ausschließlich aus der validierten URL. Browser-
History und explizite Deep Links bleiben damit maßgeblich; ungültige oder mehrfach gelieferte
Werte werden nicht stillschweigend übernommen.

Die Kennzahlen sind serverseitige Gesamtzahlen über die deduplizierte aktive Inbox. Ein Finding
mit aktivem Assignment erscheint nur als Assignment-Zeile. „Meine“ verwendet die unabhängige
Admin-Konto-ID; der Development-Principal besitzt keine persönliche Inbox. Fälligkeit wird in
Europe/Berlin angezeigt, und die Datumsauswahl wird DST-sicher auf das Ende des Berliner
Kalendertags abgebildet.

`AssignmentEditor` wird im Finding-Detail geladen und ruft Admin-Auswahl und aktuelle
Zuständigkeit gemeinsam ab. Create/Patch senden ausschließlich den Zod-validierten Taskzustand;
Actor, Zeitstempel, Versionserhöhung und Verlauf kommen vom Server. Ein 409-Konflikt fordert zum
Neuladen auf und überschreibt keine zwischenzeitliche Änderung. Das ältere Finding-Review-Feld
für eine Uranus-User-ID ist keine Admin-Zuständigkeit und wird vom Editor nicht verwendet.

### Wiedervorlagen

Der Attention-Filter und ResultSummary ergänzen „Wiedervorlagen“. Die bisherigen Counts
beziehen sich auf aktive Aufgaben; der neue Count auf alle aktiv zurückgestellten Tasks,
serverseitig dedupliziert und unabhängig von der Seite. Die Wiedervorlagen-Ansicht zeigt den
effektiven absoluten Zeitpunkt samt Admin-Zeitzone, nächster Zeitpunkt zuerst.

`AssignmentSnooze` ergänzt den gemeinsamen `AssignmentEditor` und zugewiesene Inbox-Zeilen.
Es verwendet `AppModal`, große Preset-Touchflächen und ein natives Datum-/Zeitfeld.
„Morgen“, „In 3 Tagen“, „Nächste Woche“ bedeuten +1/+3/+7 lokale Kalendertage um 09:00 Uhr
in der serverseitig gelieferten `admin_timezone`; eigene Zeiten verwenden dieselbe Zone.
DST-Lücken werden abgewiesen, doppelte Herbst-Minuten verwenden das erste Vorkommen.
PATCH sendet nur Version und UTC-Zeitpunkt bzw. null. Konflikte erfordern Neuladen und eine
neue Entscheidung; keine automatische Wiederholung mit einer neueren Version.

Finding-Snooze gehört weiterhin zum fachlichen Review. Assignment-Snooze ist organisatorisch
und verändert ihn nicht. Beide können denselben Task ausblenden; der spätere aktive Zeitpunkt
bestimmt dessen Rückkehr. Die Inbox kennzeichnet einen fachlichen Finding-Snooze gesondert
und verlinkt zu dessen Review. Aufheben der organisatorischen Wiedervorlage lässt ihn bestehen.
Ablauf wird bei der nächsten Inbox-Abfrage berücksichtigt, ohne automatische Statusmutation.

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

| rule                   | entity             | severity | Bedeutung                                              |
| ---------------------- | ------------------ | -------- | ------------------------------------------------------ |
| postal_code_whitespace | organization/venue | warning  | Führende oder abschließende Whitespaces in postal_code |

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
sowie AppIcon und die vorhandenen `entityTypes`; Graph behält seinen eigenen Root-Contract.
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

| Bereich                                | Gemerkte Werte                                            |
| -------------------------------------- | --------------------------------------------------------- |
| `sharedPeriod`                         | `today`, `24h`, `7d`, `30d`, `90d`                        |
| `entities.events`                      | `q`, Event-`status`, `temporal`, `period`                 |
| `entities.users`                       | `q`, User-`status`, `period`                              |
| `entities.organizations/venues/spaces` | `q`, `temporal`, `period`                                 |
| `entities.images`                      | `q`, `period`                                             |
| `activity`                             | Objektart und zuletzt explizit gewähltes normales Preset  |
| `statistics`                           | normales Preset, Intervall, Vergleich, ausgewählte Serien |
| `graph`                                | Entitätstyp, Beziehungstyp, Suchorganisation, Tiefe       |

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

### E-Mail-Versände and manual retry

`/notifications/deliveries` lists authenticated email audit records with exact status,
organization UUID, kind, period and pagination filters in the URL. Separate temporary and
permanent failure KPIs on `/notifications` link to their exact filters. The outstanding KPI
counts queued plus sending; the list offers both statuses separately. Recipient addresses
remain protected by the system-admin boundary and private/no-store responses.

`/notifications/deliveries/{id}` explains sanitized SMTP codes, shows scheduled automatic
attempts for temporary failures, and offers a confirmation dialog only for a permanent
failure with no non-cancelled successor. “Erneut versuchen” creates a **new queued delivery**,
then navigates to it. Pending requests disable repeat clicks. Parent/successor links preserve
the audit chain; local safe error text explains obsolete intent, state conflicts and existing
attempts. The bodyless typed POST uses the existing CSRF/Origin-protected proxy and cannot
override recipients or message content. It performs no SMTP; the normal worker processes
the request subject to current eligibility, the feature flag and daily limits.

## Global Geo Scope (phase 1)

The header's Gebiet selector sets a session-only work area alongside the shared period.
Events, Venues, Spaces and Organizations lists and autocomplete support `geo_scope_id`;
URL wins over memory, then no scope. Reload resolves cached metadata before the list
loads. Local filter reset preserves the area; global area reset preserves other filters
and returns to page 1. Logout/session loss/new login resets it. No browser persistence.

Users/images remain global and say so visibly when a scope is selected. They do not
send a geo filter. Phase 2 extends Activity/Findings/Dashboard/Statistics/Graph as
described below. Scope memory survives navigation back to supported views. Details remain accessible outside the scope.
Unlocated records (NULL/EMPTY authoritative points) are excluded from scoped lists.

See [backend Geo Scope](../../backend/docs/geo-scope.md) for the API matrix, exact event
and temporal semantics, provider limits/coverage, deployment and concrete follow-up PRs.

## Global Geo Scope: Phase 2

The shared session scope now also applies to `/activity`, `/findings`, `/`,
`/statistics` (both views) and `/graph` root discovery. Every supported page carries
`geo_scope_id` in its URL. URL takes precedence over the session store; period and
geo remain independent. Local resets preserve geo; global clear resets list pagination
and cursor without adding `page` to Dashboard, Statistics or Graph URLs. Logout and
session loss clear the session preferences.

- Activity excludes nonspatial types and hides their filter choices.
- Findings show only spatially matching affected entities; unlocated/technical findings
  are excluded. Counts and pagination reflect that population in persisted and live mode.
- Dashboard splits new-record totals and labels metrics **Gebiet** / **Systemweit**.
  Quality counts are scoped; check status and workflow queues remain systemwide.
- Statistics label each series; users, partner requests and invitations remain systemwide.
  Recent records are spatial only. Event-content rankings/shares use the scoped denominator.
- Graph search excludes nonspatial roots, while direct roots and relationship traversal
  remain complete. The traversal API never receives geo_scope_id.

All of these requests use cached areas; they work without Nominatim availability.
Details and global users/images/notification/settings views remain outside the filter.
The scope is a work context, never authorization. Phase 3 adds the systemwide `/geocoding` workflow described below.

## Location suggestions

`/geocoding` is a systemwide operations queue with entity/status filters, URL-driven
pagination, server-wide stored status counts, current source addresses and best candidates.
Missing positions cannot establish authoritative Geo Scope membership. This page and
`/geocoding/{uuid}` never send geo_scope_id; the header explains the global view while
retaining the session scope for supported pages. Stored filters/counts reflect the last
worker observation; changed source rows are displayed stale on revalidation.

Missing-location findings receive a batch-enriched request UUID and link to the detail
page. There is no geocode request per finding row. The detail page presents the current source
entity first, using the verified `source_address` as one value rather than parsing address parts
in the browser. Technical request states have German workflow labels.

`LocationSuggestion` renders up to five escaped candidates in a shared map/comparison surface with rank,
coordinates, **Adressübereinstimmung**, fixed localized reasons and constructed OpenStreetMap
links. The best stored candidate is labelled “Bester automatischer Treffer”, never as correct or
safe. A client-only Leaflet map loads the configured OSM-based XYZ raster tiles and
fits all returned positions, with a street-level zoom for a single candidate. The default is
OSMF’s public OpenStreetMap Standard service; no own tile server or API key is needed. Numbered 44px marker
buttons and list actions share one selection; a marker focuses the corresponding candidate row.
“Alle Kandidaten zeigen” restores the full comparison. The list remains the complete keyboard/
screenreader alternative, including when configuration, CSP, network or map loading fails.
OSM and configured provider attribution remain visible. The map never calls Nominatim, invents
source coordinates or offers a write action. Only numeric XYZ coordinates reach the approved tile
provider; no entity names or emails enter tile URLs. Browser caching and an origin-only Referrer
follow the OSM tile policy. No prefetch, offline downloads, provider failover or retry loop exists.
An explicitly empty tile URL disables the map. Configuration, privacy and the exact CSP origin are documented in the
[frontend README](../README.md#geocoding-karte-konfigurieren).
Low-score single candidates may also be ambiguous. Provider importance is not confidence.

“Standort erneut prüfen” sends an authenticated, bodyless CSRF-protected POST and shows
pending state. Double submissions and stale responses are guarded; the worker performs
network work later. No client address, provider or coordinate override exists. No acceptance
button exists: even a perfect match is a suggestion, never the authoritative Uranus point.
Assignment loading failure and an empty assignable-admin roster appear as distinct concise
alerts. Retry confirmation uses the shared success alert; pending/checking requests offer only
“Prüfstand aktualisieren”.

### Standortprüfung: Workflow v2

`/geocoding/:id` folgt Quelle → Evidenz/Vergleich → Bearbeitung → weitere Aktionen →
technische Informationen. Die kompakte Quelle zeigt den Namen einmal, Objektart,
Quelladresse, kurzen Prüfstatus und kanonische Aktionen. Generation und Prüfversuche
gehören ausschließlich in die Schlusssektion, ebenso die vorhandene Request-ID.
`checked_at` erscheint als Workflow-Meta und technisch; kein `observed_at` wird erfunden.

Karte und Kandidaten bilden eine gemeinsame Fläche. Ein Treffer erhält eine kompakte
Zusammenfassung ohne redundante Kartenaktion, mehrere ab xl eine Vergleichsspalte.
Auf kleineren Viewports folgen Kandidaten unter der Karte. Die Auswahl nennt „Ausgewählt“;
Marker/Listenfokus, 44px-Aktionen, OSM-Attribution und Kartenfehleralternative bleiben erhalten.
Nur gelieferte Match-Gründe werden dargestellt. Die Quelladresse ist kein strukturiertes
Adressobjekt; `display_name` wird niemals für einen Feldvergleich zerlegt.

Bearbeitung bettet den gemeinsamen AssignmentEditor ohne konkurrierenden h2/Panel ein.
Sein kompakter Fehler unterbricht den Vergleich nicht und bietet einen eigenen Retry.
„Standort erneut prüfen“ bleibt eine sekundäre enqueue-only-Aktion. Erfolg entfernt alte
Kandidaten und zeigt pending; kein automatischer Wiederholungszyklus. Beim bloßen Refresh
bleibt dagegen derselbe erfolgreiche Stand sichtbar. Andere ID sowie 401/403/404 verwerfen
ihn; sonstige Fehler kennzeichnen stale Daten, Generation-Guards verwerfen späte Antworten.
API, Auth, Source-Read-only und Provider-/CSP-Konfiguration bleiben unverändert.

### Quality Rules v2

Die bestehenden Rule-Drilldowns akzeptieren alle neuen IDs ohne Contract-Erweiterung.
Deutsche Labels und Severity stehen in `app/utils/quality.ts`; die Gruppe „Interne
Sicherheit“ trennt die Einladungstoken-Integrität von Veranstaltungs-/Adressqualität.
Die Mitgliedschaft verweist auf ihre bekannte Organisation, nicht auf eine erfundene
Detailroute. Tokenwerte werden nie geliefert oder angezeigt. Preis-/Kapazitätsgründe
erscheinen als verständliche Backend-Meldung; es gibt keine rohe Metadata-JSON-Ansicht.

Der [Regelkatalog](../../backend/docs/quality-rules.md) dokumentiert DDL-Evidenz,
Severity, interne Notification-Policy, Geo-Verhalten und zurückgestellte Kandidaten.
Die Dashboard-Gesamtzahl bleibt ein Qualitäts-/Workflow-Bestand; Maintenance-Diagnosen
für Social Posts und Passwort-Reset-Retention sind darin bewusst nicht neu enthalten.

## Uranus user presentation

Canonical Uranus user display label is: display_name → username → email → UUID.
Blank strings count as missing. The backend supplies `entity_name`, `label` and
`user_name`; Vue renders these without recomputing identity fallbacks. This applies
to Activity, memberships, queues, graph nodes/search, entity lists/details/relations
and Inbox context. Search subtitles omit identity values already used as the label.
UUIDs remain available as technical details and copy targets. Email labels stay
inside authenticated admin views, never public links or metadata. Independent
admin accounts and timeline actor subjects retain their own identity semantics.

## Globale Suche und kontextbezogene Suche

`GlobalSearchPalette` ergänzt jede geschützte Seite mit Ctrl+K / Cmd+K und einem sichtbaren
Suchtrigger im Header. `adminNavigationItems` in `utils/navigation.ts` ist die gemeinsame
Quelle für Sidebar und lokale Palette-Ziele, einschließlich Datenqualität und
Standortvorschlägen. „Dashboard“ ist auch als Suchbegriff für „Übersicht“ verfügbar.
Leere Suche zeigt ausschließlich Navigation; passende lokale Ziele stehen vor den
Entity-Gruppen. Ab zwei Zeichen folgt `/api/v1/search` nach 250ms Debounce, maximal
fünf Ergebnisse je Typ standardmäßig (API maximal zehn, 60 insgesamt).

Eingabe (`query`), gestartete Remote-Suche (`debouncedQuery`) und sichtbarer erfolgreicher
Stand (`groups` mit `resultQuery`) sind getrennt. Navigation reagiert sofort auf Eingaben;
Remote-Treffer bleiben während Debounce, laufender Anfrage und Fehlern sichtbar. Der Kopf
benennt ihren Suchbegriff ausdrücklich. Nur eine gültige erfolgreiche Antwort ersetzt den
Stand, auch wenn sie leer ist. Unter zwei getrimmten Zeichen wird Remote-State geleert.
Abbruch invalidiert nur Timer/Request, nicht die letzte erfolgreiche Antwort.
Die Auswahl folgt beim lokalen Filtern der Identität des sichtbaren Eintrags, statt bei
jedem Zeichen zurückzuspringen; eine neue erfolgreiche Antwort wählt den ersten Eintrag.
Nur Pfeiltasten scrollen zur Auswahl; Antwortwechsel setzen den Ergebnisbereich nach oben.

Die Suche ist ausdrücklich systemweit und ignoriert Gebiet/Zeitraum. `EntitySearch`
bleibt die kontextbezogene Suchoberfläche mit ihren Listenfiltern und Enter zum Anwenden.
Beide sowie Graph-Root-Suche teilen Backend-Felder, Literal-ILIKE, Presentation und
Ranking: exakte UUID → exaktes Feld → Präfix → Teilstring → Label → Schlüssel.
Die paginierte Liste behält ihre alphabetische Ordnung. Graph behält Organisations-/
Geo-Filter, seine eigenen Knoten und die zusätzliche graph-only Terminsuche.

[Canonical Search Fields und API-Contract](../../backend/docs/contracts.md#contextual-entity-search)
listen alle User-/Organisations-/Adress-/Raum-/Event-/Bildfelder. User sind über volle
oder partielle E-Mail auffindbar. Labels folgen display_name → username → email → UUID.
Action.href kommt vom Backend; Zod prüft Typ, Identität, Gruppenlimits und Linkziel.
Es gibt weder öffentliche Suche noch zusätzliche Secret-/Auth-/Workflow-Suchfelder.

Suchtext, Treffer und Auswahl leben nur in der Komponente. Neue Eingaben brechen
Requests ab; Generationsprüfungen verhindern auch verspätete erfolgreiche/fehlgeschlagene
Antworten. Schließen, Navigation, Logout und Session-Verlust leeren die Palette.
Keine Speicherung in Pinia-Präferenzen, localStorage, sessionStorage, IndexedDB oder
Cookies; kein Verlauf, keine Analytics und keine Logs von Suchtext oder Trefferwerten.

## Status von Teammitgliedschaften

`/queues/team_invitations` zeigt standardmäßig „Eingeladen“. Der Statusselector bietet
„Eingeladen“, „Beigetreten“ und „Alle“; Anwenden schreibt
`membership_status=invited|joined|all` in die URL und setzt die Seite auf 1 zurück.
Reload sowie Zurück/Vorwärts übernehmen die URL. Keine persistente Speicherung.

Ein direkter `entity_key=membership:<org_uuid>:<user_uuid>` öffnet auch beigetretene
Mitgliedschaften aus der Benutzer-Timeline. Status-, Organisations- und Altersfilter sind
dabei deaktiviert und werden serverseitig nicht angewendet. Ein Hinweis erklärt den
Direktaufruf; „Filter zurücksetzen“ kehrt zur offenen Einladungsliste zurück.
StatusBadge zeigt den aktuellen Status, das Einladungsdatum bleibt die Altersbasis und
wird niemals als Beitrittsdatum ausgegeben. Counts und Pagination kommen vom Backend.
Eine spätere Umbenennung in „Teammitgliedschaften“ bleibt eine separate Produktentscheidung.
