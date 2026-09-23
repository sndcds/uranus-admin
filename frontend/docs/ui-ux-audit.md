# Frontend UI/UX-Audit — Design System v2

## v2.1 — Visual consolidation: in progress

Ausgangspunkt: frisch geholtes `main` bei `10f41ca78cad640317fbd06be70ce2f766845b82`.
Der erste Operations-Center-Schritt umfasst kompaktere gemeinsame CSS-Rollen,
dunkle Sidebar/Drawer, kompakteren PageHeader/Topbar, explizite Panel-Surfaces,
CompactFacts, TechnicalInfoBar, DenseTable und optionale kompakte EmptyState-/Timeline-Varianten.
Die Navigationsreihenfolge, fachlichen Daten, Abrufe und Backend-Verträge bleiben erhalten.
Das Dashboard `/` ist im folgenden Schritt als Operations Overview v2.1 migriert
(Basis: `76016593bfde39d5aada821f2e0afd9f14eba63a`, nach PR #109).

**Visual consolidation / density migration pending:** sechs Record-Details →
Geocoding/Workflow → Queues/Notifications/Checks →
Graph/SQL/Statistics/Quality → abschließender Responsive-/Accessibility-Audit.
Diese Folgephasen benötigen jeweils einen eigenen Review; sie gehören nicht zu diesem PR.

[Komponenten-/Shell-Aufnahmen und Reproduktion](screenshots/operations-foundations/README.md).
Historische Auditbefunde und v2-Migrationsverträge unten bleiben als Kontext erhalten.

Foundation-Abgleich nach PR #109, erneut geprüft auf `main` bei
`b19b19d9e1381ff1d30be4dfc5ebb315a24697cc` (inklusive gemergtem Dashboard-PR #110): fehlende Shared-Verträge ergänzt. EntityTechnicalMetadata verwendet
TechnicalInfoBar mit unveränderter UUID-/Zeitsemantik. DataListShell bietet einen opt-in
dense-Modus; RecordSection ist das Panel-Pattern mit Icon und Aktionen. PageHeader erhält
einen benannten Actions-Slot, EmptyState die benannte compact-Variante. Die isolierte
Fixture zeigt den echten PageHeader und EntityTimeline in den vier geforderten Größen.
Alle sechs Record-v2-Migrationen und Geocoding Workflow v2 bleiben erhalten. Die gemeinsame
Tech-Bar-Adoption ist keine vollständige Fachseitenmigration auf v2.1.

## Operations Workflow v2.1: aktueller Migrationsstand

Basis: `b2a93f08bfeb5681782e9f2cca36ae30b0e39b0f`, main nach PR #111.
**Migriert:** `/inbox`, `/findings`, `/marks`, `/marks/:id`.

| Route        | Ausgangszustand                                                  | Aktueller Zustand                                                                                                                                                                            |
| ------------ | ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/inbox`     | Große Filterfläche, Counts als lose Badges, hohe Zeilen          | Scanbarer Count-Strip mit URL-Shortcuts, kompakte Filter, dichte Aufgaben mit Zuständigkeit/Fälligkeit, Technik am Ende                                                                      |
| `/findings`  | Listenzeilen und langes schmales Detailmodal                     | Dichte Tabelle mit Priorität, ausdrücklich seitenlokaler Severity-Verteilung, „Im Admin ansehen“ und verfügbare SQL-Diagnose als Zeilenaktionen; Befund-Detailkomponente auf Wunsch entfernt |
| `/marks`     | Hohe Rows, großer Kontextblock, Inhaltsverlust bei jedem Abruf   | Kompakte manuelle Arbeitsliste, Context-Panel mit Create-Disclosure, Refresh-Erhalt nur bei gleicher Query, technische Pagination                                                            |
| `/marks/:id` | Freie Identitäts-/Technikangaben, großes Formular, hoher Verlauf | Record-Header, Status/Gründe, Operations-Editor, dichter Mark-Verlauf, technische Schlusssektion                                                                                             |

Verträge und Grenzen: Inbox bleibt deduplizierte Aufmerksamkeit, Review bleibt fachliche
Befundentscheidung im Domainvertrag (keine Reviewoberfläche in der Befundliste), Assignment
operative Zuständigkeit, Mark manuelles Anliegen. Fachliche
Zurückstellung ist keine operative Wiedervorlage. Freigegebene Backend-/API-Erweiterungen: optionale aktuelle Bild-URL je Befund,
über die bestehende seitenweise Bildzuordnung. Keine Proxy-/Auth-/CSP-/DB-Änderung.
Marks liefert weder `observed_at` noch zuständigen Bearbeiter; vorhandene Admin-Subjects
werden als Ersteller/Abschlussautor bezeichnet. Findings liefert keinen globalen Severity-Split
für die aktuelle Auswahl und keinen vollständigen Review-Verlauf. Diese Daten werden nicht erfunden.

Die historischen Profile und ursprünglichen Auditbefunde unten bleiben erhalten. Der aktuelle
Zusätzlich unterstützt die bestehende SQL-Diagnose explizit `mode=live` mit kanonischen
Finding-Identitäten, festen Recipes und typisierten Schlüsseln. Die Standardsemantik
bleibt `persisted`; Authentifizierung und Lese-/Ressourcengrenzen bleiben erhalten.
Gemeinsame Kopieraktionen und SQL-Zeilennummern wurden ebenfalls vereinheitlicht/korrigiert.

Validierungsstand: vollständige Gates und aktuelle Review-Aufnahmen sind offen.
Lokale Tests wurden auf ausdrücklichen Wunsch wegen Rechnerauslastung gestoppt;
vorherige Ergebnisse und Screenshots belegen nur einen Zwischenstand.

Stand ist Code-/Reviewstand, keine Behauptung eines Deployments. [Review-Aufnahmen](screenshots/operations-workflows/README.md).

## Prüfstand und Methode

Audit vor Anwendungsänderungen, 23.09.2026. Frisch geholtes `main`:
`e615df3403b4ff00140e326a717fdcefb012ad78` (PR #100). Die Analyse umfasst sämtliche
131 Dateien / ursprünglich 12.634 Zeilen unter `app/pages`, `app/components`, `app/layouts`,
`app/utils`, `app/assets/css`, ihre Templates, UI-Texte, State-Lebenszyklen und CSS.
Die vollständige Dateiliste steht unten. Zusätzlich geprüft: AGENTS, Root-/Frontend-README,
Design-/Daten-/Activity-/Statistik-/Graph-/SQL-Dokumentation, Contracts, Entity-Repositories,
`layout-consistency.spec.ts`, `unified-ui.spec.ts`, Entity-Tests und Fixtures.

Abschließender main-Abgleich: `456030465c8056e3ffafae0e5d3a3c44f03bc87d` (PR #101).
Die seit Auditbeginn hinzugekommenen Änderungen an Queue-Seite, API-Client, Contracts,
Proxy und Tests wurden zusätzlich geprüft und vor Abschluss übernommen. Der aktuelle
Quellumfang umfasst weiterhin 131 Dateien, nun 12.671 Zeilen. Teammitgliedschaften haben
jetzt eine begrenzte Statusauswahl und einen erklärten Direktaufruf; die Profile und
das Inventar unten berücksichtigen diesen Stand. Die Event-Verträge bleiben unverändert.

Review-Abgleich für PR #103: `2900fe690f546bc73117d75b43beae3ac4e6920f` (PR #102).
Seit dem obigen Stand änderte main nur Ansible-Release-Paketierung und deren Dokumentation/Tests;
Frontend und Event-Relationsvertrag sind unverändert. Die Review-Entscheidung unten korrigiert
den Pilotumfang, nicht die historischen Seitenprofile.

Migrationsabgleich Organisation/Ort/Raum: frisch geholtes `main`
`4e43bffd949c86ffc8ccd71dcb7b63678ff78442` (gemergter PR #103). Vor der Änderung vollständig
geprüft: EntityDetailPage/EntityHero/RecordSection/TechnicalMetadata/Event-Presenter,
vier Route-Wrapper, Entity-/Activity-/Presentation-Helper, Zod-Verträge, Backend-Entity-/
Activity-/Preview-/Graph-Projektionen und Entity-Schemas sowie Unit-/E2E-/Layout-Fixtures.
Die drei Detailprofile und die Migrationstabelle unten beschreiben nun diese Erweiterung;
übrige historische Profile bleiben Auditbefunde, keine Behauptung eines neuen Deployments.

Verifizierte bestehende Felder und Grenzen (keine Backend-Erweiterung):

| Typ          | Unabhängig von der Relationsseite                                                                           | Grenze / Entscheidung                                                                                                                                        |
| ------------ | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Organisation | `facts.events`, `facts.venues`, `facts.memberships`; Name, Stadt-Subtitle, Adresse, Logo, optional Location | Membership-Count filtert nicht nach `has_joined`, enthält Einladungen. `organization_name` ist hier der eigene Name und wird nicht dupliziert.               |
| Ort          | `facts.spaces`; Organisationskontext, Adresse, Bild, optional `public_url`                                  | Preview projiziert derzeit keine Ortskoordinaten. Keine Koordinaten, Kontakte oder öffentliche URLs erfinden.                                                |
| Raum         | `facts.venue_name`, Organisationskontext über den zugehörigen Ort                                           | Subtitle wiederholt Venue-Kontext. Kein unabhängiger Venue-Schlüssel in Facts; Link nur über die tatsächlich gelieferte kanonische Ortsrelation, sonst Text. |

Abschlussabgleich: `a598bdeed64b82922e0073fb074db585c0df72c0` (PR #104) ergänzt nur
Ansible-Release-Paketierung, deren Tests und Dokumentation. Frontend und Source-/API-Verträge
sind gegenüber dem Migrationsausgangspunkt unverändert.

Alle drei hatten auf main noch ActivityRow als Detailzusammenfassung. Eigene Presenter
verwenden nun Kontext/Fakten in Domänenreihenfolge, generische Beziehungen, Arbeitsstand,
Timeline, technische Informationen. Raum-Kontextfakten erscheinen einmal direkt im Hero.
`RecordRelations`, `RecordWorkflowSummary` und `RecordLocation` teilen nur identisches
Verhalten; fachliche Fakt-Auswahl bleibt in den Presentern. Event nutzt die ersten beiden
Extraktionen ebenfalls. EntityDetailPage und ihre Refresh-/Stale-/Auth-Semantik bleiben
unverändert; zusätzliche Organisationstests sichern sie ab. Kein neues Markdown-Feld.

Screenshots sind ergänzende Evidenz, kein Ersatz für Codeprüfung. Insbesondere
`ui-consistency/event-detail.png` belegt den doppelten Titel und die prominente UUID.
Dashboard, Activity-Mobile, SQL-Mobile, Graph/Statistik und die aktuelle Geocoding-Karte
zeigen unterschiedliche Aufgaben, die keine universelle Activity-Seite lösen kann.
Ältere Aufnahmen enthalten noch die inzwischen entfernte Login-Leiste und alte Shell.
Sie sind keine Beschreibung des aktuellen Deployments. Neue Review-Aufnahmen sind
synthetisch und beweisen weder Produktionsdaten noch vollständige WCAG-Konformität.

## Benutzer/Bilder: aktueller Migrationsabgleich

Ausgangspunkt: frisch geholtes `main` bei `673884698b1697214fe9c8a271fbe6b3b672e33b`.
Bestehende User-/Image-Routen, Shared-Komponenten/Helper, Contracts, Entity-/Activity-/
Preview-/Queue-Repositories und Queue-Service sowie Record-/Entity-/Layouttests geprüft.
Neue Domain Presenter nutzen ausschließlich vorhandene Felder; keine Backend-Änderungen.
`entity_name` bleibt beim Benutzer serverseitig kanonisch, einschließlich UUID als letzter
Fallback. E-Mail und Username werden im Hero dedupliziert. Keine Credentials.
Bilder haben eine große sichere Vorschau aus der gelieferten URL; Vergrößerung verwendet
das bestehende AppModal. Ein Bild kann derzeit kein Graph-Root sein; dafür wird kein Link erfunden.
Alle sechs Entity-Detailtypen sind jetzt Record Detail v2, Geocoding bleibt Workflow v2.
Die Matrix trennt Ausgangszustand, aktuellen Zustand, Ziel und Status.

Synthetische Reviewbilder: [User Desktop](screenshots/record-detail-v2/user-desktop.png),
[User Mobile](screenshots/record-detail-v2/user-mobile.png),
[Image Desktop](screenshots/record-detail-v2/image-desktop.png),
[Image Mobile](screenshots/record-detail-v2/image-mobile.png).
`user-image-detail-v2.spec.ts` prüft 1440×1000, 1024×768, 390×844 und 360×800,
Pagination, Aktionen, Modal-Fokus, lange Texte, Hoch-/Querformat und Bildfehler;
dieselben Routen laufen auch mit erzwingender Production-CSP.

## Geocoding Workflow v2: aktueller Abgleich

Ausgangspunkt ist frisch geholtes `main` bei `61833d3fc59ec66106897b2e188dc4f37725deb0`
(gemergter Record-Detail-Ausbau). Geprüft wurden beide Geocoding-Seiten, Karten-/Kandidaten-
Komponenten, Assignment/Snooze, gemeinsame Struktur-/Statusprimitive, CSS/Helper, Zod und
Pydantic-Geocode-Vertrag sowie Unit-/E2E-/Layout-Fixtures.

Vorher: doppelte Source-Panels, frühe Generation/Versuche, wiederholter Prüfstatus, getrennte
Karten-/Listenrahmen, gleichrangige h2 und ein vollständiger Inhaltsverlust bei Refresh.
Entscheidung: Quelle kompakt, Standortvergleich als Hauptfläche, Assignment danach eingebettet,
sekundäre Retry-Aktion und technische Schlusssektion. Ein Kandidat benötigt keine zusätzliche
„Auf Karte zeigen“-Aktion; mehrere behalten die vollständige Tastatur-/Marker-Synchronisation.

Der Vertrag enthält `source_address` nur als Text, Kandidatenadressen als Struktur und
belegte `match_reasons`. Ein feldweiser Quell-/Zielvergleich wäre ohne neue Source-Projektion
nicht verlässlich; deshalb keine heuristische Adresszerlegung. `checked_at` ist vorhanden,
`observed_at` nicht. Request-ID/Generation/Versuche sind echte technische Daten. Kein
Backend-/Provider-/Koordinatenschreibvertrag wurde erweitert.

## Historische Audit-Befunde: Ausgangszustand und Prioritäten

- **P0 / Pilot:** Record Detail war im Audit-Ausgangszustand eine Listenvorschau mit Faktenanhang.
  Titel doppelt, Beschreibung in `DetailFacts`, UUID vor Inhalt, Timeline vor Beziehungen.
- **P1:** Sprach- und Statusdrift in Workflows; fachliche Befundbewertung, Assignment
  und Versandzustand brauchen getrennte Begriffe. Keine Workflow-Semantik ändern.
- **P2:** Uneinheitliche Apply/Reset-Texte, leere Zustände ohne Recovery, Refresh-Kollaps,
  technische Arbeitsbereiche mit unnötig englischer Produktsprache.
- Gute Grundlagen erhalten: gemeinsame Shell, URL-Präferenzen, klare API-Fehler,
  Native-Dialog-Fokus, kompakte Activity-Zeilen, Timeline-Evidenz, sichere Canonical-Links,
  neue stabile globale Suche und echte Geocoding-Karte mit Textalternative.

**Activity ist die Referenz für kompakte Listenzeilen, nicht für Record Details.**
Der alte Guide verlangte ActivityRow sogar als Detailzusammenfassung. Diese Empfehlung
wird mit fünf gleichberechtigten Seitenmustern ersetzt.

## Prüfraster, das für jede Route gilt

Die folgenden Feststellungen beschreiben den historischen Audit-Ausgangszustand;
aktuelle Migrationen stehen ausdrücklich in den v2-Profilen und der Matrix.
Die routebezogenen Profile verwenden diese gemeinsamen Feststellungen;
Abweichungen stehen im jeweiligen Profil. Damit sind auch Wrapper-Seiten über ihren
wirklich verwendeten gemeinsamen Presenter geprüft, nicht nur über ihren Dateinamen.

| Dimension             | Befund im Audit-Ausgangszustand / Ziel                                                                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Header und Typografie | Shell h1, PageHeader h2, SectionHeader h3; viele Inline-Klassen statt benannter Rollen. Workflow-Unterabschnitte teils erneut h2.                                                                 |
| Aktionen              | Filled Fuchsia und bordered vorhanden, aber Inspektionslinks häufig gleich gewichtet. Tertiäre Links und genau eine priorisierte Aktion pro Kontext definieren.                                   |
| Filter/Formulare      | Labels meist über Controls; Graph überwiegend aria-label statt sichtbarer Labels. FilterBar und FilterForm wiederverwenden, URL > Store > Default erhalten.                                       |
| Status                | Badge-Töne vorhanden. Bekannte Maschinenwerte zentral übersetzen; unbekannte Codes als technische Information, nicht erfundene Fachzustände.                                                      |
| Empty                 | EmptyState derzeit nur ein Absatz. Ziel: Titel, Erklärung, optional Recovery; null bleibt unbekannt und wird nicht 0.                                                                             |
| Loading               | RequestState vorhanden; viele lokale Seiten löschen data beim Laden. Nur bei gleicher Identität sichere letzte Antwort halten und als alt kennzeichnen.                                           |
| Error                 | RequestState mit Retry und sicheren Meldungen; 401 löscht geschützte Daten, 403 ist kein Logout. Fehler sind niemals leere Erfolge.                                                               |
| Mobile                | Shell p-4, Controls ab 640px kleiner; 390px wird bereits geprüft. Lange Schlüssel/Texte, dichte Links und Modal-Scroll getrennt prüfen; 360px Pilot ergänzen.                                     |
| Accessibility         | Skiplink, main, aktive Navigation, Dialog-Fokus, Textalternativen vorhanden. Überschriftenordnung, Linkziele, 44px Touch, Kontrast, Tabellen-Captions prüfen. Keine pauschale Konformitätszusage. |
| Surfaces              | panel/card/data-list existieren; card und panel visuell kaum unterschieden. Freie Inhaltsabschnitte brauchen keinen Kasten.                                                                       |

## Routenprofile: historische Ausgangsbefunde und markierte Migrationen

### `/` — Operations Overview v2.1

- **Current state:** Operations Overview v2.1. **Status:** migrated.
- **Hierarchie:** PageHeader → neun kompakte Neuanlagen-Tiles → vier Aufmerksamkeit-KPIs → Arbeitsliste mit Qualität/Queues rechts → erweiterte Filter → Technik.
- **Visuelle Referenz:** Dashboard-Panel des Operations-Center-Entwurfs. Dichte Tabelle, dezente Panelgrenzen, Fuchsia für Aktionen; Datenqualität und Vorgänge bilden eine schmale rechte Spalte.
- **Semantik:** weiterhin vier priorisierte Befunde, aktive Filter, neun Typen, echte Nullen, Zeitraum/Gebiet gegenüber systemweitem Bestand getrennt. „3 Arbeitslisten“ ist keine fachliche Gesamtzahl.
- **Technik:** Client-Abrufzeit präzise benannt; Zeitraum/Zeitzone, vorhandener Modus, letzte Prüfläufe und belegter Geo Scope. Keine künstlichen System- oder API-Angaben.
- **Responsive / Accessibility:** Tablet ein Hauptbereich mit 2×2 KPIs; mobile beschriftete Tabellenzellen, direkte Zeilenaktionen und Tastatur-Disclosure für Filter, 44px Controls, kompakte Empty States.
- **Grenzen:** Store-/Refresh-/Stale-/Auth-Verhalten unverändert. Keine weiteren Routen oder Backend-Verträge migriert. Shared Compact-Varianten sind opt-in.
- **Review:** [Desktop, Tablet, Mobile, Small Mobile](screenshots/operations-dashboard/README.md), ausschließlich synthetische Fixtures.

### `/activity` — COLLECTION

- **Aufgabe / Hierarchie:** Neue Quelldatensätze chronologisch prüfen. Header → Filter → Ergebniszahl → Tagesgruppen.
- **Header / Actions / Filter:** Objektart, Zeitraum, Organisation, Anwenden/Reset. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell/ActivityRow, kompakte Metadaten. Gemeinsames Prüfraster gilt; Activity-Seitennavigation; Im Admin ansehen.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Zeilenreferenz beibehalten; Aktionen benennen; Refresh stabilisieren. Priorität P2.

### `/inbox` — historischer Ausgangszustand (aktuell Operations Workflow v2.1)

- **Aufgabe / Hierarchie:** Priorisierte, deduplizierte Aufgaben bearbeiten. Header → Filter → Counts → Aufgaben.
- **Header / Actions / Filter:** Zuständigkeit, Aufmerksamkeit, Aufgabenart, Objektart, Aktualisieren. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** InboxRow und semantische Status-Badges. Gemeinsames Prüfraster gilt; Inbox, Findings, Finding-Snooze neben deutschen Labels.
- **Loading / Error / Empty:** Letzte Daten bleiben während gültiger Aktualisierung sichtbar. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Aufgabenübersicht/Befund vereinheitlichen; fachliche Zurückstellung klar benennen. Priorität P1.

### `/findings` — historischer Ausgangszustand (aktuell Operations Workflow v2.1)

- **Aufgabe / Hierarchie:** Befunde priorisieren und bewerten. Header → Filter → Bestand → Befundliste → Detailmodal.
- **Header / Actions / Filter:** Quelle, Regel, Status, Schwere, Objekt/Organisation; Review/SQL. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell; Modal mit Fakten und Formular. Gemeinsames Prüfraster gilt; Arbeitsliste/Befund/Review; rohe Regelcodes und Status im Detail.
- **Loading / Error / Empty:** Letzte Daten bleiben während gültiger Aktualisierung sichtbar. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Bewertung, Evidenz und Zuständigkeit gliedern; bekannte Status übersetzen. Priorität P1.

### `/checks` — WORKFLOW

- **Aufgabe / Hierarchie:** Prüfläufe starten und überwachen. Header → asynchroner Start → letzte Läufe.
- **Header / Actions / Filter:** Prüflauf starten, Gespeicherte Befunde, Pagination. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Kompakte Laufzeilen; StatusBadge. Gemeinsames Prüfraster gilt; Worker-Hinweis korrekt; Start ist kein Ergebnis.
- **Loading / Error / Empty:** Hintergrund-Polling hält die Laufzeilen; manueller Abruf und Fehler leeren sie. RequestState bietet Retry. Leere Historie bedeutet noch keine gespeicherten Läufe, nicht fehlerfreie Quelldaten. Refresh-Erhalt ist ein eigener Folgepunkt.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Primäre Startaktion behalten; Fortschritt und letzten Erfolg unterscheiden. Priorität P2.

### `/quality` — OVERVIEW

- **Aufgabe / Hierarchie:** Qualitätsprobleme nach Regel eingrenzen. Header → Bestandssemantik → Regelgruppen → Spezialabfrage.
- **Header / Actions / Filter:** Prüfläufe öffnen, Befunde ansehen. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Gruppierte Datenlisten, Zusatzpanel. Gemeinsames Prüfraster gilt; Lesende Diagnose korrekt; Regeln teilweise technische Codes.
- **Loading / Error / Empty:** Letzte Daten bleiben während gültiger Aktualisierung sichtbar. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Regellabels vervollständigen, Sonderpanel in gemeinsamen Überblick integrieren. Priorität P2.

### `/queues/partner_requests` — WORKFLOW

- **Aufgabe / Hierarchie:** Offene Partneranfragen prüfen. Header → Filter → Vorgänge mit Richtung/Alter.
- **Header / Actions / Filter:** Organisation, Mindestalter, Freitextstatus, Anwenden/Reset. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell; StatusBadge; kleine Aktionslinks. Gemeinsames Prüfraster gilt; Vorgang ansehen; rohe check-Codes; UUID bei fehlender Quelle.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Bekannte Statusauswahl und erklärende Prüfhinweise; Richtung erhalten. Priorität P2.

### `/queues/team_invitations` — WORKFLOW

- **Aufgabe / Hierarchie:** Einladungen und beigetretene Mitgliedschaften nach belegtem Alter und Zustand prüfen. Header → Filter → Benutzer/Organisation → Einladung.
- **Header / Actions / Filter:** Organisation, Mindestalter, Statusselect Eingeladen/Beigetreten/Alle, Öffnen/Markieren. URL steuert Filter; Direktaufruf per entity_key erklärt und deaktiviert die nicht angewendeten Filter. Reset öffnet die Einladungsliste. Keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Gleiche Queue-Zeile. Gemeinsames Prüfraster gilt; Einladungsdatum ist kein Beitritt; has_joined bleibt eigener Fakt.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Einladung klar vom Benutzer trennen; unbekannte Zeit nicht ersetzen. Priorität P2.

### `/queues/user_activation` — WORKFLOW

- **Aufgabe / Hierarchie:** Ausstehende Aktivierungen prüfen. Header → Filter → Benutzer → belegtes Alter.
- **Header / Actions / Filter:** Organisation, Mindestalter, Status, Öffnen/Markieren. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Gleiche Queue-Zeile. Gemeinsames Prüfraster gilt; Aktivierung ist keine Login-Historie.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Bekannte Status übersetzen; technische Checks nachrangig. Priorität P2.

### `/notifications` — COLLECTION

- **Aufgabe / Hierarchie:** Hinweise und Versandprobleme erkennen. Header → Filter → Versandfähigkeit → Counts → Hinweise.
- **Header / Actions / Filter:** Status, Typ, Organisation, Zeitraum; Versände öffnen. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Metriken und Liste; Warntexte. Gemeinsames Prüfraster gilt; Notification-Konfiguration, Source-Schema, Dry Run.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Deutsch, sichere Konfigurationshinweise; Filter in URL migrieren. Priorität P1.

### `/notifications/:id` — WORKFLOW

- **Aufgabe / Hierarchie:** Hinweis, Vorschau und Versandhistorie prüfen. Header → Datensatz → JSON → Vorschau → Historie.
- **Header / Actions / Filter:** Zur Sammlung, Vorschau laden, Sprache. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell als Detailkasten; mehrere h2. Gemeinsames Prüfraster gilt; Gelöst vs behoben; Dry Run; Rohdaten früh.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Domänenkontext vor Vorschau; JSON ans Ende, echte Abschnittshierarchie. Priorität P2.

### `/notifications/deliveries` — COLLECTION

- **Aufgabe / Hierarchie:** Versandversuche untersuchen. Header → Filter → Versandstatusliste.
- **Header / Actions / Filter:** Status, Art, Organisation, Zeitraum; Filter anwenden. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell, Empfänger/Fehlertexte. Gemeinsames Prüfraster gilt; Filter anwenden ohne Reset; sichere Fehlerlabels vorhanden.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Reset ergänzen; standardisierte Metadaten; Retry nicht mit Versand verwechseln. Priorität P2.

### `/notifications/deliveries/:id` — WORKFLOW

- **Aufgabe / Hierarchie:** Dauerhaften Fehler prüfen und ggf. neu einreihen. Header → Auftrag → Retry → Zuständigkeit → Hinweise.
- **Header / Actions / Filter:** Erneut versuchen mit Bestätigung; Zuweisung/Snooze. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Detail als DataListShell; AssignmentEditor. Gemeinsames Prüfraster gilt; Mehrere h2; Retry darf alte Historie nicht ersetzen.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Workflow-Kontext, Entscheidung, Zuständigkeit, Historie gliedern. Priorität P1.

### `/marks` — historischer Ausgangszustand (aktuell Operations Workflow v2.1)

- **Aufgabe / Hierarchie:** Markierte Datensätze finden bzw. kontextbezogen markieren. Header → Kontext/Create → Filter → Liste.
- **Header / Actions / Filter:** Status, Dringlichkeit, Grund, Sortierung; neue Markierung. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Kontextpanel, Formular und Datenliste. Gemeinsames Prüfraster gilt; entity_type und UUID im Kontext unübersetzt.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Kontext-Hero kompakt; technische ID nachrangig; leere Filter zurücksetzen. Priorität P2.

### `/marks/:id` — historischer Ausgangszustand (aktuell Operations Workflow v2.1)

- **Aufgabe / Hierarchie:** Markierung mit Notiz und Versionskonflikten bearbeiten. Header → Datensatz → Formular → append-only Historie.
- **Header / Actions / Filter:** Speichern, Erledigen/Wieder öffnen, Konflikt neu laden. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Panel plus Formular und DataListShell. Gemeinsames Prüfraster gilt; Rohes entity_type; technische Autoren-Subjects.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Zustand/Notiz klar gliedern; Actor-Identität nicht in Uranus-User umdeuten. Priorität P1.

### `/geocoding` — COLLECTION

- **Aufgabe / Hierarchie:** Standortprüfungen nach Zustand finden. Header → Systemweit-Hinweis → Filter → Statuszahlen → Liste.
- **Header / Actions / Filter:** Status, Entität, Pro Seite; Filter anwenden. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** RequestState/DataListShell/StatusBadge. Gemeinsames Prüfraster gilt; Entität, Pro Seite; kein Reset.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Objektart, Einträge pro Seite, Reset vereinheitlichen. Priorität P2.

### `/geocoding/:id` — WORKFLOW v2

- **Aufgabe / Hierarchie:** Quelladresse geografisch prüfen. Quelle → Standortprüfung mit Karte/Kandidaten → Bearbeitung → weitere Aktionen → technische Informationen.
- **Header / Actions / Filter:** Ein PageHeader; SQL/Datenherkunft und Collection-Link. Kompakte Record-Aktionen an der Quelle. Retry sekundär, pending/checking nur Aktualisieren. Keine Source-Write-Aktion.
- **Surfaces / Typografie / Status:** Plain RecordSections, eine gemeinsame Vergleichsfläche, kurzer Status einmal. Erläuterungen ohne Badge-Wiederholung; Warnungen/Fehler separat. Technische Daten zuletzt.
- **Loading / Error / Empty:** Gleiche ID hält letzte erfolgreiche Daten; Fehler als stale. Identitätswechsel und 401/403/404 leeren; Generation-Guard ignoriert späte Antworten. Fehlende Adresse/Prüfzeit bleiben ausdrücklich unbekannt. Assignment-Fehler kompakt und unabhängig wiederholbar.
- **Mobile / Accessibility:** 1440/1024/390/360px; ab xl mehrere Kandidaten neben der Karte, sonst darunter. Ein h2, Abschnitte h3, Kandidaten h4. Auswahltext, aria-current/pressed, Marker→Listenfokus und vollständige Textalternative bei Tile-Ausfall bleiben erhalten.
- **Terminologie / Änderung:** Workflow v2 umgesetzt. Keine Quelladressenzerlegung, keine neue Karte/Provider-Fallbacks, kein Übernehmen von Koordinaten.

### `/graph` — WORKSPACE

- **Aufgabe / Hierarchie:** Belegte Beziehungen erkunden. Header → Suche/Filter → Canvas + Detailpanel → Legende.
- **Header / Actions / Filter:** Root, Tiefe, Beziehungen, Fit/Zoom/Vollbild. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Workspace mit eigener fester Canvas-Höhe. Gemeinsames Prüfraster gilt; Entity-Relationship Graph, Entitätstypen, Im Admin ansehen, Live-Seite.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Canvas mit Pan/Zoom und separatem Detailpanel; auf kleinen Viewports stapeln. Root-Suche/Filter benötigen sichtbare Labels. Knoten-Auswahl, zugängliche Namen, Vollbild/Escape und Lesbarkeit des Detailpanels erhalten; Farbe allein darf keine Auswahl vermitteln.
- **Terminologie / Änderung:** Deutsch; Root-Suche sichtbar beschriften; Rohkennung im Detail unterordnen. Priorität P2.

### `/statistics` — WORKSPACE

- **Aufgabe / Hierarchie:** Neuanlagen zeitlich vergleichen. Header → Ansicht/Zeitraum → Diagramm → Kennzahlen → Tabelle.
- **Header / Actions / Filter:** Zeitfenster, Intervall, Serien, Vorperiode. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Chart-Panels/KPI-Cards; zugängliche Datentabelle. Gemeinsames Prüfraster gilt; Neue Entitäten, technische Gebietssemantik korrekt.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Chart hat Tastatur-Crosshair und eine Datentabelle als Textalternative mit Caption/Zeitzone. Serien-Legende und Vergleich müssen tastaturbedienbar bleiben. Mobile Kennzahlen umbrechen; Tabellen dürfen intern, nicht die Seite horizontal scrollen.
- **Terminologie / Änderung:** Datensätze statt Entitäten; Refresh ohne Chartkollaps bei gleichem Kontext. Priorität P2.

### `/statistics?view=event-content` — WORKSPACE

- **Aufgabe / Hierarchie:** Veranstaltungsinhalte nach Zuordnung vergleichen. Header → Zeitraum/Status → Coverage → Rankings.
- **Header / Actions / Filter:** Zeitraum, Status, Vorperiode. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Viele Kennzahlenkarten und Ranking-Panels. Gemeinsames Prüfraster gilt; Event-Inhalte, Events, Event-Typen.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Veranstaltungsinhalte; keine Summe auf 100 % erfinden. Priorität P2.

### `/sql` — WORKSPACE

- **Aufgabe / Hierarchie:** Begrenzte SQL-Abfragen lesend untersuchen. Header → Kontext → Editor → Ergebnis.
- **Header / Actions / Filter:** Ausführen, Abbrechen, Formatieren, Kopieren, CSV. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** SqlWorkspace; lokale Scrollbereiche; dunkler Editor. Gemeinsames Prüfraster gilt; SQL Console doppelt; Datasource/Mode/Scope/Connection/READ ONLY.
- **Loading / Error / Empty:** Abfrageergebnis gehört exakt zur Ausführung; nicht als Ergebnis geänderter SQL ausgeben. Laufender Request zeigt seinen Zustand im Workspace; Abbrechen und sichere Fehler gehören zur konkreten Ausführung. Null Ergebniszeilen sind von noch nicht ausgeführter SQL zu unterscheiden; kein Collection-Filter-Reset.
- **Mobile / Accessibility:** Editor und Ergebnistabelle scrollen lokal, die Seite nicht horizontal. Tastatursteuerung, Fokus nach Modal-Schließen, Tabellen-Caption und verständliche Beschriftung der Verbindungsdaten erhalten. Das innere main kollidiert mit dem Shell-Landmark.
- **Terminologie / Änderung:** Deutsch, ein Titel, verschachteltes main entfernen; Editor-Theme erhalten. Priorität P2.

### `/login` — WORKFLOW

- **Aufgabe / Hierarchie:** Unabhängige Admin-Anmeldung. Marke → h1 → zwei Eingaben → Anmelden → Fehler.
- **Header / Actions / Filter:** Benutzername/Passwort; Abmelden bei fehlender Berechtigung. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Eigenes Auth-Layout, kompakte Card. Gemeinsames Prüfraster gilt; Admin-Konto ist kein Uranus-Konto.
- **Loading / Error / Empty:** Kein Collection-Loading: Submit sperrt Eingaben, Passwort wird anschließend geleert; Auth-Fehler separat. Ein falsches Passwort, fehlende Systemadmin-Berechtigung und eine abgelaufene Sitzung bleiben unterscheidbare Auth-Zustände. Kein Collection-Empty-State und kein Filter-Reset.
- **Mobile / Accessibility:** Eigener Auth-Landmark statt geschützter Shell. Native Formularlabels, Passworttyp und Submit-Reihenfolge erhalten; Fehlermeldung per Alert. Auf 360/390px darf die Login-Card keine horizontale Seite erzeugen.
- **Terminologie / Änderung:** Bestehende Sicherheitszustände erhalten; Fokus/Fehlerzuordnung nachprüfen. Priorität P2.

### `/events` — COLLECTION

- **Aufgabe / Hierarchie:** Veranstaltungen suchen und Termine einordnen. PageHeader → Filter → Ergebnisübersicht → ActivityRows → Pagination.
- **Header / Actions / Filter:** Kontextsuche; nur unterstützte Status/Zeitraum/Terminlage; Anwenden/Reset. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell; Fakten inline ohne Beschreibung. Gemeinsames Prüfraster gilt; Öffnen derzeit Im Admin ansehen; Titel und Fakten konkurrieren.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Kompakte Zeilen beibehalten; domänenspezifische Metadaten verdichten. Priorität P2.

### `/events/:id` — historischer Ausgangszustand (aktuell RECORD DETAIL v2)

Die folgenden Befunde beschreiben den Zustand vor dem abgeschlossenen Event-Pilot.
Der aktuelle Zustand steht in der Migrationsmatrix und im Design Guide.

- **Aufgabe / Hierarchie:** Veranstaltungen suchen und Termine einordnen. PageHeader → ActivityRow → DetailFacts → Timeline → Beziehungen.
- **Header / Actions / Filter:** Zur Liste, Befunde, öffentliche/Graph/Markierungslinks sofern geliefert. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** Generische Datenliste als Hero, Faktenpanel, Relationsliste. Gemeinsames Prüfraster gilt; Beschreibung als Fact; Titel doppelt; Termine und Medien ungruppiert.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Pilot: Hero, Beschreibung, allgemeine verknüpfte Datensätze, Qualität, Verlauf, Technik. Typisierte Fachgruppen folgen erst mit unabhängigem Vertrag. Priorität P0.

### `/organizations` — COLLECTION

- **Aufgabe / Hierarchie:** Organisationen und ihren Kontext prüfen. PageHeader → Filter → Ergebnisübersicht → ActivityRows → Pagination.
- **Header / Actions / Filter:** Kontextsuche; nur unterstützte Status/Zeitraum/Terminlage; Anwenden/Reset. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell; Fakten inline ohne Beschreibung. Gemeinsames Prüfraster gilt; Öffnen derzeit Im Admin ansehen; Titel und Fakten konkurrieren.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Kompakte Zeilen beibehalten; domänenspezifische Metadaten verdichten. Priorität P2.

### `/organizations/:id` — RECORD DETAIL v2

- **Aufgabe / Hierarchie:** Organisation und belegten Kontext prüfen. Hero → Veranstaltungen/Orte/Teammitgliedschaften einschließlich Einladungen → optionale Adresse/Standort → generische Beziehungen → Arbeitsstand → Timeline → technische Informationen.
- **Header / Actions / Filter:** Logo, Name einmal, Stadt-Subtitle. Zur Liste, Beziehungen, Markierungen & Notizen; keine erfundene öffentliche Primäraktion. Kein Filterformular; Relationsseite in der URL.
- **Surfaces / Typografie / Status:** EntityHero, plain RecordSections, V2-Typografie; ActivityRow ausschließlich in der generischen Relationsliste. UUID nur technisch. Null-Counts bleiben unbekannt, 0 bleibt 0.
- **Loading / Error / Empty:** Gleiche Identität behält letzte erfolgreiche Daten mit Lade-/Stale-Hinweis. Identitätswechsel und 401/403/404 verwerfen Daten; späte Antworten werden ignoriert. Fehlende optionale Inhalte erzeugen keinen leeren Kasten. Leere Relation heißt nur „Keine belegten Verknüpfungen auf dieser Seite vorhanden“.
- **Mobile / Accessibility:** Vier Größen 1440/1024/390/360px, lange Namen/Adressen, umbrechende Aktionen, 44px-Touchziele; ein h2, RecordSections h3, Relationszeilen h4. Benannte Regionen, externe Links mit neuem-Tab-Kontext, Timeline vor technischen Informationen.
- **Terminologie / Änderung:** Teammitgliedschaften einschließlich Einladungen; keine aktiven Mitglieder behaupten. V2-Migration umgesetzt. Semantische Fachgruppen bleiben zurückgestellt bis zu einem typisierten, begrenzten Vertrag; globale Pagination bleibt ehrlich sichtbar.

### `/venues` — COLLECTION

- **Aufgabe / Hierarchie:** Orte und räumliche Einordnung prüfen. PageHeader → Filter → Ergebnisübersicht → ActivityRows → Pagination.
- **Header / Actions / Filter:** Kontextsuche; nur unterstützte Status/Zeitraum/Terminlage; Anwenden/Reset. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell; Fakten inline ohne Beschreibung. Gemeinsames Prüfraster gilt; Öffnen derzeit Im Admin ansehen; Titel und Fakten konkurrieren.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Kompakte Zeilen beibehalten; domänenspezifische Metadaten verdichten. Priorität P2.

### `/venues/:id` — RECORD DETAIL v2

- **Aufgabe / Hierarchie:** Ort und belegten Kontext prüfen. Hero → Räume insgesamt → optionale Adresse → generische Beziehungen → Arbeitsstand → Timeline → technische Informationen.
- **Header / Actions / Filter:** Bild, Name einmal, Organisation. Zur Liste, Beziehungen, Markierungen & Notizen; Kulturbytes-Primary nur aus vorhandenem public_url. Kein Filterformular; Relationsseite in der URL.
- **Surfaces / Typografie / Status:** EntityHero, plain RecordSections, V2-Typografie; ActivityRow ausschließlich in der generischen Relationsliste. UUID nur technisch. Null-Counts bleiben unbekannt, 0 bleibt 0.
- **Loading / Error / Empty:** Gleiche Identität behält letzte erfolgreiche Daten mit Lade-/Stale-Hinweis. Identitätswechsel und 401/403/404 verwerfen Daten; späte Antworten werden ignoriert. Fehlende optionale Inhalte erzeugen keinen leeren Kasten. Leere Relation heißt nur „Keine belegten Verknüpfungen auf dieser Seite vorhanden“.
- **Mobile / Accessibility:** Vier Größen 1440/1024/390/360px, lange Namen/Adressen, umbrechende Aktionen, 44px-Touchziele; ein h2, RecordSections h3, Relationszeilen h4. Benannte Regionen, externe Links mit neuem-Tab-Kontext, Timeline vor technischen Informationen.
- **Terminologie / Änderung:** Räume insgesamt; keine aus Adressen errechnete oder erfundene Location. V2-Migration umgesetzt. Semantische Fachgruppen bleiben zurückgestellt bis zu einem typisierten, begrenzten Vertrag; globale Pagination bleibt ehrlich sichtbar.

### `/spaces` — COLLECTION

- **Aufgabe / Hierarchie:** Räume und vererbten Ortskontext prüfen. PageHeader → Filter → Ergebnisübersicht → ActivityRows → Pagination.
- **Header / Actions / Filter:** Kontextsuche; nur unterstützte Status/Zeitraum/Terminlage; Anwenden/Reset. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell; Fakten inline ohne Beschreibung. Gemeinsames Prüfraster gilt; Öffnen derzeit Im Admin ansehen; Titel und Fakten konkurrieren.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Kompakte Zeilen beibehalten; domänenspezifische Metadaten verdichten. Priorität P2.

### `/spaces/:id` — RECORD DETAIL v2

- **Aufgabe / Hierarchie:** Raum und belegten Kontext prüfen. Hero einschließlich der zwei belegten Kontextfakten → generische Beziehungen → Arbeitsstand → Timeline → technische Informationen.
- **Header / Actions / Filter:** Name einmal, Zugehöriger Ort als Hauptkontext, Organisation darunter; kein zusätzlicher Venue-Subtitle. Zur Liste, Beziehungen, Markierungen & Notizen. Kein Filterformular; Relationsseite in der URL.
- **Surfaces / Typografie / Status:** EntityHero, plain RecordSections, V2-Typografie; ActivityRow ausschließlich in der generischen Relationsliste. UUID nur technisch. Null-Counts bleiben unbekannt, 0 bleibt 0.
- **Loading / Error / Empty:** Gleiche Identität behält letzte erfolgreiche Daten mit Lade-/Stale-Hinweis. Identitätswechsel und 401/403/404 verwerfen Daten; späte Antworten werden ignoriert. Fehlende optionale Inhalte erzeugen keinen leeren Kasten. Leere Relation heißt nur „Keine belegten Verknüpfungen auf dieser Seite vorhanden“.
- **Mobile / Accessibility:** Vier Größen 1440/1024/390/360px, lange Namen/Adressen, umbrechende Aktionen, 44px-Touchziele; ein h2, RecordSections h3, Relationszeilen h4. Benannte Regionen, externe Links mit neuem-Tab-Kontext, Timeline vor technischen Informationen.
- **Terminologie / Änderung:** Zugehöriger Ort; kanonischer Link nur aus gelieferter Ortsrelation, sonst Text. V2-Migration umgesetzt. Semantische Fachgruppen bleiben zurückgestellt bis zu einem typisierten, begrenzten Vertrag; globale Pagination bleibt ehrlich sichtbar.

### `/users` — COLLECTION

- **Aufgabe / Hierarchie:** Uranus-Benutzer und Teamkontext prüfen. PageHeader → Filter → Ergebnisübersicht → ActivityRows → Pagination.
- **Header / Actions / Filter:** Kontextsuche; nur unterstützte Status/Zeitraum/Terminlage; Anwenden/Reset. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell; Fakten inline ohne Beschreibung. Gemeinsames Prüfraster gilt; Öffnen derzeit Im Admin ansehen; Titel und Fakten konkurrieren.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Kompakte Zeilen beibehalten; domänenspezifische Metadaten verdichten. Priorität P2.

### `/users/:id` — RECORD DETAIL v2 (migriert)

- **Ausgangszustand:** Generic Entity Detail mit ActivityRow-Hero, doppeltem Titel, frühen UUID-Fakten und Timeline vor Beziehungen.
- **Aktueller Zustand:** Hero (Avatar, Servername, deduplizierte E-Mail/Username, Aktiv/Nicht aktiv) → Benutzerinformationen → Teamkontext → Verknüpfte Datensätze → Qualität & Arbeitsstand → Timeline → Technische Informationen.
- **Semantik:** `facts.memberships` zählt Teammitgliedschaften einschließlich Einladungen. Status Eingeladen/Beigetreten bleibt erhalten; kein Join-Zeitpunkt wird erfunden. Keine vollständigen Teamgruppen aus einer Relationsseite.
- **Shared:** EntityDetailPage, EntityHero, RecordSection, RecordRelations, RecordWorkflowSummary, EntityTimeline und EntityTechnicalMetadata. Keine neuen Backend-Felder, Source Writes oder Markdown-Felder.
- **Zustände / Accessibility:** Ein h2, Sections h3, Relationszeilen h4; gleiche Identität bleibt bei Refresh sichtbar, 401/403/404 und Identitätswechsel löschen alte Inhalte, späte Antworten werden verworfen. Plaintext, lange Inhalte und Vorschauverhältnisse auf 1440/1024/390/360px geprüft.

### `/images` — COLLECTION

- **Aufgabe / Hierarchie:** Bilder und Verknüpfungen prüfen. PageHeader → Filter → Ergebnisübersicht → ActivityRows → Pagination.
- **Header / Actions / Filter:** Kontextsuche; nur unterstützte Status/Zeitraum/Terminlage; Anwenden/Reset. Gemeinsamer Header; keine Source-Schreibaktion.
- **Surfaces / Typografie / Status:** DataListShell; Fakten inline ohne Beschreibung. Gemeinsames Prüfraster gilt; Öffnen derzeit Im Admin ansehen; Titel und Fakten konkurrieren.
- **Loading / Error / Empty:** Lokaler Abruf leert überwiegend den vorherigen Datensatz; bei gleicher Identität Refresh-Erhalt prüfen. Sichere Fehler/Retry erhalten; leere Ergebnisse erklären und bei Filtern Reset anbieten. Ein Detail-404 ist kein leerer Bestand.
- **Mobile / Accessibility:** Einspaltiger Lesefluss, lange Namen/IDs umbrechen; sichtbare Fokusfolge Header → Controls → Inhalt. Gemeinsames Prüfraster plus routebezogene Screenshot-Matrix anwenden.
- **Terminologie / Änderung:** Kompakte Zeilen beibehalten; domänenspezifische Metadaten verdichten. Priorität P2.

### `/images/:id` — RECORD DETAIL v2 (migriert)

- **Ausgangszustand:** Generic Entity Detail mit ActivityRow-Hero, doppeltem Titel, frühen UUID-Fakten und Timeline vor Beziehungen.
- **Aktueller Zustand:** Hero und große sichere Vorschau → Bildinformationen → Verknüpfte Datensätze → Qualität & Arbeitsstand → Timeline → Technische Informationen.
- **Semantik:** `facts.image_links` zählt Verknüpfungen, `facts.orphan` zeigt Ja/Nein/Nicht verfügbar. Große ActivityThumbnail-Variante mit bestehender URL-Prüfung und AppModal; Fehlertext ohne automatische Wiederholung. Keine Metadaten oder semantischen Bildtitel erfinden.
- **Shared:** EntityDetailPage, EntityHero, RecordSection, RecordRelations, RecordWorkflowSummary, EntityTimeline und EntityTechnicalMetadata. Keine neuen Backend-Felder, Source Writes oder Markdown-Felder.
- **Zustände / Accessibility:** Ein h2, Sections h3, Relationszeilen h4; gleiche Identität bleibt bei Refresh sichtbar, 401/403/404 und Identitätswechsel löschen alte Inhalte, späte Antworten werden verworfen. Plaintext, lange Inhalte und Vorschauverhältnisse auf 1440/1024/390/360px geprüft.

## UI-Wörterbuch-Audit: historische Fundstellen im Ausgangszustand

Alle statischen Template-Texte und sichtbaren Label-Maps der inventarisierten Dateien wurden
geprüft. API-Keys, SQL, Datenwerte und Quellinhalte werden nicht übersetzt. Folgende
Abweichungsgruppen decken die gefundenen Produkttexte ab; die verbindlichen Zielbegriffe
stehen im [Design Guide](design-system.md#2-sprache-und-terminologie).

| Text im Ausgangszustand / Ort                                                            | Ziel / Migration                                                                            |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Dashboard (`pages/index`)                                                                | Übersicht; Navigation heißt bereits so.                                                     |
| Inbox, Findings, Finding-Snooze, Finding-Review (`inbox`, `InboxRow`)                    | Aufgabenübersicht, Befunde, fachliche Zurückstellung, Befundbewertung.                      |
| Reviews/Reviewstatus/Review speichern (`FilterForm`, `FindingDetail`)                    | Bewertungen/Bewertungsstatus/Bewertung speichern.                                           |
| Im Admin ansehen (`ActivityRow`, FindingsList, GraphNodeDetails, SqlEditorModal)         | Öffnen mit spezifischem accessible name. ActivityRow im Pilot.                              |
| Zur Live-Seite (`GraphNodeDetails`)                                                      | Auf kulturbytes.de öffnen, sofern canonical public_url vorhanden.                           |
| Entity-Relationship Graph, Entitätstypen (`GraphWorkspace`, GraphFilters)                | Beziehungsgraph, Objektarten.                                                               |
| Neue/neueste Entitäten (`statistics`, Charts)                                            | Neue/neueste Datensätze.                                                                    |
| Event-Inhalte/Events/Event-Typen (`statistics`, EventContentStatistics, RankingBarChart) | Veranstaltungsinhalte/Veranstaltungen/Veranstaltungstypen.                                  |
| SQL Console/SQL Editor/SQL Abfrage (`sql`, Navigation, SQL-Komponenten, Findings)        | SQL-Konsole/SQL-Editor/SQL-Abfrage.                                                         |
| Datasource/Mode/Scope/Connection/READ ONLY/500 rows (`sql`)                              | Datenquelle/Modus/Bereich/Verbindung/Nur Lesen/500 Zeilen.                                  |
| Query Source/Query Details/Query-Quelle/Console-Abfrage (`sql/*`)                        | Abfragequelle/Abfragedetails/Abfragequelle/Konsolenabfrage.                                 |
| Executing/Cancelling etc. (`SqlQueryPanel` aus Session-State)                            | Ausführung läuft/Wird abgebrochen; State-Keys unverändert.                                  |
| Notification-Konfiguration/Source-Schema/Dry Run (`notifications`)                       | Benachrichtigungskonfiguration/Quellschema/Testbetrieb ohne Versand.                        |
| Entität/Pro Seite/Filter anwenden/Zurücksetzen                                           | Objektart/Einträge pro Seite/Anwenden/Filter zurücksetzen.                                  |
| Details/Ansehen/Vorgang ansehen/Objekt öffnen                                            | Kontextbezogen Öffnen, Befund prüfen oder Datensatz öffnen.                                 |
| Status nur open übersetzt (`FindingDetail`)                                              | Vorhandene findingStatusLabels vollständig verwenden.                                       |
| Rohregelcodes (`FilterForm`, QualityOverview unbekannte Regeln), Queue checks            | Vorhandene verifizierte Label-Maps verwenden; keine Diagnose erfinden.                      |
| `entity_type`, `created_by` (`marks`)                                                    | Typbadge; Admin-Actor bleibt belegte Identität, kein Uranus-Benutzername.                   |
| NULL/TRUE/FALSE, PostgreSQL, PostGIS, SQL, API, JSON, HTTP, UUID                         | In technischen Daten bewusst erhalten.                                                      |
| Dansk/English in E-Mail-Vorschau                                                         | Sprach-Eigennamen erhalten; nicht Admin-Oberflächensprache.                                 |
| Development-Token/Worker/Generation                                                      | Nur in explizitem Entwicklungs-/Technikkontext; normale Aufgaben nicht damit überschreiben. |

## Form-, Status- und Refresh-Audit: Ausgangszustand

Die Formflächen sind FilterBar/FilterForm, EntitySearch, GraphFilters, GeoScopeSelector,
LoginPanel/AccessPanel, MarkFields und Mark-Formulare, FindingDetail, AssignmentEditor,
AssignmentSnooze, Statistik-Zeitfenster und SQL-Editor. Jedes wurde auf sichtbare Labels,
Submit/Reset, Disabled/Pending, Fehlernähe, Tastatur und URL-Verhalten geprüft.

Konkrete Lücken: Notification-Liste führt Filter lokal statt URL-basiert; Delivery- und
Geocoding-Listen haben keinen Reset; Partner-/Aktivierungs-Queue-Status ist Freitext
(Teammitgliedschaften seit PR #101 als Select); Graph nutzt unsichtbare
Select-Labels; FilterForm lässt viele Regeln als Code stehen; FindingDetail zeigt bekannte
Review-Status roh. Markierungsfehler stehen erst unter dem ganzen Formular. SQL besitzt
ein verschachteltes `main`; im späteren Workspace-PR als Region ausweisen.

Historische Refresh-Löschstellen: EntityDetailPage, EntityListPage, Activity, Marks (Liste/Detail),
Notifications (Liste/Detail/Versände), Geocoding (Liste/Detail), Queues, Statistik und
EventContentStatistics. Checks behält Daten beim Polling, leert beim manuellen Abruf.
Inbox hält Daten außer bei ungültigen Filtern; Dashboard/Findings/Quality verwenden Stores.
GlobalSearchPalette ist bereits sauber getrennt und wird nicht neu gebaut.
EntityTimeline löscht beim Identitätswechsel korrekt. GeoScope-Suchergebnisse und
SQL-Ergebnisse dürfen nicht ungekennzeichnet zu anderen Parametern passen.
Aktuell halten alle sechs Entity-Details nur Daten derselben Datensatzidentität beim
Beziehungsseitenwechsel/Retry; Geocoding Workflow v2 hat ebenfalls einen Refresh-Erhalt.
Auth-/Identitätswechsel und verspätete Antworten bleiben geschützt.

## Verifizierter Event-Vertrag und Markdown

`backend/app/repositories/entities.py` projiziert `event.description` unverändert als
`facts.description`, außerdem `venue_name`, `space_name`, `event_dates`. Activity-Previews
liefern bereits einen **serverseitig zusammengestellten subtitle** einschließlich des
nächsten Termins, sofern vorhanden. Diesen Text unverändert verwenden; er ist kein
strukturiertes Datum und wird nicht clientseitig zerlegt oder aus Relationsseiten berechnet.
Standardort/-raum sind nicht automatisch der effektive Ort jedes Termins.

Markdown ist für **event.description** durch den Quell-Editor belegt:
[UranusAdminEventBaseTab.vue](https://github.com/sndcds/uranus-dashboard/blob/8909f6fb63adf2466c05d29e9ee34a0cf2756f77/src/component/event/editor/UranusAdminEventBaseTab.vue)
verbindet `descriptionProxy` mit `store.draft.description` und dem API-Payload `description`.
[UranusTextEditor.vue](https://github.com/sndcds/uranus-dashboard/blob/8909f6fb63adf2466c05d29e9ee34a0cf2756f77/src/component/ui/UranusTextEditor.vue)
liest Markdown und emittiert Turndown-Markdown. Lokal schreibgeschützte, saubere Checkout-Prüfung
auf SHA `8909f6fb63adf2466c05d29e9ee34a0cf2756f77`; keine Aussage über den Live-Deployment-Stand.
Der bestehende Event-Viewer verwendet ebenfalls Markdown. Die Admin-API hat keinen
`content_format`-Discriminator. Deshalb nur den explizit verifizierten Event-Beschreibungsslot
als Markdown behandeln. Andere Texte bleiben plain text bis zur Feldprüfung in PR 6.

Sicherer Renderer: Parser-Tokens → feste Vue-Elemente, niemals HTML-String-Injektion.
Keine Bilder/Raw-HTML/Plugins; Links separat validieren. Unbekannte Syntax bleibt Text.
CommonMark: Softbreak → Leerzeichen, Hardbreak → `<br>`, Leerzeile → neuer Absatz.
Nur absolute validierte http/https/mailto-Links, keine relativen Admin-Routen einschließlich
Record-Details, Querys und Fragmenten. Source-Inhalte dürfen keine privilegierte Workflow-
Navigation vorgeben. Externe Links behalten neuen Tab, noopener/noreferrer, no-referrer
und den zugänglichen Hinweis „(neuer Tab)“.
Keine API-, Quell-, CSP- oder Netzwerkänderung erforderlich.

**Relationsentscheidung für PR #103:** Beziehungen sind eine global paginierte Liste
(25 Elemente, Typ/Name/Key sortiert). Daraus abgeleitete Typgruppen suggerieren fachliche
Vollständigkeit, die der Vertrag nicht liefert. Der Pilot verwendet deshalb bewusst nur
„Verknüpfte Datensätze“, mit Seitenumfang, Gesamtzahl und gemeinsamer Pagination; keine
chronologische Terminliste. Ein Test mit 30 Terminen und vier weiteren Beziehungen zeigt
25 Termine auf Seite 1 sowie fünf Termine und die übrigen Objekte auf Seite 2.

Unabhängig davon liefert die verifizierte Event→Organisation-Beziehung den Veranstalter
im Hero; Event-Fakten liefern die vollständige Terminzahl sowie Standardort/-raum.
Diese Standardwerte behaupten keinen effektiven Ort für alle Termine. Medien bleiben
über die allgemeine Pagination erreichbar, ohne stilles Abschneiden.

Ein typisierter Event-Vertrag wäre eine zusätzliche Backend-Funktion mit eigenen begrenzten
Termin-/Medienabfragen, Counts und Pagination sowie Schema-/Proxy-/OpenAPI-/Integrationstests.
Das gehört in einen Folge-PR; kein unbeschränktes Nachladen aller Relationen im Browser.
Dieser Review-Fix erhält v2-Shell, Hero, Beschreibung, Qualität, Timeline, Technik und die
Refresh-/Auth-Semantik ohne Backend-Änderung. `finding_count` ist nicht automatisch offene Inbox-Arbeit;
`mark_count` umfasst auch erledigte Markierungen. null heißt nicht verfügbar.

## Migrationsmatrix je Route

Ausgangszustand bezeichnet den ursprünglichen Auditstand, aktueller Zustand den Code
nach den hier dokumentierten Migrationen. „Migriert“ ist keine Deployment-Aussage.
Optionale typisierte Relationsverträge sind Folgearbeit, keine Voraussetzung der v2-UI.

| Route                            | Ausgangszustand       | Aktueller Zustand        | Zielzustand                                              | Status     |
| -------------------------------- | --------------------- | ------------------------ | -------------------------------------------------------- | ---------- |
| `/`                              | OVERVIEW              | Operations Overview v2.1 | Operations Overview v2.1                                 | migrated   |
| `/activity`                      | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/inbox`                         | WORKFLOW              | Operations Workflow v2.1 | Operations Workflow v2.1                                 | migriert   |
| `/findings`                      | WORKFLOW              | Operations Workflow v2.1 | Operations Workflow v2.1                                 | migriert   |
| `/checks`                        | WORKFLOW              | WORKFLOW                 | WORKFLOW                                                 | offen (P2) |
| `/quality`                       | OVERVIEW              | OVERVIEW                 | OVERVIEW                                                 | offen (P2) |
| `/queues/partner_requests`       | WORKFLOW              | WORKFLOW                 | WORKFLOW                                                 | offen (P2) |
| `/queues/team_invitations`       | WORKFLOW              | WORKFLOW                 | WORKFLOW                                                 | offen (P2) |
| `/queues/user_activation`        | WORKFLOW              | WORKFLOW                 | WORKFLOW                                                 | offen (P2) |
| `/notifications`                 | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P1) |
| `/notifications/:id`             | WORKFLOW              | WORKFLOW                 | WORKFLOW                                                 | offen (P2) |
| `/notifications/deliveries`      | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/notifications/deliveries/:id`  | WORKFLOW              | WORKFLOW                 | WORKFLOW                                                 | offen (P1) |
| `/marks`                         | COLLECTION            | Operations Workflow v2.1 | Operations Workflow v2.1                                 | migriert   |
| `/marks/:id`                     | WORKFLOW              | Operations Workflow v2.1 | Operations Workflow v2.1                                 | migriert   |
| `/geocoding`                     | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/geocoding/:id`                 | WORKFLOW (generisch)  | WORKFLOW v2              | WORKFLOW v2                                              | migriert   |
| `/graph`                         | WORKSPACE             | WORKSPACE                | WORKSPACE                                                | offen (P2) |
| `/statistics`                    | WORKSPACE             | WORKSPACE                | WORKSPACE                                                | offen (P2) |
| `/statistics?view=event-content` | WORKSPACE             | WORKSPACE                | WORKSPACE                                                | offen (P2) |
| `/sql`                           | WORKSPACE             | WORKSPACE                | WORKSPACE                                                | offen (P2) |
| `/login`                         | WORKFLOW              | WORKFLOW                 | WORKFLOW                                                 | offen (P2) |
| `/events`                        | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/events/:id`                    | Generic Entity Detail | RECORD DETAIL v2         | RECORD DETAIL v2 + optional typisierter Relationsvertrag | migriert   |
| `/organizations`                 | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/organizations/:id`             | Generic Entity Detail | RECORD DETAIL v2         | RECORD DETAIL v2 + optional typisierter Relationsvertrag | migriert   |
| `/venues`                        | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/venues/:id`                    | Generic Entity Detail | RECORD DETAIL v2         | RECORD DETAIL v2 + optional typisierter Relationsvertrag | migriert   |
| `/spaces`                        | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/spaces/:id`                    | Generic Entity Detail | RECORD DETAIL v2         | RECORD DETAIL v2 + optional typisierter Relationsvertrag | migriert   |
| `/users`                         | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/users/:id`                     | Generic Entity Detail | RECORD DETAIL v2         | RECORD DETAIL v2 + optional typisierter Relationsvertrag | migriert   |
| `/images`                        | COLLECTION            | COLLECTION               | COLLECTION                                               | offen (P2) |
| `/images/:id`                    | Generic Entity Detail | RECORD DETAIL v2         | RECORD DETAIL v2 + optional typisierter Relationsvertrag | migriert   |

## Ursprüngliche Lieferfolge mit aktuellem Abschlussstand

1. Dieses Audit + kanonischer Design Guide v2, danach Event-Detail als begrenzter Pilot.
2. Gemeinsame Shell/Presenter, Markdown-Primitive und Pilot mit Regressionstests (gemeinsam
   reviewbar oder eigener Implementierungs-PR; keine Massenmigration).
   Vor semantischen Event-Gruppen: eigener begrenzter Event-Relationsvertrag mit fachlicher
   Terminreihenfolge, unabhängigen Referenzen und Medienpagination; keine Gruppen aus globaler Seite.
3. **PR 3 (abgeschlossen):** Organisationen/Orte/Räume mit bestehenden Facts und ehrlicher
   globaler Pagination umgesetzt; gemeinsame Relations-/Arbeitsstand-/Standort-Komponenten.
   Typisierte Fachgruppen ausdrücklich nicht Teil dieser Frontend-Migration.
4. **PR 4 (abgeschlossen):** Benutzer/Bilder migriert; Team-/Einladungsstatus und Counts bleiben präzise, keine getrennten Gruppen aus der globalen Relationsseite. Bildrechte/Herkunft fehlen im Vertrag und werden weggelassen.
5. **PR 5:** Workflows; Deutsch, Status, Formularfehler, Aufgaben-/Befund-Snooze klar trennen.
6. **PR 6:** Rich-Text-Rollout nach feldweiser Quellprüfung; kein Markdown-Heuristikschalter.
7. **PR 7:** Analytics/Workspaces; Terminologie, Labels, lokale Scrollbereiche, Refresh.
8. **PR 8:** Abschließender Responsive-/Accessibility-Audit mit Tastatur, Screenreader,
   Kontrastmessung, langen Inhalten, Fehler-/Leer-/Ladezuständen und realen Browser-Zoomstufen.

## Vollständiges Quellinventar des ursprünglichen Audits

Dieses Inventar bildet den historischen Audit-Ausgangspunkt ab, nicht das aktuelle
Dateiverzeichnis. Neuere Presenter und Migrationen sind oben separat dokumentiert.

Jede aufgeführte Datei wurde in die Code-/Template-/String-/State-Prüfung einbezogen.
Nicht jede Datei erhält Änderungen; Diagrammgeometrie, Auth, API-Adapter und SQL-Ausführung
bleiben im Pilot unverändert. Zeilenzahlen beziehen sich auf den oben genannten main-Stand.

| Datei (relativ zu frontend/)                            | Zeilen | Audit-Zuständigkeit                               |
| ------------------------------------------------------- | -----: | ------------------------------------------------- |
| `app/assets/css/main.css`                               |     94 | Typografie / Responsive / Surfaces                |
| `app/assets/css/statistics.css`                         |     83 | Typografie / Responsive / Surfaces                |
| `app/components/AccessPanel.vue`                        |     49 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/ActivityRow.vue`                        |    113 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/ActivityThumbnail.vue`                  |     71 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/AppIcon.vue`                            |     99 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/AppModal.vue`                           |     92 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/AppNavigation.vue`                      |     99 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/AssignmentEditor.vue`                   |    196 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/AssignmentSnooze.vue`                   |    182 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/CandidateMap.vue`                       |    237 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/DashboardCheckStatus.vue`               |     44 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/DataListShell.vue`                      |      7 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/DetailFacts.vue`                        |     15 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/EmptyState.vue`                         |     10 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/EntityDetailPage.vue`                   |    102 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/EntityGraph.vue`                        |    396 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/EntityListPage.vue`                     |    231 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/EntitySearch.vue`                       |    215 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/EntityTimeline.vue`                     |    140 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/EntityTypeBadge.vue`                    |     11 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/FilterBar.vue`                          |     13 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/FilterForm.vue`                         |    159 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/FindingDetail.vue`                      |    204 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/FindingsList.vue`                       |     85 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/GeoScopeSelector.vue`                   |    225 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/GlobalSearchPalette.vue`                |    345 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/GraphFilters.vue`                       |    128 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/GraphLink.vue`                          |     15 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/GraphNodeDetails.vue`                   |    224 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/GraphWorkspace.vue`                     |    205 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/InboxRow.vue`                           |    151 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/InlineAlert.vue`                        |     18 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/KpiCard.vue`                            |     34 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/KulturbytesLogo.vue`                    |     28 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/LocationSuggestion.vue`                 |    159 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/LoginPanel.vue`                         |     78 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/MarkFields.vue`                         |     39 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/NotificationPreview.vue`                |     79 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/OsmAttribution.vue`                     |     12 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/PageHeader.vue`                         |     27 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/PaginationBar.vue`                      |     51 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/QualityOverview.vue`                    |    106 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/RecordMarkLink.vue`                     |     17 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/RequestState.vue`                       |     40 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/ResultSummary.vue`                      |     30 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/SectionHeader.vue`                      |     16 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/SeverityBadge.vue`                      |     16 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/StatusBadge.vue`                        |     18 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlCodeEditor.vue`                  |     82 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlConsolePanel.vue`                |     94 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlEditorModal.vue`                 |    274 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlJsonResult.vue`                  |     52 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlParameterTable.vue`              |     67 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlProvenanceButton.vue`            |     59 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlProvenanceDrawer.vue`            |    164 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlProvenanceSource.vue`            |     64 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlQueryPanel.vue`                  |    233 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlReadonlyCode.vue`                |     69 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlReadonlyNotice.vue`              |     11 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlResultTable.vue`                 |     63 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlRuleEvaluation.vue`              |     40 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlSourceTabs.vue`                  |     63 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlWorkspace.vue`                   |     57 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/SqlWorkspaceModal.vue`              |     34 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/sql-codemirror.ts`                  |    127 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/sql/sql-theme.css`                      |    108 | Typografie / Responsive / Surfaces                |
| `app/components/statistics/EntityDistributionChart.vue` |     78 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/statistics/EntityMetricCard.vue`        |     67 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/statistics/EntitySparkline.vue`         |     45 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/statistics/EntityTimelineChart.vue`     |    256 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/statistics/EventContentStatistics.vue`  |    207 | Primitive / Interaktion / Semantik / Fokus        |
| `app/components/statistics/RankingBarChart.vue`         |     55 | Primitive / Interaktion / Semantik / Fokus        |
| `app/layouts/auth.vue`                                  |     20 | Shell / Landmarks / Navigation                    |
| `app/layouts/default.vue`                               |    169 | Shell / Landmarks / Navigation                    |
| `app/pages/activity.vue`                                |    244 | Route / Muster / Zustände                         |
| `app/pages/checks.vue`                                  |    121 | Route / Muster / Zustände                         |
| `app/pages/events/[id].vue`                             |      3 | Route / Muster / Zustände                         |
| `app/pages/events/index.vue`                            |      3 | Route / Muster / Zustände                         |
| `app/pages/findings.vue`                                |    143 | Route / Muster / Zustände                         |
| `app/pages/geocoding/[id].vue`                          |    157 | Route / Muster / Zustände                         |
| `app/pages/geocoding/index.vue`                         |    136 | Route / Muster / Zustände                         |
| `app/pages/graph.vue`                                   |    249 | Route / Muster / Zustände                         |
| `app/pages/images/[id].vue`                             |      3 | Route / Muster / Zustände                         |
| `app/pages/images/index.vue`                            |      3 | Route / Muster / Zustände                         |
| `app/pages/inbox.vue`                                   |    224 | Route / Muster / Zustände                         |
| `app/pages/index.vue`                                   |    343 | Route / Muster / Zustände                         |
| `app/pages/login.vue`                                   |     21 | Route / Muster / Zustände                         |
| `app/pages/marks/[id].vue`                              |    180 | Route / Muster / Zustände                         |
| `app/pages/marks/index.vue`                             |    255 | Route / Muster / Zustände                         |
| `app/pages/notifications/[id].vue`                      |     89 | Route / Muster / Zustände                         |
| `app/pages/notifications/deliveries/[id].vue`           |    141 | Route / Muster / Zustände                         |
| `app/pages/notifications/deliveries/index.vue`          |    154 | Route / Muster / Zustände                         |
| `app/pages/notifications/index.vue`                     |    150 | Route / Muster / Zustände                         |
| `app/pages/organizations/[id].vue`                      |      3 | Route / Muster / Zustände                         |
| `app/pages/organizations/index.vue`                     |      3 | Route / Muster / Zustände                         |
| `app/pages/quality.vue`                                 |     49 | Route / Muster / Zustände                         |
| `app/pages/queues/[kind].vue`                           |    200 | Route / Muster / Zustände                         |
| `app/pages/spaces/[id].vue`                             |      3 | Route / Muster / Zustände                         |
| `app/pages/spaces/index.vue`                            |      3 | Route / Muster / Zustände                         |
| `app/pages/sql.vue`                                     |     46 | Route / Muster / Zustände                         |
| `app/pages/statistics.vue`                              |    477 | Route / Muster / Zustände                         |
| `app/pages/users/[id].vue`                              |      3 | Route / Muster / Zustände                         |
| `app/pages/users/index.vue`                             |      3 | Route / Muster / Zustände                         |
| `app/pages/venues/[id].vue`                             |      3 | Route / Muster / Zustände                         |
| `app/pages/venues/index.vue`                            |      3 | Route / Muster / Zustände                         |
| `app/utils/activity.ts`                                 |    107 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/admin-api.ts`                                |    337 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/admin-time.ts`                               |     93 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/auth-redirect.ts`                            |     34 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/entities.ts`                                 |     67 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/entityPresentation.ts`                       |     77 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/filters.ts`                                  |     28 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/geo.ts`                                      |     28 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/geocoding.ts`                                |     40 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/graph.ts`                                    |     85 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/json-highlighter.ts`                         |     12 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/map-tiles.ts`                                |     17 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/marks.ts`                                    |     31 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/navigation.ts`                               |     29 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/notifications.ts`                            |     46 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/periods.ts`                                  |     53 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/presentation.ts`                             |     90 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/provenance.ts`                               |     50 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/quality.ts`                                  |    170 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/sql-csv.ts`                                  |     20 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/sql-finding-link.ts`                         |     20 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/sql-format.ts`                               |      9 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/sql-formatter.ts`                            |     99 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/sql-highlighter.ts`                          |     22 | Labels / Formatierung / Daten- und Aktionsgrenzen |
| `app/utils/statistics.ts`                               |    126 | Labels / Formatierung / Daten- und Aktionsgrenzen |
