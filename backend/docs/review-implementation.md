# Abschlussbericht: Admin-Review

Branch: `feat/admin-review-findings`. Basis: `1a3c9ed`.
Fachliche Referenz und aktueller Uranus-dev wurden gegen Commit
`733c54133362460353400eb96c60a0cdb9f8450a` geprüft.

## 1. Implementierte Änderungen

Composite-safe Entity-Keys mit UUID-Kompatibilitätsalias; getrennte Frontend-CI;
validierte Proxy-Fehlercodes; einheitliches Score-/Reason-Prioritätsmodell; sichere interne
View-Actions; Activity-API für neun Quelltypen; 18 zusätzliche Qualitätsregeln; Partner-,
Einladungs- und Aktivierungslisten; persistierte Check Runs und First-/Last-Seen/Resolve-Zustände;
menschlicher Reviewworkflow sowie vollständige Frontend-Anbindung.

Die bestehende Venue-Geoprüfung, TEXT-Ablage, read-only-Transaktionen, Auth-Sperre ohne globale
Adminberechtigung, SQL-Bindung und getrennte Migrationen waren bereits vorhanden und wurden
beibehalten. Neue Historie beginnt bei tatsächlichen Scans, ohne Rückdatierung.

## 2. Geänderte Dateien

Vollständige Liste gegenüber der Ausgangsbasis, einschließlich Dokumentation:

```text
.github/workflows/ci.yml
README.md
backend/.env.example
backend/README.md
backend/app/admin_database.py
backend/app/admin_tables.py
backend/app/api/activity.py
backend/app/api/checks.py
backend/app/api/findings.py
backend/app/api/queues.py
backend/app/config.py
backend/app/database.py
backend/app/main.py
backend/app/repositories/activity.py
backend/app/repositories/quality_sources.py
backend/app/repositories/queues.py
backend/app/repositories/venues.py
backend/app/schemas/action.py
backend/app/schemas/activity.py
backend/app/schemas/checks.py
backend/app/schemas/finding.py
backend/app/schemas/queues.py
backend/app/services/checks.py
backend/app/services/dashboard.py
backend/app/services/quality/core.py
backend/app/services/quality/engine.py
backend/app/services/quality/priority.py
backend/app/services/quality/urls.py
backend/app/services/quality/venues.py
backend/app/services/queues.py
backend/docs/architecture.md
backend/docs/contracts.md
backend/docs/development.md
backend/docs/review-implementation.md
backend/docs/source-verification.md
backend/docs/uranus-analysis.md
backend/migrations/versions/0002_check_review.py
backend/tests/conftest.py
backend/tests/fixtures/uranus.sql
backend/tests/test_actions.py
backend/tests/test_activity.py
backend/tests/test_auth.py
backend/tests/test_checks.py
backend/tests/test_core_rules.py
backend/tests/test_quality_venues.py
backend/tests/test_queues.py
frontend/README.md
frontend/app/components/AppNavigation.vue
frontend/app/components/FilterForm.vue
frontend/app/components/FindingDetail.vue
frontend/app/components/QualityOverview.vue
frontend/app/layouts/default.vue
frontend/app/pages/activity.vue
frontend/app/pages/checks.vue
frontend/app/pages/findings.vue
frontend/app/pages/index.vue
frontend/app/pages/queues/[kind].vue
frontend/app/utils/admin-api.ts
frontend/app/utils/filters.ts
frontend/docs/openapi.json
frontend/docs/verification.md
frontend/server/api/admin/[...path].ts
frontend/server/utils/admin-proxy.ts
frontend/shared/contracts.ts
frontend/tests/e2e/activity-workflows.spec.ts
frontend/tests/fixtures/api.ts
frontend/tests/unit/contracts.test.ts
frontend/tests/unit/proxy.test.ts
```

## 3. Neue und geänderte API-Endpunkte

