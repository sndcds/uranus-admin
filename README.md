# Kulturbytes Admin — Open Source Administration, Data Quality & Operations for Uranus

**Kulturbytes Admin** ist das Open-Source-Administrations-, Datenqualitäts- und Operations-Dashboard
für [Kulturbytes](https://kulturbytes.de/) und das Uranus-Backend. Die Anwendung kombiniert
**FastAPI**, **Nuxt 4**, **Vue 3**, **PostgreSQL/PostGIS**, **OpenStreetMap/Nominatim**, D3,
persistierte Qualitätsprüfungen, Admin-Workflows, Geocoding, Benachrichtigungen, Statistiken,
Entity-Timelines und eine abgesicherte SQL-Konsole.

Das Projekt richtet sich an Betreiber und Entwickler von Kultur- und Veranstaltungsplattformen,
die Datenqualität, Moderation, Geodaten, Beziehungen und Betriebsabläufe in einer eigenständigen,
auditierbaren Admin-Oberfläche verwalten möchten.

## Was bietet Kulturbytes Admin?

- **Datenqualität & Review:** Findings, Prüfläufe, Reviews, Markierungen und priorisierte Arbeitslisten.
- **Admin-Workflows:** Inbox, Zuständigkeiten, Wiedervorlagen und Entity-Timelines.
- **Kultur- und Eventdaten:** Veranstaltungen, Orte, Räume, Organisationen, Benutzer/Teams und Bilder.
- **Geodaten:** Geo Scope, fehlende Positionen, Nominatim-Standortvorschläge und OpenStreetMap-Bezug.
- **Analyse:** Aktivität, Statistiken und ein interaktiver Entity-Relationship-Graph.
- **Betrieb & Sicherheit:** getrennte Admin-Authentifizierung, read-only Uranus-Zugriff,
  langlebige Worker, SQL-Herkunft/Diagnostik und Ansible-Deployment.

### Technologie

`FastAPI` · `Python 3.13` · `SQLAlchemy` · `PostgreSQL` · `PostGIS` · `Nuxt 4` · `Vue 3` ·
`TypeScript` · `Pinia` · `Zod` · `D3` · `OpenStreetMap` · `Nominatim` · `Ansible` · `systemd` · `Nginx`

## Repository-Struktur

| Ordner                          | Inhalt                                                        |
| ------------------------------- | ------------------------------------------------------------- |
| [backend/](backend/README.md)   | Python-API, Migrationen, Tests und Backend-Dokumentation      |
| [frontend/](frontend/README.md) | Nuxt-Dashboard, Tests und HTML-Mockup                         |
| [ansible/](ansible/README.md)   | Sicheres Deployment, Preflight, systemd, Nginx und DB-Grenzen |

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

Activity für neun Quelltypen, zentrale Qualitätsregeln einschließlich bestehender Venue-Prüfung,
operative Arbeitslisten sowie optionale persistierte Prüfläufe und Reviews sind angebunden.
Die zentrale Inbox fasst offene Findings, Admin-Zuweisungen, Geocoding-Fälle und fehlgeschlagene
Benachrichtigungen ohne doppelte Aufgaben zusammen. Zuständigkeiten verweisen ausschließlich
auf eigenständige Admin-Konten und niemals auf Uranus-User.
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

### Selective CI

Ein kleiner `changes`-Job klassifiziert den vollständigen PR- beziehungsweise Push-Diff,
bevor teure Jobs starten. Nicht relevante Jobs bleiben als `skipped` im gestarteten
Workflow sichtbar; der Workflow selbst wird nicht mit `paths-ignore` unterdrückt. Damit
bleiben bestehende Required-Check-Kontexte erhalten, ohne dass reine Markdown-Änderungen
Backend-, Frontend- oder Deployment-Matrizen ausführen.

- Backend-CI läuft für Nicht-Markdown-Dateien unter `backend/`, insbesondere Anwendung,
  Migrationen, Tests, `pyproject.toml` und `uv.lock`, sowie für die CI-/Security-Workflows.
- Frontend-CI läuft für Nicht-Markdown-Dateien unter `frontend/`, insbesondere App,
  Nitro, Shared Contracts, Tests, Build-Konfiguration und pnpm-Abhängigkeiten, sowie für
  die CI-/Security-Workflows.
- Deployment-Checks laufen für Nicht-Markdown-Dateien unter `ansible/` und für ihren
  eigenen Workflow. Ansible-READMEs allein lösen die PostgreSQL/PostGIS-Matrix nicht aus.
- Unbekannte Nicht-Dokumentationspfade, gemeinsame Actions und der zentrale Filterkatalog
  gelten konservativ als global. Neue, noch nicht klassifizierte Workflows prüfen alle
  Hauptbereiche. Scheduled Security führt Python- und JS/TS-CodeQL immer vollständig aus.
- Dependency Review bleibt bei jedem Pull Request aktiv. Der Check ist gegenüber den
  Build-/Datenbankmatrizen günstig und schützt auch neue oder indirekte Manifesttypen,
  die noch nicht ausdrücklich im Filterkatalog stehen.

Die gepflegte Prüfmatrix für `.github/path-filters.yml` lautet:

| Änderung                                      | Backend | Frontend | Deployment | Python CodeQL | JS/TS CodeQL |
| --------------------------------------------- | ------: | -------: | ---------: | ------------: | -----------: |
| `README.md`                                   |    skip |     skip |       skip |          skip |         skip |
| `backend/docs/authentication.md`              |    skip |     skip |       skip |          skip |         skip |
| `frontend/docs/design-system.md`              |    skip |     skip |       skip |          skip |         skip |
| `backend/app/service.py`                      |     run |     skip |       skip |           run |         skip |
| `backend/migrations/versions/revision.py`     |     run |     skip |       skip |           run |         skip |
| `backend/uv.lock`                             |     run |     skip |       skip |           run |         skip |
| `frontend/app/pages/example.vue`              |    skip |      run |       skip |          skip |          run |
| `frontend/tests/unit/example.test.ts`         |    skip |      run |       skip |          skip |          run |
| `frontend/pnpm-lock.yaml`                     |    skip |      run |       skip |          skip |          run |
| `ansible/roles/uranus_admin/tasks/deploy.yml` |    skip |     skip |        run |          skip |         skip |
| `ansible/README.md`                           |    skip |     skip |       skip |          skip |         skip |
| `ansible/tests/test_deployment.py`            |    skip |     skip |        run |           run |         skip |
| `.github/workflows/ci.yml`                    |     run |      run |       skip |           run |          run |
| `.github/workflows/security.yml`              |     run |      run |       skip |           run |          run |
| `.github/workflows/deployment-checks.yml`     |    skip |     skip |        run |           run |          run |
| Backend- und Frontend-Code                    |     run |      run |       skip |           run |          run |
| Markdown plus Backend-Code                    |     run |     skip |       skip |           run |         skip |

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

Das vorsichtige Deployment der bestehenden Installation auf `admin.kulturbytes.de`
ist in [ansible/README.md](ansible/README.md) beschrieben. Die Rolle prüft die bestehenden Source/Admin-Grenzen
ausschließlich lesend und verwaltet separat die isolierte SQL-Console-Infrastruktur.
Produktive Änderungen benötigen einen geprüften Dry Run und ausdrückliche Freigaben.

FastAPI authentifiziert eigene Admin-Konten; eine separate Tabelle in `admin` vergibt globale
System-Admin-Rechte. Es gibt keine Uranus-Authentifizierung oder Statusabfrage. Der Browser nutzt
HttpOnly-Sitzungscookies über Nitro. Einrichtung einschließlich Migration 0004, eingeschränkter
Runtime-Grants und Betreiber-CLI: [Auth-Vertrag](backend/docs/authentication.md) und
[Provisionierung](backend/docs/development.md#eigenständige-admin-authentifizierung-migration-0004).

Der [Entity-Relationship Graph](frontend/docs/entity-relationship-graph.md) unter `/graph`
zeigt belegte Beziehungen zwischen Organisationen, Orten, Räumen, Veranstaltungen, Terminen
und Benutzern als interaktiven, begrenzten D3-Graph.

## Statistiken

`/statistics` zeigt Neuanlagen im Zeitverlauf mit D3, sieben Kennzahlen, Zeitraumvergleich und
neuesten Entitäten. Zeitstempel, Grenzen und Einladungssemantik: [Statistik-Dokumentation](frontend/docs/statistics.md).

Domain inspection now includes events, venues/spaces, organizations, users/teams,
and images with searchable lists, paginated relations, graph links and workflow
links. Creation remains unavailable until authorized Uranus API delegation exists.
The dashboard distinguishes the latest check run from the latest successful run.
All six entity detail pages show one server-aggregated, cursor-paginated timeline of
evidenced source and admin workflow events; missing timestamps are never synthesized.
Operators can audit source metadata with `python -m app.source_schema_verify --json`;
see [source verification](backend/docs/source-verification.md).

Optional public URL observations run separately with
`python -m app.url_check_worker --once` (migration 0007 and explicit runtime grants).
They never run during normal list requests or the deterministic syntax scan.
See [worker operations and SSRF safeguards](backend/docs/development.md).

Organization email notifications (DE/DA/EN) use a separate durable worker:
`cd backend && uv run python -m app.notification_worker --once`.
Migration 0008 and explicit notification runtime grants are required. Delivery defaults off;
inspect `/notifications` and previews before enabling SMTP. See the
[notification architecture, source verification and deployment guide](backend/docs/notifications.md).

[Entity timeline contract, sources and deployment](backend/docs/entity-timeline.md).

[Assignments and admin inbox](backend/docs/assignments-inbox.md) documents task identity,
optimistic locking, due dates, aggregation and the migration/grant sequence.

[SQL / Datenherkunft – registrierte Queries, Sicherheitsmodell und Coverage](backend/docs/sql-provenance.md).


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
[Suchvertrag](backend/docs/contracts.md#global-search-and-command-palette).
