# Verifikation nach Review-Umsetzung

Stand: 2026-09-14, Branch `feat/admin-review-findings`.

| Prüfung | Ergebnis |
| --- | --- |
| pnpm install --frozen-lockfile | erfolgreich; pnpm 12.3.4, Lockfile unverändert |
| pnpm lint | erfolgreich |
| pnpm typecheck | erfolgreich |
| pnpm test | 50 Tests bestanden |
| pnpm build | erfolgreich |
| TEST_PRODUCTION=1 pnpm test:e2e | 14 Tests bestanden, Desktop/Mobil, 9,1 Sekunden |
| pnpm test:e2e | 14 Tests bestanden, Desktop/Mobil, 42,3 Sekunden |

Frontend-Prüfungen liefen mit Node 22.22.3; zusätzlich wurde der erste Installations-/Buildlauf
mit dem bereits vorhandenen Node 26.8.2 ausgeführt. Beide erfüllen package.json.
Playwright benötigt außerhalb der Dateisandbox einen lokalen Loopback-Server. Fehlgeschlagene
Starts in der Sandbox wurden mit dieser Freigabe wiederholt. Keine Assertions abgeschwächt;
ein Select-Locator wurde auf seine zugängliche Rolle präzisiert und synthetische UUID-Fixtures
wurden auf gültige UUID-Formate korrigiert. Chromium/Node melden lediglich die bestehende
NO_COLOR/FORCE_COLOR-Warnung.

Backend separat vollständig geprüft: **117 Tests bestanden**, kein DB-Test übersprungen.
Dazu Ruff, Ruff-Format, strict mypy; isolierte PostgreSQL-17/PostGIS-Testinstanz. Ein abschließender
gezielter Auth-/OpenAPI-Snapshot-Lauf bestand ebenfalls (19 Tests). Die acht DeprecationWarnings
im vollständigen Backend-Lauf betreffen ausschließlich den bewusst erhaltenen entity_id-Alias.

Browserprüfungen verwenden synthetische Admin-Responses. Sie prüfen Navigation, Pagination,
Fehler-/Zugangszustände, unbekannte Zeitstempel, Einladung ohne erfundenes Alter, Reviewausnahmen,
fehlenden manuellen Resolve und die reale Nitro-Route-/Methoden-/Authgrenze. Sie ersetzen keine
produktive Uranus-Autorisierungsprüfung oder Lastmessung. Die DB-Regeln und eingeschränkten
Runtime-/Migrationsrollen werden in den Backend-Integrationstests geprüft.

GitHub Actions wurde erweitert, aber in dieser Sitzung weder gepusht noch auf GitHub ausgeführt.
Branch-Protection wurde nicht geändert. Die CI führt den lokal reproduzierten Produktionsbrowserlauf
im eigenen Frontend-Job aus. Kein produktives Deployment und keine Produktivmigration.
