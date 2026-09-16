# Kulturbytes Admin

Administrationsdashboard für Uranus mit einem FastAPI-Backend und einem Nuxt-Frontend.

| Ordner | Inhalt |
| --- | --- |
| [backend/](backend/README.md) | Python-API, Migrationen, Tests und Backend-Dokumentation |
| [frontend/](frontend/README.md) | Nuxt-Dashboard, Tests und HTML-Mockup |

Beide Anwendungen besitzen eigene Abhängigkeiten und `.env`-Dateien.
Die gemeinsame GitHub-Actions-Konfiguration liegt unter `.github/workflows/`.

## Backend starten

Python 3.13 und uv verwenden. Vom Repository-Wurzelverzeichnis aus:

```bash
cd backend
uv sync --locked
cp .env.example .env  # nur beim ersten Einrichten; vorhandene Konfiguration behalten
# Datenbankzugang und lokale Einstellungen in .env setzen.
uv run uvicorn app.main:app --reload --no-access-log
```

API: http://127.0.0.1:8000. Details zu Konfiguration, Authentifizierung und Tests
stehen in der [Backend-Anleitung](backend/README.md) und unter
[Entwicklung](backend/docs/development.md).

## Frontend starten

In einem zweiten Terminal vom Repository-Wurzelverzeichnis aus:

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env  # nur beim ersten Einrichten; vorhandene Konfiguration behalten
pnpm dev
```

Dashboard: http://127.0.0.1:3000. Voraussetzungen, Konfiguration und Tests
stehen in der [Frontend-Anleitung](frontend/README.md).

## Review-Funktionen

Activity für neun Quelltypen, 19 zentrale Qualitätsregeln einschließlich bestehender Venue-Prüfung,
operative Arbeitslisten sowie optionale persistierte Prüfläufe und Reviews sind angebunden.
Die neue Admin-Schreibverbindung verwaltet ausschließlich eigene Metadaten; Uranus bleibt read-only.
Globale Admin-Autorisierung wird ausdrücklich in der separaten Admin-Berechtigungstabelle vergeben.

Die Admin-Ablage erfordert den aktuellen Alembic-Head und einen separat eingeschränkten
`ADMIN_DATABASE_URL`-Account. Ohne Ablage bleibt explizites `mode=live`-Reporting mit lokalem Dev-Token nutzbar; normale Listen und Dashboard
verwenden gespeicherte Findings und benötigen die Admin-Ablage.
Details: [Backend-Verträge](backend/docs/contracts.md),
[verifizierter Uranus-dev-Stand](backend/docs/source-verification.md).
Frontend und Backend werden in getrennten CI-Jobs geprüft, einschließlich Frontend-Produktionsbuild
und reproduzierbarer Chromium-Tests. Zusätzlich prüfen CodeQL (Python/JS/TS) und
Dependency Review (neue high/critical Sicherheitslücken) Änderungen; siehe
[CI-Gates und Berechtigungen](backend/docs/development.md#security-gates).

Qualitätsprüfungen werden dauerhaft eingereiht (HTTP 202). Zusätzlich zur API muss der
[Check-Worker](backend/docs/development.md#durable-quality-check-worker-migration-0006)
mit `cd backend && uv run python -m app.check_worker` laufen. Migration 0006 und Runtime-Grants
vor dem Start prüfen; ohne Worker bleiben neue Jobs in der Warteschlange.


## Markierungen und Notizen

Datensätze lassen sich unabhängig von Prüfhinweisen mit mehreren Anliegen markieren.
Jedes Anliegen enthält Gründe, Dringlichkeit, fortlaufende Notizen und einen Status.
Erledigung und Wiederöffnung werden mit Autor und Zeitpunkt im Verlauf festgehalten.
Die Übersicht „Markierungen“ bietet Status-, Grund- und Dringlichkeitsfilter.

Voraussetzung: Admin-Migration `0003` und die zusätzlichen
[Runtime-Rechte und Rollen-Provisionierung](backend/docs/development.md#minimale-rechte-nach-migration-0003).

## Production-Anmeldung

FastAPI authentifiziert eigene Admin-Konten; eine separate Tabelle in `admin` vergibt globale
System-Admin-Rechte. Es gibt keine Uranus-Authentifizierung oder Statusabfrage. Der Browser nutzt
HttpOnly-Sitzungscookies über Nitro. Einrichtung einschließlich Migration 0004, eingeschränkter
Runtime-Grants und Betreiber-CLI: [Auth-Vertrag](backend/docs/authentication.md) und
[Provisionierung](backend/docs/development.md#eigenständige-admin-authentifizierung-migration-0004).

Der [Entity-Relationship Graph](frontend/docs/entity-relationship-graph.md) unter `/graph`
zeigt belegte Beziehungen zwischen Organisationen, Orten, Räumen, Veranstaltungen, Terminen
und Benutzern als interaktiven, begrenzten D3-Graph.
