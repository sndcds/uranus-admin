# Kulturbytes Admin API

Internes FastAPI-Backend für ein zukünftiges Nuxt-4-Administrationsdashboard.
Projektname: `kulturbytes-admin-api`. Das Backend liegt unter `uranus-admin/backend`.

## Zweck und Architektur

Die API liefert systemweite Übersichten und Datenqualitätsbefunde aus Uranus.
Uranus bleibt die Go-Domain-API für fachliche Schreiboperationen und Validierung.
Dieses Projekt liest PostgreSQL/PostGIS; es dupliziert keine Event-, Venue- oder Benutzerverwaltung.
Nuxt übernimmt Darstellung und Interaktion.

```text
Nuxt Admin → FastAPI Admin API → Uranus PostgreSQL/PostGIS (SELECT)
                              → Uranus API (spätere geprüfte Schreibaktionen)
```

Siehe [Architektur](docs/architecture.md), [Uranus-Analyse](docs/uranus-analysis.md)
und [Entwicklung](docs/development.md).

## Development

Python 3.13 und uv installieren, dann vom Repository-Wurzelverzeichnis aus:

```bash
cd backend
uv sync --locked
cp .env.example .env
# DATABASE_URL und die bestätigte URANUS_TIMESTAMP_TIMEZONE in .env setzen.
uv run uvicorn app.main:app --reload --no-access-log
```

`uv sync` funktioniert ebenfalls. `uv.lock` fixiert die Abhängigkeiten;
CI verwendet `--locked`. `uv run python -m app` berücksichtigt zusätzlich `APP_HOST`
und `APP_PORT` und eignet sich als systemd-Startkommando. Der direkte Uvicorn-Aufruf
nimmt Host/Port aus seinen CLI-Optionen.

Alle weiteren Backend-Befehle in dieser Anleitung werden im Ordner `backend/` ausgeführt.

## Environment

Alle Laufzeitwerte stehen in [.env.example](.env.example). Keine Secrets committen.
`ADMIN_TIMEZONE=Europe/Berlin` definiert „heute“; `24h` sind tatsächlich 24 Stunden.
UTC als Speicherzeitzone der naiven Uranus-Timestamps wurde vom Betreiber bestätigt und ist
der Standard. `URANUS_TIMESTAMP_TIMEZONE` bleibt für andere Installationen konfigurierbar.

## API

| GET | Bedeutung |
| --- | --- |
| `/health` | Liveness ohne Datenbankzugriff |
| `/ready` | Datenbankverbindung prüfen; 503 bei Ausfall |
| `/api/v1/dashboard/summary?period=24h` | Neue Datensätze; `today`, `24h`, `7d`; aktuelle Venue-Befunde |
| `/api/v1/findings` | Einheitliche, paginierte Live-Befunde |
| `/api/v1/quality/venues/missing-geolocation` | Erste Regel mit Adressen und Terminzahlen |

Findings: `severity`, `entity_type`, `rule`, `organization_id`, `status`, `page`,
`page_size` (maximal 100). `mode=live`; `first_seen_at=null`, kein erfundener Erstfund.
Review-/Resolved-Filter liefern in diesem Modus keine historischen Ergebnisse.

## Tests

```bash
uv run pytest
```

Ohne `TEST_DATABASE_URL` laufen die Unit-/Security-Tests; DB-Tests werden ausdrücklich
übersprungen. Für den vollständigen Meilenstein-Testlauf ist eine **leere, wegwerfbare**
PostGIS-Datenbank mit Namen auf `_test` erforderlich:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/kulturbytes_admin_test uv run pytest
```

Die Fixture verweigert vorhandene Uranus-Schemas. Sie erstellt den versionierten Testausschnitt
und entfernt ausschließlich ihr eigenes Schema anschließend. CI überspringt keine DB-Tests.

## Lint und Typen

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## OpenAPI

Im Development `OPENAPI_ENABLED=true` setzen: `/docs` und `/openapi.json`.
Standardmäßig sowie in Staging/Production deaktiviert. Alle Admin-Routen tragen
Bearer-Security und das gemeinsame Fehlerformat im OpenAPI-Vertrag.

## Sicherheit und Meilensteingrenze

Die API ist nicht als öffentliche API vorgesehen. **Produktive Admin-Authentifizierung
ist in Meilenstein 1 bewusst gesperrt**, weil Uranus keine belegte globale Adminrolle liefert.
Ohne Credential: 401; mit Credential ohne konfigurierte Integration: 503.
Es gibt keine eigene Benutzerverwaltung und keine ungeprüfte JWT-Akzeptanz.

Nur für lokale Entwicklung: `APP_ENV=development`, `DEV_AUTH_ENABLED=true` und ein zufälliges
`DEV_ADMIN_TOKEN` mit mindestens 32 Zeichen konfigurieren. Das Token als
`Authorization: Bearer …` senden. Es repräsentiert ausdrücklich keinen Uranus-Benutzer.
Dieser Override wird in Staging/Production bereits beim Konfigurationsladen abgelehnt.

Der Laufzeitzugang soll nur SELECT auf den benötigten Uranus-Tabellen besitzen. Zusätzlich
erzwingt die Anwendung read-only Transaktionen. Admin-Migrationen verwenden ausschließlich
`ADMIN_MIGRATION_DATABASE_URL` und das Schema `admin`; siehe Entwicklungsdokumentation.
Keine automatische Migration, keine Domain-Schreiboperation, kein Deployment ist enthalten.

## Nuxt-Administrationsfrontend

Das lokale Dashboard liegt unter [frontend/](../frontend/README.md) und verwendet die separate
Admin-API über einen begrenzten Nuxt-Proxy. Installation und Start:

```bash
cd ../frontend
pnpm install --frozen-lockfile
pnpm dev
```

Browser: http://127.0.0.1:3000. Ohne gültigen Zugang bleiben administrative Daten gesperrt.
Die Frontend-Anleitung beschreibt den optionalen manuellen Development-Zugang sowie
Tests, Konfiguration und noch fehlende Backend-Funktionen. Das HTML-Mockup bleibt unverändert.
