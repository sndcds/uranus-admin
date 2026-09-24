# Kulturbytes Admin Design System v2.1

## Admin Operations Center

Kanonischer UI-Vertrag für neue und migrierte Oberflächen. Version 2.1 folgt dem
Operations-Center-Mockup: dunkles Navy, Fuchsia-Akzente, kompakte Überschriften,
klare Panelgrenzen und horizontale technische Metadaten.

**Stand dieser Phase:** gemeinsame Foundations und Shell sowie Dashboard `/` als
Referenz für **Overview v2.1 / Operations Center**. Die fachlichen Datenverträge
bleiben erhalten; weitere Routen benötigen separate Migrationen. [Review-Aufnahmen und offene Anpassungen](screenshots/operations-foundations/README.md).
Die bisherigen v2-Verträge unten gelten weiter, sofern die neuen Dichte-/Surface-Regeln
sie nicht ausdrücklich ersetzen. Beispiele sind keine neuen API-Felder. Grundlage ist der
[vollständige Frontend-Audit](ui-ux-audit.md) gegen `main` bei `4560304` (initialer Audit: `e615df3`).
Alle sechs Entity-Detailtypen verwenden Record Detail v2; Geocoding verwendet Workflow v2.
Bestehende Seiten sind nicht allein durch diese Dokumentation bereits migriert.
Fachliche Datenverträge: [Datenansichten](data-pages.md), [Aktivität](activity-stream.md),
[Statistiken](statistics.md), [Graph](entity-relationship-graph.md), [SQL](sql-editor.md).

## 1. Prinzipien

Aufgabe vor Dekoration. Erkennen → Einordnen → Handeln → Belege prüfen.
Eine lesende Datensatzansicht ist kein Bearbeitungsformular. Admin-Workflowänderungen
sind keine Uranus-Schreibrechte. Fehlende Daten bleiben unbekannt.

Fünf Muster sind gleichberechtigt: Overview, Collection, Record Detail, Workflow,
Workspace. **Activity ist die Referenz für kompakte Listenzeilen, nicht für Record
Details.** Domain-Inhalt bestimmt die Gliederung; gemeinsame Primitive bestimmen
Abstände, Typografie, Fokus, Fehler und Aktionen. Routing, Navigation und Zugangsregeln der Shell bleiben bestehen.

## 2. Sprache und Terminologie

Die normale Oberfläche ist Deutsch, sachlich, kurz und handlungsorientiert. Technische
Eigennamen bleiben SQL, API, UUID, HTTP, JSON, PostgreSQL, PostGIS, OpenStreetMap.
Quellinhalt, SQL-Bezeichner, URLs und API-Keys werden niemals zur Übersetzung verändert.

| Ausgangsbegriff           | Verbindlicher UI-Begriff                                     |
| ------------------------- | ------------------------------------------------------------ |
| Dashboard / Overview      | Übersicht                                                    |
| Activity                  | Aktivität                                                    |
| Event / Events            | Veranstaltung / Veranstaltungen                              |
| Event date                | Termin                                                       |
| Entity                    | Datensatz; bei Typauswahl Objektart                          |
| Finding                   | Befund                                                       |
| Review                    | Bewertung; fachlich genauer Befundbewertung                  |
| Inbox                     | Aufgabenübersicht                                            |
| Assignment                | Zuständigkeit / zugewiesene Aufgabe                          |
| Snooze                    | Wiedervorlage (Assignment); Zurückstellung (Befundbewertung) |
| SQL Console / SQL Editor  | SQL-Konsole / SQL-Editor                                     |
| Datasource / Query Source | Datenquelle / Abfragequelle                                  |
| Mode / Scope / Connection | Modus / Bereich / Verbindung                                 |
| READ ONLY                 | Nur Lesen                                                    |
| Event-Inhalte             | Veranstaltungsinhalte                                        |
| Source schema / Dry Run   | Quellschema / Testbetrieb ohne Versand                       |
| Apply / Reset             | Anwenden / Filter zurücksetzen                               |
| Page size                 | Einträge pro Seite                                           |

Zentrale Typ-/Statuslabels bleiben in `utils/entityPresentation.ts`, `entities.ts`,
`presentation.ts`, `marks.ts`, `notifications.ts`, `geocoding.ts`. Keine zweite
Statusmap pro Route. Bekannte Werte übersetzen; unbekannte als unbekannt kennzeichnen
und Originalcode bei Bedarf technisch zugänglich halten. Backend-Timeline-Titel und
serverseitige Subtitles sind Evidenztexte, keine frei umzuschreibenden UI-Labels.
Die verbleibenden Sprachabweichungen sind im Audit mit Fundstellen geplant.

## 3. Informationsarchitektur

Die Shell bietet Navigation, globale Suche, Gebiet, Sitzung und deaktiviertes Anlegen.
Eine Seitenaktion gehört in den Seitenkontext, nicht in die globale Shell. Zur Liste
führt zur fachlichen Collection. Root-Suche im Graph ist kein globaler Gebietsfilter.

Geschütztes Layout: Skiplink → App-Navigation → Shell-Header (h1) → `main` →
PageHeader (h2; Slots `leading`, `badge`, `context`, `actions`, Default als Actions-Fallback) → Abschnitte (h3) → Datensatzzeilen (h4 in Abschnittslisten).
Login besitzt ein eigenes h1. Dialoge haben eigene benannte Überschriften.
Kein zweites `main` im Workspace. Keine Überschrift nur wegen ihrer Schriftgröße wählen.

## 4. Seitenmuster

| Muster        | Hauptaufgabe              | Reihenfolge                                                             | Referenz / Ziel                      |
| ------------- | ------------------------- | ----------------------------------------------------------------------- | ------------------------------------ |
| Overview      | Prioritäten erkennen      | Kontext → wichtigste Kennzahlen → Arbeit → Vertiefung                   | Übersicht / Datenqualität            |
| Collection    | Finden und vergleichen    | Header → Filter → Summary → Liste → Pagination                          | Activity-Zeilen, EntityListPage      |
| Record Detail | Einen Datensatz verstehen | Identität → Fachinhalt → Beziehungen → Arbeitsstand → Verlauf → Technik | Veranstaltungsdetail v2              |
| Workflow      | Einen Fall bearbeiten     | Kontext → Evidenz → Entscheidung/Zuständigkeit → Historie               | Befunde, Standortprüfung, Versand    |
| Workspace     | Interaktiv analysieren    | Kontext/Controls → Arbeitsfläche → Inspektion/Ergebnis                  | Graph, SQL, Statistiken, Suchpalette |

Ein Muster ist keine starre Vorlage für alle Domänen. Workflows dürfen eine Collection
enthalten; eine Statistik bleibt ein Workspace mit Tabellenalternative.

### Overview v2.1 — Dashboard als Referenz

