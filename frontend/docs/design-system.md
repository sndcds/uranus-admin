# Kulturbytes Admin Design System v2

Kanonischer UI-Vertrag für neue und migrierte Oberflächen. Grundlage ist der
[vollständige Frontend-Audit](ui-ux-audit.md) gegen `main` bei `e615df3`.
V2 wird schrittweise eingeführt: `/events/:id` ist der erste Record-Detail-Pilot.
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
Abstände, Typografie, Fokus, Fehler und Aktionen. Bestehende Shell bleibt bestehen.

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
PageHeader (h2) → Abschnitte (h3) → Datensatzzeilen (h4 in Abschnittslisten).
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

## 5. Typografie

Tailwind bleibt die einzige CSS-Basis. Benannte V2-Rollen liegen in `assets/css/main.css`;
keine zweite Typografiebibliothek. Neue Presenter verwenden diese Rollen statt eigener Skalen.

| Rolle         | Token                | Größe / Gewicht / Verwendung                                         |
| ------------- | -------------------- | -------------------------------------------------------------------- |
| Page title    | `type-page-title`    | 24px, bold, tight; genau ein primärer Titel                          |
| Record title  | `type-record-title`  | 24px mobil / 30px ab sm, bold, tight; ersetzt den Page-Titel im Hero |
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

Shell/Workspace: `max-w-7xl`; bestehende Shell-Innenabstände behalten.
Record Detail: `record-detail` mit `max-w-6xl`, innerhalb der Shell links ausgerichtet.
Fließtext: `prose-admin`, 72ch. Kein erzwungener zweispaltiger Text.
Karten/Diagramme/SQL besitzen eigene lokale Scroll-/Zoomflächen, keinen Seitenoverflow.

## 7. Abstände

Mobile: Shell `p-4`, Hauptabschnitte `space-y-4`; Desktop Shell `p-8`, Record-Abschnitte
`space-y-8`. Innerhalb eines Abschnitts 12–16px, Label → Eingabe 6px, zusammengehörige
Metadaten 4–8px. 24–32px trennen unterschiedliche Aufgaben. Keine zusätzlichen
verschachtelten Außen-Paddings, die auf 360px die Lesebreite aufbrauchen.

## 8. Farben und semantische Töne

Slate-50 Seitenfläche, Weiß begrenzte Arbeitsflächen, Slate-900 Haupttext, Slate-600
Metadaten. Fuchsia-700 primäre Aktion und Links, Fuchsia-800 Hover; Fokus Fuchsia-700.
Rose = Fehler/kritisch, Amber = Warnung, Emerald = Erfolg, Slate = neutral.
Objektfarben stammen aus `entityPresentation`, Graph übernimmt deren Identität.
Farbe nie allein: Label, Symbol oder Text ergänzt Bedeutung. Kein Status aus Farbe ableiten.
Kontrast für kleine Texte mindestens 4,5:1, große Texte/Controls mindestens 3:1 prüfen.

## 9. Surfaces

| Surface       | Bedeutung                                              | Primitive                   |
| ------------- | ------------------------------------------------------ | --------------------------- |
| Plain section | Inhalt mit Überschrift, keine eigene Interaktionsebene | `RecordSection` / section   |
| Panel         | Zusammengehörige Controls oder abgegrenzte Daten       | `.panel`                    |
| Card          | Eigenständig verständlicher Einstieg/Überblick         | `.card`, KpiCard            |
| Data list     | Wiederholte gleichartige Zeilen                        | DataListShell + `.data-row` |
| Inline alert  | Handlungsrelevanter Zustand/Fehler                     | InlineAlert                 |

Beschreibung, einfache Fakten und technische Schlusssektion brauchen keine weiße Card.
Keine Card in Card in Card. Ein Alert ist keine dekorative Zusammenfassung.

## 10. Aktionen

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
3. Termine; Veranstalter; Orte & Räume; Medien.
4. Qualitäts-/Markierungsbestand, wenn verfügbar; keine erfundene Assignment-Zusammenfassung.
5. EntityTimeline, unveränderte Evidenz und Aktionen.
6. Technische Informationen: UUID, belegtes created_at, beobachteter Abrufzeitpunkt.

Die API liefert Beziehungen seitenweise, nicht gruppenweise. Nur gelieferte Elemente
nach Typ gruppieren, Seitenumfang nennen und gemeinsame Pagination erhalten. Kein
„keine Termine“ aus einer Seite ohne Termine folgern. Standardort/-raum nicht als
effektiven Ort aller Termine ausgeben. Subtitle mit serverseitigem nächsten Termin
unverändert verwenden, nicht parsen. UUID ist technischer Inhalt, kein Hero-Fakt.

Künftige Presenter: Organisation → Veranstaltungen, Orte/Räume, Team, Partner, Medien;
Benutzer → Mitgliedschaften, Einladungen, Organisationen; Ort → Räume, Veranstaltungen,
Organisation, Medien. Nur vorhandene Relationen verwenden; Rollenlücken dokumentieren.

## 15. Workflow-Seiten

