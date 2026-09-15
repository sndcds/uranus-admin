# Entwicklung und Betriebsvorbereitung

## Installation und Start

Alle Befehle dieser Anleitung werden im Ordner `backend/` ausgeführt
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
| URANUS_API_URL | http://localhost:8080; für spätere Integration reserviert |
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
`admin.record_mark_event` sind der komplette Umfang.
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
`/health` bleibt bei DB-Ausfall erreichbar; `/ready` prüft nur Verbindung, weder vollständiges
Schema noch globale Auth. Ein 503 `source_timezone_unconfigured` erfordert den belegten
Speichervertrag, ein 503 `admin_auth_unconfigured` die geplante Uranus-Auth-Integration.

Der Test `test_quality_query_explain` schreibt einen JSON-Plan ins pytest-Tempverzeichnis.
Lokaler erster Lauf mit PostgreSQL 17/PostGIS: 2 Ergebniszeilen, oberer Knoten Hash Join,
Planung ca. 1,5 ms, Ausführung ca. 7 ms. Minimalfixture, kalter/kleiner Datenbestand und lokale
Umgebung: daraus keine Produktionslaufzeit ableiten. Für größere anonymisierte Kopien
`EXPLAIN (ANALYZE, BUFFERS)` der parametrisierten Query ausführen. Indexkandidaten stehen in
[future-uranus-improvements.md](future-uranus-improvements.md).

## CI

GitHub Actions führt getrennte Jobs für Lint/Format, strict mypy und Tests aus. Python 3.13,
fixierte uv-Version und `uv sync --locked`; Testjob mit PostgreSQL/PostGIS-Service und Healthcheck.
Actions sind auf Commit-SHAs, das PostGIS-Image auf einen amd64-Manifest-Digest fixiert. Keine produktiven Secrets oder Datenbankzugänge.
Eine lokale Prüfung des Workflows ersetzt keinen tatsächlich auf GitHub gelaufenen Job.

## Erweiterung: Check Runs und Reviews

Der neue Vertrag steht unter [contracts.md](contracts.md); er ersetzt die früheren Aussagen
über noch nicht angebundene Persistenz. Migration `0002` ergänzt Regelabdeckung und Reviewfelder.
Keine Domain-Tabelle wird geändert. Vorhandene Daten bleiben beim Upgrade erhalten.

Die vollständigen Reader- und Runtime-Grants stehen in der
[zentralen Rollen-Anleitung](#minimale-rechte-nach-migration-0003).
`ADMIN_DATABASE_URL` aktiviert die Ablage. Ohne diese Variable bleiben explizite
`mode=live`-APIs verfügbar; persistierte Standardlisten und Reviews liefern 503
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
0001–0003 erzeugen fünf Tabellen in `admin`; deren Owner bleibt `admin_migrator`. Ownership des
Schemas allein ändert den Owner bereits vorhandener Tabellen nicht. `admin_user` wird niemals
Owner, sondern erhält nur explizite DML-Grants. Keine neue Migration ist dafür notwendig.

`record_mark_event` enthält die unveränderlichen Versionen, Autoren, Notizen und Statuswechsel
von Markierungen. Der Anwendungscode fügt Ereignisse atomar hinzu; PostgreSQL gestattet dafür
nur SELECT/INSERT. UPDATE, DELETE, TRUNCATE, TRIGGER und UPDATE-Spaltengrants würden diese
append-only-Grenze verletzen. Versions-Eindeutigkeit sichert zusätzlich die Datenbank-Constraint.

### Effektive Runtime-Rechte

Das vom Betreiber am 2026-09-15 lokal bestätigte Setup bestand den Boundary-Check mit
`unsafe = false`. Die folgende Matrix reproduziert dieses Profil:

| Tabelle | SELECT | INSERT | UPDATE | DELETE | TRUNCATE | TRIGGER |
| --- | --- | --- | --- | --- | --- | --- |
| `admin.alembic_version` | ja, optional für Diagnose | nein | nein | nein | nein | nein |
| `admin.check_run` | ja | ja | ja | nein | nein | nein |
| `admin.finding` | ja | ja | ja | nein | nein | nein |
| `admin.record_mark` | ja | ja | ja | nein | nein | nein |
| `admin.record_mark_event` | ja | ja | nein | nein | nein | nein |

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
GRANT SELECT, INSERT, UPDATE ON admin.check_run, admin.finding, admin.record_mark TO admin_user;
GRANT SELECT, INSERT ON admin.record_mark_event TO admin_user;
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
-- All five owners: admin_migrator. owner_privileges: false.
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
`record_mark_event`. Er ist **keine vollständige Installationsprüfung**: Er prüft nicht, ob
alle erforderlichen positiven Grants oder Tabellen existieren, und testet CREATEDB/LOGIN nicht
separat. Deshalb Rollenattribute, Owner und Rechte-Matrix zusätzlich prüfen. `/ready` prüft
nur die Source-Verbindung, nicht diese Admin-Grenze.

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

- `0003 → 0002`: löscht alle Markierungen einschließlich Gründen, Notizen, Versionen,
  Abschlussdaten und des vollständigen Ereignisverlaufs. Findings/Reviews bleiben erhalten.
- `0002 → 0001`: löscht Run-Coverage (`rule_results`), Zuweisung (`assigned_to`),
  Reviewer-Subject (`reviewed_subject`), Snooze-Ende und Exception-Grund. Die Zustände
  `in_progress`, `snoozed`, `exception` werden zu `open`; bestehende Kommentare,
  `reviewed_by`, `reviewed_at` und übrige Finding-Daten bleiben erhalten.
- `0001 → base`: löscht zusätzlich alle Findings und Check Runs.

Vor einem produktiven Downgrade Admin-Daten sichern und Runtime stoppen. Downgrades können
verlorene Historie nicht rekonstruieren. Keine dieser Migrationen verändert Uranus.
