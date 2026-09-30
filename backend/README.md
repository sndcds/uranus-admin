# Kulturbytes Admin API — FastAPI, PostgreSQL/PostGIS & Data Quality Backend

Die **Kulturbytes Admin API** ist das Python-/FastAPI-Backend für Administration,
Datenqualität und Operations rund um Kulturbytes/Uranus. Sie nutzt **Python 3.13**,
**FastAPI**, asynchrones **SQLAlchemy**, **PostgreSQL/PostGIS** und getrennte Source-/Admin-
Datenbankverbindungen.

Das Backend liest Uranus-Domänendaten ausschließlich über einen eingeschränkten Reader und
liefert Dashboard, Activity, globale Suche, Qualitätsbefunde, Entity-Timelines, Inbox,
Zuständigkeiten, Geocoding, Benachrichtigungen, Statistiken und sichere Diagnosefunktionen.
Persistente Admin-Workflows werden ausschließlich im eigenen `admin`-Schema gespeichert;
fachliche Uranus-Schreiblogik wird nicht dupliziert.

## Kernfunktionen

- **Data quality:** deterministische Regeln, persistierte Findings, Reviews und Prüflaufhistorie.
- **Operations:** Inbox, Assignments, Markierungen, URL-Prüfung und langlebige Worker.
- **Geospatial:** PostGIS, Geo Scope, Nominatim-Geocoding und Standortvorschläge.
- **Domain inspection:** Events, Venues, Spaces, Organisations, Users/Teams und Images.
- **Security:** eigene Admin-Authentifizierung, HttpOnly-Sessions, CSRF/Origin-Prüfung,
  Least-Privilege-Rollen und read-only Source-Zugriff.
- **Diagnostics:** Source-Schema-Verifikation, registrierte SQL-Diagnostik und isolierte
  read-only SQL Console.

Zur Gesamtübersicht siehe [Repository-README](../README.md), für die Oberfläche
[Frontend-README](../frontend/README.md) und für den Betrieb [Ansible-Deployment](../ansible/README.md).

Die [automatische Admin-Datenbankdokumentation](docs/database/README.md) erzeugt
Migrationshistorie, finales PostgreSQL-Schema, DBML für dbdiagram.io sowie vollständige
und thematische ER-Diagramme als SVG/PDF – ohne Datenbankverbindung.

## Start

```bash
cd backend
uv sync --locked
cp .env.example .env  # nur bei der ersten Einrichtung
uv run uvicorn app.main:app --ws wsproto --ws-max-size 200000 --reload --no-access-log
```

`DATABASE_URL` verwendet einen SELECT-Account. Source-Zeitzone `URANUS_TIMESTAMP_TIMEZONE=UTC`
ist durch den Betreiber für den bisherigen Backup bestätigt; andere Installationen müssen
sie prüfen. `ADMIN_TIMEZONE`/`EVENT_TIMEZONE` sind davon getrennte Reporting-Einstellungen.
`uv run python -m app` berücksichtigt außerdem `APP_HOST`/`APP_PORT`.

Für lokale Fehlerdiagnose mit Exception-Details und Tracebacks im JSON-Serverlog:

```bash
APP_ENV=development APP_DEBUG=true LOG_LEVEL=DEBUG \
uv run uvicorn app.main:app --ws wsproto --ws-max-size 200000 --reload --log-level debug --no-access-log
```

`APP_DEBUG=true` aktiviert zusätzliche Exception-Details im Feld `traceback` der
Serverlogs. API-Fehlerantworten bleiben bereinigt. Debuglogs können sensible
Daten aus Exceptions enthalten. Ohne `APP_DEBUG` bleiben Exception-Details verborgen,
auch bei `LOG_LEVEL=DEBUG`.

In staging/production ist deshalb zusätzlich `ALLOW_PRODUCTION_DEBUG=true` erforderlich;
`APP_DEBUG=true` allein wird weiterhin abgewiesen. Beide Einstellungen bleiben standardmäßig
`false` und sollten nur während einer aktiven Diagnose eingeschaltet werden:

```bash
APP_ENV=production \
APP_DEBUG=true \
ALLOW_PRODUCTION_DEBUG=true \
LOG_LEVEL=DEBUG \
uv run uvicorn app.main:app --ws wsproto --ws-max-size 200000 --no-access-log
```

`ALLOW_PRODUCTION_DEBUG` erlaubt ausschließlich Production-/Staging-Debugging.
`DEV_AUTH_ENABLED=true` und `OPENAPI_ENABLED=true` bleiben dort verboten;
die HTTPS-Anforderungen bleiben unverändert.

