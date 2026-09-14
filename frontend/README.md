# Kulturbytes Admin Dashboard

Nuxt 4 / Vue 3 / TypeScript, TailwindCSS 4 über das Vite-Plugin, Pinia mit `@pinia/nuxt`.
Die unveränderte visuelle Referenz liegt in diesem Verzeichnis:
[kulturbytes-admin-dashboard-mockup.html](kulturbytes-admin-dashboard-mockup.html). Das Frontend wurde ergänzt; die bestehende
FastAPI-Anwendung und ihr Datenmodell werden nicht verändert.

## Installation und Start

Node gemäß `package.json` (z.B. 22.22.3) und pnpm 12.3.4 verwenden:

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env
pnpm dev
```

Browser: **http://127.0.0.1:3000**. `pnpm dev` bindet ausschließlich an Loopback.
FastAPI wird separat im Ordner [backend/](../backend/README.md) gestartet und läuft auf Port 8000.
Es gibt kein automatisches Starten, Migrieren oder Verändern der Backend-Datenbank.

```env
NUXT_ADMIN_API_BASE=http://127.0.0.1:8000
NUXT_PUBLIC_ALLOW_DEV_TOKEN_ENTRY=false
```

`NUXT_ADMIN_API_BASE` ist ausschließlich serverseitige runtimeConfig. Es gibt keinen
serverseitig hinterlegten Admin-Schlüssel. Für Container: **127.0.0.1/localhost bezeichnet
den Nuxt-Server bzw. dessen Container, nicht den Browser-Rechner.** Bei getrennten Containern
z.B. `NUXT_ADMIN_API_BASE=http://admin-api:8000` konfigurieren. Keine öffentliche Freigabe
oder produktives Deployment ist Teil dieses Projektschritts.

## Authentifizierung

Uranus-/Admin-Systemlogin ist im vorhandenen Backend noch nicht integriert. Daher ist
der normale Zustand ohne bereitgestellten Zugang ehrlich gesperrt (401). 403 bedeutet
fehlende Berechtigung; 503 bedeutet nicht bereite API/DB oder nicht konfigurierte Backend-Auth.
Eine Frontend-Navigation umgeht diese Prüfung nicht. Es gibt keine erfundene Login-Route,
Token-Ausgabe, Benutzeridentität oder automatische Vergabe von Adminrechten.

Für **explizite lokale Entwicklung** kann die bereits vorhandene Bearer-Authentifizierung
der FastAPI verwendet werden:

1. FastAPI muss bereits ausdrücklich mit ihrem Development-Override konfiguriert sein.
2. Im Frontend `.env` `NUXT_PUBLIC_ALLOW_DEV_TOKEN_ENTRY=true` setzen und `pnpm dev` starten.
3. „Lokaler Entwicklungszugang“ öffnen und den selbst bereitgestellten `DEV_ADMIN_TOKEN`
   der Backend-`.env` eingeben, nur den Wert ohne `Bearer`-Präfix.
4. „Zugang verwenden“ lädt die Daten erneut. „Zugang entfernen“ löscht Credential und Daten.

Das ist keine Anmeldung und keine Fake-Autorisierung: FastAPI prüft jeden Request. Der Token
bleibt nur in einer Closure der aktuellen Nuxt-App im Browser-Speicher. Eingabefeld wird geleert;
kein localStorage/sessionStorage, Cookie, Pinia-State, SSR-Payload, URL oder Log enthält ihn.
Ein Neuladen entfernt den Zugang. In einem Production-Build existiert die manuelle Eingabe
auch mit gesetzter Variable nicht (`import.meta.dev`-Grenze). Keine Backend-Secrets werden
automatisch aus dem übergeordneten Projekt übernommen.

## Proxy und verwendeter Vertrag

Der Browser verwendet ausschließlich gleiche Origin `/api/admin/...`.
Der vollständige Backend-Pfad wird angehängt, z.B.
`/api/admin/api/v1/findings` → `${NUXT_ADMIN_API_BASE}/api/v1/findings`.

| FastAPI GET                                  | Frontend                                                             |
| -------------------------------------------- | -------------------------------------------------------------------- |
| `/health`                                    | Typisierter Diagnosezugriff über Proxy                               |
| `/ready`                                     | Typisierter Diagnosezugriff über Proxy                               |
| `/api/v1/dashboard/summary`                  | KPI-Karten, Zeitraum, neue Datensätze, Qualitätsübersicht            |
| `/api/v1/findings`                           | Dashboard-Vorschau und filterbare, paginierte Arbeitsliste           |
| `/api/v1/quality/venues/missing-geolocation` | Typisierter Diagnosezugriff; UI verwendet die generische Befundliste |

