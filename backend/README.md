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

Produktive globale Admin-Autorisierung bleibt gesperrt: gültiger Uranus-Login ist keine
systemweite Adminberechtigung. Nur ausdrücklich lokal: `APP_ENV=development`,
`DEV_AUTH_ENABLED=true`, zufälliger `DEV_ADMIN_TOKEN` mit mindestens 32 Zeichen.
Der Bearer-Token ist kein Uranus-Benutzer. Development-Override ist in Production verboten.

## API

| Methode / Pfad | Zweck |
| --- | --- |
| GET `/health`, `/ready` | Liveness / DB-Readiness; ohne Datenpreisgabe |
| GET `/api/v1/dashboard/summary` | Neuanlagen today/24h/7d; Qualität aller implementierten Regeln |
| GET `/api/v1/dashboard/activity` | Neuanlagenliste für neun Typen, Org-/Zeitfilter und Pagination; undatierte Bilder separat |
| GET `/api/v1/findings` | `mode=live` oder `mode=persisted`, Severity/Typ/Regel/Org/Status/Pagination |
| GET `/api/v1/quality/venues/missing-geolocation` | Bestehende Venue-Prüfung mit Adressen und Terminanzahlen |
| GET `/api/v1/work-queues/{kind}` | partner_requests, team_invitations, user_activation |
| GET `/api/v1/check-runs` | Persistierte Prüfläufe mit Regelabdeckung |
| POST `/api/v1/check-runs` | Vollständigen Scan ausführen und Befunde persistieren |
| PATCH `/api/v1/finding-reviews` | Menschlichen Reviewstatus und Metadaten ändern; kein manuelles resolved |

Alle `/api/v1`-Routen verwenden dieselbe Admin-Auth. Standardmäßig 401 ohne Credential;
503 bei unkonfigurierter globaler Auth. OpenAPI nur explizit in development/test einschalten:
`OPENAPI_ENABLED=true`; `/docs` und `/openapi.json`.

## Optionale Persistenz

1. Schema `admin` mit eingeschränktem Migrator bereitstellen.
2. `ADMIN_MIGRATION_DATABASE_URL` separat im Prozess-Environment setzen.
3. `uv run alembic upgrade head` ausführen (Revisionen 0001 und 0002).
4. Eigenen Runtimeaccount nur für SELECT/INSERT/UPDATE auf admin.finding/admin.check_run
   bereitstellen und als `ADMIN_DATABASE_URL` konfigurieren.

Keine automatische Migration, keine Cross-Schema-FKs und kein DDL-Fallback auf DATABASE_URL.
Die Source-Verbindung erzwingt weiterhin read-only Transaktionen. Der Admin-Writer verweigert
privilegierte Rollen oder vorhandene Uranus-Schreibrechte. Ohne optionale Ablage bleibt
Live-Reporting verfügbar; persistente Operationen melden `admin_storage_unconfigured`.

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
- [Architektur](docs/architecture.md), [Entwicklung und Rollen](docs/development.md).
- [Ursprüngliche Analyse](docs/uranus-analysis.md), [offene Uranus-Verbesserungen](docs/future-uranus-improvements.md).
- [Nuxt-Frontend](../frontend/README.md).
