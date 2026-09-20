# Kulturbytes Admin Dashboard

Nuxt 4 / Vue 3 / Pinia / TypeScript / Zod. Dashboard, filterbare Findings, Activity für neun
Objektarten, Partner-/Einladungs-/Aktivierungslisten, Prüfläufe und menschliche Reviews.
Das ursprüngliche HTML-Mockup bleibt unverändert.

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
| `/activity`                               | GET dashboard/activity; Typ/Organisation/Zeitraum oder separate undatierte Liste |
| `/queues/partner_requests`                | GET work-queues/partner_requests                                                 |
| `/queues/team_invitations`                | GET work-queues/team_invitations                                                 |
| `/queues/user_activation`                 | GET work-queues/user_activation                                                  |
| `/checks`                                 | GET/POST check-runs                                                              |
| Finding-Detail bei persistiertem Erstfund | PATCH finding-reviews                                                            |

Die fachlichen Backend-Pfade haben Prefix `/api/v1`; Anmeldung verwendet `/auth`. Browserzugriff ausschließlich über gleiche Origin:
`/api/admin/api/v1/findings` → `${NUXT_ADMIN_API_BASE}/api/v1/findings`.
Health/ready und der bestehende spezielle Venue-Endpunkt bleiben für Diagnose verfügbar.

Proxy-Allowlist: exakte bekannte Routen, GET sowie POST für Login/Logout, check-runs und
record-marks; PATCH ausschließlich für finding-reviews und streng validierte Markierungs-UUIDs. Keine Domain-Updates. Begrenzte Querynamen, keine doppelten Parameter,
feste konfigurierte Origin ohne Pfade/Credentials, keine Redirects. Nur explizites Authorization, das vorgesehene Sitzungscookie und Origin/CSRF werden
weitergeleitet; keine fremden Cookies/Headers. Antworten `private, no-store`.
Reviews verwenden einen strikt Zod-validierten Body. Alle Aufrufe haben 10 Sekunden Upstream-Timeout. Prüfläufe werden mit HTTP 202 eingereiht;
ein separater Worker verarbeitet sie. Die Check-Seite pollt queued/running-Läufe alle zwei Sekunden
und beendet Polling bei Abschluss, Fehler, Auth-Verlust oder Unmount.

Bekannte Fehlercodes werden ausschließlich aus streng validiertem JSON mit passendem HTTP-Status
erhalten. Fehlermeldungen werden lokal erzeugt; Tracebacks und beliebige Upstream-Daten bleiben
sanitisiert. [OpenAPI-Snapshot](docs/openapi.json) und `shared/contracts.ts` beschreiben den Vertrag;
Responses werden zur Laufzeit validiert. Keine Demo-Daten außerhalb der Tests.

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
exception; Snooze braucht Ablauf, Ausnahme einen Grund. Zuweisung verlangt eine existierende
User-UUID. Es gibt keinen manuellen resolved-Schalter. Reviews ändern keine Domain-Daten.

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
UUID detail pages, using the Activity visual language. Search/filter/page state is
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

[SQL / Datenherkunft – registrierte Queries, Sicherheitsmodell und Coverage](../backend/docs/sql-provenance.md).
