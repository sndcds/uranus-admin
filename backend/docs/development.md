# Entwicklung und Betriebsvorbereitung

## Installation und Start

Soweit nicht anders angegeben, werden die Befehle dieser Anleitung im Ordner `backend/` ausgeführt
(vom Repository-Wurzelverzeichnis aus zunächst `cd backend`).

Python 3.13, uv, PostgreSQL mit PostGIS. Python-Abhängigkeiten ausschließlich in pyproject.toml
und uv.lock. Mit `uv sync --locked` installieren, `.env.example` nach `.env` kopieren und bearbeiten.

```bash
uv run uvicorn app.main:app --reload --no-access-log
# Ohne Reload, mit APP_HOST / APP_PORT:
uv run python -m app
```

Kein Netzwerkzugriff auf Uranus beim Import; DB-Pool entsteht im Lifespan und wird beim Shutdown
aufgeräumt. SIGTERM beendet Uvicorn geordnet. Für systemd ein dediziertes Benutzerkonto,
`WorkingDirectory=/pfad/zum/projekt/backend` und eine geschützte EnvironmentFile verwenden;
ExecStart kann auf `/pfad/zum/projekt/backend/.venv/bin/python -m app` zeigen.
Kein produktives Deployment erfolgt hier.

## Datenbank und Rollen

Das Quellschema heißt in diesem Meilenstein bewusst fest `uranus`. Abweichende Schemanamen
erfordern einen geprüften Code-/Testvertrag, keine dynamischen SQL-Identifier aus Requests.
PostGIS-Funktionen müssen verfügbar sein (üblich im Schema public). Die API legt weder
Erweiterungen noch Quelltabellen an. Für Development eine separate DB/Kopie bereitstellen.

