# PR #14: Review-Korrekturen und Verifikation

Stand: 2026-09-15. Repository `sndcds/uranus-admin`, bestehender Branch
`feat/admin-review-findings`, [PR #14](https://github.com/sndcds/uranus-admin/pull/14).
Ausgangspunkt der Korrekturen: `93ed7bf` (Passwort-Fix bereits nach dem ursprünglich genannten
Head `fa3b8a2`). Kein separater Feature-Branch, keine zusätzliche Migration, kein Merge.

## Behobene Review-Punkte

| Bereich | Ergebnis |
| --- | --- |
| Testrollen | Echte separate PostgreSQL-Login-Rolle mit eigenem statischem Testpasswort; exakt dieselben Credentials in der URL, keine Passwortinterpolation. Setup-DDL transaktional, Rollen/Grants/Schema werden entfernt. |
| Entity Keys | SELECT/RETURNING verwenden explizite Labels für `entity_key`; ausschließlich die Legacy-DB-Spalte und der deprecated UUID-Ausgabealias heißen weiter `entity_id`. |
| Scan-Performance | Indizes und Relevanzaggregate einmal je Snapshot; kein wiederholter Gesamtdurchlauf der Termine je Venue, Space, Organisation oder URL-Feld. |
| Operative GETs | Findings und Dashboard standardmäßig persisted; Live nur explizit. Gespeicherte Findings werden in SQL gefiltert, gezählt, sortiert und paginiert. |
| Work Queues | Filter, Alter, Status, Organisation, Schlüssel, Sortierung, COUNT/LIMIT/OFFSET in PostgreSQL; Aktivierungszuordnungen einmal gruppiert. Grant-Richtung und Einladungstimestamps unverändert. |
| Runtime-Rechte | Echte eingeschränkte Rolle in Integrationstests: Domain SELECT erlaubt, Schreiben/DDL verboten, kein Superuser/CREATEROLE. Boundary prüft Schema-CREATE und schädliche History-Rechte zusätzlich. |
| Mark-Historie | SELECT/INSERT für Events; UPDATE/DELETE/TRUNCATE verweigert. Eindeutige Versionen, atomare Events, stale Update 409, unveränderte alte Ereignisse; Zeitstempel laufen nicht rückwärts. |
| Check Runs | Nur vollständige erwartete Regelmenge zählt als Erfolg; fehlgeschlagen/leer/abgeschnitten löst nichts auf. Coverage schützt nicht geprüfte Entitäten. Check und Review serialisiert; Freigabe nach Erfolg, Fehler und Cancellation geprüft. |
| Persisted Reload | UUID- und Composite-Lebenszyklen einschließlich ursprünglicher API-Metadaten; Foundation-Zeilen ohne optionale Metadaten; SQL-Pagination gegen rekonstruierte Ergebnisse geprüft. |
| Proxy | Bestehende Route-/Method-/Query-Allowlist, Bodylimit, Zod und bereinigte Fehler bleiben; strenge UUID-Pfade, nur bewusstes Authorization-Forwarding und keine ambienten Credentials. |
| Migrationen | 0001 → 0002 → 0003, 0003 → 0002 → 0001 → base sowie erneutes Upgrade geprüft; Uranus-Schemafingerprint unverändert. Datenverluste dokumentiert. |

## Neue oder erweiterte Regressionen

- UUID-Venue, Composite-Partneranfrage und Composite-Mitgliedschaft: scan → persist → reload →
  review → recheck → resolve; Action, Organisation, Priority/Score/Reasons und Metadaten bleiben gleich.
- Foundation-Zeilen, SQL-Filter/Pagination, gespeicherte Dashboard-Zähler und keine versteckten
  Scans beim Standard-GET oder bei normaler Browsernavigation/Aktualisierung.
- Fehlgeschlagene, teilweise, leere und abgeschnittene Runs; nicht abgedeckte Objekte;
  unveränderte und altersbedingt veränderte Evidence, echte Evidence-Änderung; aktiver/abgelaufener Snooze.
- Zwei parallele Checks, Check mit gleichzeitigem Review, Scan-/Review-Exception und Cancellation;
  eine unabhängige PostgreSQL-Verbindung kann den Lock danach wieder erwerben.
- Mehrere Events/Venues/Termine, effektive Venue-/Space-Vererbung, veröffentlichte/kommende/baldige
  Termine. Arbeitszähler mit 30 und 100 Entitäten begrenzen Terminbesuche linear statt zeitabhängiger Benchmarks.
- Queue-Filter und Seiten einschließlich Gleichständen, NULL-/zukünftiger Einladungstimestamps,
  geschlossener Zustände, Organisationen und injektionsartiger Schlüssel gegen fachliches Mapping.
- Reale Runtime-Grants, verbotene Domain-/DDL-/History-Schreiboperationen, doppelte History-Version;
  bestehende Create/Update/Note/Complete/Reopen/409-Tests mit stärkerem Vergleich früherer Events.
- Schrittweise Migrationen mit echten Foundation-/Review-/Mark-/History-Daten und Verlustprüfung.

## Lokale Ergebnisse

| Prüfung | Ergebnis |
| --- | --- |
| uv sync --locked | erfolgreich, Lockfile unverändert |
| uv/venv Ruff check und format --check | erfolgreich, 73 Python-Dateien formatiert |
| mypy | erfolgreich, 51 Quelldateien |
| uv run pytest -q mit TEST_DATABASE_URL und CI=1 | **168 bestanden**, keine übersprungen, 16,00 s |
| Test-DB | PostgreSQL 17/PostGIS, isolierte DB mit `_test`-Suffix, TCP mit SCRAM-Passwortanmeldung |
| Cleanup-Nachprüfung | 0 admin/uranus-Schemas, 0 admin_history_test/admin_migrator_test-Rollen |
| Frontend Install/Lint/Typecheck/Build | erfolgreich |
| Frontend Unit-Tests | **59 bestanden** |
| Playwright Production / Development | **20 / 20 bestanden**, Desktop und Mobil |
| git diff --check | erfolgreich |

Die lokale DB lief isoliert auf Port 55439, nicht auf einer vorhandenen Development-/Produktions-DB.
Acht Backend-DeprecationWarnings betreffen ausschließlich den bewusst erhaltenen `entity_id`-Alias.
GitHub prüft den gepushten Head separat über [PR Checks](https://github.com/sndcds/uranus-admin/pull/14/checks).
Keine Assertions wurden abgeschwächt oder Tests entfernt. Die bisherigen Live-API-Tests wählen
nun ausdrücklich `mode=live` und behalten ihre fachlichen Assertions.

## Deployment und verbleibende Grenzen

- [Minimale Runtime-Grants und Downgrade-Verluste](development.md#minimale-rechte-nach-migration-0003)
  vor Deployment beachten. Vorhandene breite History-Grants einschließlich geerbter/Spaltengrants
  müssen korrigiert werden; die neue Boundary weist sie ab. Migrationen 0002/0003 separat ausführen.
- Standardlisten benötigen `ADMIN_DATABASE_URL`. Kein Live-Fallback; vor dem ersten Check ist
  der leere Speicher kein Beleg für Datenqualität. Domain Reader, Runtime und Migrator bleiben getrennt.
- Vollscans bleiben synchron und halten ausgewählte Quellspalten/Befunde im Speicher. Der Proxy
  wartet höchstens 120 Sekunden; eine produktive Maximallaufzeit ist ohne Lastmessung nicht belegt.
  Lookup/Relevanz ist linear, Sortierungen und Datenbankarbeit bleiben zusätzliche Kosten.
- COUNT und Sortierung können trotz kleiner API-Seite viele DB-Zeilen verarbeiten. Keine Uranus-DDL
  oder neuen Source-Indizes in diesem PR. Die passenden produktiven Indizes bleiben Betriebsarbeit.
- Background Worker mit 202/run_id und Run-Detailendpoint, Streaming/Batches und produktive
  Lastmessung bewusst verschoben; [Semantik und Folgearbeit](contracts.md#operative-gets-und-scan-kosten).
- Produktive globale Uranus-Admin-Autorisierung bleibt eine bestehende separate Voraussetzung.
  Finding-Reviews besitzen weiterhin kein vollständiges Ereignisjournal; Markierungen besitzen es.

## Implementierungscommits

- `93ed7bf`: Testrollen-Passwort (bereits vor dieser Review-Runde).
- `682f9e8`: konsistente Persistenz-Mappings und UUID-/Composite-Lebenszyklen.
- `014e7f7`: Scan-Indizes und aggregierte Relevanz.
- `4cd20f1`: SQL-seitige Work Queues.
- `466c078`: Runtime-/History-Rechte, Cleanup und Migrationstests.
- `e9739ef`: gespeicherte Standardabrufe, vollständige Runs, Lock-/Proxy-/UI-Regressionen.

Der abschließende Dokumentationscommit enthält diesen Bericht; sein Hash steht im PR-Verlauf.

## Geänderte Dateien dieser Review-Runde

- [README.md](../../README.md)
- [backend/README.md](../README.md)
- [backend/app/admin_database.py](../app/admin_database.py)
- [backend/app/api/checks.py](../app/api/checks.py)
- [backend/app/api/dashboard.py](../app/api/dashboard.py)
- [backend/app/api/findings.py](../app/api/findings.py)
- [backend/app/repositories/queues.py](../app/repositories/queues.py)
- [backend/app/schemas/dashboard.py](../app/schemas/dashboard.py)
- [backend/app/schemas/finding.py](../app/schemas/finding.py)
- [backend/app/services/checks.py](../app/services/checks.py)
- [backend/app/services/dashboard.py](../app/services/dashboard.py)
- [backend/app/services/marks.py](../app/services/marks.py)
- [backend/app/services/quality/core.py](../app/services/quality/core.py)
- [backend/app/services/quality/engine.py](../app/services/quality/engine.py)
- [backend/app/services/queues.py](../app/services/queues.py)
- [backend/docs/contracts.md](contracts.md)
- [backend/docs/development.md](development.md)
- [backend/docs/pr14-review-verification.md](pr14-review-verification.md)
- [backend/tests/conftest.py](../tests/conftest.py)
- [backend/tests/test_checks.py](../tests/test_checks.py)
- [backend/tests/test_core_rules.py](../tests/test_core_rules.py)
- [backend/tests/test_dashboard.py](../tests/test_dashboard.py)
- [backend/tests/test_database.py](../tests/test_database.py)
- [backend/tests/test_marks.py](../tests/test_marks.py)
- [backend/tests/test_quality_venues.py](../tests/test_quality_venues.py)
- [backend/tests/test_queues.py](../tests/test_queues.py)
- [frontend/README.md](../../frontend/README.md)
- [frontend/app/components/FilterForm.vue](../../frontend/app/components/FilterForm.vue)
- [frontend/app/components/QualityOverview.vue](../../frontend/app/components/QualityOverview.vue)
- [frontend/docs/openapi.json](../../frontend/docs/openapi.json)
- [frontend/docs/verification.md](../../frontend/docs/verification.md)
- [frontend/server/utils/admin-proxy.ts](../../frontend/server/utils/admin-proxy.ts)
- [frontend/shared/contracts.ts](../../frontend/shared/contracts.ts)
- [frontend/tests/e2e/activity-workflows.spec.ts](../../frontend/tests/e2e/activity-workflows.spec.ts)
- [frontend/tests/unit/contracts.test.ts](../../frontend/tests/unit/contracts.test.ts)
- [frontend/tests/unit/proxy.test.ts](../../frontend/tests/unit/proxy.test.ts)
