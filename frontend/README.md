# Kulturbytes Admin Dashboard — Nuxt 4 Administration UI

Das **Kulturbytes Admin Dashboard** ist die responsive Administrationsoberfläche für
Kulturbytes/Uranus. Das Frontend basiert auf **Nuxt 4**, **Vue 3**, **TypeScript**, **Pinia**
und **Zod** und verbindet Datenqualität, Moderation, Geodaten, Event-Administration,
Beziehungsanalyse und Betriebsworkflows in einer geschützten Weboberfläche.

## Funktionen der Admin-Oberfläche

- Dashboard, Inbox und priorisierte Arbeitslisten.
- Veranstaltungen, Orte, Räume, Organisationen, Benutzer/Teams und Bilder.
- Activity, filterbare Findings, Reviews, Markierungen und Prüfläufe.
- Globale Entity-Suche und direkte Navigation zwischen verknüpften Datensätzen.
- Geo Scope, Nominatim-Standortvorschläge und Geocoding-Review.
- D3-Statistiken und Entity-Relationship-Graph.
- Benachrichtigungen, SQL-Datenherkunft, SQL-Diagnostik und abgesicherte SQL Console.
- SSR, responsive/mobile UI, Runtime-Contracts mit Zod und Production-CSP-Tests.

Backend und Sicherheitsmodell: [Kulturbytes Admin API](../backend/README.md).
Deployment und Betrieb: [Ansible-README](../ansible/README.md).
Projektübersicht: [Repository-README](../README.md).

## Start und Versionen

Node gemäß `package.json`, CI verwendet fest **22.22.3**; pnpm **12.3.4** über `packageManager`.

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env  # nur bei der ersten Einrichtung
pnpm dev
```

Browser http://127.0.0.1:3000. FastAPI separat starten, standardmäßig Port 8000.
`NUXT_ADMIN_API_BASE=http://127.0.0.1:8000` bleibt ausschließlich serverseitig.
Bei getrennten Containern eine passende Backend-Origin konfigurieren. Nitro überträgt dort
auch Login-Passwörter und Sitzungscookies: außerhalb von Loopback einen verschlüsselten
Transport verwenden (HTTPS oder authentifizierter verschlüsselter Kanal).
Keine automatische Backend-Migration oder Domain-Schreiboperation.

## Authentifizierung

Die „Admin-Anmeldung“ verwendet eigene FastAPI-Admin-Konten. Uranus-Login und Organisationsrechte
werden nicht verwendet. Die globale Berechtigung steht separat in `admin.auth_system_admin`;
ein korrektes Passwort allein genügt nicht. Der Betreiber legt Konten über das CLI an.
[Auth-Vertrag und Betrieb](../backend/docs/authentication.md).

Browser → `/api/admin/auth/{login,session,logout}` → Nitro → FastAPI. Der Browser hält nur ein
HttpOnly-Sitzungscookie (Production: Secure, SameSite=Strict, host-only); keine Zugangsdaten in
localStorage, Pinia, SSR-Payload oder URLs. Login-Antworten enthalten nur Identität/Berechtigung,
keine Tokens. Logout widerruft die Sitzung; Ablauf/Sperrung/Rechteentzug verwerfen Verwaltungsdaten.
Ohne Credential bzw. bei ungültiger Sitzung 401, fehlende globale Vergabe 403, Auth-Infrastruktur-
fehler 503. Loginlimits liefern 429. Für Cookie-Schreibrequests wird `X-Admin-CSRF: 1` gesetzt;
FastAPI verlangt zusätzlich die exakte Browser-Origin aus `AUTH_PUBLIC_ORIGIN`.

Production benötigt HTTPS zwischen Browser und Admin-Origin; FastAPI `AUTH_PUBLIC_ORIGIN` muss
diese Origin exakt enthalten. Lokal muss sie zur verwendeten Browseradresse passen, z. B.
`http://127.0.0.1:3000`. Der lokale Sitzungscookiename gilt nur für `pnpm dev` und
FastAPI development/test; ein Production-Build erwartet das Secure-Cookie.

`/login` ist die einzige öffentliche Seite. Alle anderen Routen erfordern vor dem
SSR-/Client-Render eine vom Backend bestätigte Systemadmin-Sitzung. Nach Login wird das
validierte interne Ziel einschließlich Query/Hash wiederhergestellt. 401 beendet den lokalen
Admin-Zustand; 403 zeigt einen Berechtigungsfehler ohne Logout. Die Login-Seite verwendet ein
eigenes Layout ohne Admin-Shell. Architektur und Testfälle: [Route-Authentifizierung](docs/auth-routing.md).

