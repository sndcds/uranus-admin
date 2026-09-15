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
Bei getrennten Containern eine passende interne Backend-Origin konfigurieren.
Keine automatische Backend-Migration oder Domain-Schreiboperation.

## Authentifizierung

Ein Uranus-Login ist keine globale Adminberechtigung. Die Backend-Integration bleibt produktiv
bewusst gesperrt. Ohne Credential 401, fehlende Berechtigung 403, unkonfigurierte Auth/DB 503.
Es gibt keine erfundene Loginroute, Tokenausgabe oder automatische Vergabe von Adminrechten.

Nur lokale Entwicklung: FastAPI muss ihren Development-Override aktivieren. Im Frontend
`NUXT_PUBLIC_ALLOW_DEV_TOKEN_ENTRY=true` setzen, `pnpm dev` starten und unter
„Lokaler Entwicklungszugang“ den selbst bereitgestellten DEV_ADMIN_TOKEN eingeben.
Der Token bleibt ausschließlich in einer Closure der aktuellen Nuxt-App: kein localStorage,
Cookie, Pinia-State, SSR-Payload, URL oder Log. Reload entfernt ihn. Ein Production-Build entfernt
die Eingabe unabhängig vom Flag. Ein Zugangwechsel verwirft geladene Verwaltungsdaten und
invalidiert laufende Detailansichten. Das Development-Subject ist kein Uranus-User.

## Seiten und API

| Seite | Backend |
| --- | --- |
| `/` und `/quality` | GET dashboard/summary und findings |
| `/findings` | GET findings; Standard persisted, explizite Live-Diagnose, Filter/Pagination |
| `/activity` | GET dashboard/activity; Typ/Organisation/Zeitraum oder separate undatierte Liste |
| `/queues/partner_requests` | GET work-queues/partner_requests |
| `/queues/team_invitations` | GET work-queues/team_invitations |
| `/queues/user_activation` | GET work-queues/user_activation |
| `/checks` | GET/POST check-runs |
| Finding-Detail bei persistiertem Erstfund | PATCH finding-reviews |

Alle Backend-Pfade haben Prefix `/api/v1`. Browserzugriff ausschließlich über gleiche Origin:
`/api/admin/api/v1/findings` → `${NUXT_ADMIN_API_BASE}/api/v1/findings`.
Health/ready und der bestehende spezielle Venue-Endpunkt bleiben für Diagnose verfügbar.

Proxy-Allowlist: exakte bekannte Routen, GET, zusätzlich ausschließlich POST check-runs und
PATCH finding-reviews. Keine Domain-Updates. Begrenzte Querynamen, keine doppelten Parameter,
feste konfigurierte Origin ohne Pfade/Credentials, keine Redirects. Nur Authorization wird
weitergeleitet; keine Cookies/fremden Headers. Antworten `private, no-store`.
Reviews verwenden einen strikt Zod-validierten Body. Reads haben 10 Sekunden Upstream-Timeout,
synchrone Prüfläufe/Reviews 120 Sekunden; ein Timeout beweist keinen erfolgreichen Abschluss.

Bekannte Fehlercodes werden ausschließlich aus streng validiertem JSON mit passendem HTTP-Status
erhalten. Fehlermeldungen werden lokal erzeugt; Tracebacks und beliebige Upstream-Daten bleiben
sanitisiert. [OpenAPI-Snapshot](docs/openapi.json) und `shared/contracts.ts` beschreiben den Vertrag;
Responses werden zur Laufzeit validiert. Keine Demo-Daten außerhalb der Tests.

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
Responses. Backend/PostGIS-Integration wird separat im Backend geprüft.

Ergebnisse und Grenzen: [Verifikation](docs/verification.md).
Verbindliche Fach-/Sicherheitsverträge: [Backend-Verträge](../backend/docs/contracts.md).

## Bewusst offen

Produktive Uranus-Systemadmin-Autorisierung, fachliches Editieren, persönlicher Sichtungsstand,
vollständiges Auditjournal, automatische Geocodierung/Merges und externe URL-/Dateiabfragen.
Portal-Bildziele sowie Space-Feature-Zuordnungen bleiben bis zur eindeutigen Quellklärung offen.