Die Dashboard-Migration basiert auf `main` bei `76016593bfde39d5aada821f2e0afd9f14eba63a`
(nach PR #109). Visuelle Referenz ist der Dashboard-Entwurf „Operations Center“:

- Kompakter PageHeader mit Zeitraum und einer primären Aktualisierungsaktion.
- Neun kleine Neuanlagen-Tiles, bis zu fünf Spalten am Desktop, drei am Tablet,
  zwei mobil (ohne dekorative Icons auf den kleinsten Viewports). Zeitraum und Gebietsbezug stehen als Metadaten am Abschnitt.
- Vier gleichwertige Aufmerksamkeit-KPIs verwenden `KpiCard compact`, einschließlich
  Prüfstatus. „3 Arbeitslisten“ bezeichnet Navigation, keine Summe offener Vorgänge.
- Hauptbereich ab `xl` im Verhältnis 1.7:0.8: priorisierte Arbeitsliste links,
  Datenqualität und offene Vorgänge rechts. Darunter einspaltiger Lesefluss.
- `FindingsList compact` verwendet eine semantische Tabelle mit vier Befunden,
  Priorität, Titel/Evidenz, Typ/Status, Quelle/Feld/Beobachtungszeit und Aktionen.
  Unter 640px werden beschriftete Zellen gestapelt. Zeilenaktionen sind „Im Admin ansehen“
  und bei verfügbarer Diagnose „SQL Editor“. Nur die SQL-Aktion öffnet ein Modal.
- `QualityOverview compact` zeigt fünf Regeln nach vorhandener Anzahl absteigend;
  bei Gleichstand bleibt die bestehende Reihenfolge erhalten. Fehlende Counts bleiben
  unbekannt und folgen vorhandenen Zahlen. Die normale Qualitätsseite bleibt unverändert.
- Drei kompakte Queue-Links ohne erfundene Counts; native `details` für standardmäßig
  geschlossene erweiterte Filter. Filter navigieren weiterhin mit `active_only` zur Arbeitsliste.
- `TechnicalInfoBar` nennt den **letzten erfolgreichen Abruf** ausdrücklich als
  Client-Abrufzeit. Zeitraum, Admin-Zeitzone, Qualitätsmodus, belegte Prüfläufe und
  vorhandener Geo Scope werden aus bestehenden Daten abgeleitet. Keine API-Version,
  Datenbankverbindung oder Systemgesundheit ohne entsprechenden Vertrag.

Die kompakte Darstellung lädt keine zusätzlichen Befunde und verändert weder Stores
noch API-, Auth- oder Domain-Semantik. Leere Ergebnisse verwenden `EmptyState compact`;
vorhandene Stale-/Fehlerzustände bleiben sichtbar. Formularcontrols behalten 44px
Mindesthöhe; die dichten Befundaktionen folgen der unten beschriebenen Workflow-Variante. [Synthetische Review-Screenshots](screenshots/operations-dashboard/README.md).

### Operations Workflow v2.1 — Inbox, Befunde und Markierungen

Regelbezeichnungen stammen zentral aus `app/utils/quality.ts`. Filter, Befundlisten,
Qualitätsübersicht, Warteschlangen und SQL-Regelinformationen zeigen deutsche Labels.
Slugs bleiben technische Werte in URLs und API-Anfragen; unbekannte Regeln erscheinen
als „Unbekannte Prüfregel“, ohne den ausgewählten Filterwert zu verändern.

Migration auf Basis von `b2a93f08bfeb5681782e9f2cca36ae30b0e39b0f` (main nach PR #111).
Die vier Routen `/inbox`, `/findings`, `/marks` und `/marks/:id` verwenden die vorhandenen
Operations-Surfaces. Die Bereiche behalten unterschiedliche Aufgaben:

- **Inbox:** aktuelle Aufmerksamkeit und operative Zuständigkeit. Sechs kompakte
  Count-Buttons vor den Filtern zeigen die globalen, serverseitig deduplizierten Counts.
  Die Buttons ändern jeweils `scope` oder `attention`, erhalten weitere URL-Filter und
  setzen die Seite zurück. Erneutes Betätigen hebt diese Auswahl auf. Auswahlzustand
  kommt ausschließlich aus der URL (`aria-pressed`); die globalen Zahlen sind keine
  Vorschau der Schnittmenge mit anderen Filtern.
- **Arbeitsliste — Operations Workspace v2.1:** `FindingsList compact workspace`
  zeigt **Prio → Datensatz → Befund → Status → Aktionen**. P1–P6 stehen links in dunklen
  Badges, ohne neue Bewertungslogik. Datensatzname/Bild/Organisation und deutsche Regel/
  zusätzliche Evidenz sind getrennt. Stärkere Divider, Hover und Focus-within führen durch
  weiße Zeilen. Oberhalb von 1100px hält ein lokaler vertikaler Scrollbereich (max. 68dvh)
  den Tabellenkopf bei `top: 0`; er konkurriert nicht mit dem umbrechenden App-Header.
  Bis 1100px folgt eine Grid-Zeile, unter 640px eine gestapelte Darstellung ohne horizontales
  Scrollen. Primäraktion ist „Befund bearbeiten“, SQL bleibt bei vorhandener Capability
  direkt erreichbar. Controls sind mindestens 44px hoch. Weitere Werkzeuge stehen im Detail.
  Die kompakte Filterfläche erhält alle Queryparameter; die Ergebnisübersicht steht direkt
  an der Tabelle und benennt Severity-Zahlen ausdrücklich **auf dieser Seite**.
  Die Dashboard-Variante bleibt unabhängig von diesem Workspace-Aufbau.
- **Markierungen:** manuelle Anliegen, Gründe und Notizen. Dichte, responsive Listenzeilen
  zeigen Ersteller und vorhandenen Abschluss; diese Angaben sind keine Zuständigkeit.
  Der Datensatzkontext ist ein Operations-Panel, Anlegen standardmäßig geschlossen.
  Reset erhält `entity_type`/`entity_key`. Das Detail ordnet Identität → Markierungsstatus
  und Gründe → Bearbeitung → unveränderten Notizverlauf → Technik.

`FilterBar compact` verwendet 12px Innenabstand und 12px Radius, weiterhin 44px Controls,
vier Filterspalten am großen Desktop und zwei am Tablet. Der optionale `actions`-Slot
bündelt Anwenden/Reset. `FilterForm compact` erhält alle Filter einschließlich Quelle,
Reviewstatus, Organisations-UUID und der vorhandenen Entity-/Geo-Queryparameter.
Kein neuer Filterstore, keine Browserpersistenz. Standardvarianten bleiben kompatibel.

**Finding Detail — Workflow v2.1:** Ein breiter nativer `AppModal wide workspace` ordnet
Identität → Evidenz → Priorisierung → fachliche Bewertung → Zuständigkeit → Werkzeuge →
Technik. Evidenz und Priorisierung stehen auf Desktop nebeneinander. Review und operative
Zuständigkeit bleiben getrennte Panels; `AssignmentEditor embedded` verwendet seinen
bestehenden Vertrag einschließlich eigenständiger Wiedervorlage. Reviewstatus, Kommentar,
Ausnahmegrund und fachliche Zurückstellung verwenden die vorhandene Review-API. Der
Datumsinput nennt Europe/Berlin, verwirft ungültige lokale Zeiten und erhält vorhandene
Snooze-Instants ohne erneute Interpretation. Späte Speicherantworten nach Schließen werden
verworfen; nach erfolgreichem Review lädt die Liste beim Schließen neu.

Der gelieferte **Modus** bestimmt die Bearbeitbarkeit, nicht `first_seen_at`: fehlender
Erstfund bleibt unbekannt. Live zeigt Evidenz/Tools, aber keine Review- oder Assignment-Aktion.
Behobene gespeicherte Befunde erhalten keine manuelle Wiedereröffnung. SQL (live/persisted),
kanonischer Admin-Link, vorhandener Standortvorschlag, Graph und Markierungen bleiben in
Werkzeuge erreichbar. SQL-Hashlinks erhalten ihren Modus. Die Seiten-Technikleiste verwendet
`showTitle=false`, das Detail einen benannten technischen Abschnitt mit echten IDs/Zeitwerten.
`AssignmentSnooze compact` verdichtet nur die Auslöser; Presets, Zeitzone, Konfliktbehandlung
und das bestehende Modal bleiben erhalten. `RecordMarkLink variant="action"` bietet einen
44px-Aktionslink; Default bleibt `button` samt bisherigem Außenabstand.

Befunde verwenden `ActivityThumbnail compact`: 56px große, nicht interaktive Vorschauen
mit unverändertem Seitenverhältnis, validierter öffentlicher URL, Lazy Loading und
Typ-Platzhalter bei fehlendem oder defektem Bild. Veranstaltungsbilder, Terminbilder,
Ortsbilder, Organisationslogos, Benutzeravatare und Bilddatensätze folgen derselben
serverseitigen Zuordnung wie die Aktivitätsansicht. Technische/composite Datensätze
bekommen keine erfundene Bildzuordnung. Die freigegebene Ausnahme vom Frontend-only-Scope
ist das optionale `Finding.image_url`: eine deduplizierte Abfrage für die aktuelle Seite,
keine zusätzlichen API-Abfragen pro Zeile, keine Änderung an Ranking oder Reviewzuständen.

`MarkFields` gruppiert Gründe links und Erläuterung, Dringlichkeit und zusätzliche Formularfelder
rechts; mobil einspaltig. Checkboxlabels bieten 44px Touchfläche. Mark-Statusänderungen behalten
die Submitter-`value`-Semantik; ein 409 lässt den Entwurf stehen und verlangt explizites Neuladen.
Die eigene Mark-Event-Struktur bleibt eine dichte Liste, keine EntityTimeline-Ableitung.

Alle vier Routen schließen mit `TechnicalInfoBar`: Inbox mit `observed_at`, Admin-Zeitzone
und Pagination; Befunde mit `observed_at`, Modus, Pagination und ausdrücklich benannter
Client-Abrufzeit; Marks-Liste nur mit Pagination; Mark-Detail mit ID, Entity Key, Version und
belegten Erstellungs-/Abschlusszeiten. Keine erfundenen Datenstände oder Bearbeiternamen.

Inbox und Marks behalten beim Refresh derselben Auswahl den letzten erfolgreichen Stand
mit Lade-/Stale-Hinweis; Querywechsel und Zugangsfehler verwerfen ihn. Request-Generationen
verhindern verspätete Antworten nach ungültigen/neuen Filtern. Der Findings-Store bleibt
unverändert. Fehler erzeugen keinen leeren Erfolgszustand. Native Dialogfalle, Focus Return,
Tabellencaption, Zeitzonen und `time datetime` bleiben erhalten.

[Synthetische Review-Aufnahmen und Testmatrix](screenshots/operations-workflows/README.md).

### Operations Workflow v2.1 — Queues, Benachrichtigungen, Versände und Prüfläufe

Basis: `44bd5c1a5fb426f0024f55b8757a0a46e279bbb4` (main nach PR #112).
Diese Migration ist frontend-only; bestehende API-/Domain-Verträge bleiben unverändert.

- **Queues:** kompakte Filter mit Actions-Slot, gerichtete Organisationsanfragen oder
  Benutzer/Mitgliedschaft als Zeilenidentität, Status, belegtes Alter und Zeitpunkte.
  Fehlende Organisationsnamen bleiben verständliche Fallbacks; UUIDs sind nachrangig
  und über CopyValueButton kopierbar. `membership_status=invited|joined|all` und
  Direktaufruf per `entity_key` bleiben erhalten. Direktaufrufe deaktivieren/ignorieren
  Organisations-, Alters- und Statusfilter. `has_joined` ist kein Beitrittsdatum.
- **Benachrichtigungen:** systemweite Counts sind von gefilterten Ergebnissen getrennt.
  Fachlicher Hinweisstatus, Typ, Organisation und Erkennungszeiten führen die Tabelle.
  Filter/Pagination werden aus der URL wiederhergestellt; keine neue Browserpersistenz.
  Der Detailworkflow ordnet Identität → fachlichen Zustand → Vorschau → Versandhistorie
  → geschlossenes Payload-Disclosure → Technik. Dry Run ist ein kompakter Informationshinweis.
- **Versände:** Status, Betreff/Empfänger, Art/Sprache/Versuche und Zeitpunkte sind gruppiert.
  Fehlerlabels verwenden smtpErrorLabel. Das Detail trennt Versandinformationen,
  Fehler/Wiederholung, operative Zuständigkeit, enthaltene Hinweise und Versandkette.
  Nur permanent_failure ohne nicht-abgebrochenen Nachfolger bietet bestätigten Retry.
  Dieser erstellt weiterhin einen neuen Auftrag; er behauptet weder Versand noch Erfolg.
- **Prüfläufe:** primärer asynchroner Start, kompakter aktiver Lauf und dichte Historie.
  Pending deaktiviert Start. Der vorhandene einzelne Zwei-Sekunden-Pollingtimer bleibt;
  Unmount und Fehler stoppen ihn. `started_at` wird schon beim Einreihen gesetzt:
  eine aus Start/Ende abgeleitete Dauer ist daher ausdrücklich **inkl. Wartezeit**.
  Fehler und laufende Prüfungen belegen keine automatische Behebung.

Alle Listen schließen mit einer titellosen TechnicalInfoBar, Details mit benanntem
technischem Abschnitt. Nur Queues liefern observed_at; Hinweise, Versände und Prüfläufe
bekommen keinen erfundenen Datenstand. „Neuester Lauf auf dieser Seite“ und UI-Pollingzustand
sind ausdrücklich lokal; aus einer paginierten Historie wird kein globaler letzter Erfolg abgeleitet.
DeliveryDetail hat keinen eigenen Organisationsnamen: die UUID steht in der Technik,
keine Zusatzabfrage oder Umdeutung eines beliebigen enthaltenen Hinweises.

`DenseTable stackAt="tablet"` schaltet ausschließlich opt-in bis 1100px auf ein
beschriftetes zweispaltiges Raster, unter 640px auf eine Spalte. Default bleibt der
bisherige Mobile-Breakpoint. Optionale Spaltenbreiten gewichten Fachinhalt; caption,
scope und explizite Tabellenrollen bleiben erhalten. FilterBar unterstützt optional
`columns=3` für die Queue-Toolbar; Default bleibt vier. PageHeader setzt mit
`stackActions` seine Aktionen auf Tablet unter die Identität, damit lange Toolbars
den Titel nicht zusammendrücken; andere Seiten behalten das bisherige Verhalten. NotificationPreview kann
`embedded` ohne doppelte Abschnittsüberschrift erscheinen; iframe/Sandbox/CSP/Locale
bleiben unverändert. NotificationDeliveryTable teilt die gleiche Versanddarstellung
zwischen Liste und fachlicher Historie. OperationTime rendert belegte Instants mit
`time datetime`, andernfalls „Nicht verfügbar“, in der bestehenden Europe/Berlin-Konvention.

`useOperationsRequest` erhält nur Antworten derselben Auswahl/Identität. Querywechsel,
401/403/404/422 und verspätete Antworten werden sicher behandelt; temporäre Refreshfehler
zeigen ausdrücklich veraltete Daten. Detail-Retry und Check-Polling behalten eigene
Generationsguards. Weder neue Timer noch Requests pro Zeile oder neue Dependencies.

[Synthetische Review-Aufnahmen und Prüfstand](screenshots/operations-queues-notifications/README.md).

## 5. Typografie

Tailwind bleibt die einzige CSS-Basis. Benannte V2-Rollen liegen in `assets/css/main.css`;
keine zweite Typografiebibliothek. Neue Presenter verwenden diese Rollen statt eigener Skalen.

| Rolle         | Token                | Größe / Gewicht / Verwendung                                         |
| ------------- | -------------------- | -------------------------------------------------------------------- |
| Page title    | `type-page-title`    | 24px, bold, tight; genau ein primärer Titel                          |
| Record title  | `type-record-title`  | 24px mobil / 28px ab sm, bold, tight; ersetzt den Page-Titel im Hero |
| Section title | `type-section-title` | 18px, semibold; h3                                                   |
| Row title     | `type-row-title`     | 14px, semibold; h3 oder h4 nach Kontext                              |
| Body          | `type-body`          | 14px, 1.5; slate-700                                                 |
| Metadata      | `type-metadata`      | 12px, 1.5; slate-600, nicht für Hauptinhalt                          |
| Badge         | `type-badge`         | 12px, medium; State/Typ/Schwere                                      |
| Long-form     | `prose-admin`        | 16px, 1.75; maximal 72ch                                             |

Lange Namen umbrechen. Keine Ellipse als einzige Textquelle. Zahlen bei Vergleichen
`tabular-nums`; UUID/SQL dürfen monospace sein. Bereits existierende Komponenten werden
nur bei ihrer gezielten Migration auf Tokens umgestellt, nicht durch einen globalen Reset.

## 6. Inhaltsbreiten

Shell/Workspace: `max-w-7xl`; 16px Innenabstand mobil, 20px ab sm.
Record Detail: `record-detail` mit `max-w-6xl`, innerhalb der Shell links ausgerichtet.
Fließtext: `prose-admin`, 72ch. Kein erzwungener zweispaltiger Text.
Karten/Diagramme/SQL besitzen eigene lokale Scroll-/Zoomflächen, keinen Seitenoverflow.

## 7. Abstände

### Density

Hauptblöcke 16–24px; Standard `.operations-page` und `.record-detail` 20px.
Panel-Innenabstand 16px, Grid-Abstand 12px, zusammengehörige Metadaten 4–8px.
Keine verschachtelten Außen-Paddings auf kleinen Screens. Kein pauschales
`sm:space-y-8` für neue Record-Seiten. Tailwind-Tokens in `main.css`:

| Token                        | Wert | Verwendung                    |
| ---------------------------- | ---- | ----------------------------- |
| `--spacing-operations-page`  | 20px | Hauptblöcke                   |
| `--spacing-operations-panel` | 16px | Panelinhalt/Header horizontal |
| `--spacing-operations-grid`  | 12px | Gemeinsame Grids              |

Buttons/Inputs: 8px Radius; Panels/Listen: 12px. Borders tragen die Gliederung;
`shadow-soft` ist nur ein sehr dezenter 1px-Schatten. Echte Controls bleiben 44px hoch.
Dichte entsteht durch weniger Zwischenraum und kompakte Metadaten, nicht kleinere Touchflächen.

## 8. Farben und semantische Töne

Slate-50 Seitenfläche, Weiß begrenzte Arbeitsflächen, Slate-900 Haupttext, Slate-600
Metadaten. Fuchsia-700 primäre Aktion und Links, Fuchsia-800 Hover; Fokus Fuchsia-700.
Rose = Fehler/kritisch, Amber = Warnung, Emerald = Erfolg, Slate = neutral.
Objektfarben stammen aus `entityPresentation`, Graph übernimmt deren Identität.
Farbe nie allein: Label, Symbol oder Text ergänzt Bedeutung. Kein Status aus Farbe ableiten.
Kontrast für kleine Texte mindestens 4,5:1, große Texte/Controls mindestens 3:1 prüfen.

## 9. Surfaces

### Operations surfaces

Benannte Rollen sind Tailwind-Kompositionen in `main.css`, kein zweites CSS-System:

| Rolle                      | Aufgabe                                  |
| -------------------------- | ---------------------------------------- |
| `.operations-page`         | Abstand zwischen Hauptblöcken            |
| `.operations-panel`        | Begrenzte Arbeitsfläche                  |
| `.operations-panel-header` | Titelband mit optionalen Aktionen        |
| `.operations-toolbar`      | Umbrechende Controls                     |
| `.operations-grid`         | Responsives Inhaltsraster                |
| `.operations-meta`         | Sekundäre Metadaten                      |
| `.operations-techbar`      | Kompakter technischer Abschluss          |
| `.operations-row`          | Dichte, bei Bedarf wachsende Zeile       |
| `.operations-table`        | Semantische Tabelle mit kompakten Zellen |

| Surface | Zweck                                             | Primitive                                                 |
| ------- | ------------------------------------------------- | --------------------------------------------------------- |
| Plain   | Einfacher Text ohne eigene Interaktionsebene      | `.section-plain`, `RecordSection surface="plain"`         |
| Panel   | Standard für zusammengehörige Informationen       | `.section-panel` / `.operations-panel`, `surface="panel"` |
| Subtle  | Kontext, untergeordnete Bearbeitung               | `.section-subtle`, `surface="subtle"`                     |
| Table   | Dichte Datenlisten ohne zusätzliches Panelpadding | `.section-table`, `surface="table"`                       |
| Technik | Technischer Abschluss mit belegten Werten         | `.operations-techbar`, `TechnicalInfoBar`                 |

`RecordSection` bleibt zur kompatiblen schrittweisen Migration standardmäßig plain.
Panel/Subtle/Table erhalten ein Headerband (`.operations-panel-header`), Panel/Subtle
zusätzlich 16px Inhaltsabstand. `RecordSection surface="panel"` ist das gemeinsame
OperationsPanel-Pattern: `title`, `description`, dekorativer `icon`-Slot, `actions`-Slot
und Default-Inhalt. Es gibt keinen zweiten Panel-Wrapper. Neue größere Informationsgruppen explizit begrenzen.
Keine verschachtelten dekorativen Karten. `.operations-grid` bietet mobil eine, ab sm
zwei Spalten. `.operations-toolbar` bricht Controls um; `.operations-meta` ist 12px.

### Sidebar und Topbar

Sidebar ab lg: Slate-900, Labels Slate-200, aktive Route Fuchsia-900 mit weißem Text
und sichtbarem `aria-current`. Fokus Fuchsia-300 auf dunkler Fläche. Navigation bleibt
bei 256px Breite, 44px Linkhöhe und eigenem Scrollbereich. Systembereich durch Border
getrennt. Bestehende Reihenfolge und `utils/navigation.ts` bleiben maßgeblich.
Mobile Drawer verwendet dieselben Farben und unveränderte Dialog-/Fokusregeln.
Desktop-Topbar: Suche links, Zeit/Gebiet/Sitzung rechts, bei Platzmangel Umbruch.
Der App-Titel bleibt als h1 für Hilfstechnologien erhalten; PageHeader bleibt h2.
Kein aus einer Anmeldung abgeleiteter Live-Systemstatus.

### CompactFacts

`items`: eindeutiges `label`, `value`, optional `description` und `tone`.
`metadata` bleibt als kompatibler Beschreibungsalias verfügbar; `description` hat Vorrang.
`columns`: 2 (Default), 3 oder 4; mobil eine, ab sm zwei, ab xl die gewählte Zahl.
`missing="label"` zeigt „Nicht verfügbar“ für null/undefined/leere Strings;
`missing="omit"` lässt diese aus. 0 und false bleiben sichtbar; Boolean als Ja/Nein.
Domain-Labels und formatierte Zeit-/Zahlenwerte liefert der Aufrufer. Semantik: dl/dt/dd.
Keine Feldableitung oder API-Abrufe in diesem Präsentationsbaustein.

### Kopieraktionen

Alle Kopieraktionen verwenden `CopyValueButton`: Partneranfragen, Graph-Knotendetails,
`TechnicalInfoBar` (einschließlich Datensatzdetails) und die gemeinsamen SQL-Panels für
Editor, Konsole und Datenherkunft. Nur diese Komponente greift auf die Zwischenablage zu.
`value` enthält den Originalwert, `label` benennt den zugänglichen Button. `variant="button"`
eignet sich für Toolbars; standardmäßig erscheint ein Action-Link mit Kopiersymbol und Text.
Optionale Texte erhalten fachliche Rückmeldungen wie „SQL kopiert“. Ein `role="status"`
meldet Erfolg oder Fehler für 2,5 Sekunden. Wert-/Kontextwechsel, Deaktivierung und Unmount
verwerfen veraltete Rückmeldungen und ausstehende Formatierungen. SQL übergibt `formatSql`
als `formatValue`: Formatierung erfolgt erst beim Klick und bleibt für denselben Wert
zwischengespeichert. Nullwerte und explizit deaktivierte Aktionen sind nicht kopierbar.

### TechnicalInfoBar

`items`: dieselben Felder plus `copyable` und `mono`. Leere Werte und komplett leere
Leisten entfallen. Standardtitel „Technische Informationen“, anpassbar über `title`.
`showTitle=false` lässt das Titelband weg und erhält die benannte Region.
Optionale `datetime`/`timezone` erhalten `<time datetime>` und die sichtbare Zeitzone.
`EntityTechnicalMetadata` verwendet diese Leiste für UUID/Kopieren, belegtes created_at
und observed_at mit den bestehenden Europe/Berlin-Formattern.
Nur echte Contract-Werte übergeben, keine erfundenen Release-/API-/Verbindungsdaten.
Desktop: horizontale, umbrechende Metadaten; mobil einspaltig, Tablet zweispaltig.
UUIDs bleiben vollständig lesbar. Kopieren ist explizit, mit Live-Rückmeldung und
lesbarem Fehler; nach Datenwechsel werden veraltete Kopierrückmeldungen verworfen.
Töne: neutral, info, success, warning, error; stets auch ein aussagekräftiger Textwert.

### Technical info: Einsatzregel

**Technische Informationen sollen auf jeder Seite erscheinen, wenn dafür verifizierte
technische Daten verfügbar sind.** Eine Seite braucht keine künstliche Tech-Bar.
Die folgenden Beispiele sind Auswahlhilfen, keine zusätzlichen API-Felder oder Auftrag
zur sofortigen Seitenmigration:

| Kontext    | Mögliche belegte Werte                                                             |
| ---------- | ---------------------------------------------------------------------------------- |
| Record     | UUID, created_at, observed_at                                                      |
| Geocoding  | Request-ID, Generation, Attempts, checked_at                                       |
| Dashboard  | Datenstand, Zeitzone, letzter erfolgreicher Prüflauf aus einem vorhandenen Vertrag |
| Statistics | Zeitraum, Intervall, Timezone, Scope                                               |
| SQL        | Datasource, Readonly, Limits, Connection                                           |
| Graph      | Root, Depth, Nodes, Edges, Truncated                                               |
| Collection | observed_at, Scope, hilfreiche Seitengröße                                         |

Nur gelieferte Werte und vorhandene verifizierte Konfiguration verwenden. Kein
zusätzlicher Request oder erfundener Timestamp nur für diese Darstellung.

### Dense rows

`DataListShell dense` verdichtet ausschließlich direkte `.data-row`-Kinder. `as="ul"`
und echte `li` erhalten Listensemantik; `aria-label`/`aria-busy` werden durchgereicht.
Alternativ kann `.operations-row` eine einzelne Zeile kennzeichnen. Minimum 44px,
mit Controls typischerweise 52px; lange Inhalte wachsen ohne Abschneiden.
Divider, Hover und 12px Seitenpadding sind gemeinsam definiert. Der Aufrufer ordnet
seine fachlichen Felder und Aktionen; mobil darf deren Flex-/Grid-Struktur stapeln.
Der Default von DataListShell und alle bestehenden Listen bleiben kompatibel.

### Dense tables — DenseTable

Typisierte `columns` (`key`, `label`, optional `rowHeader`), `rows`, stabile `rowKey`-
Funktion und Pflicht-`caption`. Slots `cell-<key>` erhalten `row`/`value`, `actions`
erhält `row`. Statuszellen verwenden `StatusBadge`; zugängliche Aktionsnamen nennen das Ziel.
Keine eingebaute Sortierung, Filterung, Pagination oder Datenbeschaffung.
Desktop-Zeilen ca. 48px, bei Controls 52px oder bei langen Inhalten bedarfsgerecht höher.
Default `mobile="stack"`: beschriftete Zellen untereinander unter 640px, alle Werte
bleiben erhalten. Native Tabelle plus explizite Rollen/Headers erhalten die Zuordnung.
Für echte Vergleichsmatrizen `mobile="scroll"`: benannte, fokussierbare lokale Scrollfläche.
`busy` zeigt Aktualisierung statt leerem Erfolg; ohne Zeilen kompakter EmptyState.

## 10. Aktionen

### Action hierarchy

Maximal eine Primary Action pro Kontext; ohne priorisierte Aufgabe ist keine nötig.
Danger kennzeichnet ausschließlich echte destruktive Aktionen, nicht normale Navigation,
Filter-Reset oder eine Warnung. Keine sechs gleich starken Buttons nebeneinander.

| Gewicht   | Darstellung                       | Einsatz                              |
| --------- | --------------------------------- | ------------------------------------ |
| Primary   | `.button-primary`, filled Fuchsia | Eine priorisierte Aufgabe je Kontext |
| Secondary | `.button`, bordered               | Alternative Entscheidung/Inspektion  |
| Tertiary  | `.action-link`, Textlink          | Navigation und ergänzende Details    |

| Bedeutung  | Verben                                                                     |
| ---------- | -------------------------------------------------------------------------- |
| Navigation | Öffnen, Zur Liste                                                          |
| Extern     | Auf kulturbytes.de öffnen, Auf OpenStreetMap öffnen                        |
| Inspektion | Befunde anzeigen, Beziehungen, Markierungen & Notizen, SQL / Datenherkunft |
| Workflow   | Prüfen, Bearbeiten, Zuweisen, Wiedervorlegen, Erledigen, Erneut prüfen     |

Nicht „Im Admin ansehen“, wenn der Benutzer bereits im Admin ist. Accessible name
enthält bei wiederholten Aktionen das Ziel, z. B. „Öffnen: Hafenbühne“.
Beim Event-Pilot ist der gelieferte öffentliche Link primär; fehlt er, wird kein
Ersatz-Write-Button erfunden. Beziehungen sekundär, Markierungen/Zur Liste tertiär.
Externe Links kennzeichnen neuen Tab und verwenden `noopener noreferrer` und
`referrerpolicy="no-referrer"`. Nur validierte canonical URLs benutzen.

## 11. Formulare

Sichtbare Labels über Inputs, keine Placeholder als Labelersatz. `.label`, `.input`,
FilterBar und vorhandene Field-Komponenten nutzen. Controls/Touchlinks mobil mindestens
44px; Checkboxen in ausreichend großen Labels. Validierung nahe am Control mit
`aria-invalid`/`aria-describedby`; Gesamtfehler zusätzlich sichtbar.

Anwenden und Filter zurücksetzen konsistent. Filterzustand URL > Session-Store > Default;
keine neuen Persistenzsysteme. Bei Konflikt aktuelle Version explizit laden, keine stille
Überschreibung. Busy deaktiviert nur betroffene Aktionen. Keine zusätzlichen Pill-Systeme.

## 12. Suche

Globale Suche: synchroner Input/Navigation, debounced Remote-Query, resultQuery und letzte
Ergebnisse getrennt. Bestehende Ergebnisse während Revalidation, feste responsive Höhe,
Loading im Input, Status ohne Layout-Shift. Arrow-Navigation scrollt, Tippen nicht.
Combobox/Listbox/Option, gültiger aktiver Descendant, Escape, Enter und Fokus-Rückgabe.
Auth-/Route-/Close-Cleanup bleiben zwingend. Keine Suchbegriffe in Logs/Persistenz.
EntitySearch und GeoScope-Suche sind eigene fachliche Controls, keine zweite globale Suche.

## 13. Listen

ActivityRow ist die kompakte Referenz für Identität, Kontext, belegte Zeit und kleine
Aktionen. DataListShell liefert Grenzen/Divider. Findings und Inbox behalten ihre
fachlichen Zeilen. ResultSummary unterscheidet Gesamtergebnis und sichtbare Seite.
Keine Seitensumme als Gesamtzahl. Pagination erhält angewendete URL-Filter.
Activity ist Neuanlage, keine erfundene Änderungshistorie. Kein Detail-Hero aus ActivityRow.

## 14. Record Details

`EntityDetailPage` besitzt Abruf, Fehler/Loading, Standard-Header, Canonical-Findings-Link,
Timeline und Default-Presenter. Typisierte Slots erlauben Domain-Header, Inhalt und
Schlussmetadaten. Keine wachsende Serie von `v-if="section === …"` für Fachabschnitte.

Event-Pilot: EntityHero verwendet PageHeader für genau einen Record-Titel, dazu Thumbnail,
Typ/Status, Organisation, serverseitigen Subtitle und Kontext. Danach:

1. Primäre Fakten (belegte Terminzahl, Standardort/-raum).
2. Beschreibung, nur wenn nicht leer.
3. Verknüpfte Datensätze mit gemeinsamer Pagination.
4. Qualitäts-/Markierungsbestand, wenn verfügbar; keine erfundene Assignment-Zusammenfassung.
5. EntityTimeline, unveränderte Evidenz und Aktionen.
6. Technische Informationen: UUID, belegtes created_at, beobachteter Abrufzeitpunkt.

Die API liefert eine gemeinsame Relationsliste mit 25 Einträgen pro Seite, sortiert
nach Typ, Name und Schlüssel. Der Pilot zeigt deshalb bewusst **keine semantischen
Relationsgruppen**, sondern „Verknüpfte Datensätze“ mit Seitenumfang, Gesamtzahl und
Pagination. Das ist keine chronologische Terminliste. Bei 30 Terminen können Medien
und weitere Objekte erst auf Seite 2 erscheinen; ihr Fehlen auf Seite 1 bedeutet nicht,
dass es sie nicht gibt. Keine vollständige Hydration im Browser.

Veranstalter im Hero sowie Termin-Gesamtzahl und Standardort/-raum in den primären Fakten
kommen unabhängig von dieser Liste aus der Event-Projektion. Standardwerte sind nicht
der effektive Ort aller Termine: Termin-Overrides bleiben möglich. Subtitle mit
serverseitigem nächsten Termin unverändert verwenden, nicht parsen. UUID ist technischer
Inhalt, kein Hero-Fakt. Ein Folge-PR benötigt für semantische Bereiche einen typisierten,
begrenzten Vertrag: eigene chronologische Terminpagination, unabhängiger Veranstalter,
Standardreferenzen und begrenzte Medien mit Gesamtzahl und Zugang zu weiteren Seiten.

Organisationen, Orte und Räume verwenden ebenfalls Record Detail v2. Ihre Presenter
wählen eigene Fakten; sie kopieren nicht die Veranstaltungsstruktur:

| Detailtyp    | Hero-Kontext                                                         | Fachlicher Inhalt vor den Beziehungen                                                                        |
| ------------ | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Organisation | Belegter Stadt-Subtitle; kein wiederholter eigener Organisationsname | Veranstaltungen, Orte, Teammitgliedschaften **einschließlich Einladungen**; Adresse/Standort falls vorhanden |
| Ort          | Organisation                                                         | Räume insgesamt; Adresse falls vorhanden                                                                     |
| Raum         | Zugehöriger Ort, darunter Organisation                               | Die beiden belegten Kontextfakten stehen bereits einmal im Hero; kein redundanter Faktenkasten               |

`EntityHero` bietet einen optionalen `context`-Slot. Ohne Überschreibung bleiben
Veranstalter/Organisation und Subtitle des Events unverändert. Raum-Subtitle wiederholt
bereits den Ort und wird deshalb im eigenen Kontext nicht zusätzlich ausgegeben. Ein
Ortslink verwendet ausschließlich die passende kanonische Aktion einer tatsächlich
gelieferten Ortsrelation. Liegt diese nicht auf der aktuellen Seite, bleibt der Name Text;
Namen werden niemals zu URLs umgedeutet.

`RecordRelations` zeigt für alle sechs Typen dieselbe globale Seite mit Umfang, Gesamtzahl,
Server-Reihenfolge, `aria-busy` und Navigation über `related_page`; andere Query-Parameter
bleiben erhalten. Keine Fachgruppen oder vollständige Teams aus dieser Seite ableiten.
`RecordWorkflowSummary` zeigt gemeinsame Befund-/Markierungszahlen und den Link zu
persistierten Befunden. Null bedeutet nicht verfügbar, null wird nicht zu 0. Das gilt
auch für fachliche Gesamtzahlen; 0 ist ein belegter Wert.

`RecordLocation` zeigt vorhandene Adresse und optional den validierten OSM-Link über
`activityMapUrl`, keine Karte und keine zusätzlichen Requests. Die aktuelle Preview liefert
Koordinaten nur für Organisationen; Orts-Fixtures behaupten keine zusätzlichen Koordinaten.
Keine Adresse im Hero wiederholen. Öffentliche Kulturbytes-Links erscheinen ausschließlich
bei vorhandenem `public_url`; ohne sinnvolle öffentliche Aktion ist kein Primary Button nötig.
Danach folgen stets Arbeitsstand, Timeline und technische Informationen zuletzt.

`/users/:id` und `/images/:id` sind ebenfalls **RECORD DETAIL v2**. Die eigenen
Presenter `UserDetailContent` und `ImageDetailContent` enthalten ihren Hero vor den
fachlichen Abschnitten; die Shell übernimmt weiterhin RequestState und Timeline.
Ein bewusst leerer Header-Slot darf keinen Default-Header erzeugen.

Benutzer: Avatar, unveränderter kanonischer Servername, Typ und Aktiv/Nicht aktiv im Hero.
E-Mail und Username erscheinen dort als Plaintext nur, wenn sie nicht bereits den Namen
oder einander wiederholen. Benutzerinformationen zeigen den Kontostatus, Teamkontext
zeigt Teammitgliedschaften **einschließlich Einladungen**. Null bleibt unbekannt.
`has_joined` liefert Eingeladen/Beigetreten; `invited_at` liefert keinen Beitrittszeitpunkt.
Es gibt keine scheinbar vollständigen getrennten Teamgruppen und keinen öffentlichen
Benutzerlink. Der kanonische UUID-Fallback für Benutzer bleibt als letzte belegte
Identität erhalten; eine zusätzliche technische UUID steht ausschließlich am Ende.

Bilder: ein Hero-Titel und große Vorschau vor Bildinformationen, Beziehungen und Arbeitsstand.
Ein UUID-Bildname wird mit dem bestehenden Helper neutral als „Bild ohne Anzeigenamen“
angezeigt. Bildverknüpfungen zählen Links; „Ohne Verknüpfung“ zeigt Ja/Nein/Nicht verfügbar,
keine Aussage über Nutzung. `ActivityThumbnail` bietet eine `record`-Variante mit
reserviertem, auf 55dvh/32rem begrenztem Rahmen und unbeschnittenem Originalverhältnis.
Sie nutzt ausschließlich `activityImagePreviewUrl` für die vorhandene öffentliche URL,
lazy/async, anonymous CORS und no-referrer. Der vorhandene AppModal bleibt zuständig für
Vergrößerung und Fokus-Rückgabe. Bei Bildfehlern bleibt lesbarer Text ohne Retry-Schleife;
fehlende URL bleibt ein nicht interaktiver Fallback. Keine neue Remote-Quelle.
Der `leading`-Slot von EntityHero ersetzt beim Bild das kleine Thumbnail durch ein Typ-Icon.

Künftige semantische
Beziehungsgruppen benötigen unabhängige, explizite Vollständigkeits-/Paginationsverträge;
eine gemeinsame Relationsseite reicht dafür nicht aus.

## 15. Workflow-Seiten

Kontext, Evidenz, bearbeitbarer Admin-Zustand, nächste Aktion und Historie getrennt.
Befund-Zurückstellung gehört zur fachlichen Bewertung; Assignment-Wiedervorlage zur
Organisation der Aufgabe. Beide sind keine Lösung/Erledigung. Zuweisung, Fälligkeit,
Status und Wiedervorlage im gemeinsamen AssignmentEditor.
Geocoding bleibt Inspection-only. Retry reiht einen neuen Versuch ein; kein sofortiger
Erfolg, kein Quellschreiben. Notification-Historie bleibt unveränderlich.

`/geocoding/:id` ist die migrierte Workflow-v2-Referenz für **Quelle → Evidenz/Vergleich →
Bearbeitung → weitere Aktionen → technische Informationen**. GeocodeSourceSummary zeigt
Name, Typ, Quelladresse und den kurzen Prüfstatus ohne technische Faktenkarte.
LocationSuggestion verbindet die unveränderte Leaflet-Karte mit der vollständigen
Textalternative in einer Vergleichsfläche: ein Treffer kompakt darunter, mehrere ab xl
neben der Karte, mobil darunter. Auswahl ist zusätzlich zur Farbe als „Ausgewählt“ markiert.
Match-Gründe stammen aus dem Vertrag; ein hoher Score ist keine Freigabe.

PageHeader bleibt das einzige h2; RecordSection verwendet h3, Kandidatentitel h4.
AssignmentEditor bietet einen eingebetteten Modus ohne eigenen Header/Faktenrahmen;
Ladefehler bleiben als kompakter InlineAlert mit Wiederholungsaktion im Abschnitt Bearbeitung.
Andere Assignment-Einbettungen behalten ihr bisheriges Layout. Retry ist eine sekundäre
Aktion und bestätigt nur das Einplanen. Generation/Versuche/Request-ID stehen zuletzt.
Refresh behält nur Daten derselben ID, kennzeichnet Fehler als veraltet und verwirft den
Stand bei Identitätswechsel oder 401/403/404. Keine erfundene Abruf-/Beobachtungszeit.

## 16. Workspaces

Graph: eigene Canvas-Höhe, Fit/Zoom, zugängliche Knoten/Sidebar, begrenzte Expansion,
Fullscreen innerhalb Browser-API; Daten nicht aus Bildpositionen ableiten.
SQL: SqlWorkspace und gemeinsames Theme; Editor und Resultat scrollen lokal. Readonly und
editierbare Konsole bleiben fachlich getrennt. Originalquery/-parameter nicht umformatieren.
Statistik: Serienlegende, Textwerte/Datentabelle, klare Periodenbasis, Gebiets-/Systemgrenzen.
Karte: Leaflet clientseitig, konfigurierte Tiles, Attribution, Fehleroverlay, vollständige Liste.
Details stehen in den verlinkten Spezialdokumenten; V2 ersetzt keine Sicherheitsgrenze.

## 17. Rich Text / Markdown

Nur explizit nachgewiesene Felder: zunächst `event.description`; Nachweis im
[Audit](ui-ux-audit.md#verifizierter-event-vertrag-und-markdown). Keine Inhaltserkennung
an Sternchen/HTML-Zeichen. Andere Felder bleiben interpolierter Text.

MarkdownContent nutzt markdown-it ausschließlich als Tokenparser. Ein geschlossener
Vue-Renderer erstellt Absätze, strong/em, Listen, nachgeordnete Überschriften,
Blockzitate, Inline-/Block-Code, Links und Umbrüche. **Kein `v-html`, innerHTML oder
HTML-Renderer**, Raw-HTML deaktiviert, Bilder deaktiviert, keine Plugins/Autolinkifizierung.
Code wird escaped und lokal gescrollt. Quellüberschriften werden unter die Abschnittsebene
(h4–h6) eingeordnet. `.prose-admin` ist eine kleine eigene Typografieschicht.

CommonMark-Umbrüche: Softbreak wird zu einem Leerzeichen im Fließtext, nur Hardbreak
zu `<br>`. Eine Leerzeile trennt Absätze (`<p>`).

Links: nur absolute, validierte http/https/mailto ohne Credentials/Steuerzeichen.
Source-Markdown darf keine relativen Admin-Links erzeugen, auch nicht zu Record-Details,
Querys oder Fragmenten. Keine protocol-relative, JavaScript-, data- oder
verschleierten Protokolle. Abgewiesene Links als Text erhalten. Externe Links öffnen
mit no-referrer/noopener/noreferrer und zugänglichem Hinweis. Keine Netzwerkrequests
für Markdown-Bilder, Embeds oder Preview-URLs. Parserfehler/übergroße Texte bleiben
vollständig als sicherer Plaintext lesbar. Tests mit bösartigen Protokollen/HTML sind Pflicht.

## 18. Datum, Zahlen und Kennungen

Normale neue Detaildarstellung: `DD.MM.YYYY · HH:mm`, kompakt `DD.MM. · HH:mm`.
Vorhandene zentrale Formatter verwenden; keine Locale-Logik je Komponente.
`ADMIN_TIMEZONE` aus Antwort verwenden, wo vorhanden; bestehende Activity-/Timeline-
Fallback-Konvention Europe/Berlin bleibt, bis der Vertrag explizit erweitert wird.
Serverseitig in EVENT_TIMEZONE formatierte Termin-Subtitles nicht neu interpretieren.

`<time datetime>` für belegte Instants, Zeitzone in title/aria bzw. sichtbar wenn relevant.
Kein Mitternacht-Ersatz für unbekannte Uhrzeit, kein invitation→joined, kein now→created.
Zahlen de-DE; null „Nicht verfügbar“, echte 0 „0“. UUID umbrechen und optional kopieren;
Kopierfehler zugänglich anzeigen, Original immer lesbar halten. Benutzerlabel serverseitig:
display_name → username → email → UUID; leere Strings fehlen. Admin-Actors sind getrennt.

## 19. Status und Badges

Nur Typ, Zustand oder Schwere. Keine dekorativen Badges für beliebige Zahlen/Links.
EntityTypeBadge, StatusBadge, SeverityBadge weiterverwenden. Labels aus Maps; kein
„reviewed“ aus einem Snooze, kein Erfolg aus laufender Prüfung. Unknown/null explizit.
Workflowstatus, Quellveröffentlichung und Qualitätsstatus nicht auf einen Badge reduzieren.

## 20. Loading

Erstladen: klare Ladeanzeige im erwarteten Inhaltsbereich. Refresh derselben Identität:
letzte erfolgreiche Daten behalten, `aria-busy`, dezentes „Daten werden aktualisiert …“.
Bei Fehler bleibt der alte Stand ausdrücklich als alt gekennzeichnet.
Identitäts-/Authwechsel sowie 401/403/404: vorherige Detaildaten sofort verwerfen. Generation-/Abort-Guards
gegen verspätete Antworten. Nicht alle `data=null`-Stellen blind entfernen. SQL-Ausführung
und andere sicherheits-/parametergebundene Ergebnisse benötigen eigene Semantik.

## 21. Fehler

Kurzer Titel, sichere Erklärung, konkrete Wiederherstellung. APIError/RequestState statt
Treiber-/Providertext. 401 Sessionverlust löscht lokale Daten, 403 untersagt Zugriff ohne
Logoutbehauptung. 404 Detail nicht als „keine Ergebnisse“ kaschieren. Versionskonflikte
benennen und Neuladen anbieten, ungespeicherte Änderungen nicht still überschreiben.

## 22. Leere Zustände

### Compact empty states

`EmptyState variant="compact"` reduziert die leere Fläche auf mindestens 64px.
Optionaler `title`, Beschreibung über das bestehende `message` und ein `actions`-Slot.
Der boolesche Alias `compact` und Aktionen im Default-Slot bleiben kompatibel;
ein explizites `variant` hat Vorrang. Die Standardvariante behält ihre bisherigen Abstände.

### Compact timeline

`EntityTimeline compact` reduziert Padding/Icon/Summary-Abstände bei identischen
Ereignissen, Zeitangaben, Metadaten und Pagination. Keine abgeschnittene Evidenz.
Links bleiben echte 44px-Controls; Datum und Europe/Berlin-Bedeutung ändern sich nicht.

Titel + kurze Erklärung + optionale Aktion. Beispiel Collection: „Keine passenden
Veranstaltungen“ / „Ändere die Filter, um weitere Datensätze zu sehen.“ / „Filter zurücksetzen“.
Ungefilterter Bestand: keine Ergebnisse erfinden, keine Recovery anbieten, die nichts tut.
Leere Event-Beschreibung erzeugt keinen Kasten. Paginierte Beziehungsseite ist keine
Aussage über das Fehlen anderer Gruppen. API-Fehler ist kein Empty State.

## 23. Accessibility

Überschriften nicht duplizieren; Regionen per Überschrift benennen. Focus-visible nicht
entfernen. Native Dialoge mit Escape, Fokusfalle, Rückgabe; keine neue Modal-Implementierung.
Keyboard-Parität für Auswahl/Zoom/Charts, `aria-current` bei Navigation, `aria-pressed` bei
Toggles, `aria-selected` für echte Auswahlrollen. Statusmeldungen höflich, Fehler gezielt.
Keine Live-Ansage jedes Tastendrucks. Bilder mit Textalternative, dekorative Icons versteckt.
Tabellen mit caption/th/scope, externe Ziele erkennbar. Kontrast nicht aus Tailwind-Namen
allein ableiten; kleine farbige Texte in der Abschlussprüfung messen.

## 24. Responsive / Mobile

Shell: dunkle Sidebar ab lg, darunter Native-Navigation, kompakter Header und Gebiet.
Record-Inhalt einspaltig mobil, Fakten ab sm in zwei/drei Spalten. Reihenfolge im DOM bleibt
Lesereihenfolge. Mindestens 44px Touchflächen, keine schwebende Leiste vor Text.
Lange URLs/Namen/UUID umbrechen; Code/Table lokal scrollen. Keine horizontalen Seitenleisten.
Viewports: 1440×1000, 1024×768, 390×844; Event zusätzlich 360×800. 200%-Zoom und
Screenreader-Prüfung gehören zum finalen manuellen Audit, nicht zur Screenshotbehauptung.

## 25. Komponenten-Inventar

| Familie       | Bestehende / neue Verantwortung                                                                                                                                                                                      |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shell         | layouts/default, auth, AppNavigation, GeoScopeSelector, GlobalSearchPalette                                                                                                                                          |
| Struktur      | PageHeader, SectionHeader, DataListShell, FilterBar, ResultSummary, PaginationBar                                                                                                                                    |
| Zustände      | RequestState, InlineAlert, EmptyState, StatusBadge, SeverityBadge, EntityTypeBadge                                                                                                                                   |
| Record v2     | EntityDetailPage (Shell/Slots), EntityHero (PageHeader/Identität), RecordSection (explizite Surfaces), Event/Organization/Venue/Space/User/ImageDetailContent (Domänen), SpaceDetailContext, EntityTechnicalMetadata |
| Record-Inhalt | RecordRelations (globale Seite), RecordWorkflowSummary (Counts), RecordLocation (Adresse/Link)                                                                                                                       |
| Inhalt        | CompactFacts / TechnicalInfoBar (v2.1), DetailFacts (bestehend), MarkdownContent (verifiziertes Rich Text), ActivityThumbnail                                                                                        |
| Listen        | DenseTable (v2.1), ActivityRow, EntityListPage, FindingsList, InboxRow                                                                                                                                               |
| Workflow      | AssignmentEditor/Snooze, MarkFields, GeocodeSourceSummary, LocationSuggestion, GeocodeTechnicalMetadata, NotificationPreview                                                                                         |
| Workspaces    | GraphWorkspace/EntityGraph/GraphNodeDetails, SqlWorkspace/QueryPanel, Statistik-Charts, CandidateMap                                                                                                                 |
| Interaktion   | AppModal, EntitySearch, AppIcon                                                                                                                                                                                      |

Keine Domain-Platzhalter ohne fachliche Migration. Slot-Vertrag statt
riesigem Switch. Neue Primitive gezielt testen, nicht bloß Implementierungsdetails spiegeln.

## 26. Anti-Patterns

- ActivityRow als universeller Detailheader.
- Doppelter Seiten-/Datensatztitel.
- Lange Prosa in DetailFacts.
- UUID als Hauptinhalt trotz lesbarer Identität.
- Sechs gleich gewichtete Aktionen.
- Rohe bekannte Statuswerte.
- Unbegründeter Wechsel zwischen Deutsch/Englisch.
- Routenspezifische Designsysteme oder zweite CSS-Library.
- Unsicheres `v-html` / HTML-Injektion für Quelltext.
- Erfundene Zeitpunkte/Beziehungen/Counts.
- Unnötiges Leeren stabiler Inhalte beim Refresh.
- Undifferenzierte Beziehungslisten trotz vollständig typisiertem Vertrag.
- Scheinbar vollständige Fachgruppen aus einer global paginierten Relationsseite.
- Card soup, unbegrenzte Textbreite, horizontaler Seitenoverflow.
- Alte Ergebnisse ohne Hinweis als neue Parameterantwort darstellen.

## 27. Screenshot-Regressionsmatrix

Review-Artefakte, keine Vollseiten-Pixelgoldens. `layout-consistency.spec.ts` erfasst
jede Haupt-Route mit kontrollierten Fixtures, lokal gemockten Bildern/Tiles und ohne
Produktionsdaten. Jede Aufnahme nach geladenem Inhalt, nicht nur nach sichtbarem Header.

| Bereich                                                   | Desktop 1440×1000 | Tablet 1024×768 | Mobile 390×844 | Zusatz                                        |
| --------------------------------------------------------- | ----------------- | --------------- | -------------- | --------------------------------------------- |
| Übersicht, Aktivität, Aufgaben, Befunde, Checks, Qualität | ja                | ja              | ja             | leer/Fehler in Fachtests                      |
| Alle drei Queues                                          | ja                | ja              | ja             | Alter unbekannt separat                       |
| Notifications + Versände, jeweils Liste/Detail            | ja                | ja              | ja             | Retry/Preview Fachtests                       |
| Marks Liste/Detail                                        | ja                | ja              | ja             | Konflikt Fachtests                            |
| Sechs Entity-Collections + Details                        | ja                | ja              | ja             | Alle sechs Record-v2-Typen zusätzlich 360×800 |
| Geocoding Liste/Detail                                    | ja                | ja              | ja             | Tiles lokal, Fehlerfall                       |
| Graph                                                     | ja                | ja              | ja             | Fullscreen Fachtests                          |
| Statistik + Veranstaltungsinhalte                         | ja                | ja              | ja             | Tabelle/Serien Fachtests                      |
| SQL                                                       | ja                | ja              | ja             | bestehende Editor-Token-Goldens behalten      |
| Login                                                     | ja                | ja              | ja             | eigener Auth-Kontext                          |

Event v2: genau ein Haupttitel, Beschreibung eigener Abschnitt, allgemeine Relationspagination auch mit über 25 Einträgen,
Veranstalter und Standardort/-raum unabhängig von der Relationsseite,
Canonical-Aktionen, Timeline vor technischen Daten, UUID nur dort, keine überbreite Seite.
Die Tests legen PNGs unter Playwrights Testausgaben ab; ausgewählte Event-Desktop-/Mobile-
Bilder sowie Organisation/Ort/Raum/Benutzer/Bild werden unter `docs/screenshots/record-detail-v2/` dauerhaft reviewbar abgelegt.
`place-detail-v2.spec.ts` prüft alle drei neuen Typen in vier Größen, Kontext/Counts,
kanonische Aktionen, Touch-Ziele, generische Pagination und CSP.
`user-image-detail-v2.spec.ts` ergänzt alle vier Größen für Benutzer/Bilder, lange
E-Mail/Alttexte, Hoch-/Querformat, Bildfehler, Modal-Fokus und globale Pagination.
Kompakte synthetische Beispiele erzeugen `user-desktop.png`, `user-mobile.png`,
`image-desktop.png` und `image-mobile.png`; größere Fixtures prüfen zusätzlich die Pagination.
Sämtliche Review-Aufnahmen sind über das Testartefakt verfügbar, keine goldene Pixelpflicht.

Geocoding Workflow v2: `geocoding.spec.ts` prüft 1440×1000, 1024×768, 390×844 und
360×800, Einzel-/Mehrfachtreffer, Marker-/Listenfokus, optionalen Assignment-Fehler,
Tile-Ausfall und Production-CSP. Review-Artefakte unter
`docs/screenshots/geocoding-workflow-v2/` verwenden ausschließlich synthetische Daten und
lokal abgefangene Testkacheln; keine Produktionsdaten oder externen Tile-Requests.
