# Kulturbytes Admin API

FastAPI / Python 3.13 / SQLAlchemy async / PostgreSQL/PostGIS. Das Backend liest Uranus-
Domänendaten und liefert Dashboard, Activity, Qualitätsbefunde und Arbeitslisten. Optional
speichert es Prüfläufe und Reviews ausschließlich im eigenen `admin`-Schema.
Fachliche Uranus-Schreiblogik wird nicht dupliziert.

## Start

```bash
cd backend
uv sync --locked
cp .env.example .env  # nur bei der ersten Einrichtung
uv run uvicorn app.main:app --reload --no-access-log
```

`DATABASE_URL` verwendet einen SELECT-Account. Source-Zeitzone `URANUS_TIMESTAMP_TIMEZONE=UTC`
ist durch den Betreiber für den bisherigen Backup bestätigt; andere Installationen müssen
sie prüfen. `ADMIN_TIMEZONE`/`EVENT_TIMEZONE` sind davon getrennte Reporting-Einstellungen.
`uv run python -m app` berücksichtigt außerdem `APP_HOST`/`APP_PORT`.

Für lokale Fehlerdiagnose mit Exception-Details und Tracebacks im JSON-Serverlog:

```bash
APP_ENV=development APP_DEBUG=true LOG_LEVEL=DEBUG \
uv run uvicorn app.main:app --reload --log-level debug --no-access-log
```

`APP_DEBUG=true` aktiviert das Feld `traceback` einschließlich Fehlermeldung nur in
development/test. API-Fehlerantworten bleiben bereinigt. Debuglogs können sensible
Daten aus Exceptions enthalten. Ohne `APP_DEBUG` bleiben Exception-Details verborgen,
auch bei `LOG_LEVEL=DEBUG`; in staging/production wird `APP_DEBUG=true` abgewiesen.

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
| GET `/api/v1/dashboard/summary` | Neuanlagen today/24h/7d; Qualität aller implementierten Regeln |
| GET `/api/v1/dashboard/activity` | Neuanlagenliste für neun Typen, Org-/Zeitfilter und Pagination; undatierte Bilder separat |
| GET `/api/v1/findings` | Standard `mode=persisted`; explizite Diagnose `mode=live`, Severity/Typ/Regel/Org/Status/Pagination |
| GET `/api/v1/quality/venues/missing-geolocation` | Bestehende Venue-Prüfung mit Adressen und Terminanzahlen |
| GET `/api/v1/work-queues/{kind}` | partner_requests, team_invitations, user_activation |
| GET `/api/v1/check-runs` | Persistierte Prüfläufe mit Regelabdeckung |
| POST `/api/v1/check-runs` | Vollständigen Scan ausführen und Befunde persistieren |
| PATCH `/api/v1/finding-reviews` | Menschlichen Reviewstatus und Metadaten ändern; kein manuelles resolved |

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
Migrationen 0001–0003 erzeugen Check Runs, Findings, Record Marks und deren append-only-Historie.

Keine automatische Migration und kein DDL-Fallback auf `DATABASE_URL`. Die Runtime ist nie
Migrator/Owner. Gespeicherte Standardlisten benötigen die Admin-Ablage; ohne sie bleiben nur
mit lokalem Dev-Token explizite `mode=live`-Abrufe verfügbar. Production-Anmeldung benötigt
die Admin-Ablage. Ein `admin_storage_unconfigured` kann eine fehlende DSN
oder **zu mächtige** Runtime-Rechte bedeuten; die Response-Message unterscheidet beides.

Scanfehler schließen niemals Findings. Nur erfolgreich abgedeckte Objekte können resolved werden;
wiederholte Scans bewahren ID und Erstfund. Review: open/in_progress/snoozed/exception.
Authentifizierter Development-Principal wird als `reviewed_subject=development-only` gespeichert,
nicht als erfundener User. Zuweisungen referenzieren nur existierende Uranus-User.

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
- [Ursprüngliche Analyse](docs/uranus-analysis.md), [offene Uranus-Verbesserungen](docs/future-uranus-improvements.md).
- [Nuxt-Frontend](../frontend/README.md).