Die drei Verbindungen verwenden getrennte Rollen: `uranus_reader` für `DATABASE_URL`,
`admin_user` für `ADMIN_DATABASE_URL` und `admin_migrator` ausschließlich für
`ADMIN_MIGRATION_DATABASE_URL`. Vollständige Provisionierung, Rechteprüfung und Fehlerdiagnose
stehen unter [Minimale Rechte nach Migration 0003](#minimale-rechte-nach-migration-0003).

Die Source-Verbindung setzt `default_transaction_read_only` und je Transaktion zusätzlich
READ ONLY / REPEATABLE READ. PostgreSQL-Rechte sichern diese Grenze unabhängig vom Python-Code.
Die Admin-Verbindung muss DML ausführen können und darf deshalb nicht generell read-only sein.

Der bereitgestellte Live-Backup wurde zusätzlich in einem lokalen Schema `uranus` unter
`kulturbytes_admin_snapshot` geprüft. Der ursprüngliche Backup wird nicht versioniert.
Alle fünf Endpunkte funktionierten dort mit SELECT-Account; Ergebnisse und Schemaabweichungen
stehen in [uranus-analysis.md](uranus-analysis.md). UTC-Speicherung ist vom Betreiber bestätigt.

## Environment

| Variable | Default / Zweck |
| --- | --- |
| APP_ENV | production; development/test/staging/production |
| APP_DEBUG | false; aktiviert keine HTTP-Stacktraces |
| APP_HOST / APP_PORT | 127.0.0.1 / 8000 bei `python -m app` |
| DATABASE_URL | asyncpg-DSN des Readers, als SecretStr behandelt |
| URANUS_API_URL | http://localhost:8080; öffentliche Activity-Links nur bei https://api.kulturbytes.de |
| URANUS_TIMESTAMP_TIMEZONE | UTC; vom Betreiber für diesen Backup bestätigt, IANA-Zeitzone konfigurierbar |
| ADMIN_TIMEZONE | Europe/Berlin; Kalendertag „today“ |
| EVENT_TIMEZONE | Europe/Berlin; Reporting-Zeitzone lokaler Terminzeiten |
| UPCOMING_DAYS | 14; baldige Relevanz, 1–365 |
| CORS_ORIGINS | leer; kommaseparierte exakte HTTP(S)-Origins ohne Pfad/Trailing Slash |
| LOG_LEVEL | INFO; DEBUG/INFO/WARNING/ERROR/CRITICAL |
| DB_POOL_SIZE / DB_MAX_OVERFLOW | 5 / 5 |
| DB_TIMEOUT_SECONDS | 10; Verbindungs-, Pool- und Query-Zeitlimit |
| OPENAPI_ENABLED | false; nur development/test kann /docs und /openapi.json aktivieren |
| DEV_AUTH_ENABLED | false; ausschließlich development/test |
| DEV_ADMIN_TOKEN | kein Default; mindestens 32 Zeichen, nur für expliziten Dev-Override |
| ADMIN_DATABASE_URL | optionaler separater Runtime-Login für Admin-Metadaten; für die Standardlisten erforderlich |
| ADMIN_MIGRATION_DATABASE_URL | ausschließlich Alembic; muss im Prozess-Environment gesetzt sein |
| AUTH_PUBLIC_ORIGIN | kein Default; exakte Browser-Origin für Login/Logout/Cookie-Schreibrequests; HTTPS in Production/Staging |
| AUTH_SESSION_SECONDS | 3600; absolute Sitzungsdauer, 300–28800 Sekunden |
| AUTH_IDLE_SECONDS | 900; Inaktivitätsfrist, 60–3600 Sekunden, höchstens absolute Dauer |
| ADMIN_AUTH_MANAGEMENT_DATABASE_URL | nur Betreiber-CLI; niemals dem Runtime-Service geben |

Die Anwendung liest `.env` über Pydantic Settings. Alembic liest seinen separaten Zugang
bewusst nur aus dem Prozess-Environment, nicht implizit aus der Runtime-Konfiguration.
Passwörter/Tokens niemals über eine öffentliche URL, Screenshots oder Git weitergeben.

Für lokale Requests einen zufälligen Development-Token erzeugen:

```bash
uv run python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

In `.env` setzen, `DEV_AUTH_ENABLED=true`, `APP_ENV=development`. Der Bearer-Token ist
kein Uranus-Login. Kein sicherer Production-Workaround wird daraus abgeleitet.

## Admin-Migrationen

Das Schema `admin` muss separat durch den DB-Betreiber bereitgestellt werden, bevor die
Alembic-Versionstabelle darin angelegt werden kann. Keine Uranus-Migrationen importieren.

```bash
# ADMIN_MIGRATION_DATABASE_URL sicher in der Shell/Serviceumgebung bereitstellen.
uv run alembic upgrade head
uv run alembic current
uv run alembic check
# Nur in einer wegwerfbaren Development-DB: eigene Daten werden dabei entfernt.
uv run alembic downgrade base
```

Ohne explizite Migrations-DSN wird abgebrochen; DATABASE_URL ist niemals ein DDL-Fallback.
`admin.alembic_version`, `admin.check_run`, `admin.finding`, `admin.record_mark` und
`admin.record_mark_event` bilden die Workflow-Ablage. Migration `0004` ergänzt ausschließlich
`admin.auth_account`, `admin.auth_system_admin`, `admin.auth_session` und `admin.auth_login_bucket`.
Kein Create/Drop von uranus, keine automatischen Migrationen beim Start. Generierte Migrationen
immer prüfen; Schemafilter plus eingeschränkte DB-Rolle verhindern Domain-Änderungen.

## Tests mit PostgreSQL/PostGIS

Ein eigener Container ist eine einfache Möglichkeit (nur Testdaten, Port lokal gebunden):

```bash
docker run --name kulturbytes-admin-test-db --rm \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=kulturbytes_admin_test \
  -p 127.0.0.1:55432:5432 -d postgis/postgis:17-3.5
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/kulturbytes_admin_test uv run pytest
docker stop kulturbytes-admin-test-db
```

Die Testrolle braucht in dieser **ausschließlich wegwerfbaren Testdatenbank** DDL-/CREATEROLE-
Rechte für Fixture-Aufbau und Migrationsgrenztest; der Runtime-Account braucht das niemals.
Integrationstests verweigern DB-Namen ohne `_test` sowie vorhandene Uranus-Schemas. Kein SQLite.
Bei abgebrochenem Testlauf den wegwerfbaren Container neu erstellen, nicht Schutzprüfungen entfernen.

Fixture: zwei Organisationen, drei Venues (NULL, gültiger Point, POINT EMPTY), drei Events,
zehn Termine, ein Space, User, Membership, Partneranfrage und zwei Bilder (eines ohne Datum).
Die CREATE TABLE-Statements, vollständigen Enums, Constraints und Indizes stammen aus dem
bereitgestellten Live-Backup. Es werden keine Produktivzeilen übernommen. Triggerfunktionen
sind ausgeschlossen: Event-Textsuche hängt von Funktionen außerhalb des Dump-Schemas ab.
Die Fixture ist ausdrücklich kein installierbares Uranus-Schema.

Tests decken Perioden inkl. DST, Prioritäten, Mapping, API-/Filter-/Pagination-Verträge,
Auth-/CORS-/Fehlergrenzen, echte PostGIS-Geometrien, Vererbung, Status, Zeitgrenzen,
neue Termine alter Events, NULL-Timestamps, read-only Transaktionen sowie migrationssichere
Upgrade/Check/Downgrade ab. Der Migrationstest verwendet eine eingeschränkte eigene Rolle.

## Qualität und Debugging

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Logs sind JSON mit Methode, Route-Template, Status und Dauer. Querystrings und Datenwerte
werden nicht geloggt. DB-Fehler erscheinen als 503 mit Fehlercode; interne Fehler als 500,
ohne Stacktrace oder SQL. SQLAlchemy echo nicht zur Fehlersuche auf echten Daten aktivieren.
Auch bewusst ausgelöste API-Fehler mit Status 5xx erzeugen einen `admin.error`-Eintrag mit
Fehlercode, Status und Route. Mit `APP_DEBUG=true` in Development/Test enthält dieser Eintrag
zusätzlich den Traceback einschließlich verketteter Ursachen, beispielsweise bei abgelehnten
Admin-Runtime-Rechten. Die HTTP-Antwort enthält weiterhin keinen Traceback; ohne Debug bleiben
auch die Serverlogs frei davon. Nach Konfigurationsänderungen den Backend-Prozess neu starten.
`/health` bleibt bei DB-Ausfall erreichbar; `/ready` prüft Source-Verbindung und die
konfigurierte Admin-/Auth-Ablage einschließlich Migrationstand, Boundary und positiven Grants. Ein 503 `source_timezone_unconfigured` erfordert den belegten
Speichervertrag, ein 503 `admin_auth_unconfigured` die unabhängige Admin-Auth-Konfiguration (Origin und Admin-Ablage).

Der Test `test_quality_query_explain` schreibt einen JSON-Plan ins pytest-Tempverzeichnis.
Lokaler erster Lauf mit PostgreSQL 17/PostGIS: 2 Ergebniszeilen, oberer Knoten Hash Join,
Planung ca. 1,5 ms, Ausführung ca. 7 ms. Minimalfixture, kalter/kleiner Datenbestand und lokale
Umgebung: daraus keine Produktionslaufzeit ableiten. Für größere anonymisierte Kopien
`EXPLAIN (ANALYZE, BUFFERS)` der parametrisierten Query ausführen. Indexkandidaten stehen in
[future-uranus-improvements.md](future-uranus-improvements.md).

## CI

Der Workflow [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) läuft bei jedem
Push und Pull Request. Vor einem Merge müssen alle vier funktionalen Jobs und die
Security-Prüfungen für den aktuellen PR-Stand erfolgreich sein:

| Job | Arbeitsverzeichnis | Prüfungen |
| --- | --- | --- |
| `lint` | `backend/` | Ruff-Lint und Formatprüfung |
| `typecheck` | `backend/` | strict mypy |
| `tests` | `backend/` | pytest einschließlich PostgreSQL-/PostGIS-Integrationstests und Prüfung der dokumentierten Rollen-Grants |
| `frontend` | `frontend/` | ESLint, Nuxt-Typecheck, Vitest, Produktionsbuild und Playwright-E2E mit Chromium |

Dies sind die im Workflow ausgeführten Merge-Prüfungen. Ob GitHub sie technisch als
Required Status Checks erzwingt, wird separat durch Branch Protection bzw. Repository-Rulesets
festgelegt; diese Einstellungen sind nicht in der Workflow-Datei definiert.

### Security gates

[security.yml](../../.github/workflows/security.yml) ist die maßgebliche CodeQL-Konfiguration.
GitHub Default Setup wurde am 16.09.2026 über die Repository-API geprüft: `not-configured`.
Deshalb eigener Workflow für Python und JavaScript/TypeScript, keine parallele Default-Konfiguration.
Er läuft für PRs, Pushes auf main und wöchentlich. Beide Sprachen verwenden `build-mode: none`:
keine Installation oder Ausführung fremder PR-Paketskripte mit dem CodeQL-Upload-Token.

Dependency Review läuft für Pull Requests und scheitert bei neu eingeführten **high/critical**
Vulnerabilities. Moderate/low werden nicht zum Gate erhoben. Das Repository ist öffentlich;
[GitHub unterstützt Dependency Review dafür](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review).
Voraussetzung ist der aktivierte **Dependency graph** unter Repository Settings → Advanced
Security. Meldet der Job „Dependency review is not supported … ensure that Dependency graph
is enabled“, muss ein Repository-Administrator diese Einstellung aktivieren und den Job erneut
starten. Aktivierte Dependabot-Alerts allein belegen diese Voraussetzung nicht. Die Anleitung
[Dependency graph aktivieren](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/enable-dependency-graph)
beschreibt die Repository-Einstellung. Fehlende Features/Berechtigungen werden nicht per
`continue-on-error` verborgen; der PR bleibt bis zur erfolgreichen Prüfung nicht mergebereit.

Alle Actions sind auf Commit-SHAs fixiert. Token standardmäßig nur `contents: read`; ausschließlich
CodeQL darf Security-Ergebnisse hochladen (`security-events: write`). Dependency Review benötigt
keine Schreibrechte oder PR-Kommentare. Kein `pull_request_target`, keine Production-Secrets,
keine Production-DB und kein privilegierter Build aus einem Fork. Fork-PRs verwenden den normalen
`pull_request`-Kontext mit GitHubs eingeschränkten Token-Rechten.

Als erforderliche Checks in Branch Protection/Rulesets zusätzlich `CodeQL (python)`,
`CodeQL (javascript-typescript)` und `Dependency review` auswählen. Workflow-Dateien ersetzen
keine Repository-Rulesets. Konfiguration lokal mit actionlint prüfen; bestehende funktionale
Jobs und deterministische Lockfile-Installationen bleiben unverändert.

### Backend

Alle drei Backend-Jobs installieren ihre Abhängigkeiten mit `uv sync --locked` und verwenden
Python 3.13.15 sowie uv 0.12.5. Die entsprechenden lokalen Befehle aus `backend/` sind:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
# TEST_DATABASE_URL für den separaten Testcluster setzen, siehe Abschnitt oben.
uv run pytest -q
```

Der CI-Testjob startet einen PostgreSQL-17-/PostGIS-3.5-Service mit Healthcheck und setzt
`TEST_DATABASE_URL` auf seine wegwerfbare Testdatenbank. Für einen vergleichbaren lokalen Lauf
muss ebenfalls ein isolierter Testcluster erreichbar sein; ohne Test-DSN überspringt ein lokaler
pytest-Lauf die DB-Integrationstests und ersetzt dieses Merge-Gate nicht. Mit gesetztem `CI`
bricht die Testfixture bei fehlender Test-DSN ausdrücklich mit einem Fehler ab.

### Frontend

Der Frontend-Job verwendet Node.js 22.22.3 und die in
[`frontend/package.json`](../../frontend/package.json) festgelegte pnpm-Version (aktuell 12.3.4).
Er installiert mit unverändertem Lockfile und führt die folgenden Schritte in dieser Reihenfolge
aus. Aus `backend/` lässt sich derselbe Ablauf in einer Subshell starten:

```bash
(
  cd ../frontend || exit
  pnpm install --frozen-lockfile &&
  pnpm lint &&
  pnpm typecheck &&
  pnpm test &&
  pnpm build &&
  pnpm exec playwright install --with-deps chromium &&
  TEST_PRODUCTION=1 pnpm test:e2e
)
```

`TEST_PRODUCTION=1` lässt Playwright den zuvor erzeugten Produktionsbuild starten. Ein grüner
Vitest-Lauf allein reicht nicht: Build und E2E gehören ebenfalls zum Frontend-Merge-Gate.
Die Playwright-Konfiguration und Testfixtures stehen unter
[`frontend/playwright.config.ts`](../../frontend/playwright.config.ts) und
[`frontend/tests/e2e/`](../../frontend/tests/e2e/).

Actions sind auf Commit-SHAs, das PostGIS-Image auf einen amd64-Manifest-Digest fixiert.
Der Workflow verwendet keine produktiven Secrets oder Datenbankzugänge.
Eine lokale Prüfung ersetzt keinen tatsächlich auf GitHub gelaufenen Job.

## Erweiterung: Check Runs und Reviews

Der neue Vertrag steht unter [contracts.md](contracts.md); er ersetzt die früheren Aussagen
über noch nicht angebundene Persistenz. Migration `0002` ergänzt Regelabdeckung und Reviewfelder.
Keine Domain-Tabelle wird geändert. Vorhandene Daten bleiben beim Upgrade erhalten.

Die vollständigen Reader- und Runtime-Grants stehen in der
[zentralen Rollen-Anleitung](#minimale-rechte-nach-migration-0003).
`ADMIN_DATABASE_URL` aktiviert die Ablage. Ohne diese Variable bleiben mit lokalem Dev-Token explizite
`mode=live`-APIs verfügbar; Production-Anmeldung benötigt die Admin-Ablage. persistierte Standardlisten und Reviews liefern 503
`admin_storage_unconfigured`.

Neue Reporting-Schwellen: `IMAGE_ORPHAN_GRACE_HOURS=48`, `PENDING_AGE_DAYS=14`,
`ACTIVATION_AGE_DAYS=7`. Änderungen sind Produktentscheidungen, keine historischen Fakten.

Manuelle Prüfläufe über POST `/api/v1/check-runs`; es gibt keinen automatisch gestarteten Scheduler.
Ein Worker-/Serverabbruch erzeugt keinen Erfolg. Ein noch laufender alter Eintrag wird beim nächsten
exklusiven Lauf als unterbrochen markiert. Die Detailsemantik steht im Vertragsdokument.

Aktuelle Tests ergänzen die ursprünglichen Fixtures um synthetische Event-Links, Lizenzen,
Bildlinks und Grants aus dem überprüften dev-DDL sowie isolierte Admin-Rollen. Upgrade/check/
Downgrade werden weiterhin mit einem eingeschränkten Migrator ausgeführt. Tests verändern
niemals eine bestehende Uranus-Installation.


## Markierungen, Notizen und Abschlussverlauf

Migration `0003` legt `admin.record_mark` und `admin.record_mark_event` an. Vorhandene
Findings und Reviews bleiben erhalten. Wie bei den bisherigen Migrationen wird das Upgrade
explizit mit `ADMIN_MIGRATION_DATABASE_URL` über `uv run alembic upgrade head` ausgeführt.
Anschließend die [expliziten Runtime-Grants](#minimale-rechte-nach-migration-0003) anwenden.
`record_mark_event` ist append-only; bestehende pauschale Grants müssen eingeschränkt werden.
Die API schreibt Markierung und Verlauf atomar und prüft die übermittelte Version gegen
konkurrierende Änderungen. Kein Upgrade erfolgt automatisch beim Anwendungsstart.

Im Frontend führt „Markierungen & Notizen“ an Activity-Datensätzen, Arbeitslisten und
Prüfhinweisen zur jeweiligen Übersicht. Über „Neue Markierung“ werden Gründe,
Dringlichkeit und eine optionale Notiz erfasst. Die Navigation „Markierungen“ sammelt
standardmäßig alle offenen Anliegen. Erledigte Anliegen bleiben über den Statusfilter
zugänglich. Im Detail können Notizen ergänzt, Anliegen erledigt und wieder geöffnet werden.


## Minimale Rechte nach Migration 0003

### PostgreSQL-Rollenmodell

| Rolle | Verwendet von | Aufgaben und Grenze |
| --- | --- | --- |
| `uranus_reader` | `DATABASE_URL` | SELECT auf explizite Uranus-Quelltabellen; keine Domain-Writes, kein Domain-Ownership/DDL |
| `admin_user` | `ADMIN_DATABASE_URL` | Admin-Workflow lesen, anlegen und aktualisieren; keine DDL-, Owner- oder Uranus-Schreibrechte |
| `admin_migrator` | `ADMIN_MIGRATION_DATABASE_URL` | Alembic und Ownership/DDL im Schema `admin`; kein Domain Writer; nie Runtime-Account |

Dies sind Beispiel-Rollennamen, keine fest im Anwendungscode verlangten Namen. Alle drei
Rollen sind unterschiedliche Logins ohne Superuser, CREATEROLE oder CREATEDB. Sie dürfen weder
die Datenbank noch Uranus-Objekte besitzen oder privilegierte Rollen erben. `admin_user` erhält
keine Mitgliedschaft in `admin_migrator`, auch nicht indirekt oder mit späterer SET-ROLE-Option.

Alembic meldet sich unmittelbar als `admin_migrator` an. `migrations/env.py` verwendet keine
andere Rolle und liest seine DSN ausschließlich aus dem Prozess-Environment. Die Migrationen
0001–0004 erzeugen neun Tabellen in `admin`; deren Owner bleibt `admin_migrator`. Ownership des
Schemas allein ändert den Owner bereits vorhandener Tabellen nicht. `admin_user` wird niemals
Owner, sondern erhält nur explizite DML-Grants. Rollen-/Grant-Anpassungen benötigen selbst
keine zusätzliche Migration. Die neuen Auth-Tabellen werden durch Migration 0004 erzeugt.

`record_mark_event` enthält die unveränderlichen Versionen, Autoren, Notizen und Statuswechsel
von Markierungen. Der Anwendungscode fügt Ereignisse atomar hinzu; PostgreSQL gestattet dafür
nur SELECT/INSERT. UPDATE, DELETE, TRUNCATE, TRIGGER und UPDATE-Spaltengrants würden diese
append-only-Grenze verletzen. Versions-Eindeutigkeit sichert zusätzlich die Datenbank-Constraint.

### Effektive Runtime-Rechte

Das vom Betreiber am 2026-09-15 lokal bestätigte Setup bestand den Boundary-Check mit
`unsafe = false`. Die Workflow-Zeilen der folgenden Matrix reproduzieren dieses Profil; die vier Auth-Zeilen
ergänzen die Anforderungen ab Migration 0004:

| Tabelle | SELECT | INSERT | UPDATE | DELETE | TRUNCATE | TRIGGER |
| --- | --- | --- | --- | --- | --- | --- |
| `admin.alembic_version` | ja, optional für Diagnose | nein | nein | nein | nein | nein |
| `admin.check_run` | ja | ja | ja | nein | nein | nein |
| `admin.finding` | ja | ja | ja | nein | nein | nein |
| `admin.record_mark` | ja | ja | ja | nein | nein | nein |
| `admin.record_mark_event` | ja | ja | nein | nein | nein | nein |
| `admin.auth_account` (0004) | ja | nein | nein | nein | nein | nein |
| `admin.auth_system_admin` (0004) | ja | nein | nein | nein | nein | nein |
| `admin.auth_session` (0004) | ja | ja | ja | nein | nein | nein |
| `admin.auth_login_bucket` (0004) | ja | ja | ja | nein | nein | nein |

Die Runtime liest `alembic_version` im aktuellen Code nicht. SELECT ist somit **keine
Anwendungsvoraussetzung**, aber ein zulässiger Diagnose-Grant im lokal bestätigten Profil.
Die untenstehende Provisionierung enthält ihn. Alembic selbst braucht den Migrationsaccount.
Sequenzrechte sind nicht erforderlich: Die Anwendung erzeugt UUIDs selbst; Finding-IDs sind Text.
REFERENCES, MAINTAIN und GRANT OPTION werden für die Runtime ebenfalls nicht benötigt.

Erforderlich ist USAGE auf `admin`; CREATE auf `admin` und `uranus` ist verboten. Domain-SELECT
für `admin_user` ist zulässig, aber für seine Aufgaben nicht erforderlich: Source-Abfragen laufen
über `DATABASE_URL`. Das Beispiel vergibt deshalb Uranus-SELECT ausschließlich an `uranus_reader`.
Ein optionaler Domain-Lesezugriff für Runtime darf dieselbe explizite Tabellenliste verwenden.

### Provisionierung: neue Installation

Voraussetzung: In der ausgewählten Datenbank existiert das passende Uranus-Schema einschließlich
PostGIS bereits. Die folgenden zwei SQL-Blöcke sind in dieser Datenbank durch einen dafür
berechtigten DB-Betreiber auszuführen; dazwischen werden die vorhandenen Alembic-Migrationen
mit dem separaten Login ausgeführt. Keine Superuser-Rolle für Anwendung oder Migration verwenden.
Neue Rollen und `admin` dürfen noch nicht existieren; bei Bestandsinstallationen zuerst Rechte
und Ownership prüfen, nicht vorhandene Schemas löschen. Authentifizierung über `pg_hba.conf`,
CONNECT zur Zieldatenbank und Netzwerkerreichbarkeit müssen passend eingerichtet sein.

**1. Rollen, Schema und sichere Defaults vor den Migrationen:**

```sql
-- provisioning: before migrations
BEGIN;
CREATE ROLE uranus_reader LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS NOREPLICATION;
CREATE ROLE admin_migrator LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS NOREPLICATION;
CREATE ROLE admin_user LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS NOREPLICATION;
CREATE SCHEMA admin AUTHORIZATION admin_migrator;
REVOKE ALL PRIVILEGES ON SCHEMA admin FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA admin TO admin_migrator;
GRANT USAGE ON SCHEMA admin TO admin_user;
REVOKE CREATE ON SCHEMA admin FROM admin_user, uranus_reader;
REVOKE CREATE ON SCHEMA uranus FROM admin_user, uranus_reader, admin_migrator;
REVOKE admin_migrator FROM admin_user;

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA uranus
    FROM uranus_reader, admin_user, admin_migrator;
GRANT USAGE ON SCHEMA uranus TO uranus_reader;
GRANT SELECT ON uranus.organization, uranus.venue, uranus.space,
    uranus.event, uranus.event_date, uranus.event_link, uranus.license,
    uranus.pluto_image, uranus.pluto_image_link, uranus."user",
    uranus.organization_partner_request, uranus.organization_member_link,
    uranus.organization_access_grants TO uranus_reader;

-- Dedicated admin_migrator: no automatic grants to runtime or PUBLIC.
-- Reset both global and schema-specific defaults in this database.
ALTER DEFAULT PRIVILEGES FOR ROLE admin_migrator
    REVOKE ALL PRIVILEGES ON TABLES FROM admin_user, PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE admin_migrator IN SCHEMA admin
    REVOKE ALL PRIVILEGES ON TABLES FROM admin_user, PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE admin_migrator
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM admin_user, PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE admin_migrator IN SCHEMA admin
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM admin_user, PUBLIC;
COMMIT;
```

Dieser Block enthält absichtlich keine Passwörter. Vor der ersten Anmeldung Kennwörter über das
Secrets-Verfahren des Betreibers setzen, beispielsweise interaktiv mit `psql` und
`\password uranus_reader`, `\password admin_user`, `\password admin_migrator`.
Keine Kennwörter in SQL-Dateien oder Shell-History hinterlegen.

**2. Migrationen aus `backend/` als `admin_migrator`:**

```bash
# ADMIN_MIGRATION_DATABASE_URL sicher im Prozess-Environment bereitstellen.
# Nur ein Eintrag in backend/.env reicht für Alembic nicht.
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

Die Credentials nur dem Migrationsprozess geben, nicht dem Runtime-Service. Neue Tabellen
gehören dadurch `admin_migrator`; nie nachträglich an `admin_user` übertragen. Nach einem
Downgrade/Re-Upgrade oder weiteren Migrationen die tabellenspezifischen Grants erneut prüfen.

**3. Runtime-Grants nach den Migrationen:**

```sql
-- provisioning: after migrations
BEGIN;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA admin FROM admin_user, PUBLIC;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA admin FROM admin_user, PUBLIC;
GRANT USAGE ON SCHEMA admin TO admin_user;
REVOKE CREATE ON SCHEMA admin, uranus FROM admin_user;
REVOKE admin_migrator FROM admin_user;

-- Optional: reproduces the verified read-only diagnostic access.
GRANT SELECT ON admin.alembic_version TO admin_user;
GRANT SELECT, INSERT, UPDATE ON admin.check_run, admin.finding, admin.record_mark, admin.url_check TO admin_user;
GRANT SELECT, INSERT ON admin.record_mark_event TO admin_user;
-- Migration 0004: runtime cannot create accounts or grant itself global access.
GRANT SELECT ON admin.auth_account, admin.auth_system_admin TO admin_user;
GRANT SELECT, INSERT, UPDATE ON admin.auth_session, admin.auth_login_bucket TO admin_user;
REVOKE UPDATE, DELETE, TRUNCATE, TRIGGER ON admin.record_mark_event FROM admin_user;
COMMIT;
```

**Bestandsrollen:** Direkte REVOKEs beseitigen weder PUBLIC-/geerbte Rechte noch separate
Spaltengrants. PostgreSQL hat kein pro Rolle wirkendes DENY, das diese Quellen überschreibt.
Vor breiten Revokes die Auswirkungen auf andere Anwendungen prüfen. Spaltengrants gezielt
entfernen, z. B. `REVOKE UPDATE (note) ON admin.record_mark_event FROM admin_user;`;
alle betroffenen Spalten/Rollen über die Diagnose unten ermitteln. Keine Owner-Rechte durch
DML-REVOKEs zu reparieren versuchen: Ein Owner kann Rechte wieder vergeben. Er muss Migrator
bleiben; die Runtime darf dessen Rolle nicht erben oder per SET ROLE annehmen.

### Default Privileges: bewusst keine Runtime-Baseline

Neue Tabellen erhalten keine automatischen Runtime-Rechte. Jede neue Tabelle wird nach ihrer
Migration ausdrücklich freigegeben; so erhält eine neue History-Tabelle nicht versehentlich
UPDATE/DELETE. Der zusätzliche Deployment-Schritt ist beabsichtigt.

Defaults betreffen nur zukünftig erzeugte Objekte und die **tatsächlich erzeugende Rolle**.
Globale und Schema-Defaults wirken additiv; ein schema-lokales REVOKE entfernt keinen globalen
Grant. Deshalb zeigt das Beispiel beide Ebenen für den dedizierten Migrator. Defaults anderer
Erzeugerrollen und bereits bestehende Grants müssen separat geprüft werden. Details:
[PostgreSQL: ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html).

### Diagnose und Verifikation

Mit einem Diagnoseaccount in derselben Datenbank prüfen (Rollennamen bei Bedarf anpassen):

```sql
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin
FROM pg_roles WHERE rolname IN ('uranus_reader', 'admin_user', 'admin_migrator');
-- Expected for admin_user: false, false, false, true.
SELECT has_schema_privilege('admin_user', 'admin', 'USAGE') AS admin_usage,
       has_schema_privilege('admin_user', 'admin', 'CREATE') AS admin_create,
       has_schema_privilege('admin_user', 'uranus', 'CREATE') AS uranus_create;
-- Expected: true, false, false.
SELECT pg_has_role('admin_user', 'admin_migrator', 'MEMBER') AS migrator_member,
       pg_has_role('admin_user', 'admin_migrator', 'USAGE') AS migrator_inherited,
       pg_has_role('admin_user', 'admin_migrator', 'SET') AS migrator_set;
-- Expected: false, false, false.

SELECT c.relname, pg_get_userbyid(c.relowner) AS owner,
       has_table_privilege('admin_user', c.oid, 'SELECT') AS can_select,
       has_table_privilege('admin_user', c.oid, 'INSERT') AS can_insert,
       has_table_privilege('admin_user', c.oid, 'UPDATE') AS can_update,
       has_table_privilege('admin_user', c.oid, 'DELETE') AS can_delete,
       has_table_privilege('admin_user', c.oid, 'TRUNCATE') AS can_truncate,
       has_table_privilege('admin_user', c.oid, 'TRIGGER') AS can_trigger,
       has_any_column_privilege('admin_user', c.oid, 'UPDATE') AS any_column_update,
       pg_has_role('admin_user', c.relowner, 'USAGE') AS owner_privileges
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='admin' AND c.relkind IN ('r','p') ORDER BY c.relname;
-- All nine owners after 0004: admin_migrator. owner_privileges: false.
-- Other columns must match the runtime matrix above.

SELECT c.relname,
       has_table_privilege('admin_user', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
       OR has_any_column_privilege('admin_user', c.oid, 'INSERT,UPDATE') AS domain_write
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='uranus' AND c.relkind IN ('r','p','v','f');
-- domain_write must be false for every row.

SELECT defaclrole::regrole AS creator, defaclnamespace::regnamespace AS schema,
       defaclobjtype, defaclacl
FROM pg_default_acl WHERE defaclrole='admin_migrator'::regrole;
SELECT grantee, table_name, column_name, privilege_type
FROM information_schema.column_privileges
WHERE table_schema='admin' AND table_name='record_mark_event';
```

Bei `column_privileges` sind insbesondere Grants für UPDATE relevant; die Sicht zeigt nur die
für den Diagnoseaccount sichtbaren Grants. Effektive Rechte mit den obigen `has_*`-Abfragen
prüfen; in `psql` helfen außerdem `\dp admin.*`, `\ddp` und `\du`.
`pg_has_role(..., 'USAGE')` prüft ohne SET ROLE verfügbare Owner-Rechte, nicht jede mögliche
Mitgliedschaft. Darum zusätzlich MEMBER/SET prüfen; NOINHERIT allein ersetzt keine saubere
Rollentrennung. [PostgreSQL: Rechteprüffunktionen](https://www.postgresql.org/docs/17/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE),
[PostgreSQL: Rollenmitgliedschaft](https://www.postgresql.org/docs/17/role-membership.html).

Den **unveränderten Anwendungscheck** direkt mit der tatsächlich konfigurierten Runtime-DSN
aufrufen, aus `backend/` (nur lesende Systemkatalogabfragen, kein DDL oder DML):

```bash
uv run python - <<'PY'
import asyncio
from app.admin_database import create_admin_engine, assert_admin_boundary
from app.config import Settings
from app.errors import APIError

async def main():
    engine = create_admin_engine(Settings())
    if engine is None:
        raise SystemExit('ADMIN_DATABASE_URL fehlt')
    try:
        async with engine.connect() as connection, connection.begin():
            try:
                await assert_admin_boundary(connection)
            except APIError as error:
                print(f'unsafe = true ({error.code})')
                raise SystemExit(1) from None
            print('unsafe = false')
    finally:
        await engine.dispose()

asyncio.run(main())
PY
```

Erwartet: `unsafe = false`. Der Check prüft Superuser/CREATEROLE, Schema-CREATE,
Uranus-Schreibrechte einschließlich Spaltengrants sowie schädliche Rechte/Owner-Vererbung für
`record_mark_event`, `auth_account` und `auth_system_admin`. Die Runtime darf insbesondere
keine Identitäten ändern oder globale Rechte vergeben. Er ist **keine vollständige Installationsprüfung**: Er prüft nicht, ob
alle erforderlichen positiven Grants oder Tabellen existieren, und testet CREATEDB/LOGIN nicht
separat. Deshalb Rollenattribute, Owner und Rechte-Matrix zusätzlich prüfen. `/ready` prüft zusätzlich diese Admin-Grenze, den aktuellen Migrationstand und alle
erforderlichen positiven Runtime-Grants.

### Fehlerbild: 503 admin_storage_unconfigured

`Admin storage requires a restricted role.` bedeutet, dass `assert_admin_boundary()` die
Runtime-Rolle als **zu mächtig** abgelehnt hat. Mögliche Ursachen: Superuser, CREATEROLE,
CREATE auf `admin`/`uranus`, Domain-Writes, UPDATE/DELETE/TRUNCATE/TRIGGER auf der History
oder geerbte Owner-Rechte durch Mitgliedschaft in `admin_migrator`.

Derselbe Code mit `Admin history storage is not configured.` bedeutet dagegen, dass
`ADMIN_DATABASE_URL` fehlt. Fehlende Tabellen, fehlende positive Grants, falsche Credentials
oder eine nicht erreichbare Datenbank erscheinen normalerweise als `503 database_unavailable`.
Deshalb zuerst den JSON-Response-Body (`error.code` und `error.message`) lesen; ein Access-Log
mit bloßem Status 503 unterscheidet diese Ursachen nicht. Dann die tatsächlich verwendete
DSN/Rolle, Migrationen und obige Katalogabfragen prüfen. Nach Konfigurationsänderungen den
Runtime-Prozess neu starten. Keine Grenze durch Superuser-Zugang oder pauschale GRANT ALL
umgehen.

### Automatisierte Prüfung der Anleitung

`tests/test_admin_roles.py` führt die beiden markierten Provisionierungsblöcke dieser Anleitung
gegen eine isolierte Testdatenbank aus, migriert als `admin_migrator` und prüft echte Reader-/
Runtime-Logins, Ownership sowie die gesamte Rechte-Matrix. Eine zusätzliche Tabelle mit Sequenz
prüft, dass zukünftige Objekte keine pauschalen Runtime-Grants erben. Weitere Fälle prüfen die
Ablehnung von Schema-CREATE, Domain-UPDATE, History-Mutationen und Owner-Mitgliedschaft.
Die bestehenden Tests in `test_database.py` und `test_marks.py` ergänzen Spaltengrants,
verbotene Schreiboperationen, Migrationen und den unveränderlichen Markierungsverlauf.

Nur einen separaten PostgreSQL-Testcluster verwenden: Rollen sind clusterweit, auch wenn
`TEST_DATABASE_URL` auf eine Datenbank mit Suffix `_test` zeigt. Die Provisionierungsprüfung
verweigert vorhandene Beispielrollen oder ein vorhandenes Admin-Schema und entfernt ihre
Testrollen, Schemas und Grants auch bei Testfehlern.

### Downgrade-Verluste

- `0004 → 0003`: löscht eigene Admin-Konten, Passworthashes, globale Vergaben, sämtliche Sitzungen
  und Login-Limits. Production-Anmeldung funktioniert danach nicht mehr; Workflow-Daten und
  bestehende textuelle Audit-Autoren bleiben erhalten. Runtime vor dem Downgrade stoppen.
- `0003 → 0002`: löscht alle Markierungen einschließlich Gründen, Notizen, Versionen,
  Abschlussdaten und des vollständigen Ereignisverlaufs. Findings/Reviews bleiben erhalten.
- `0002 → 0001`: löscht Run-Coverage (`rule_results`), Zuweisung (`assigned_to`),
  Reviewer-Subject (`reviewed_subject`), Snooze-Ende und Exception-Grund. Die Zustände
  `in_progress`, `snoozed`, `exception` werden zu `open`; bestehende Kommentare,
  `reviewed_by`, `reviewed_at` und übrige Finding-Daten bleiben erhalten.
- `0001 → base`: löscht zusätzlich alle Findings und Check Runs.

Vor einem produktiven Downgrade Admin-Daten sichern und Runtime stoppen. Downgrades können
verlorene Historie nicht rekonstruieren. Keine dieser Migrationen verändert Uranus.


## Eigenständige Admin-Authentifizierung (Migration 0004)

Der vollständige [Auth-Vertrag](authentication.md) trennt eigene Identitäten und die explizite
Berechtigungstabelle. Keine Uranus-Passwörter, Rollen oder Status-Lookups. Migration `0004`
führt nur Admin-Tabellen ein; `ADMIN_DATABASE_URL` bleibt ohne DDL- und Uranus-Schreibrechte.
Die beiden markierten Provisionierungsblöcke oben enthalten bereits die Runtime-Grants für
`0004`. Nach `uv run alembic upgrade head` diese tabellenspezifischen Grants anwenden.

### Betreiberzugang und Kontoanlage

Die Runtime darf `auth_account`/`auth_system_admin` ausschließlich lesen. Für das CLI einen
separaten DML-Operator bereitstellen; der Migrator bleibt ausschließlich für Alembic zuständig.
Beispiel, nach Migration 0004 durch einen dazu berechtigten DB-Betreiber ausführen:

```sql
CREATE ROLE admin_auth_operator LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS NOREPLICATION;
GRANT USAGE ON SCHEMA admin TO admin_auth_operator;
REVOKE CREATE ON SCHEMA admin, uranus FROM admin_auth_operator;
GRANT SELECT, INSERT, UPDATE ON admin.auth_account TO admin_auth_operator;
GRANT SELECT, INSERT, DELETE ON admin.auth_system_admin TO admin_auth_operator;
GRANT SELECT, UPDATE ON admin.auth_session TO admin_auth_operator;
GRANT SELECT ON admin.alembic_version TO admin_auth_operator;
-- No membership in admin_migrator, no Uranus or record_mark_event write grants.
```

Passwort des DB-Operators über das Secrets-Verfahren setzen (z. B. interaktiv
`\password admin_auth_operator`). `ADMIN_AUTH_MANAGEMENT_DATABASE_URL` ausschließlich dem
CLI-Prozess geben; nie dem FastAPI-/Nuxt-Dienst. Keine tatsächlichen Passwörter in Shell-Argumenten.
Konto-Passwörter werden zweimal verdeckt über `getpass` abgefragt, mit 15–1024 Zeichen:

```bash
# Nach Migration und Operator-Grants zuerst Preflight:
uv run python -m app.auth.manage doctor
# Erster System-Administrator: beide Entscheidungen müssen ausdrücklich gesetzt sein.
uv run python -m app.auth.manage create operator --active --system-admin
# Ein normales Konto hat zunächst weder Aktivierung noch globale Rechte:
uv run python -m app.auth.manage create reviewer
uv run python -m app.auth.manage activate reviewer
uv run python -m app.auth.manage grant reviewer
uv run python -m app.auth.manage revoke reviewer
uv run python -m app.auth.manage disable reviewer
uv run python -m app.auth.manage password operator
```

UUIDs sind unabhängige Admin-Identitäten. Rechte-/Passwort-/Statusänderungen im CLI erhöhen die
Credential-Version und widerrufen bestehende Sitzungen in derselben Transaktion. Re-Login ist
anschließend erforderlich. Keine initialen Benutzer oder Default-Passwörter werden migriert.

### Production und lokale Konfiguration

```dotenv
APP_ENV=production
APP_DEBUG=false
DEV_AUTH_ENABLED=false
OPENAPI_ENABLED=false
AUTH_PUBLIC_ORIGIN=https://admin.example.invalid
AUTH_SESSION_SECONDS=3600
AUTH_IDLE_SECONDS=900
```

`ADMIN_DATABASE_URL` sicher als Runtime-Secret bereitstellen; `DATABASE_URL` bleibt der getrennte
Domain-Reader für Reporting. Frontend `NUXT_ADMIN_API_BASE` zeigt serverseitig auf FastAPI.
Authentifizierung benötigt weder `URANUS_API_URL` noch einen erreichbaren Uranus-Reader.
Keine Migration oder Kontovergabe erfolgt beim Dienststart. Nach Origin-Änderungen neu starten.

Lokal: `APP_ENV=development`, `AUTH_PUBLIC_ORIGIN=http://127.0.0.1:3000` (oder exakt die verwendete
localhost-Origin), `pnpm dev`. Eigene Konten funktionieren auch ohne Dev-Override.
`DEV_AUTH_ENABLED=true` plus `DEV_ADMIN_TOKEN` ist weiterhin nur eine separate Testhilfe.
Production-/Staging-Flags können weder Dev-Auth noch unverschlüsselte Cookie-Origin aktivieren.

### Bereinigung

Nach Migration 0005 stehen zusätzliche Ablauf-/Widerruf-Indizes bereit (Downgrade entfernt nur
Indizes, keine Daten). Maintenance läuft explizit mit dem CLI-Operator, nie im Request-Pfad.
Zusätzliche Rechte nur für diesen Prozess, **nicht** für admin_user:

```sql
GRANT SELECT ON admin.alembic_version TO admin_auth_operator;
GRANT DELETE ON admin.auth_session TO admin_auth_operator;
GRANT SELECT, UPDATE, DELETE ON admin.auth_login_bucket TO admin_auth_operator;
```

UPDATE wird für `FOR UPDATE SKIP LOCKED` benötigt; Cleanup aktualisiert keine Sitzungen.

```bash
uv run python -m app.auth.maintenance cleanup --batch-size 500 --max-batches 10
```

Regelmäßig, beispielsweise stündlich, extern planen. Pro Transaktion maximal batch-size
Sitzungen und Buckets, maximal max-batches Transaktionen. Mehrere Wartungsprozesse überspringen
bereits gesperrte Zeilen. Wiederholung ist sicher. Entfernt werden absolut oder per Idle-Timeout
abgelaufene Sitzungen, ausreichend alte Widerrufe und abgelaufene Buckets. Noch gültige aktive
Sitzungen bleiben erhalten. `AUTH_REVOKED_RETENTION_SECONDS=86400` hält reine Widerrufe bis zu
einem Tag; absolute/Idle-Abläufe dürfen früher gelöscht werden. Ausgabe enthält nur Mengen.
Bei großem Rückstand öfter aufrufen, keine unbeschränkten Deletes in normalen Requests.
`record_mark_event` bleibt vollständig unberührt und append-only.

`AUTH_SESSION_HEARTBEAT_SECONDS=60` schreibt Aktivität höchstens einmal pro Minute.
Der Wert muss positiv, höchstens 300 und kleiner als AUTH_IDLE_SECONDS sein. Ein SQL-Prädikat
verhindert doppelte Heartbeats paralleler Requests. Der Idle-Nachweis ist konservativ: letzte
Aktivität wird mit höchstens einem Intervall Verzögerung gespeichert; eine Sitzung kann entsprechend
früher erneut Login verlangen. Die absolute Lebensdauer wird niemals verlängert.

## Activity previews

For a source database belonging to the public Kulturbytes instance, set
`URANUS_API_URL=https://api.kulturbytes.de` to enable verified public image/page URLs in the
Activity response. Keep the local URL for unrelated test datasets. This does not change auth,
DB grants or introduce outbound API calls. See [the preview contract](contracts.md#activity-previews-and-public-links)
for source evidence and unsupported entity routes.

This also applies when the dashboard runs at `http://localhost:3000`: for the Kulturbytes
source database, set `URANUS_API_URL=https://api.kulturbytes.de` in `backend/.env`, then
restart the backend (settings are loaded at application startup). The browser origin does
not determine the image host. With the default `http://localhost:8080`, `image_url` and
`public_url` are deliberately null, so the UI shows placeholders. Keep
`NUXT_ADMIN_API_BASE=http://127.0.0.1:8000`; only the public images load from Kulturbytes.

### Image CSP and deployment verification

The CSP on the HTML response must allow the public image origin. Retain existing required
image sources and add only `https://api.kulturbytes.de`, for example:

```text
img-src 'self' data: blob: https://api.kulturbytes.de;
```

A read-only check of `https://admin.kulturbytes.de/activity` on 2026-09-16 returned
`img-src 'self' data: blob:`. That policy **blocks these thumbnails**: an operator must deploy
the targeted `img-src` addition in the configuration that owns this response header.
Adding another permissive CSP header in Nuxt cannot relax an existing stricter policy;
all policies apply. No live nginx/systemd changes were made for this implementation.
Leave `script-src` unchanged for this feature; image loading needs no `unsafe-eval`.
Public image responses must allow anonymous CORS; the public image endpoint was verified
with `Access-Control-Allow-Origin: *`. Images send no cross-origin cookies or referrer.

Deploy the frontend contract update before the backend thumbnail change: the updated client
accepts the former cropped URLs and the new 320px URLs without a ratio; older clients
only accept their previous cropped formats. There are no new required response fields.

After deployment, verify the response CSP in browser DevTools, check that the Activity
response contains a 320px `image_url` without a `ratio` parameter, and check that the image loads without CSP or
CORS errors. If URLs are null, first verify the server-side `URANUS_API_URL` assertion above;
do not switch unrelated datasets to the public instance just to show a picture.
Missing files or network errors retain the type icon and all row metadata/actions.
No database migration or additional grant is required. The production Playwright test in
`frontend/tests/e2e/activity-drilldown.spec.ts` enforces the targeted policy and intercepts
images locally, so CI does not depend on the external image service.

## Production Readiness

`GET /health` ist reine Prozess-Liveness und bleibt bei Datenbankausfall 200.
`GET /ready` prüft die Source-Verbindung sowie Admin-Verbindung, Restricted-Role-Boundary,
alle neun Admin-Tabellen, effektive USAGE-/DML-Rechte und den exakten Alembic-Head aus den
mitgelieferten Migrationen. Tabellenrechte werden einzeln geprüft, inklusive Auth-Account/
Berechtigungs-SELECT und Session-/Bucket-SELECT/INSERT/UPDATE. Der tatsächlich verbundene
DB-User zählt, nicht ein fest verdrahteter Rollenname. Keine DML, DDL oder Auto-Migration.
Fehler liefern 503 ohne Roh-DB-Details. `/ready` gehört in Deployment-/Monitoring-Probes,
`/health` in Prozess-Liveness-Probes. Nach Migrationen explizite Grants anwenden, dann Readiness prüfen.
Nur Development/Test mit aktiviertem Dev-Auth und ohne ADMIN_DATABASE_URL darf bewusst
Source-only laufen. Staging/Production benötigt immer die vollständige Admin-Ablage.
Eine Readiness-Prüfung authentifiziert kein Benutzerkonto und erteilt keine Admin-Rechte.

## Durable quality-check worker (Migration 0006)

Deploy-Reihenfolge: alte API-/Worker-Prozesse kontrolliert stoppen, Alembic mit Migrator auf
Head bringen, Runtime-Grants prüfen, neue API und Worker starten. Keine Auto-Migration.
0006 ergänzt queued, Worker-ID, Lease und einen Unique-Index für maximal einen aktiven Job.
Beim Upgrade werden alte running-Zeilen failed; beim Downgrade werden queued/running-Zeilen
failed und Lease-Metadaten entfernt. Erfolgreiche Historie/Findings bleiben erhalten. Uranus wird
nicht verändert. 0005 ergänzt ausschließlich Retention-Indizes, Downgrade ohne Datenverlust.

```bash
cd backend
uv run python -m app.check_worker
# Einzelner Poll für kontrollierte Operator-/Integrationstests:
uv run python -m app.check_worker --once
```

Der Worker benötigt dieselben getrennten DATABASE_URL (read-only) und ADMIN_DATABASE_URL
(restricted DML) wie die API, **keinen** Migrator-/Auth-Operator-Zugang. CHECK_JOB_LEASE_SECONDS
ist standardmäßig 120 (30–3600), Erneuerung alle lease/3 Sekunden; Poll-Intervall
CHECK_WORKER_POLL_SECONDS standardmäßig 2. Erneuerung läuft als überwachte, vollständig
abgewartete Worker-Aufgabe. Keine Fire-and-forget-Aufgabe im HTTP-Prozess.
Während der abschließenden atomaren Speicherung schützt der Job-Zeilenlock die Eigentümerschaft.
Der Heartbeat überspringt dann die gesperrte eigene Zeile, statt auf seine eigene Speicherung
zu warten und durch einen DB-Timeout den Run abzubrechen. Eine abgelaufene, ungesperrte Lease
kann nicht erneuert werden.

Mehrere Worker dürfen laufen, aber nur einer besitzt den aktiven Job. Während Scan/Heartbeat
werden keine langfristigen DB-Locks gehalten. Bei Crash läuft die Lease ab; ein weiterer Poll
markiert den Job failed. Ein pausierter alter Prozess könnte noch rechnen, ist jedoch durch
Lease/Worker-ID von jeder Ergebnisspeicherung ausgeschlossen. Wiederholung bewusst neu starten.
Bei Netzwerkfehlern endet die aktuelle Arbeit sicher; fehlen DB-Verbindungen für eine sofortige
Fehlermarkierung, stellt der nächste Worker den Fehler nach Lease-Ablauf fest. Kein Phantom-Erfolg.

Betriebsbeispiel (nur Vorlage, keine Live-Änderung):

```ini
[Service]
WorkingDirectory=/srv/uranus-admin/backend
EnvironmentFile=/etc/uranus-admin/worker.env
ExecStart=/usr/local/bin/uv run python -m app.check_worker
Restart=on-failure
```

Environment-Datei nur für den Dienst lesbar, ohne Migration-/Operator-Credentials.
Worker-Prozess und Alter queued/running-Jobs separat überwachen: `/ready` prüft die DB-/Schema-
Voraussetzungen der API, beweist aber nicht, dass ein externer Worker gerade läuft.

## Auth operator diagnostics

Bootstrap: **Migration → explizite Operator-Grants → doctor → create**. Doctor und jeder
normale Account-Befehl prüfen vor einer Passwortabfrage Verbindung, Datenbank/Rolle, Admin-
Schema, den zentral ermittelten Alembic-Head, alle erforderlichen Operator-Tabellen und jedes
benötigte Recht einzeln. Owner-Mitgliedschaft (auch NOINHERIT), CREATE auf admin/uranus,
Superuser/CREATEROLE/CREATEDB/BYPASSRLS/REPLICATION und Uranus-Schreibrechte werden abgelehnt.
Doctor führt ausschließlich SELECTs aus, keine Reparatur, Migration oder Kontoänderung.

```bash
uv run python -m app.auth.manage doctor
```

Ausgabe: konfigurierte DSN ja/nein, Verbindungsstatus, DB-/Rollenname, Migration und Grants;
keine DSN, Passwörter, Hashes, Tokens oder Roh-Exceptions. Fehler unterscheiden insbesondere
`database authentication failed`, `database unreachable`, `admin schema missing`,
`migration incompatible`, `operator privileges incomplete`, `unsafe operator role`,
`account already exists` und `unknown account`. Abbruch mit nonzero Exit-Code.
Kein Debug-Flag mit unredigierten Driver-Stacktraces. Erfolgreiche Kontoänderungen bleiben
atomar einschließlich Credential-Version und Session-Widerruf. Der CLI-Operator darf nur im
Operator-Prozess konfiguriert sein, nie als ADMIN_DATABASE_URL.

### Read-only source verification and domain pages

`uv run python -m app.source_schema_verify --json` is an operator-invoked catalog
report using `DATABASE_URL`. See [source verification](source-verification.md) for
required live review and timezone confirmation. Do not treat fixture tests as live
verification. Domain list/detail APIs use the same read-only source connection and
existing explicit admin metadata grants; no new grant or migration is required.
Create operations remain blocked pending a delegated Uranus write-auth contract.

## Optional asynchronous URL reachability worker (migration 0007)

Deploy the migration as `admin_migrator`, then explicitly grant the runtime role:

```sql
GRANT SELECT, INSERT, UPDATE ON admin.url_check TO admin_user;
```

No DELETE/TRUNCATE/TRIGGER/ownership/DDL or Uranus write privilege is required.
Readiness verifies the new table, migration head and positive runtime grants.
The documented full provisioning block above includes this table. Default privileges
remain restrictive. Stop workers before downgrading: `0007 → 0006` removes URL
observations, TTLs and leases, while retained URL findings stay in `admin.finding`.

Start only when public outbound checks are desired:

```bash
cd backend
uv run python -m app.url_check_worker --once
# Or run continuously under the deployment's process supervisor:
uv run python -m app.url_check_worker
```

This separate worker reuses restricted source/admin connections and existing finding
persistence; neither normal GETs, `url_syntax`, nor the core quality-check worker
perform HTTP requests. Source URLs are discovered in 200-row keyset pages. At most
`URL_CHECK_BATCH_SIZE` due URLs are processed per cycle (default 100), with at most
`URL_CHECK_CONCURRENCY` simultaneous chains (default 8), one chain per source host
per worker and a one-second spacing. Multiple workers coordinate individual URL
claims through PostgreSQL. Per-host pacing is local to each worker, so use one worker
unless the aggregate outbound budget is intentionally increased.

`admin.url_check` uses unique source type/key/field identity, explicit URL, timestamps
of last attempt/success, HTTP code, final redirected target, failure type/count,
next-due time, owner UUID and a 120-second lease. Claims and results are fenced;
a crashed worker's claim can be reclaimed after expiry. A changed source URL resets
observations and invalidates old claims. No deleted source is scheduled again.
Network work never holds the finding/review lock. Only the final short transaction
shares the review lock and preserves human review fields. Old observations are
retained as history; no request-path cleanup or implicit destructive retention runs.

Success TTL defaults to 24 hours, other observations to one hour. Two consecutive
failed scheduled observations produce a `url_unreachable` warning. 401/403 mean
blocked; 429 means rate-limited; neither creates a broken-link warning nor resolves
an existing one. Only a bounded successful 2xx response resolves the exact URL field's
finding. Other fields on the entity remain untouched. Evidence includes a URL hash,
not the URL itself, and no response body is stored.

### SSRF boundary

Only HTTP(S), public addresses and ports 80/443 are accepted. Credential-bearing URLs
and known sensitive query keys are excluded. Every DNS answer must be public; private,
loopback, link-local, metadata, multicast, reserved and IPv6 transition addresses are
rejected. The [HTTPCore network backend](https://www.encode.io/httpcore/network-backends/)
connects to the validated numeric IP while retaining the original Host/TLS identity.
There is no second hostname resolution for the connection, no environment proxy,
no cookies/authorization and no automatic redirect following. Each redirect is parsed
again and each fresh connection resolves/validates again; maximum five redirects.
TLS certificate/hostname verification stays enabled.

A streamed, identity-encoded range GET handles sites that reject HEAD. The total
budget is 20 seconds including DNS/redirects, with four-second connect and six-second
read limits; at most 256 KiB of body is accepted (one transport chunk may cross the
threshold before cancellation). Bodies are discarded, never decoded or persisted.
Oversized responses are inconclusive, not broken-link findings. This is an observation
from this worker, not proof of browser availability. Network egress restrictions remain
useful defense in depth; redirects/WAFs/robots policies can cause inconclusive results.
No production credentials or live configuration changes are part of deployment here.