| Methode | Pfad unter /api/v1 | Änderung |
| --- | --- | --- |
| GET | /dashboard/activity | neu: neun Typen, Zeit-/Org-/Typ-/Schlüsselfilter, separate undatierte Liste, Pagination |
| GET | /work-queues/partner_requests | neu: aktuelle Anfragen, Partner-/Userdaten, Status, Alter und Checks |
| GET | /work-queues/team_invitations | neu: offene Einladungen; Alter ausschließlich aus invited_at |
| GET | /work-queues/user_activation | neu: inaktive Accounts; kein Login-/Inaktivitätsverlauf |
| GET / POST | /check-runs | neu: Läufe lesen bzw. vollständigen Scan persistieren |
| PATCH | /finding-reviews | neu: open/in_progress/snoozed/exception, Zuweisung und Reviewmetadaten |
| GET | /findings | erweitert: alle Regeln, entity_key, Score/Reasons, Action, mode=persisted |
| GET | /dashboard/summary | Qualität und Dringlichkeit über alle Regeln |
| GET | /quality/venues/missing-geolocation | unverändert vorhanden; neuer gemeinsamer Finding-/Prioritätsvertrag |

OpenAPI-Snapshot und Zod wurden aktualisiert; ein Test vergleicht den Snapshot mit der Anwendung.
Die persistierte Liste bleibt auch ohne verfügbare Source-Verbindung lesbar.

## 4. Neue Quality Rules

```text
url_syntax
event_without_dates
event_without_location
event_date_without_location
event_date_space_venue_mismatch
image_link_without_image
image_link_unknown_context
image_link_invalid_identifier
image_link_missing_target
image_orphaned_upload
partner_self_request
partner_missing_organization
partner_missing_user
partner_unknown_status
partner_long_pending
partner_accepted_without_grant
team_invitation_old
user_activation_old
```

Zusammen mit bestehendem `venue_missing_geolocation`: **19 Regeln**.
[Regelkatalog und bestätigte Quellen](source-verification.md) erläutern Severity und Ausnahmen.

## 5. Datenbankmigrationen

Revision `0002_check_review.py`, nach 0001: Admin-Run-Coverage, assigned_to,
reviewed_subject, snoozed_until, exception_reason und erweiterte Status-Constraint.
Keine Änderung von Uranus-Tabellen, keine Cross-Schema-FKs. Die bestehende TEXT-Spalte
entity_id bleibt physisch erhalten und wird im Code als entity_key angesprochen.
Migration wurde in einer isolierten Testdatenbank auf Upgrade/check/Downgrade geprüft;
keine Produktivmigration ausgeführt. Optionalen Admin-Account separat bereitstellen.

## 6. Security-relevante Änderungen

Separate eingeschränkte Admin-Schreibverbindung; Superuser/CREATEROLE und Uranus-Schreibrechte
werden abgelehnt. Alle neuen Routen verwenden die vorhandene zentrale Auth-Grenze.
Zuweisung setzt einen existierenden User voraus und vergibt keine Berechtigung.
Nuxt erlaubt nur konkrete neue Admin-Operationen mit validiertem Body. Fehlercodes nur aus
strengem bekannten Format und passendem Status; keine Upstream-Rohtexte. Interne Actions werden
serverseitig erzeugt und clientseitig exakt geprüft. Keine Domain-Schreiblogik oder externen URL-Aufrufe.

## 7. Backend-Tests

- `uv sync --locked`: erfolgreich.
- `uv run ruff check .`: erfolgreich.
- `uv run ruff format --check .`: erfolgreich.
- `uv run mypy`: erfolgreich (47 Quelldateien).
- Vollständiges `uv run pytest -q` mit isolierter PostgreSQL-17/PostGIS-Datenbank: **117 bestanden**,
  keine DB-Skips. Acht Warnungen ausschließlich wegen des deprecated entity_id-Alias.
- Abschließender gezielter Auth-/Snapshot-Test: **19 bestanden**.
- Zusätzlicher Lauf ohne DB mit `-m 'not integration'`: 71 bestanden, 20 explizite DB-Skips,
  23 deselektiert; der vollständige DB-Lauf oben ist maßgeblich.