Production verwendet eigene Admin-Konten und explizite globale Vergaben (siehe unten).
Ein Uranus-Login oder Organisationsrechte begründen keinen Zugriff. Nur ausdrücklich lokal: `APP_ENV=development`,
`DEV_AUTH_ENABLED=true`, zufälliger `DEV_ADMIN_TOKEN` mit mindestens 32 Zeichen.
Der Bearer-Token ist kein Uranus-Benutzer. Development-Override ist in Production verboten.

## API

| Methode / Pfad | Zweck |
| --- | --- |
| POST `/auth/login`, `/auth/logout` | Eigene Admin-Anmeldung bzw. Sitzungswiderruf; exakte Origin/CSRF |
| GET `/auth/session` | Aktive Identität und getrennt geprüfte globale Berechtigung |
| GET `/health`, `/ready` | Liveness / DB-Readiness; ohne Datenpreisgabe |
| GET `/api/v1/search` | Authentifizierte globale Suche; q 2–120, maximal 10 je Typ / 90 insgesamt |
| GET `/api/v1/dashboard/summary` | Neuanlagen today/24h/7d; Qualität aller implementierten Regeln |
| GET `/api/v1/dashboard/activity` | Neuanlagenliste für neun Typen, Org-/Zeitfilter und Pagination; undatierte Bilder separat |
| GET `/api/v1/findings` | Standard `mode=persisted`; explizite Diagnose `mode=live`, Severity/Typ/Regel/Org/Status/Pagination |
| GET `/api/v1/quality/venues/missing-geolocation` | Bestehende Venue-Prüfung mit Adressen und Terminanzahlen |
| GET `/api/v1/work-queues/{kind}` | partner_requests, team_invitations, user_activation |
| GET `/api/v1/check-runs` | Persistierte Prüfläufe mit Regelabdeckung |
| POST `/api/v1/check-runs` | Vollständigen Scan ausführen und Befunde persistieren |
| PATCH `/api/v1/finding-reviews` | Menschlichen Reviewstatus und Metadaten ändern; kein manuelles resolved |
| GET `/api/v1/entities/{entity_type}/{entity_key}/timeline` | Belegte Source-/Workflow-Ereignisse, stabile Cursor-Pagination |
| GET `/api/v1/inbox` | Deduplizierte Findings, Zuweisungen und operative Workflow-Fälle |
| GET/POST `/api/v1/assignments` | Aktive Finding-Zuweisung lesen bzw. anlegen |
| GET/PATCH `/api/v1/assignments/{id}` | Versionierte Admin-Zuweisung lesen bzw. ändern |
| GET `/api/v1/admins` | Aktive, global berechtigte Admin-Konten als Zuweisungsziele |

Alle `/api/v1`-Routen verwenden dieselbe Admin-Auth. Standardmäßig 401 ohne Credential;
503 bei unkonfigurierter globaler Auth. OpenAPI nur explizit in development/test einschalten:
`OPENAPI_ENABLED=true`; `/docs` und `/openapi.json`.

## Production-Anmeldung