Kontext, Evidenz, bearbeitbarer Admin-Zustand, nächste Aktion und Historie getrennt.
Befund-Zurückstellung gehört zur fachlichen Bewertung; Assignment-Wiedervorlage zur
Organisation der Aufgabe. Beide sind keine Lösung/Erledigung. Zuweisung, Fälligkeit,
Status und Wiedervorlage im gemeinsamen AssignmentEditor.
Geocoding bleibt Inspection-only. Retry reiht einen neuen Versuch ein; kein sofortiger
Erfolg, kein Quellschreiben. Notification-Historie bleibt unveränderlich.

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

Links: validierte http/https/mailto ohne Credentials/Steuerzeichen; relative Links nur
auf freigegebene lokale Routen. Keine protocol-relative, JavaScript-, data- oder
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

Shell unverändert: Sidebar ab lg, darunter Native-Navigation, kompakter Header und Gebiet.
Record-Inhalt einspaltig mobil, Fakten ab sm in zwei/drei Spalten. Reihenfolge im DOM bleibt
Lesereihenfolge. Mindestens 44px Touchflächen, keine schwebende Leiste vor Text.
Lange URLs/Namen/UUID umbrechen; Code/Table lokal scrollen. Keine horizontalen Seitenleisten.
Viewports: 1440×1000, 1024×768, 390×844; Event zusätzlich 360×800. 200%-Zoom und
Screenreader-Prüfung gehören zum finalen manuellen Audit, nicht zur Screenshotbehauptung.

## 25. Komponenten-Inventar

| Familie     | Bestehende / neue Verantwortung                                                                                                                |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Shell       | layouts/default, auth, AppNavigation, GeoScopeSelector, GlobalSearchPalette                                                                    |
| Struktur    | PageHeader, SectionHeader, DataListShell, FilterBar, ResultSummary, PaginationBar                                                              |
| Zustände    | RequestState, InlineAlert, EmptyState, StatusBadge, SeverityBadge, EntityTypeBadge                                                             |
| Record v2   | EntityDetailPage (Shell/Slots), EntityHero (PageHeader/Identität), RecordSection (plain), EventDetailContent (Domäne), EntityTechnicalMetadata |
| Inhalt      | DetailFacts (kurze Werte), MarkdownContent (verifiziertes Rich Text), ActivityThumbnail                                                        |
| Listen      | ActivityRow, EntityListPage, FindingsList, InboxRow                                                                                            |
| Workflow    | FindingDetail, AssignmentEditor/Snooze, MarkFields, LocationSuggestion, NotificationPreview                                                    |
| Workspaces  | GraphWorkspace/EntityGraph/GraphNodeDetails, SqlWorkspace/QueryPanel, Statistik-Charts, CandidateMap                                           |
| Interaktion | AppModal, EntitySearch, AppIcon                                                                                                                |

Kein OrganizationDetailContent-Platzhalter ohne fachliche Migration. Slot-Vertrag statt
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
- Undifferenzierte Beziehungslisten trotz bekannter Typen.
- Card soup, unbegrenzte Textbreite, horizontaler Seitenoverflow.
- Alte Ergebnisse ohne Hinweis als neue Parameterantwort darstellen.

## 27. Screenshot-Regressionsmatrix

Review-Artefakte, keine Vollseiten-Pixelgoldens. `layout-consistency.spec.ts` erfasst
jede Haupt-Route mit kontrollierten Fixtures, lokal gemockten Bildern/Tiles und ohne
Produktionsdaten. Jede Aufnahme nach geladenem Inhalt, nicht nur nach sichtbarem Header.

| Bereich                                                   | Desktop 1440×1000 | Tablet 1024×768 | Mobile 390×844 | Zusatz                                   |
| --------------------------------------------------------- | ----------------- | --------------- | -------------- | ---------------------------------------- |
| Übersicht, Aktivität, Aufgaben, Befunde, Checks, Qualität | ja                | ja              | ja             | leer/Fehler in Fachtests                 |
| Alle drei Queues                                          | ja                | ja              | ja             | Alter unbekannt separat                  |
| Notifications + Versände, jeweils Liste/Detail            | ja                | ja              | ja             | Retry/Preview Fachtests                  |
| Marks Liste/Detail                                        | ja                | ja              | ja             | Konflikt Fachtests                       |
| Sechs Entity-Collections + Details                        | ja                | ja              | ja             | Event 360×800                            |
| Geocoding Liste/Detail                                    | ja                | ja              | ja             | Tiles lokal, Fehlerfall                  |
| Graph                                                     | ja                | ja              | ja             | Fullscreen Fachtests                     |
| Statistik + Veranstaltungsinhalte                         | ja                | ja              | ja             | Tabelle/Serien Fachtests                 |
| SQL                                                       | ja                | ja              | ja             | bestehende Editor-Token-Goldens behalten |
| Login                                                     | ja                | ja              | ja             | eigener Auth-Kontext                     |

Event v2: genau ein Haupttitel, Beschreibung eigener Abschnitt, alle Typgruppen,
Canonical-Aktionen, Timeline vor technischen Daten, UUID nur dort, keine überbreite Seite.
Die Tests legen PNGs unter Playwrights Testausgaben ab; ausgewählte Event-Desktop-/Mobile-
Bilder werden unter `docs/screenshots/record-detail-v2/` dauerhaft reviewbar abgelegt.
Sämtliche Review-Aufnahmen sind über das Testartefakt verfügbar, keine goldene Pixelpflicht.