Auch lokal wird die dedizierte Login-Seite verwendet. Der Backend-Development-Override bleibt
auf development/test beschränkt; die Oberfläche injiziert keine Development-Credentials.
Die frühere manuelle Token-Eingabe wird nicht mehr global eingebunden.

## Seiten und API

| Seite                                     | Backend                                                                          |
| ----------------------------------------- | -------------------------------------------------------------------------------- |
| `/` und `/quality`                        | GET dashboard/summary und findings                                               |
| `/findings`                               | GET findings; Standard persisted, explizite Live-Diagnose, Filter/Pagination     |
| `/inbox`                                  | GET inbox; GET admins; POST/PATCH assignments                                    |
| `/activity`                               | GET dashboard/activity; Typ/Organisation/Zeitraum oder separate undatierte Liste |
| `/queues/partner_requests`                | GET work-queues/partner_requests                                                 |
| `/queues/team_invitations`                | GET work-queues/team_invitations                                                 |
| `/queues/user_activation`                 | GET work-queues/user_activation                                                  |
| `/checks`                                 | GET/POST check-runs                                                              |
| Finding-Detail bei persistiertem Erstfund | PATCH finding-reviews                                                            |
| Entity-Details                            | GET entities/{type}/{key}/timeline                                               |

Die fachlichen Backend-Pfade haben Prefix `/api/v1`; Anmeldung verwendet `/auth`. Browserzugriff ausschließlich über gleiche Origin:
`/api/admin/api/v1/findings` → `${NUXT_ADMIN_API_BASE}/api/v1/findings`.
Health/ready und der bestehende spezielle Venue-Endpunkt bleiben für Diagnose verfügbar.

Proxy-Allowlist: exakte bekannte Routen, GET sowie POST für Login/Logout, check-runs,
record-marks und assignments; PATCH ausschließlich für finding-reviews sowie streng validierte
Markierungs-/Assignment-UUIDs. Keine Domain-Updates. Begrenzte Querynamen, keine doppelten Parameter,
feste konfigurierte Origin ohne Pfade/Credentials, keine Redirects. Nur explizites Authorization, das vorgesehene Sitzungscookie und Origin/CSRF werden
weitergeleitet; keine fremden Cookies/Headers. Antworten `private, no-store`.
Reviews verwenden einen strikt Zod-validierten Body. Alle Aufrufe haben 10 Sekunden Upstream-Timeout. Prüfläufe werden mit HTTP 202 eingereiht;
ein separater Worker verarbeitet sie. Die Check-Seite pollt queued/running-Läufe alle zwei Sekunden
und beendet Polling bei Abschluss, Fehler, Auth-Verlust oder Unmount.

Bekannte Fehlercodes werden ausschließlich aus streng validiertem JSON mit passendem HTTP-Status
erhalten. Fehlermeldungen werden lokal erzeugt; Tracebacks und beliebige Upstream-Daten bleiben
sanitisiert. [OpenAPI-Snapshot](docs/openapi.json) und `shared/contracts.ts` beschreiben den Vertrag;
Responses werden zur Laufzeit validiert. Keine Demo-Daten außerhalb der Tests.

`EntityTimeline` lädt auf allen sechs Entity-Detailseiten eine serverseitig aggregierte,
stabil sortierte Seite und weitere Seiten nur über den opaken Cursor. Deep Links werden gegen
eine geschlossene interne Allowlist validiert; fehlende Zeitpunkte erscheinen nicht erfunden.

`/inbox` besitzt URL-basierte Filter für alle/eigene/nicht zugewiesene, kritische, heute fällige
und überfällige Aufgaben. Das Backend ersetzt ein zugewiesenes Finding durch genau einen
Assignment-Eintrag. `AssignmentEditor` lädt die begrenzte Admin-Auswahlliste erst im
Finding-Detail; Versionen verhindern verlorene parallele Änderungen. Fälligkeitstage werden als
Europe/Berlin-Kalendertage einschließlich DST in einen belegten `due_at`-Zeitpunkt umgerechnet.