FastAPI verwendet unabhängige Admin-Konten und eine separate globale Berechtigungstabelle.
[Auth-Vertrag](docs/authentication.md) und
[Provisionierung](docs/development.md#eigenständige-admin-authentifizierung-migration-0004)
erklären Migration 0004, Betreiber-CLI, Cookies und Production-Konfiguration.
Uranus-Login und Organisationsrechte werden nicht als Admin-Zugang verwendet.

## Optionale Persistenz

Die [zentrale PostgreSQL-Rollen-Anleitung](docs/development.md#minimale-rechte-nach-migration-0003)
enthält die vollständigen SQL-Blöcke, Default Privileges, Ownership, Diagnose und Rechte-Matrix.
`DATABASE_URL` verwendet `uranus_reader`; `ADMIN_DATABASE_URL` verwendet `admin_user`;
`ADMIN_MIGRATION_DATABASE_URL` verwendet ausschließlich für Alembic `admin_migrator`.
Alembic legt ein fehlendes `admin`-Schema vor der Versionstabelle an. Dafür benötigt
der Migrator beim ersten Lauf `CREATE` auf der Zieldatenbank; anschließend kann dieses
Recht entzogen werden. Bestehende Schemas bleiben unverändert. Rollen und explizite
Runtime-/Operator-Grants werden weiterhin separat provisioniert.
Migration 0012 ergänzt die append-only Finding-Historie für Entity-Timelines; bestehende
Findings werden nur an tatsächlich gespeicherten Zeitpunkten zurückgefüllt.
Migration 0013 ergänzt unabhängige Admin-Zuweisungen und deren append-only Verlauf. Die Runtime
erhält DML nur auf `assignment` und ausschließlich SELECT/INSERT auf `assignment_event`.

Keine Migration beim Anwendungsstart und kein DDL-Fallback auf `DATABASE_URL`. Der
bewachte Ansible-Deployment-Pfad kann einen explizit fingerprint-verifizierten älteren
Admin-Head nach separater Freigabe mit `admin_migrator` transaktional auf den
Release-Head migrieren und die exakten Grants anwenden; beliebiger Drift bleibt ein
Abbruch. Die Runtime ist nie Migrator/Owner. Gespeicherte Standardlisten benötigen die Admin-Ablage; ohne sie bleiben nur
mit lokalem Dev-Token explizite `mode=live`-Abrufe verfügbar. Production-Anmeldung benötigt
die Admin-Ablage. Ein `admin_storage_unconfigured` kann eine fehlende DSN
oder **zu mächtige** Runtime-Rechte bedeuten; die Response-Message unterscheidet beides.

Scanfehler schließen niemals Findings. Nur erfolgreich abgedeckte Objekte können resolved werden;
wiederholte Scans bewahren ID und Erstfund. Review: open/in_progress/snoozed/exception.
Authentifizierter Development-Principal wird als `reviewed_subject=development-only` gespeichert,
nicht als erfundener User. Das ältere Review-Feld `assigned_to` bezeichnet ausschließlich eine
Uranus-Identität. Phase-4-Zuständigkeiten verwenden getrennt `admin.assignment` und referenzieren
nur aktive Konten mit globaler Admin-Vergabe; zwischen beiden Identitäten gibt es kein Mapping.

## Tests

Alle Befehle im Backend-Verzeichnis:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Ohne TEST_DATABASE_URL werden DB-Tests ausdrücklich übersprungen. Vollständig mit **leerer,
wegwerfbarer PostGIS-Datenbank**, deren Name auf `_test` endet:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/kulturbytes_admin_test uv run pytest
```

Fixture verweigert vorhandenes Uranus-Schema. Rollen-/Migrationsprüfungen benötigen ausschließlich
in dieser Testdatenbank administrative Rechte. CI führt den vollständigen DB-Lauf aus.

## Dokumentation

- [Verträge](docs/contracts.md): Finding Identity, Priority, Actions, Activity-Zeitsemantik,
  Auth/Authorization Boundary, Check Run/Resolve Semantics, Reviewworkflow.
- [Quellverifikation und Regelkatalog](docs/source-verification.md).
- [Quality Rules v2](docs/quality-rules.md): DDL-Audit, interne Regeln,
  bewusst zurückgestellte Kandidaten und versionierter Source Contract.
- [Architektur](docs/architecture.md), [Entwicklung und Rollen](docs/development.md).
- [Entity Timeline](docs/entity-timeline.md): Quellen, Zeitsemantik, Pagination und Deployment.
- [Assignments und Inbox](docs/assignments-inbox.md): Identität, Concurrency, Aggregation und Grants.
- [Ursprüngliche Analyse](docs/uranus-analysis.md), [offene Uranus-Verbesserungen](docs/future-uranus-improvements.md).
- [Nuxt-Frontend](../frontend/README.md).

[Finding SQL Diagnostics – Sicherheitsmodell und Pilotqueries](docs/sql-diagnostics.md).

[SQL / Datenherkunft – registrierte Queries, Sicherheitsmodell und Coverage](docs/sql-provenance.md).

[SQL Console – Ansible-Infrastruktur, Quell-Audit und Freigabekriterien](docs/sql-console-infrastructure.md).

[Phase 3 – interaktive READ-ONLY SQL Console](docs/sql-console-runtime.md):
Same-Origin-WebSocket, eigene Console-DSN, AST-Prüfung, begrenztes Streaming und echter Query-Abbruch.
Contract v6 erlaubt Systemadministratoren bewusst `SELECT *` auf allen Tabellen und Spalten
in `uranus.*`, einschließlich sensibler Token-/Passwort-Hash-Werte. Ausschließlich
`uranus_console_reader`, Search Path `pg_catalog, uranus`, kein DSN-Fallback.
Ansible verwaltet direkte SELECT-Grants und Default Privileges des geprüften Source-Owners.
`admin.*` und Systemkataloge bleiben für User-SQL verboten; DB-Schreibrechte bleiben entzogen.
Keine Maskierung, kein Logging von SQL/Ergebnissen und kein Phase-4-Writezugriff.
Registered Diagnostics und SQL Provenance behalten ihre bisherigen begrenzten Pfade.


## Globale Suche und Command Palette

**Ctrl+K / Cmd+K** oder der Suchtrigger im Desktop-/Mobile-Header öffnet die globale
Palette auf geschützten Seiten. Sie durchsucht lokale Admin-Navigation sowie Benutzer,
Organisationen, Orte, Räume, Veranstaltungen, Termine, Bilder, Partneranfragen und
Teameinladungen/Mitgliedschaften. Benutzer sind auch über E-Mail
auffindbar; fehlende Anzeigenamen fallen auf Username, E-Mail und zuletzt UUID zurück.
Entity-Autocomplete, globale Suche und Graph-Root-Suche teilen kanonische Suchfelder,
Labels und Ranking (exakte UUID, exaktes Feld, Präfix, Teilstring, Label, Schlüssel).

`GET /api/v1/search`: q 2–120 Zeichen, standardmäßig fünf und maximal zehn Treffer pro
Typ, insgesamt maximal 90; optional `types=user,venue`. Die Palette sucht systemweit,
unabhängig von Zeitraum/Gebiet, und öffnet serverseitig erzeugte Detail- oder Queue-Actions.
Keine Suchhistorie, Browser-Persistenz, Analytics oder Query-Logs. Source bleibt read-only;
keine Migrationen/Grants/Worker-Änderungen. Backend und Frontend gemeinsam ausrollen.

Kanonische Felder, Privacy, Queryplan und spätere Uranus-eigene pg_trgm-Indizes:
[Suchvertrag](docs/contracts.md#global-search-and-command-palette).

## Research workspace

The dedicated `/api/v1/research` API uses an explicit journalist-or-system-admin
authorization dependency and public projections. See [account setup and rollout](docs/authentication.md#research-authorization).

### Research planner (Phase 1)

`POST /api/v1/research/plan` accepts `{"query":"Culture this evening in Flensburg"}`
and returns a validated `research-query-plan-v1` / `research-planner-v4` envelope.
It requires a journalist or system-admin session. Queries are 1–2,000 characters,
nonblank and preserved exactly. Unknown body fields are rejected. The backend supplies
`EVENT_TIMEZONE` and `language=auto`; the planner calculates `reference_date`.
See the [wire contract and error mapping](docs/contracts.md#research-language-planning).

The optional Ansible transport uses one SSH connection with three local forwards:

```text
uranus-admin
  ├─ 127.0.0.1:8090 → SSH → planner 127.0.0.1:8090
  ├─ 127.0.0.1:6333 → SSH → Qdrant 127.0.0.1:6333
  └─ 127.0.0.1:6335 → SSH → Jina-v3 encoder 127.0.0.1:6335
```

Phase 1 adds the FastAPI endpoint only. No frontend UI, Nitro allowlist or browser client
is added yet. Future browser use must pass through Nuxt and Admin; the browser never
contacts the planner directly or receives its service key. Admin never receives, stores
or forwards the OpenAI key. The planner receives no PostgreSQL/Qdrant records: `/plan`
only interprets language. The separate execution endpoint below resolves and executes
validated plans in Admin.

The planner port stays private on the remote host. FastAPI sees only loopback;
the optional [Ansible-managed tunnel](../ansible/README.md#research-planner-ssh-tunnel)
owns SSH host/key configuration and pins the host identity through `known_hosts`.
Its SSH key is separate from the planner service Bearer key. Same-host development
uses the same URL with the tunnel disabled. Only the planner host holds the OpenAI key.

All three remote services remain loopback-only, and all local forwards bind only
`127.0.0.1`; Qdrant and the embedding service have no direct public exposure.
The remote AWS operator must separately allow all three destinations in sshd
`PermitOpen` and matching `authorized_keys permitopen=` restrictions (see the Ansible
instructions). This repository does not manage those remote files.

With the tunnel and semantic mode enabled, operators must separately provision
`/etc/uranus-admin/runtime.env`:

```dotenv
SEMANTIC_SEARCH_NONCOMMERCIAL_JINA=true
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=<qdrant-service-secret>
EMBEDDING_URL=http://127.0.0.1:6335
EMBEDDING_API_KEY=<embedding-service-secret>
```

Ansible preflight requires exact URLs matching the configured local Qdrant/embedding
ports and nonempty keys. Service keys stay independent of each other and the SSH key;
Ansible neither generates secrets nor copies them from AWS. Secret validation is
hidden from logs, and service keys never enter the tunnel unit. Deployment checks
local vector TCP connectivity only, without inference; this proves local listeners,
not remote service readiness or key validity. Planner `/health` checks remain unchanged.
Before a tunnel start/restart, Ansible stops only its managed tunnel and rejects
collisions on any of the three local ports without killing foreign processes.

Provision these settings in the **Admin API's own environment** and restart that process:

```dotenv
RESEARCH_PLANNER_URL=http://127.0.0.1:8090
RESEARCH_PLANNER_API_KEY=replace-with-planner-service-key
RESEARCH_PLANNER_TIMEOUT_SECONDS=30
```

`RESEARCH_PLANNER_API_KEY` is the internal Bearer key for Admin → planner, **not an
OpenAI API key**. Replace the placeholder with the same secret value provisioned as
the planner's `RESEARCH_PLANNER_SERVICE_API_KEY` (32–512 printable ASCII characters,
without whitespace). Each service owns its environment; Admin must not read
`/etc/research-planner/planner.env` or receive the planner's model credentials.

Only `http://127.0.0.1:<port>` is accepted (canonical decimal port 1–65535, required,
no leading zeroes). Hostnames, IPv6, other loopback addresses, external origins, HTTPS,
credentials, paths including `/`, query strings, fragments and whitespace are rejected.
Both URL and key may be absent; partial configuration fails startup. A missing or
unreachable planner affects only this endpoint, returning safe 503. `/health` and
`/ready` remain unchanged and do not contact the planner. No migrations, grants or
worker changes are needed.

One process-lifetime HTTP client uses no environment proxies, redirects, cookie replay
or automatic retries. The timeout defaults to 30 seconds (allowed 1–30), including a
total deadline; responses are limited to 32 KiB. Submit another request explicitly
after a timeout if appropriate. No queries/plans are persisted or logged.
The 30-second default matches the planner's configured timeout, avoiding a much earlier
Admin cutoff while paid inference is still running. The observed roughly 4.3-second
request is not a p95/p99 latency measurement; matching deadlines cannot guarantee
completion before Admin's total deadline, which also includes transport overhead.

For a direct backend request with an existing Research-authorized **Admin session
Bearer token** (not the planner service key):

```sh
curl --request POST http://127.0.0.1:8000/api/v1/research/plan \
  --header 'Authorization: Bearer <ADMIN_SESSION_TOKEN>' \
  --header 'Content-Type: application/json' \
  --data '{"query":"Was ist heute Abend in Flensburg kulturell interessant?"}'
```

Cookie-authenticated POSTs additionally require the exact configured `Origin` and
`X-Admin-CSRF: 1`. Mocked transport tests require neither the planner nor an OpenAI call.

### Research plan execution

`POST /api/v1/research/query` accepts only `{"query":"Welche Veranstaltungen gibt es heute in Flensburg?"}`.
Natural language → planner → deterministic executor → PostgreSQL/PostGIS and optionally
Jina/Qdrant. The LLM neither queries the database nor sees source records; all source
facts come from Admin. The endpoint returns bounded typed records, counts, aggregates,
comparisons or clarification, without generated answer prose. `/plan` is unchanged.

Structured lists/counts support events, venues and organizations. Event semantic
search/recommendation first selects the complete hard-eligible UUID population in
PostgreSQL/PostGIS, then ranks only those IDs in Qdrant (top 50), and finally
rehydrates and validates contextual evidence in a fresh source snapshot. The
10,000-event eligibility bound fails with 422 `research_execution_too_broad` when
exceeded; it never silently truncates. Empty eligibility returns empty records
without encoder/Qdrant calls. For nonempty eligibility, semantic-required queries
fail explicitly with 503 when retrieval is unavailable; structured-only queries work independently. Exact metrics use SQL;
top-K semantic results never establish exact counts, aggregates or comparisons.
Evening follows the planner contract: known local start >=18:00 and <24:00, excluding
all-day/unknown-time occurrences. No migrations, new grants, query persistence or
Uranus writes. Frontend UI and Nitro integration remain deferred. See the
[execution contract, resolver rules and capability gaps](docs/contracts.md#research-plan-execution).
