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

Beispiel für vom DB-Betreiber anzulegende Rollen; Passwörter über dessen Secrets-Verfahren setzen:

```sql
CREATE ROLE kulturbytes_admin_reader LOGIN;
GRANT USAGE ON SCHEMA uranus TO kulturbytes_admin_reader;
GRANT SELECT ON uranus.organization, uranus.venue, uranus.space,
    uranus.event, uranus.event_date, uranus."user",
    uranus.organization_partner_request, uranus.organization_member_link,
    uranus.pluto_image TO kulturbytes_admin_reader;

CREATE ROLE kulturbytes_admin_migrator LOGIN;
CREATE SCHEMA admin AUTHORIZATION kulturbytes_admin_migrator;
```

Beide Rollen dürfen keine Uranus-Tabellen besitzen, keine privilegierten Rollen erben und keine
Domain-Schreibrechte haben. Migrationsrolle nicht als Superuser betreiben. Falls PUBLIC in der
Zielumgebung weitergehende Rechte besitzt, muss der Betreiber diese Rollen wirksam begrenzen.
Der Reader kann durch SQL-Rechte technisch auch andere Spalten der freigegebenen Tabellen
lesen; Anwendung und Antworten selektieren keine Passwort-/Tokenfelder. Bei Bedarf später
Spaltengrants oder ausschließlich lesbare Reporting-Views einführen.

Die Runtime setzt default_transaction_read_only, jede Query-Transaktion zusätzlich READ ONLY und
REPEATABLE READ. DB-Berechtigungen sind die maßgebliche Absicherung unabhängig vom Python-Code.
Timeouts und Poolgrenzen sind konfigurierbar; Session-Zeitzone UTC. Summary/Listen lesen einen
konsistenten Snapshot, selbst wenn Uranus gleichzeitig schreibt.

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

Der Reader braucht zusätzlich SELECT auf `uranus.event_link`, `uranus.license`,
`uranus.pluto_image_link` und `uranus.organization_access_grants`.

Optionalen Admin-Runtimeaccount durch den DB-Betreiber anlegen (nach Migration):

```sql
CREATE ROLE kulturbytes_admin_history LOGIN;
GRANT USAGE ON SCHEMA admin TO kulturbytes_admin_history;
GRANT SELECT, INSERT, UPDATE ON admin.finding, admin.check_run TO kulturbytes_admin_history;
```

Secrets separat setzen, keine Kennwörter in SQL-Dateien/Git hinterlegen. Dieser Account erhält
keine Uranus-Schreibrechte, keine Superuser-/CREATEROLE-Rechte und keine DDL-Rechte. Vor Verwendung
prüft die Anwendung die Grenze einschließlich Domain-Spaltenschreibrechten.
`ADMIN_DATABASE_URL=postgresql+asyncpg://...` in der Backend-Konfiguration aktiviert die Ablage.
Ohne diese Variable bleiben explizite `mode=live`-APIs verfügbar; Persistenz-/Reviewzugriff liefert 503
`admin_storage_unconfigured`. Reader, Writer und Migrator sind verschiedene Verantwortlichkeiten.

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
Anschließend benötigt der bereits vorhandene Runtimeaccount zusätzliche Rechte:

```sql
GRANT SELECT, INSERT, UPDATE ON admin.record_mark TO kulturbytes_admin_history;
GRANT SELECT, INSERT ON admin.record_mark_event TO kulturbytes_admin_history;
```

Der Ereignistabelle werden keine UPDATE-/DELETE-Rechte eingeräumt. Ein eventuell vorhandenes
`ALTER DEFAULT PRIVILEGES` mit weitergehenden Rechten muss entsprechend angepasst werden.
Die API schreibt Markierung und Verlauf atomar und prüft die übermittelte Version gegen
konkurrierende Änderungen. Kein Upgrade erfolgt automatisch beim Anwendungsstart.