Verifiziert anhand des laufenden `/openapi.json` und lokalen Backend-Codes. Der abgerufene
Vertrag liegt ohne Daten/Secrets in [docs/openapi.json](docs/openapi.json).
`shared/contracts.ts` bildet ihn mit expliziten Zod-Schemas ab und leitet TypeScript-Typen ab.
Das liefert zusätzlich Laufzeitvalidierung; ungültige Responses werden nicht durch Casts oder
Demo-Zahlen kaschiert. Für diesen kleinen Vertrag ist kein weiterer Codegenerator erforderlich.

Proxy-Schutz: exakte Route- und GET-Allowlist, erlaubte Query-Namen, keine doppelten Parameter,
feste konfigurierte Ziel-Origin ohne Credentials/Pfade, keine Redirects, 10-Sekunden-Timeout,
keine Weiterleitung von Cookies oder fremden Requestheaders. Nur das vom Browser übergebene
Authorization-Header wird weitergegeben. 401 bei fehlendem Credential, Backend-Status bleiben
erhalten; Fehlertexte werden datensparsam normalisiert. Antworten sind `private, no-store`.
Es existiert kein unbeschränkter Proxy und keine Domain-Schreiboperation.

## Oberfläche und Zustandsverwaltung

- Sidebar, responsive Raster, fünf KPI-Karten, Arbeitsliste, Qualitätsübersicht, dunkle
  Veranstaltungskarte, neue Datensätze, offene Vorgänge und Schnellfilter folgen dem Mockup.
- Mobile Navigation und Details verwenden native modale Dialoge mit Escape/Fokus-Rückgabe.
- Zeiträume `today`, `24h`, `7d` werden unverändert an das Backend gegeben. Keine eigene
  Zeitfensterberechnung. Formate explizit Deutsch/Europe-Berlin; Headerzeit per Nuxt `useState`
  zwischen SSR und Hydration geteilt.
- Dashboard-/Findings-Stores kapseln Laden, Fehler, letzten Erfolg, Filter und Pagination.
  Request-IDs verhindern Überschreiben durch verspätete Antworten. Filterwechsel setzt Seite 1.
- Filter und Seitenzahlen liegen in der URL; Organisation per UUID, da kein Organisations-
  Suchendpoint existiert. Keine lokale Filterung einer Teilseite als angeblich vollständige Suche.
- Fehlende Werte: „Nicht verfügbar“; echte 0: „0“. Bei Aktualisierungsfehlern werden alte Daten
  als veraltet markiert, bei 401/403 entfernt. Geänderte Perioden kennzeichnen ggf. alte Zahlen.
- Daten werden erst im Browser geladen; SSR überträgt weder sensible Listen noch Credentials.
  Pinia-Instanzen und API-Client entstehen pro Nuxt-App, kein globaler Benutzerzustand.

## Noch nicht verfügbar

Aktivitätsfeed, persönlicher Besuchsstand, offene Vorgänge, nächste Veranstaltung, Prüfläufe
und Abdeckungsprozente, weitere Qualitätsregeln, Objektverwaltung, Bearbeiten, Reviews,
Ignorieren und Export. Keine erfundenen Aufrufe, Demo-Zahlen oder Erfolgsbestätigungen.
Der Schweregrad fehlender Geopositionen bleibt laut API **Warnung**, auch wenn das Mockup
ein solches Beispiel als Fehler markiert. `urgent_findings` ist sichtbar, aber nicht als
exakter Schnellfilter verlinkt: dafür fehlt ein passender Backend-Filter.

Status im normalen UI: offene Live-Befunde. Historische reviewed/ignored/resolved-Mengen
sind fachlich noch nicht implementiert. Befunddetails verwenden ausschließlich schon geladene
Felder. „Erstmals gefunden“ bleibt bei fehlender Historie nicht verfügbar.

## Tests und Build

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm exec playwright install chromium  # einmalig, falls noch nicht vorhanden
pnpm test:e2e
pnpm build
TEST_PRODUCTION=1 pnpm test:e2e  # dieselben Browser-Tests gegen den fertigen Build
pnpm preview
```

Unit-/Komponententests: Vertrag, Mapping, Null vs. 0, Fehlertypen, Stores, Pagination,
veraltete Antworten, Proxy-Ziel/Route/Header/Status/Timeout. Playwright: Desktop/Mobil,
Navigation/Escape/Fokus, Filter/Pagination, Detailpanel, gesperrter Zugang, API-Ausfall,
Proxy-Allowlist, Überbreite und Hydration. Testdaten liegen ausschließlich unter `tests/`.
Die Browser-Tests starten einen eigenen Loopback-Testserver auf Port 3100. Screenshots und
Fehlertraces liegen im ignorierten `test-results/`. Regulärer Betrieb benutzt keine Fixtures.

Die ausgeführten Prüfungen und ihre Grenzen stehen in [docs/verification.md](docs/verification.md).

Verwendete Integrationen: [Nuxt](https://nuxt.com/docs/4.x),
[Tailwind Vite-Integration](https://tailwindcss.com/docs/installation/framework-guides/nuxt),
[Pinia/Nuxt](https://pinia.vuejs.org/ssr/nuxt.html).
