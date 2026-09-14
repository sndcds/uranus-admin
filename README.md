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