Geprüft: echte SQL-/PostGIS-Abfragen, Org-/Zeitgrenzen, jede neue Kernregel, umgekehrte Grant-Richtung,
fehlende Referenzen, Nullzeitpunkte, Idempotenz, Coverage, Fehler-/Teilfehler-Schutz, Wiederöffnung,
Ausnahmen, Snooze, Assignment, Locks, eingeschränkte Rollen und schemaexklusive Migrationen.

## 8. Frontend-Tests

Installation mit unverändertem Lockfile, Lint, Typecheck und Build erfolgreich.
**50 Unit-Tests**, **14 Produktions-E2E-Tests** und **14 Development-E2E-Tests** bestanden.
Details: [Frontend-Verifikation](../../frontend/docs/verification.md).
GitHub Actions selbst wurde noch nicht remote ausgeführt; keine Branch-Protection geändert.

## 9. Offene fachliche Review-Punkte

- Nachfolgende Umsetzung zu Issue #2: [eigene Admin-Konten und explizite globale Vergabe](authentication.md);
  keine Uranus-Authentifizierung oder Statusabfrage.
- Venue-scope-Default widerspricht weiterhin dem bestätigten Quell-DDL; Korrektur gehört nach Uranus.
- space_feature_link.space_id ist weiterhin ungeklärt; keine spekulative Regel.
- Space-Vererbung ist in Uranus uneinheitlich. Die neue Regel kennzeichnet ausdrücklich die
  bestätigte öffentliche COALESCE-Semantik, vereinheitlicht aber keine Uranus-Handler.
- Portal-Bildziel: portal versus exportiertes portal2 nicht eindeutig. Zielprüfung und
  Portal-Bild-Orgzuordnung bleiben ausgesetzt; Kontext-/Identifierprüfung ist vorhanden.
- Wikidata/Wikipedia-Feldformat nicht eindeutig; keine URL-Regel dafür.

## 10. Bewusst nicht implementiert / Grenzen

Keine direkten Domain-Edits, Geocoding-Schreibvorgänge, Merges, externe URL-/Dateiabfragen oder
Browser-DB-Verbindungen. Keine erfundene Login-, Join-, Partnerentscheidungs- oder Bildverwendungshistorie.
View-Actions verwenden vorhandene Admin-Seiten; fachliches Editieren wartet auf autorisierte Uranus-Pfade.
Scheduler, persönlicher Sichtungsstand und vollständiges Auditjournal jeder früheren Reviewänderung
sind nicht enthalten. Findings speichern aktuelle Reviewmetadaten und Beobachtungshistorie;
Run-Coverage wird separat festgehalten. Kleine Live-Mengen werden im Speicher global sortiert;
kein ungeprüftes Skalierungsversprechen. Quellabgleich war Repository/Backup-basiert, keine neue
Produktiv-Liveschema-Verifikation. Diese Grenzen sind in [contracts.md](contracts.md) dokumentiert.

## 11. Implementierungscommits

```text
c7528a1 refactor(findings): support composite entity keys
3e33b84 ci(frontend): add locked lint typecheck test build and browser checks
d8ebffe fix(proxy): preserve validated admin api error codes
d7e2f8a refactor(findings): unify priority and add validated action targets
a159c64 feat(activity): add paginated source creation feed and navigation
2cf0fff feat(quality): add deterministic milestone one source rules
567cd38 feat(workflows): add partner invitation and activation queues
7083826 feat(checks): persist covered runs and protect finding review workflow
d172617 feat(frontend): connect activity queues checks and finding reviews
3b70770 fix(review): revisit queue exceptions when source evidence changes
```

Der abschließende Dokumentationscommit enthält diesen Bericht; sein Hash steht in `git log -1`
und im Abschluss der Sitzung.

## 12. PR

Kein PR erstellt und kein Push ausgeführt. Die Änderungen liegen als lokale Commits auf dem
oben genannten Branch vor; kein Deployment und keine Änderung produktiver Daten.