Im Frontend führt „Markierungen & Notizen“ an Activity-Datensätzen, Arbeitslisten und
Prüfhinweisen zur jeweiligen Übersicht. Über „Neue Markierung“ werden Gründe,
Dringlichkeit und eine optionale Notiz erfasst. Die Navigation „Markierungen“ sammelt
standardmäßig alle offenen Anliegen. Erledigte Anliegen bleiben über den Statusfilter
zugänglich. Im Detail können Notizen ergänzt, Anliegen erledigt und wieder geöffnet werden.


## Minimale Rechte nach Migration 0003

| Zugang | Rolle und erlaubte Arbeit |
| --- | --- |
| `DATABASE_URL` | Domain Reader: SELECT/USAGE auf Uranus, keine Schreib- oder DDL-Rechte |
| `ADMIN_DATABASE_URL` | Admin Runtime: eigene Metadaten lesen/ändern; Historie ausschließlich lesen/anhängen |
| `ADMIN_MIGRATION_DATABASE_URL` | Migration User: Owner/DDL im Schema admin; kein Domain Writer |

Das vollständige Beispiel nach `alembic upgrade head` (Logins/Passwörter separat durch den
Betreiber setzen; keine Mitgliedschaft in privilegierten Owner-/Writer-Rollen):

```sql
CREATE ROLE kulturbytes_admin_history LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB;
GRANT USAGE ON SCHEMA admin TO kulturbytes_admin_history;
GRANT SELECT, INSERT, UPDATE
    ON admin.check_run, admin.finding, admin.record_mark TO kulturbytes_admin_history;
GRANT SELECT, INSERT ON admin.record_mark_event TO kulturbytes_admin_history;

-- Auch bei bereits existierenden Runtime-Rollen/alten breiten Grants durchführen:
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON admin.record_mark_event FROM kulturbytes_admin_history;
REVOKE CREATE ON SCHEMA admin, uranus FROM kulturbytes_admin_history;

-- Optionaler Domain-Lesezugriff für Runtime; Quellabfragen nutzen weiterhin DATABASE_URL.
GRANT USAGE ON SCHEMA uranus TO kulturbytes_admin_history;
GRANT SELECT ON uranus.organization, uranus.venue, uranus.space,
    uranus.event, uranus.event_date, uranus.event_link, uranus.license,
    uranus.pluto_image, uranus.pluto_image_link, uranus."user",
    uranus.organization_partner_request, uranus.organization_member_link,
    uranus.organization_access_grants TO kulturbytes_admin_history;
```

Die Rechte auf alle vier Admin-Tabellen werden explizit vergeben; `alembic_version` und Sequenzen
brauchen keine Runtime-Grants (IDs erzeugt die Anwendung). Bei Bestandsrollen außerdem breite
Grants, Spaltengrants, PUBLIC-Rechte, Rollenvererbung und Default Privileges des Migrators prüfen:
Ein REVOKE vom direkten Login hebt geerbte oder PUBLIC-Rechte nicht auf. Runtime darf weder
Schema noch Tabellen besitzen. Die Boundary-Prüfung weist Superuser/CREATEROLE, Domain-Schreib-
oder Schema-CREATE-Rechte sowie UPDATE/DELETE/TRUNCATE/TRIGGER, UPDATE-Spaltengrants oder
Owner-Rechte auf der Ereignistabelle zurück. Keine Trigger sind erforderlich. Eine falsch
konfigurierte Ablage liefert 503 statt unsicherer Runtime-Verwendung.

Die Test-Fixture provisioniert eine echte separate Login-Rolle mit einem statischen,
ausschließlich synthetischen Testpasswort. CREATE ROLE und Test-URL benutzen denselben Wert;
Passwörter werden nicht in SQL interpoliert. Admin-Schema, Domain-Lesegrants und Rolle werden
nach dem Test entfernt. Der vollständige Testlauf wird auch mit SCRAM-Passwortanmeldung geprüft.

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
