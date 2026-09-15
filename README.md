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
Produktive globale Admin-Autorisierung muss weiterhin explizit in Uranus definiert werden.

Die optionale Ablage erfordert Admin-Migration `0002` und einen separat eingeschränkten
`ADMIN_DATABASE_URL`-Account. Ohne Ablage bleibt explizites `mode=live`-Reporting nutzbar; normale Listen und Dashboard
verwenden gespeicherte Findings und benötigen die Admin-Ablage.
Details: [Backend-Verträge](backend/docs/contracts.md),
[verifizierter Uranus-dev-Stand](backend/docs/source-verification.md).
Frontend und Backend werden in getrennten CI-Jobs geprüft, einschließlich Frontend-Produktionsbuild
und reproduzierbarer Chromium-Tests.


## Markierungen und Notizen

Datensätze lassen sich unabhängig von Prüfhinweisen mit mehreren Anliegen markieren.
Jedes Anliegen enthält Gründe, Dringlichkeit, fortlaufende Notizen und einen Status.
Erledigung und Wiederöffnung werden mit Autor und Zeitpunkt im Verlauf festgehalten.
Die Übersicht „Markierungen“ bietet Status-, Grund- und Dringlichkeitsfilter.

Voraussetzung: Admin-Migration `0003` und die zusätzlichen
[Runtime-Rechte](backend/docs/development.md#markierungen-notizen-und-abschlussverlauf).