`/geocoding/:id` zeigt die betroffene Entität und unverändert gelieferte Quelladresse vor dem
Kandidatenvergleich. Leaflet 1.9 stellt die Kandidaten auf einer interaktiven OSM-Rasterkarte dar;
Marker und Kandidatenliste teilen dieselbe Auswahl. Status, Matchgründe und Retry-Zustände sind
deutsch; es existiert weiterhin keine Übernahme- oder Uranus-Schreibaktion.

### Geocoding-Karte konfigurieren

Leaflet wird erst in `onMounted` importiert, CSS wird lokal gebündelt. Die kleine Rasterbibliothek
wird als separates Paket geladen (ca. 43 kB gzip im Produktionsbuild) und benötigt weder
WebGL noch Worker oder API-Schlüssel; für maximal fünf Marker sind keine
Vektorkartenfunktionen erforderlich. Sie unterstützt Tastatur-Pan/Zoom, Touch und eigene native
Marker-Buttons. [Leaflet API](https://leafletjs.com/reference.html).

Für die manuelle interne Prüfung ist **OpenStreetMap Standard (OSMF)** voreingestellt.
Ein eigener Tile-Server oder API-Schlüssel ist nicht erforderlich. Der separat dokumentierte
Nominatim-Dienst bleibt ausschließlich für Geocoding zuständig.

- `NUXT_PUBLIC_MAP_TILE_URL`: Standard `https://tile.openstreetmap.org/{z}/{x}/{y}.png`.
  Die URL kann durch einen anderen freigegebenen OSM-basierten Rasteranbieter ersetzt werden;
  ein ausdrücklich leerer Wert deaktiviert Kartenkacheln.
  Unterstützt werden feste Hosts, optionale Pfadpräfixe und `.png`, `.jpg`, `.webp`;
  alternativ ein bereits bereitgestellter Same-Origin-Pfad. Keine Queryparameter,
  Credentials, `{s}`-Subdomains, API-Schlüssel oder dynamischen Entity-Werte.
- `NUXT_PUBLIC_MAP_TILE_ATTRIBUTION`: zusätzliche Provider-Attribution als Plaintext.
- `NUXT_PUBLIC_MAP_TILE_ATTRIBUTION_URL`: optionaler HTTPS-Link zur Provider-Attribution.

Die [OSMF Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) erlaubt
normales interaktives Ansehen. Die Karte lädt nur sichtbare Kacheln, zeigt OSM-Attribution und
sendet den Browser-User-Agent sowie die Admin-Origin als Referrer. Browsercache und bedingte
Requests folgen den HTTP-Cache-Headern des Providers; keine Cache-Buster oder No-Cache-Header.
Kein Prefetch, Offline-Download, automatisierter Kartenscan oder Retry. Der öffentliche Dienst
bietet keine Verfügbarkeitsgarantie; bei größerem Bedarf einen passenden Anbieter konfigurieren
und dessen Bedingungen/Zoomabdeckung (1–19) prüfen. Bei Ausfall wird nicht automatisch zu einem
anderen Provider gewechselt. Zusätzliche Provider-Credits bleiben beim OSM-Standard leer, da die
OSM-Attribution bereits separat sichtbar ist.

Externe Bilder benötigen ausschließlich die **exakte Tile-Origin in `img-src`**. `connect-src`,
`worker-src`, `script-src` und `style-src` brauchen keine Änderung; kein `unsafe-eval` und keine
zusätzliche Inline-Freigabe. Eine strengere Nginx-CSP lässt sich nicht durch Nuxt lockern.
Ansible setzt Runtime-Werte und CSP gemeinsam über die [Map-Variablen](../ansible/README.md#geocoding-kartenkacheln).
Same-Origin-Konfiguration erzeugt keinen generischen Proxy und stellt selbst keine Tiles bereit.

Der Browser sendet normale numerische XYZ-Pfade, seine IP und nur die Admin-Origin als Referrer.
Kandidatenregionen sind dadurch beim Provider erkennbar; Entity-Namen, Adressen, E-Mails,
Admin-API-Credentials und Detail-URLs werden nicht in Tile-URLs/Headers eingebaut. Es gibt keine
clientseitige Geocoding-Abfrage. OSM-Attribution und zusätzliche Provider-Credits bleiben sichtbar.
Die vollständige Kandidatenliste funktioniert ohne Karte. Explizit leere/ungültige Konfiguration,
Import-/Tile-Fehler oder 12 Sekunden ohne Ladeabschluss zeigen einen Inline-Hinweis ohne Retry-Loop.

Playwright interceptiert alle konfigurierten Test-Tiles mit einer lokalen synthetischen SVG-Fixture;
auch Produktions-CSP und Screenshots benötigen kein externes Internet. Die Testkacheln sind
keine geografische Evidenz und werden nicht mit der Anwendung ausgeliefert.

Die Activity-Seite verwendet kompakte Zeilen, deutsche Typ-Badges und Berliner Tagesgruppen.
Typzahlen zählen ausschließlich die sichtbare Seite; undatierte Einträge bleiben ohne Chronologie.
[Darstellung, Grenzen und Vorher-/Nachher-Screenshots](docs/activity-stream.md).
Öffentliche Links und Bild-URLs kommen ausschließlich aus dem Activity-Response.
Bild-Einträge zeigen 320px-Vorschauen im Original-Seitenverhältnis, dargestellt mit 96/128px
Breite, lazy/async geladen;
bei Ladefehlern bleibt das Typ-Icon. Ein Klick lädt eine größere, unbeschnittene Bildansicht
im gemeinsamen `AppModal` (auch für Befunddetails). Escape/Schließen stellt den Fokus zurück.
Interne Actions und Markierungen bleiben erhalten.
[Öffentliche Routen und Preview-Vertrag](../backend/docs/contracts.md#activity-previews-and-public-links)
sowie [CSP-/Deployment-Voraussetzungen](../backend/docs/development.md#image-csp-and-deployment-verification)
sind zentral dokumentiert. Insbesondere muss `img-src` die öffentliche Image-API erlauben;
eine zusätzliche Nuxt-CSP kann eine strengere Proxy-CSP nicht lockern.

## Semantik und Bedienung

`entity_key` unterstützt UUIDs und Composite Keys. `entity_id` ist nur ein veralteter nullable
UUID-Alias. Die Oberfläche verwendet entity_key. Finding-Actions enthalten bekannte Route,
Objektschlüssel und einen exakt dagegen validierten internen href; Bearbeitungsrouten werden
nicht aus Texten erraten. Für noch nicht vorhandene Objektdetails bleibt action NULL.

`priority_score` bestimmt die globale Reihenfolge; diskrete priority und priority_reasons stehen
im Detail. Terminanzahlen sind Informationen, kein zusätzlicher versteckter Sortierschlüssel.

Activity zeigt reale created_at-Werte. Unknown-Zeitpunkte haben eine separate Identitätsreihenfolge;
es gibt kein erfundenes Datum. Today ist lokaler Kalendertag, 24h/7d sind gleitende Zeiträume.
Einladungsalter beruht auf invited_at; created_at ist kein Beitritt. User-Aktivierungsstatus liefert
keine Aussage über Login/Inaktivität. Partneranfragen liefern keine rekonstruierte Entscheidungshistorie.

Ein Prüflauf benötigt die optionale Admin-Ablage im Backend. Nur vollständig erfolgreiche
Prüfungen schließen abgedeckte Findings. Die persistierte Liste bietet open/in_progress/snoozed/
exception; Snooze braucht Ablauf, Ausnahme einen Grund. Das bestehende optionale Review-Feld für
eine Uranus-User-UUID ist keine Admin-Zuständigkeit. Die neue Zuweisung verwendet ausschließlich
aktive unabhängige Admin-Konten. Es gibt keinen manuellen resolved-Schalter. Reviews und
Assignments ändern keine Domain-Daten.

Die Dashboard-Vorschau lädt `active_only=true`: alle gespeicherten Status außer
`resolved`, einschließlich Zurückstellungen und Ausnahmen. Gesamtzahl und Links zur
Arbeitsliste behalten diesen Filter sowie Severity und Geo Scope bei. `/findings`
ohne diesen URL-Filter zeigt weiterhin die Historie; „Filter zurücksetzen“ entfernt
auch die Einschränkung auf nicht behobene Befunde.

Dashboard-/Finding-Stores schützen vor verspäteten Responses und entfernen Daten bei Authverlust.
Neue Activity-/Queue-/Check-Seiten laden ausschließlich clientseitig, verwenden Request-IDs und
verwerfen alte Daten beim Filter-/Zugangswechsel. Datumsanzeige Deutsch/Europe-Berlin; das
Snooze-Eingabefeld nennt ausdrücklich die lokale Browserzeit und sendet einen ISO-Zeitpunkt.

## Production-CSP und Zod

Die Production-App benötigt **kein `'unsafe-eval'`**. Als Script-Direktive kann die
Deployment-CSP weiterhin Folgendes verwenden:

```text
Content-Security-Policy: script-src 'self' 'unsafe-inline';
```

Dies ist nur die Script-Direktive; weitere Direktiven müssen zum Deployment passen.
`'unsafe-inline'` bleibt vorerst für die Inline-Scripts erlaubt. Der spätere Wechsel auf
Nonces/Hashes ist eine separate Aufgabe. Die Live-Nginx-Konfiguration wird durch diese
Anwendungsänderung nicht verändert.

Die zentrale [Zod-Konfiguration](shared/zod.ts) setzt beim Auswerten des Moduls
`z.config({ jitless: true })` und exportiert erst danach `z`. Alle Schemas in
[`shared/contracts.ts`](shared/contracts.ts) importieren diesen Export. Die statische
ES-Modul-Abhängigkeit garantiert die Konfiguration vor der Schema-Konstruktion, unabhängig
von Nuxt-Plugin-Reihenfolge, SSR, Hydration oder später geladenen Seiten. Auch die Type-Imports
verwenden diesen Einstieg. Neue Schemas müssen Zod ebenfalls daraus importieren; kein
Laufzeit-Import direkt aus `zod` oder seinen Unterpaketen außerhalb des Bootstrap-Moduls.

Zod kann Objektvalidierung durch erzeugten JavaScript-Code beschleunigen. Schon seine
Verfügbarkeitsprüfung mit `new Function('')` kann eine CSP-Verletzung melden, selbst wenn
Zod die Exception abfängt. `jitless` deaktiviert diese Pfade vor der ersten Schema-Nutzung.
Der Anwendungscode verwendet weder `zod/compile` noch `z.compile()` oder eigene Parser über
`z.withParser()`. Der Regressionstest schützt diesen Standardpfad vor unbeabsichtigten Opt-ins.
Insbesondere kann
`z.compile()` die globale `jitless`-Einstellung umgehen; siehe
[Zod: Content Security Policy](https://zod.dev/compile#content-security-policy).

`tests/unit/zod-csp.test.ts` lädt die echten Schemas mit gesperrtem `Function`-Konstruktor
und prüft gültige/ungültige Daten sowie das Ausbleiben jeglicher Codegenerierungsversuche.
Ein zusätzlicher Quellcode-Check schützt den zentralen Importweg und verbietet Compiler-Opt-ins.
`tests/e2e/csp.spec.ts` setzt ausschließlich auf Testantworten einen erzwingenden CSP-Header
ohne `'unsafe-eval'`, prüft Dashboard/Findings und erfasst `securitypolicyviolation`-Events.
Dieser Test läuft mit `TEST_PRODUCTION=1` gegen `.output/public/_nuxt/`, auch in CI.
Bei Development-E2E wird er ausdrücklich übersprungen. Bloße `Function`-Vorkommen in
Dependency-Fallbacks des Bundles sind kein Fehlernachweis; entscheidend ist der Browserlauf.

## Tests und Build

```bash
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
TEST_PRODUCTION=1 pnpm test:e2e
```

CI führt Installation/Lint/Typen/Unit/Build und Chromium-Tests gegen den Produktionsbuild aus,
getrennt von Backend-Jobs. SHA-gepinnte Actions, feste Node-Version, pnpm aus packageManager,
Lockfile strikt und pnpm-Cache. Branch-Protection/Required-Checks werden nicht automatisch verändert.
Playwright startet seinen eigenen Loopback-Server auf Port 3100; Tests verwenden synthetische
Responses. Für Login/Logout verwendet Playwright einen kontrollierten lokalen Test-Backendprozess
auf Port 31902; dieser wird nie in die Anwendung eingebunden. Backend/PostGIS-Integration wird
separat im Backend geprüft.

Ergebnisse und Grenzen: [Verifikation](docs/verification.md).
Verbindliche Fach-/Sicherheitsverträge: [Backend-Verträge](../backend/docs/contracts.md).

## Bewusst offen

Uranus-SSO, MFA und Self-Service-Kontowiederherstellung, fachliches Editieren, persönlicher Sichtungsstand,
vollständiges Auditjournal, automatische Geocodierung/Merges und externe URL-/Dateiabfragen.
Portal-Bildziele sowie Space-Feature-Zuordnungen bleiben bis zur eindeutigen Quellklärung offen.

## Design System v2

Der [Design Guide v2](docs/design-system.md) ist der kanonische UI-Vertrag.
Der [vollständige Frontend-Audit](docs/ui-ux-audit.md) dokumentiert den main-Ausgangsstand,
alle Routen, Sprachabweichungen und den Migrationsplan. `/events/:id` ist der erste
Record-Detail-Pilot; andere Detailtypen folgen in eigenen PRs.

Markdown wird zunächst ausschließlich für die verifizierte Veranstaltungsbeschreibung
verwendet. markdown-it wurde wegen seines konfigurierbaren Tokenparsers gewählt; Vue
rendert nur freigegebene Elemente, niemals HTML-Strings. Keine Raw-HTML-/Bildunterstützung,
keine zusätzliche CSS-Library, keine CSP-Ausnahme. Softbreaks werden zu Leerzeichen,
Hardbreaks zu `<br>`; Leerzeilen trennen Absätze. Source-Markdown erlaubt nur validierte
absolute http/https/mailto-Links; sämtliche relativen Admin-Links bleiben Text. Externe
Links behalten neuen Tab, noopener/noreferrer, no-referrer und einen zugänglichen Hinweis.
Details und Feldnachweis im Audit.

Der Pilot zeigt Beziehungen bewusst als allgemeine Liste „Verknüpfte Datensätze“ mit
25 Einträgen pro Seite, Gesamtzahl und Pagination, sortiert nach Typ/Name/Schlüssel.
Das sind keine vollständigen semantischen Gruppen und keine chronologische Terminliste.
Veranstalter, Standardort/-raum und Termin-Gesamtzahl kommen unabhängig davon aus der
Event-Projektion; Standardwerte gelten nicht zwingend für jeden Termin. Medien sind über
die gemeinsame Pagination erreichbar. Getrennte Fachbereiche folgen erst mit einem eigenen
begrenzten Backend-Vertrag; dieser PR ändert keine Backend- oder Source-Semantik.
`event-detail-v2.spec.ts` prüft 1440/1024/390/360px und sichere Inhalte auch im Production-Build;
`layout-consistency.spec.ts` erzeugt Review-Aufnahmen aller Hauptrouten auf drei Größen.

## Gemeinsame Datenansichten

[Informationsarchitektur, Kennzahlen-Semantik, UI-Bausteine und Seiten-Audit](docs/data-pages.md)
beschreiben die gemeinsame Designsprache. „Neu eingegangen“ ist periodengebunden;
Dringlichkeit und Qualitätszahlen sind Bestandswerte. Ergebnisübersichten trennen stets
API-Gesamtzahlen von Aufschlüsselungen der sichtbaren Seite.

### Activity: Benutzer und Organisationen

Benutzereinträge zeigen ihre E-Mail nur im geschützten Admin-Response. Vorhandene Avatare
werden direkt vom öffentlichen Uranus-Avatar-Endpunkt geladen (128px, Modal 512px);
fehlende Dateien fallen auf das Benutzer-Icon zurück. Organisationslogos und Ortsbilder behalten ihr
Seitenverhältnis und bekommen denselben Innenabstand. Vorhandene Adressbestandteile und geprüfte
WGS84-Koordinaten werden angezeigt; der OpenStreetMap-Link lädt erst beim Öffnen die Karte.
Es gibt keine zusätzlichen JSON-Metadatenanfragen pro Zeile und kein Geocoding.
Siehe [Activity-Vertrag](../backend/docs/contracts.md#user-avatars-and-organization-locations).

## Domain inspection

Events, venues, spaces, organizations, users and images have paginated list and
UUID detail pages. Activity remains the compact list-row reference; event, organization,
venue and space details use the Record Detail v2 pattern. EntityDetailPage retains retrieval,
stale/auth/identity handling and Timeline; domain presenters override the EntityHero context.
Organizations show event/venue/membership counts (including invitations) and address;
venues show organization, room count, address and a public link only when supplied;
spaces show the verified parent venue and organization once in their hero context.
RecordRelations retains the global bounded relation page and other query parameters;
RecordWorkflowSummary shares count semantics, and RecordLocation uses the existing OSM
helper only for provided coordinates (currently organization previews). Null is unknown,
not zero. Technical metadata follows Timeline. Users/images await migration. No source writes,
API semantics, Markdown fields or external requests are added. Search/filter/page state is
URL-based. Detail relations are independently paginated; graph, marks and exact
finding links remain available. Source timestamps retain their actual meaning.
The global create action remains disabled until an authorized Uranus write adapter
exists; the independent admin login does not grant Uranus domain write permissions.

### Remaining domain-management prerequisites

The six list/detail sections remain read-only. User search includes username as well
as display name/UUID. Event location facts are labeled Standardort/Standardraum;
related event dates retain their own effective locations. Invitation timestamps and
membership creation timestamps remain distinct; no joined-at/last-login history is
inferred. The global create control stays disabled until a verified server-side
Uranus delegation and per-operation authorization contract exists. There is no client
capability override or browser-visible Uranus credential. See the current audit in
`backend/docs/open-issues-audit.md` and the write-contract matrix in `backend/docs/contracts.md`.

## SQL Workspace

Der [SQL Editor](docs/sql-editor.md) öffnet verfügbare registrierte Finding-Diagnosen in einem
breiten Nur-Lese-Workspace mit Kontextspalte, formatiertem SQL, Parametern und Ergebnissen.
SQL / Datenherkunft verwendet dieselben Komponenten mit Quell-Tabs und Nachbearbeitung.
Auch `copy_sql` wird vor dem Kopieren formatiert; Ergebnisse lassen sich als Tabelle, JSON
oder CSV anzeigen bzw. herunterladen.
Die registrierte Diagnose sendet weiterhin ausschließlich die Finding-ID, niemals den sichtbaren SQL-Text.

### Interaktive READ-ONLY Console (Phase 3)

Datasource **Uranus**, Scope `uranus.*`: Systemadministratoren können bewusst alle
Tabellen und Spalten lesen, auch sensible Uranus-Werte. Startquery:
`SELECT * FROM uranus.event LIMIT 50;`. Keine Maskierung oder Legacy-View-Pflicht.
Finding-Startqueries behalten ihre serverseitigen `uranus.*`-Relationen.
`admin.*` und Systemkataloge bleiben gesperrt. Ausschließlich `uranus_console_reader`,
READ ONLY, keine Phase 4. Theme, Editor, Protokoll und Grenzen bleiben unverändert.

`/sql` und „SQL bearbeiten“ im Finding-Workspace verwenden denselben SQL-Editor und
Ergebnisbereich. CodeMirror 6 wird clientseitig lazy geladen und verwendet dieselbe
Prism-/CSS-Definition wie der Readonly-Renderer. Formatieren und Copy verwenden den
bestehenden PostgreSQL-Formatter. Die registrierte Diagnose bleibt separat verfügbar.
Freies SQL läuft über den exakten Same-Origin-WebSocket und ausschließlich den
Console-Reader: 5s Statement, 8s Gesamtdeadline, 50/500 Zeilen, quittierte Batches,
echter Cancel. Keine Writes und keine serverseitige Query-History.
[Runtime, Protokoll, Grenzen und Tests](../backend/docs/sql-console-runtime.md).

## Globale Suche und Command Palette

**Ctrl+K / Cmd+K** oder der Suchtrigger im Desktop-/Mobile-Header öffnet die globale
Palette auf geschützten Seiten. Sie durchsucht lokale Admin-Navigation sowie Benutzer,
Organisationen, Orte, Räume, Veranstaltungen und Bilder. Benutzer sind auch über E-Mail
auffindbar; fehlende Anzeigenamen fallen auf Username, E-Mail und zuletzt UUID zurück.
Entity-Autocomplete, globale Suche und Graph-Root-Suche teilen kanonische Suchfelder,
Labels und Ranking (exakte UUID, exaktes Feld, Präfix, Teilstring, Label, Schlüssel).

`GET /api/v1/search`: q 2–120 Zeichen, standardmäßig fünf und maximal zehn Treffer pro
Typ, insgesamt maximal 60; optional `types=user,venue`. Die Palette sucht systemweit,
unabhängig von Zeitraum/Gebiet, und öffnet serverseitig erzeugte Detail-Actions.
Keine Suchhistorie, Browser-Persistenz, Analytics oder Query-Logs. Source bleibt read-only;
keine Migrationen/Grants/Worker-Änderungen. Backend und Frontend gemeinsam ausrollen.

Kanonische Felder, Privacy, Queryplan und spätere Uranus-eigene pg_trgm-Indizes:
[Suchvertrag](../backend/docs/contracts.md#global-search-and-command-palette).
