# Vorsichtiges Deployment für admin.kulturbytes.de

Diese Rolle übernimmt die **bereits vorhandene** Installation auf `webserver`.
Sie ist kein Datenbank-Bootstrap und kein allgemeines Server-Provisioning.
Der bestehende Source/Admin-Preflight bleibt **READ ONLY**; es gibt keine
Admin-Migration und keinen Datenbank-Restore. Ein eigener, zusätzlich freigegebener
Schritt verwaltet ausschließlich die isolierte SQL-Console-Infrastruktur.
Er verändert keine Uranus-Domain-Daten, Uranus-Tabellendefinitionen oder bestehenden
App-Rollenattribute. Der versionierte TEMP-Vertrag erhält die TEMP-Rechte der vier
App-Rollen und der explizit geprüften weiteren Verbraucher durch gezielte Grants.
Der automatische Fehlerpfad stellt ausschließlich
Systemkonfiguration und Service-Zustände wieder her. Unpassende bestehende Grenzen bleiben ein Abbruchgrund.

Die Implementierung darf lokal geprüft werden. Ein produktiver Check Mode benötigt
eine gesonderte Freigabe; ein Echtlauf zusätzlich die ausdrückliche Bestätigung
`Ja, führe das Deployment jetzt aus.` nach Prüfung seines Dry Runs.
Diese Rolle erteilt diese Freigaben nicht selbst. `mach weiter` genügt nicht.

## Berücksichtigter Befund

Die Bestandsaufnahme vom 19. September 2026 ist eine Momentaufnahme, keine Garantie
für einen späteren Lauf. Grundlage des Anwendungsstands:
`0d2c70896d9bb8522ff79162981f0802596e5fb6` auf `main`.

| Befund                                                                                | Umsetzung / verbleibende Grenze                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ubuntu 24.04.4, systemd 255.4, Nginx 1.24                                             | Preflight verlangt Ubuntu 24.04/systemd 255; vollständiges `nginx -t`; keine Paket-/OS-Upgrades.                                                                                                                                                                |
| PostgreSQL 16.15, PostGIS 3.4.2; Client 17.0                                          | Bestehender lokaler Socket, Datenbank `oklab`; keine Extension-Änderung. Tests zusätzlich mit PostgreSQL 17.                                                                                                                                                    |
| `uranus` gehört `oklab`, `admin` gehört `admin_migrator`                              | Live-Quelle bleibt unverändert. Ownership/effektive Rechte werden geprüft. Linux-User `oklab` ist nicht die DB-Verbindungsrolle.                                                                                                                                |
| `admin.alembic_version = 0011`, 16 Admin-Tabellen                                     | Head/Grant-Matrix stammen aus dem ausgewählten Release. Abweichung stoppt, ohne automatische Migration.                                                                                                                                                         |
| Reader besitzt SELECT auf 72 Quellobjekten, keine Sequenzrechte                       | Mindestens die 19 benötigten Quellobjekte werden geprüft. Bestehende weitere Leserechte bleiben erhalten; kein pauschales SELECT auf Sequenzen.                                                                                                                 |
| Vier getrennte App-Rollen, keine Memberships, keine privilegierten Attribute          | Attribute, Memberships in beide Richtungen, Ownership, Tabellen-/Spaltenrechte und indirekte Schreibmöglichkeiten werden erneut geprüft.                                                                                                                        |
| App-Rollen haben CONNECT/TEMP, kein Datenbank-CREATE                                  | PUBLIC TEMP wird ausschließlich nach Prüfung des versionierten Vertrags der Erhaltungsrollen atomar auf explizite TEMP-Grants umgestellt; unbekannte Verbraucher blockieren.                                                                                             |
| Backend, Frontend, Check-Worker existieren und laufen                                 | Nur diese drei bekannten Services werden übernommen. Keine zusätzlichen Service-Namen.                                                                                                                                                                          |
| Notification-Timer ist aktiv, Notification-Service ist ein stündlicher Oneshot        | Standard: unverändert. Nur explizites Notification-Management mit zweiter Zustimmung stoppt/deaktiviert ihn; Recovery stellt dann seinen vorherigen Zustand wieder her.                                                                                         |
| Kein URL-/Geocode-Service gefunden                                                    | Keine Installation oder Aktivierung dieser Worker.                                                                                                                                                                                                              |
| Bisherige `.env`-Dateien sind 0664, Backend enthält auch privilegierte Variablennamen | Werte wurden beim Audit nicht veröffentlicht. Übernahme liest sie geschützt, erhält Passwörter und trennt neue Runtime/Operator; Legacy-Backend-Env nur bei Notification-Management bereinigen; keine Behauptung, dass alle gefundenen Variablen befüllt waren. |
| Check-Worker startet bisher über `uv run`, ohne EnvironmentFile                       | `uv run --no-cache --no-sync --offline --no-python-downloads --no-env-file` aus dem fertigen Release, explizites Runtime-EnvironmentFile; kein Dependency-Sync beim Service-Start.                                                                              |
| Frontend-Dev-Token-Flag true, vertrauenswürdiger Ingress nicht konfiguriert           | Flag explizit false; Nitro vertraut ausschließlich dem lokalen Nginx-Peer `127.0.0.1`. Das alte Flag allein bewies keinen Production-Auth-Bypass.                                                                                                               |
| Nginx und Apache aktiv                                                                | Nur den bestehenden Admin-Vhost und einen eigenen Logformat-Snippet verwalten. Apache, andere Sites, TLS-Zertifikate und Rate-Zonen bleiben bestehen.                                                                                                           |
| Nginx-Limits ohne expliziten 429-Status, Headerverlust im Fehler-Location             | Request-/Connection-Limits liefern 429; vollständige Security-Header auch dort.                                                                                                                                                                                 |
| Globales Access-Log enthält rohe Requests/Querystrings                                | Minimiertes Admin-Access-Log und dediziertes Error-Log mit Level warn; Zugriffsrechte und Rotation vor Einsatz prüfen.                                                                                                                                          |
| CSP ohne Nonce-System, bereits ohne unsafe-eval                                       | Bestehende CSP erhalten, nicht vorzeitig entfernen.                                                                                                                                                                                                             |
| Kein bestätigtes Wartungsfenster, kein bestätigtes DB-Backup                          | Echtlauf bleibt gesperrt, bis beides angegeben und tatsächlich geprüft wurde. Ein vorhandener dpkg-Backup-Timer ist kein PostgreSQL-Backup.                                                                                                                     |

Ein identischer Head ist **kein vollständiger struktureller Schema-Diff**. Der
Preflight prüft Objektbestand, Rechte und gefährliche Abhängigkeiten; die spätere
Release-Prüfung zusätzlich den Source-Spaltenvertrag. Die Rolle behauptet weder
eine geprüfte Backup-Wiederherstellung noch erfolgreiche SMTP-Zustellung.

## Datenbankgrenzen und Grants

**Keine der folgenden bestehenden App-Berechtigungen wird von Ansible gesetzt.** Die Tabelle beschreibt
die bereits erwarteten Grenzen. Bei fehlenden oder zusätzlichen kritischen Rechten
ist ein separat geprüfter SQL-Plan nötig; die Rolle repariert nichts automatisch.

Das `uranus-admin` Deployment verwaltet ausschließlich die isolierte SQL-Console-Infrastruktur
(Rollen, `uranus_console`-Schema, explizite Views und minimale Grants).
Es verändert keine Uranus-Domain-Daten oder Uranus-Tabellendefinitionen.
Der [versionierte Console-Vertrag](../backend/docs/sql-console-infrastructure.md)
beschreibt den zusätzlichen Plan-/Provisionierungs-/Verifikationsschritt und seine Blocker.
Die bestehende `uranus_reader`-Rolle wird nicht für freie SQL-Abfragen wiederverwendet.

| Rolle                 | Erwartete Verwendung in `oklab`                                                                                                                                                                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `uranus_reader`       | CONNECT; USAGE `uranus`; SELECT auf benötigten Quelltabellen. Keine Ownership, Membership, DML/DDL, Sequenz-USAGE/UPDATE oder Grant Options. Kein Zugriff auf `admin`.                                                                                 |
| `admin_user`          | CONNECT; USAGE `admin`; folgende explizite Runtime-Matrix. Kein CREATE, Ownership, DELETE, TRUNCATE, REFERENCES, TRIGGER oder Grant Options. Kein Zugriff auf `uranus`.                                                                                |
| `admin_migrator`      | Owner von `admin` und dessen Tabellen. Kein Datenbank-CREATE, kein Quellzugriff, keine Membership. In dieser Rolle nicht benutzt.                                                                                                                      |
| `admin_auth_operator` | CONNECT; USAGE `admin`; SELECT Versionstabelle, SELECT/INSERT/UPDATE `auth_account`, SELECT/INSERT/DELETE `auth_system_admin`, SELECT/UPDATE `auth_session`. Nicht im Service-Environment. Zusätzliche Retention-Rechte brauchen eine eigene Freigabe. |

Alle vier Rollen müssen LOGIN ohne SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS
sein und dürfen weder andere Rollen erben noch selbst Mitgliedschaften vergeben haben.
`rolinherit` allein ist ohne Mitgliedschaften kein Rechtezuwachs. Die vorhandene Rolle
`oklab` wird weder verändert noch für die Anwendung als DB-Runtime benutzt.

Aktuelle Runtime-Matrix, autoritativ aus
[`RUNTIME_GRANTS`](../backend/app/storage_preflight.py):

| Tabellen in `admin`                                                                                                                                             | Rechte für `admin_user` |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| `alembic_version`, `auth_account`, `auth_system_admin`                                                                                                          | SELECT                  |
| `record_mark_event`, `notification_delivery_item`, `geocode_candidate`                                                                                          | SELECT, INSERT          |
| `check_run`, `finding`, `record_mark`, `auth_session`, `auth_login_bucket`, `url_check`, `notification`, `notification_delivery`, `geo_area`, `geocode_request` | SELECT, INSERT, UPDATE  |

Der SQL-Prüfer berücksichtigt auch PUBLIC-Rechte, Spaltengrants, SECURITY-DEFINER-
Funktionen, nichtinterne Admin-Trigger, Rules, aktive Event-Trigger, schemaübergreifende
FKs und Migrator-Default-ACLs. Unerwartete Konstruktionen werden zur Prüfung gemeldet,
auch wenn sie im Einzelfall harmlos sein könnten. Kein automatisches REVOKE.

### Vollständiger SQL-Ausführungsumfang

Die ausführbaren SQL-Texte stehen vollständig in
[`tasks/preflight.yml`](roles/uranus_admin/tasks/preflight.yml) und
[`files/boundary.sql`](roles/uranus_admin/files/boundary.sql):

1. **READ ONLY** — als lokaler Operator `postgres`, Datenbank explizit `oklab`:
   `current_database()`, Read-only-Status, `to_regnamespace('uranus')`,
   `to_regclass` für `uranus.event`, `event_date`, `venue`, `organization`,
   `admin.alembic_version`, PostGIS-Existenz.
2. **READ ONLY** — derselbe Operator, `pg_catalog` und `admin.alembic_version`:
   ein gebundener SELECT/CTE in `boundary.sql` prüft Rollen, Rechte, Ownership,
   Abhängigkeiten und Release-Head. Kein DDL/DML.
3. **READ ONLY**, optional `ua_counts: true` — vier feste `SELECT COUNT(*)` auf
   den genannten Uranus-Kerntabellen. Nur Orientierung, kein Gleichheits-/Mindestwert-Guard.
4. **READ ONLY**, nach Build vor Umschaltung — echte Runtime-DSNs als
   `uranus_reader` bzw. `admin_user`; `SET TRANSACTION ... READ ONLY`,
   `SELECT current_database(), current_user`, vorhandene lesende
   [Source-Verifikation](../backend/app/source_schema_verify.py),
   [Admin-Grenzprüfung](../backend/app/admin_database.py) und
   [Head-/Grant-Prüfung](../backend/app/storage_preflight.py).
   Keine App-Startup-Funktion, kein Worker-/Auth-Management-Aufruf.

Die Operator-Queries verwenden `default_transaction_read_only=on`, 10 Sekunden
Statement-Timeout, 2 Sekunden Lock-Timeout und `search_path=pg_catalog`.
Die Runtime-Verifikation nutzt explizite read-only Transaktionen und die Zeitlimits
der Anwendung. Source-Queries sind schemaqualifiziert. Der bestehende Datenbank-
`search_path` bleibt erhalten; nur der dedizierte Console-Reader erhält seine eigene
Datenbank-Rolleneinstellung `pg_catalog, uranus_console`. Counts können durch legitime parallele Live-
Schreibvorgänge schwanken und beweisen deshalb keinen unveränderten Datenbestand.

**Source/Admin-Preflight: keine schreibenden SQL-Kommandos.** Der getrennte
Console-Schritt verwendet CREATE ROLE, CREATE SCHEMA, CREATE OR REPLACE VIEW,
explizite GRANTs und ALTER ROLE ausschließlich gemäß dem Console-Vertrag. Nach Wiederanlauf kann der vorhandene
Check-Worker bereits eingereihte Aufträge bearbeiten und dabei bestimmungsgemäß
in `admin` schreiben (**CHANGES ADMIN SCHEMA ONLY**, normales Runtime-DML).
Er erhält keine Rechte zum Schreiben in `uranus`.

### Ansible-managed Console-Infrastruktur

Capability: `SQL_CONSOLE_DATABASE_URL` muss im Environment-Vertrag des authentifizierten
Release-Manifests stehen. Alte Releases planen keine Console-Änderungen und löschen
vorhandene Console-Objekte nicht. Der eigene
[Contract v5](roles/uranus_admin/files/sql_console_contract.json) pinnt Uranus
`7ae87ea7fe39692c1f3dcc3a5621f6c9e7bb574d`: vier Views (`event_date`, `event`,
`venue`, `organization`), 31 explizite Spalten und Datentypen.

1. `sql_console_plan.yml`: reine Katalog-READ-ONLY-Prüfung und geheimnisfreier Plan.
2. `sql_console_provision.yml`: zusätzliches `ua_sql_console_provision_approved: true`
   plus bestehende Apply-Gates; idempotente Rollen/Schema/Views/Minimal-Grants und
   datenbankbezogener Reader-Search-Path. Wiederholte Prüfung und atomarer DB-Commit.
3. `sql_console_verify.yml`: neue READ-ONLY-Verbindung, exakter Sollzustand ohne Drift.
4. Erst dann Release-Build und echte Console-DSN-Verifikation, anschließend Maintenance
   und App-Aktivierung. Recovery bleibt ausschließlich systembezogen.

`uranus_console_owner` ist NOLOGIN; `uranus_console_reader` ist LOGIN. Beide erhalten
NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS und NOINHERIT. Bestehende
INHERIT-Rollen führen zu `unsafe_role_inherit:<role>`; keine automatische Reparatur.
Keine Memberships. Nur der Owner besitzt Console-Schema/Views und exakte Quellspaltenrechte.
Nur der Reader erhält View-SELECT, Console-USAGE und CONNECT. Überprivilegierte bestehende
Rollen, falsche Owner und Zusatzrechte werden abgewiesen, nicht still repariert.
Abweichende View-Definitionen bei unverändertem Spaltenvertrag werden reconciled;
unbekannte Objekte führen zu `unexpected_sql_console_object`, niemals automatischem DROP.

PUBLIC TEMP wird nur dann automatisch reconciled, wenn alle betroffenen normalen
Login-Rollen vom versionierten TEMP-Vertrag abgedeckt sind. `database_temp_roles` enthält:
`uranus_reader`, `admin_user`, `admin_migrator`, `admin_auth_operator`. Diese vier
bestehenden LOGIN-Rollen müssen vorhanden sein. `additional_database_temp_roles`
ergänzt 14 bekannte weitere Verbraucher, sofern sie bereits existieren. Der Plan
inventarisiert effektive Rechte, direkte TEMP-Grants, Membership-Pfade und privilegierte Identitäten.
Superuser und der Datenbank-Owner mit eigener TEMP-ACL verlieren keine Rechte und
werden separat ausgewiesen. Die Console-Rollen sind ausdrückliche TEMP-freie Ziele.

Apply vergibt zuerst fehlende explizite TEMP-Grants an die geprüften vorhandenen Rollen, entzieht
anschließend ausschließlich PUBLIC TEMP und prüft den gesamten Sollzustand erneut,
bevor dieselbe Console-Provisionierungstransaktion committet. Ein Fehler rollt alle
Änderungen zurück. Der zweite Apply bleibt unverändert. Unbekannte Login-Verbraucher
(`unexpected_public_temp_consumer:<role>`), nicht erlaubte direkte Grants,
Grant Options und ungeprüfte TEMP-Membership-Pfade blockieren ohne Teiländerung.
Auch indirekte SET-ROLE-Pfade werden geprüft; NOINHERIT allein genügt dafür nicht.

Der Function-/Extension-Vertrag in Contract v5 / Policy v3 prüft exakte Katalog-Fingerprints.
Geprüfte Kombinationen:

- PostgreSQL **16.15 / PostGIS 3.4.2** — dokumentierte Production-Baseline,
  reproduzierbarer Ubuntu-24.04-Testbuild aus gepinnten Image-/Paketquellen.
- PostgreSQL **16 / PostGIS 3.4.3** — CI-Kompatibilität (auditiert mit 16.4).
- PostgreSQL **17 / PostGIS 3.5.2** — CI-Kompatibilität (auditiert mit 17.5).

`function_policy.catalogs[PG-Major].postgis_versions[extversion]` wählt den vollständigen
Core-/plpgsql-/PostGIS-Snapshot anhand der **tatsächlich installierten exakten** Version.
Keine 3.4.x-Wildcard, kein nächster Patchstand und kein Core-Fallback zwischen Snapshots.
Neue PostGIS-Patchstände und abweichende Build-/Katalog-Fingerprints bleiben fail-closed.
Der [3.4.2-Audit](tests/images/pg16-postgis342/README.md) dokumentiert feste Quellen,
Definition-/ACL-/Metadatenvergleich und Reproduktion. Core und plpgsql aus Ubuntu 16.15
wurden geprüft und entsprechen dem bisherigen PG16-CI-Katalog. Der separat genehmigte
Katalogaudit vom 20. September 2026 bestätigt diese Baseline für den erfassten Bestand.
Jeder spätere Lauf muss die Fingerprints erneut prüfen. Neue Versionen oder Definitionen
benötigen ein neues Review. Sichere geprüfte PostGIS-IMMUTABLE/STABLE-Funktionen behalten PUBLIC EXECUTE;
Schema, Extension-Zugehörigkeit, Owner, Sprache/C-Bibliothek und Sicherheitsattribute
werden geprüft. Kein pauschales PostGIS-Allowlisting und kein `oid >= 16384`-Blocker.

Für konkret geprüfte gefährliche Signaturen inventarisiert Ansible PUBLIC-/direktes und
effektives EXECUTE sowie Membership-/SET-ROLE-Pfade. Nur bekannte Verbraucher erlauben
den atomaren Übergang: vorhandene PUBLIC-Rechte durch explizite Grants an die separat
geprüften EXECUTE-Erhaltungsrollen erhalten, PUBLIC EXECUTE dieser Signatur entziehen,
vollständige Grenze erneut
prüfen, erst dann Commit. Beide Console-Rollen bleiben ohne gefährliches EXECUTE.
Unbekannte Verbraucher/Funktionen/Extensions, SECURITY DEFINER, Zusatzgrants und
Membership-Pfade blockieren. Bereits nicht öffentliche privilegierte Funktionen erhalten
keine neuen App-Grants. Der Plan zeigt jede betroffene Signatur, Erhaltungsrollen und
geplante Grants/REVOKEs; Fehler rollen auch TEMP und Console-Objekte zurück. Zweiter Apply:
`changed=0`. Keine pauschale Manipulation von Funktionsrechten.

Contract v5 ergänzt vier optionale Contrib-Extensions, zwölf stets eingeschränkte
eigene Funktionen und konkrete Eigentümerregeln für den erfassten Bestand. TEMP-
und EXECUTE-Erhaltungslisten sind getrennt; zusätzliche Rollen werden nie angelegt.
Details, Review-Nachweise und Grenzen stehen im
[Bestandskatalog-Vertrag](../backend/docs/sql-console-reviewed-catalog.md).

Die drei fingerprintgeprüften Standard-Metadatenobjekte von PostGIS behalten ausschließlich
ihr vorhandenes SELECT. Die Testfixture verwendet unverändertes `CREATE EXTENSION postgis`,
keine vorbereitenden pauschalen PUBLIC-REVOKEs. Der Search-Path bleibt
`pg_catalog, uranus_console`; sichere schemaqualifizierte PostGIS-Aufrufe sind möglich.
Details, Signaturmengen, Audit-Reproduktion und Grenzen stehen im
[Function-/Extension-Vertrag](../backend/docs/sql-console-infrastructure.md#public-temp-und-function-extension-grenze).

Andere gemeinsame Rechte, insbesondere PUBLIC CREATE, bleiben Blocker. Kein allgemeines
Aufräumen von CONNECT, CREATE, Extensions oder sonstigen PUBLIC-Grants. Kein Unsafe-Override
und keine heimliche Ersatz-DB. Phase 3 benötigt zusätzlich AST-/Function-Denylist und
Ressourcen-, Timeout-, Zeilen- und Parallelitätslimits; kein freier Executor in diesem PR.

Secret ausschließlich als `SQL_CONSOLE_DATABASE_URL` in geschützter `operator.env`
(root:root 0600) oder bereits expliziter Runtime-Konfiguration bereitstellen. Lokales
`oklab`, Benutzer `uranus_console_reader`, eigenes Passwort (mindestens 24 druckbare
ASCII-Zeichen ohne Leerzeichen, URL-kodiert). Keine Inventory-/CLI-Secrets und keine
Fallbacks auf Source/Admin-DSNs. `no_log`, keine Secret-Diffs, keine automatische
Rotation. Frontend erhält keine DSN. Keine Secret-Generation bei jedem Deployment.

#### Lesender Diagnoseexport bei Console-Blockern

Für einen freigegebenen Katalogabgleich kann unabhängig von Release-Artefakt,
Runtime-/Operator-Environment und Deployment ein Diagnoseexport ausgeführt werden:

```sh
export ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg"
uv run --no-project --python 3.13 --with-requirements ansible/requirements-controller.txt ansible-playbook -i ansible/inventory.local.yml ansible/sql-console-audit.yml
```

Der Aufruf verwendet dieselbe SSH-Verbindung wie das Deployment und auf dem Ziel
`become_user: postgres`, `/usr/bin/python3` mit psycopg2 sowie den festen lokalen
Socket `/var/run/postgresql`, Port 5432, Datenbank `oklab`. Er benötigt keine DSN
und liest keine Environment-Dateien. Die Datenbanktransaktion ist **READ ONLY /
REPEATABLE READ**, mit 10 Sekunden Statement- und 2 Sekunden Lock-Timeout.
Katalogblocker verhindern den Export nicht; Verbindungs-/Abfragefehler bleiben Fehler.
Keine Provisionierung, Grants, Migrationen, Service- oder Deployment-Aktionen.
Ansible kann wie beim Preflight temporäre Transferdateien auf dem Ziel benötigen.

Der Controller speichert pro Inventory-Host
`ansible/sql-console-audit.local/<inventory_hostname>.json` (Datei 0600,
Verzeichnis 0700, gitignored). Ein erneuter Export ersetzt die vorherige Datei
desselben Hosts. `--check` liest die Kataloge ebenfalls, speichert aber keine Datei;
die Zusammenfassung weist dies mit `saved: false` aus. Zum Sammeln der Diagnose
deshalb den obigen Aufruf ohne `--check` verwenden. Die Terminalausgabe enthält nur
Blockerkategorien und den lokalen Dateipfad.

Der JSON-Bericht enthält den bisherigen Plan, Rollenattribute und Memberships,
Extension-Versionen/-Eigentümer, Katalog-Fingerprints und die einzelnen Nicht-Core-
Funktionssignaturen mit Definitions-Hashes, Eigentümern und EXECUTE-ACLs. Für
PostGIS-Metadaten stehen tatsächliche und erwartete Definitions-Hashes,
`owner_matches_extension`, `definition_matches_contract`, fehlende Objekte und
Strukturmerkmale separat bereit. Damit lassen sich Eigentümer- und
Definitionsabweichungen sowie deren Folgeblocker unterscheiden.

Keine Anwendungszeilen, Passwörter, Funktions-/View-SQL-Texte oder rohen
Konfigurationswerte werden ausgegeben. Auch Funktionsdefinitionen können Secrets
enthalten; sie werden deshalb nur gehasht. Die interne Rollen-/Objektinventur
trotzdem vertraulich behandeln. Definitionen anschließend gegen den zugehörigen
Quellstand bzw. eine isolierte Paket-Referenzinstallation prüfen; ein Hash allein
beweist keine sichere Implementierung. Der Bericht enthält Erfassungszeit und
Vertrags-Hash, er **aktualisiert oder genehmigt keinen Vertrag**. Unbekannte Rollen,
Extensions und Funktionen bleiben bis zum geprüften Vertragsupdate blockiert.

Beispiel eines gekürzten **Plans**, keine Aussage über Production:

```yaml
sql_console:
  required: true
  role: uranus_console_reader
  schema: uranus_console
  contract_version: 5
  owner_role: uranus_console_owner
  changes_planned:
    - would grant explicit TEMPORARY uranus_reader
    - would revoke PUBLIC TEMPORARY
    - would create role uranus_console_owner
    - would create role uranus_console_reader
    - would create schema uranus_console
    - would create view event_date
    - would reconcile owner SELECT event_date.uuid
    - would reconcile reader SELECT event_date
    - would set role search_path
  runtime_dsn_present: true
  fallback: false
  public_temp: true
  temp_login_roles:
    [admin_auth_operator, admin_migrator, admin_user, postgres, uranus_reader]
  temp_reconcile:
    allowed: true
    would_grant_explicit:
      [uranus_reader, admin_user, admin_migrator, admin_auth_operator]
    would_revoke_public_temp: true
  extensions:
    - name: plpgsql
      version: "1.0"
      status: allowed
      reviewed_functions: 3
      restricted_functions: 0
      blocked_functions: 0
    - name: postgis
      version: "3.5.2"
      status: reconcile_required
      reviewed_functions: 776
      restricted_functions: 86
      blocked_functions: 0
  execute_reconcile:
    allowed: true
    changes: # Auszug; der echte Plan zeigt jede betroffene Signatur.
      - signature: pg_catalog.set_config(text, text, boolean)
        catalog: core
        retained_roles:
          [uranus_reader, admin_user, admin_migrator, admin_auth_operator]
        would_grant_explicit:
          [uranus_reader, admin_user, admin_migrator, admin_auth_operator]
        would_revoke_public_execute: true
  blockers: []
```

`--check --diff` zeigt den Plan auch ohne Console-Approval und führt keine Console-
Mutationen aus. Ein Blocker wird nach dem Report als Fehler ausgegeben. Inspect
provisioniert auch ohne Check Mode nicht. Keine erfolgreiche echte Runtime-Anmeldung
wird im Check Mode behauptet. Für einen kompatiblen, versionierten Produktionszustand
ist kein manueller psql-Schritt nötig; ungeprüfte gemeinsame DB-Rechte bleiben ausdrücklich außerhalb dieser Freigabe.
Details und Phase-3-Kriterien: [Console-Infrastruktur](../backend/docs/sql-console-infrastructure.md).

### Alembic-Audit des Ausgangsstands

| Revision | Betroffene Objekte; Upgrades ausschließlich in `admin`                                        |
| -------- | --------------------------------------------------------------------------------------------- |
| 0001     | `check_run`, `finding`, Constraints/Index                                                     |
| 0002     | Review-Spalten/Constraints `finding`, `check_run.rule_results`                                |
| 0003     | `record_mark`, `record_mark_event`                                                            |
| 0004     | `auth_account`, `auth_system_admin`, `auth_session`, `auth_login_bucket`                      |
| 0005     | Retention-Indizes auf Auth-Tabellen                                                           |
| 0006     | `check_run`: bestehende laufende Jobs als fehlgeschlagen markieren, Status/Lease/Worker/Index |
| 0007     | `url_check` und Index                                                                         |
| 0008     | `notification`, `notification_delivery`, `notification_delivery_item`                         |
| 0009     | Retry-Verknüpfung, FK innerhalb `admin`, Index auf `notification_delivery`                    |
| 0010     | `geo_area`, PostGIS-Geometrie und Indizes                                                     |
| 0011     | `geocode_request`, `geocode_candidate`                                                        |

[`migrations/env.py`](../backend/migrations/env.py) setzt Metadatenfilter und
Versionstabelle auf `admin`, verlangt `ADMIN_MIGRATION_DATABASE_URL` und besitzt
einen Admin-Schema-Bootstrap. Es setzt keinen `search_path`. Die geprüften Revisionen
schreiben nicht nach `uranus`; manche Downgrades löschen jedoch Admin-Daten.
**Daher kein Upgrade, Bootstrap, Downgrade oder `alembic stamp` in dieser Rolle.**
Ein neues Head erfordert erneut Migrationsprüfung, vollständigen SQL-/Grant-Plan,
Backup-/Downtime-Plan und separate Zustimmung. Es gibt keinen Schalter zum Umgehen
des aktuellen Head-Checks.

## Releases, systemd und Dateien

**CHANGES SYSTEM CONFIGURATION** — folgende Pfade sind der vollständige verwaltete
Produktionsumfang; temporäre Ansible-/Validierungsdateien kommen technisch hinzu:

| Pfad                                                                       | Aktion                                                                                                                                                                                                             |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/home/oklab/build/uranus-admin/.deployment-builds/<commit>/`              | Lokaler Arbeitsbereich als `oklab` für uv/pnpm-Befehle. Der laufende Checkout daneben bleibt erhalten. `.build-complete` markiert einen abgeschlossenen Build für die begrenzte Aufbewahrung.                      |
| `/var/lib/uranus-admin/releases/<commit>/`                                 | Neues getrenntes Release mit Backend-venv und gebautem Nitro-Server; nach Build root-owned. Vorheriges Checkout wird nicht überschrieben.                                                                          |
| `/var/lib/uranus-admin/releases/<commit>/.complete`                        | SHA256 des fertig gebauten Archivs; vorhandene abweichende Marker führen zum Abbruch.                                                                                                                              |
| `/var/lib/uranus-admin/releases/<commit>/deployment/`                      | Prüfprogramme und nichtgeheime Konfigurationskandidaten.                                                                                                                                                           |
| `/var/lib/uranus-admin/current`                                            | Verweis auf zuletzt erfolgreich aktiviertes Release, erst nach Healthchecks geändert. Units verwenden feste Release-Pfade.                                                                                         |
| `/var/cache/uranus-admin-build/`                                           | Build-Cache von uv/pnpm, Benutzer `oklab`. Kein Laufzeit-Schreibpfad des Services.                                                                                                                                 |
| `/var/lib/uranus-admin/maintenance/`                                       | Root-owned statische Wartungsseite, lokale Assets und Marker `enabled`; Details unter [Wartungsmodus](#wartungsmodus).                                                                                             |
| `/etc/uranus-admin/`                                                       | root:root, 0700.                                                                                                                                                                                                   |
| `/etc/uranus-admin/runtime.env`                                            | root:root, 0600; systemd liest und übergibt ausschließlich Runtime-Konfiguration.                                                                                                                                  |
| `/etc/uranus-admin/operator.env`                                           | root:root, 0600; vorhandene Migrator-/Operator-/Dev-Token-Einträge gesichert, nie in Units geladen. Unterschiedliche bereits gesicherte Werte führen zum Abbruch.                                                  |
| `/etc/uranus-admin/recovery/<commit>/attempt-<zufall>/`                    | Frischer root-only Snapshot pro Aktivierungsversuch: geänderte Altdateien und Manifest mit Existenz, Ownership, Modi, Service-Zuständen und vorherigem current-Verweis. Kein DB-Backup.                            |
| `/home/oklab/build/uranus-admin/backend/.env`                              | Standard unverändert, weil der bestehende Notification-Service sie liest. Nur mit beiden Notification-Flags bereinigen und auf root:root 0600 setzen; Altdatei im Recovery-Snapshot.                               |
| `/home/oklab/build/uranus-admin/frontend/.env`                             | Inhalt erhalten, root:root 0600.                                                                                                                                                                                   |
| `/etc/systemd/system/uranus-admin-{backend,frontend,check-worker}.service` | Bekannte Units mit festen Release-Pfaden aktualisieren. UMask 0027; Python-Dienste starten über `uv run --no-cache --no-sync --offline --no-python-downloads --no-env-file python`, keine Installation beim Start. |
| `/etc/nginx/sites-available/uranus-admin`                                  | Bestehenden Vhost aktualisieren. Der vorhandene sites-enabled-Symlink muss bereits genau hierhin zeigen.                                                                                                           |
| `/etc/nginx/conf.d/uranus-admin-logging.conf`                              | Eigenes Access-Logformat ohne Querystring, Referer, Cookies, User-Agent oder fremdes X-Forwarded-For.                                                                                                              |
| `/var/log/nginx/uranus-admin-access.log`                                   | Nginx schreibt das dedizierte Log; vorhandene Nginx-Logrotation muss diesen `*.log`-Pfad erfassen.                                                                                                                 |

Zusätzlich schreibt Nginx `/var/log/nginx/uranus-admin-error.log` mit Level `warn`
für HTTP und HTTPS. Die Rolle verändert keine globale Logrotate-Konfiguration.

Der laufende Checkout unter `/home/oklab/build/uranus-admin` wird beim Build nicht
überschrieben. uv/pnpm arbeiten in `.deployment-builds/<commit>` darunter. Nur die
fertige Runtime liegt unter `/var/lib/uranus-admin/releases/<commit>`: Backend-Quellen,
die direkt am endgültigen Pfad angelegte Python-Umgebung und die standalone Nitro-Ausgabe.
`UV_PROJECT_ENVIRONMENT` legt die Python-Umgebung direkt am späteren Runtime-Pfad an.
Sie wird nicht verschoben; Interpreterlinks und Shebangs bleiben nach dem Aufräumen
gültig. Nitro-Links außerhalb der kopierten
`.output` werden vor Aktivierung verweigert. Releases und Toolchain liegen unter
root-kontrollierten Elternverzeichnissen; der Runtime-Benutzer kann sie nicht durch
Umbenennen eines schreibbaren Home-Elternverzeichnisses ersetzen.

**READ ONLY:** Vor Downloads oder DB-Zugriff prüft Ansible die Mount-Tabelle und alle
Elternpfade von Build-, Runtime-/Toolchain- und Cache-Verzeichnissen. Nur `ext4`, `xfs`,
`btrfs` und `zfs` sind zugelassen; NFS, CIFS, unbekannte Dateisysteme, Symlink-Eltern,
zusätzliche Mounts innerhalb der verwalteten Bäume und Read-only-Dateisysteme führen
zum Abbruch. Mindestens **6 GiB** müssen auf jedem betroffenen Dateisystem frei sein
(`ua_min_free_bytes`, nur nach oben anpassbar). Das ist eine Reserve, keine Garantie
für die Größe künftiger Dependencies. Check Mode prüft dieselben Voraussetzungen
ohne Dateien anzulegen oder Speicher automatisch freizugeben.

Alte Dateien unter `/opt/uranus-admin` werden weder verwendet noch automatisch
verschoben, übernommen oder gelöscht. Alte `ua_root`-Overrides müssen entfernt werden;
es gibt keinen NFS-Fallback. Keine automatische Release-/Cache-/Backup-Bereinigung.
Ansible installiert und prüft die benötigte
isolierte Toolchain selbst; globale Runtime-Versionen werden nicht ersetzt oder verwendet.
Der Build lädt gesperrte Dependencies, kann also Paketregistry-Zugriff benötigen.
Das Artefakt enthält `pnpm-workspace.yaml` einschließlich der erlaubten Build-Scripts.
Keine Secrets, Tests oder Test-Fixtures gelangen in das Release-Archiv.

### Drei abgeschlossene Build-Arbeitsverzeichnisse behalten

`ua_cleanup_builds: true` ist der Standard. **CHANGES SYSTEM CONFIGURATION:** Erst
nach erfolgreicher Aktivierung und allen Healthchecks entfernt Ansible als `oklab`
ältere abgeschlossene Arbeitsverzeichnisse ausschließlich unter
`/home/oklab/build/uranus-admin/.deployment-builds`. Die drei neuesten werden anhand
der Änderungszeit ihres gültigen `.build-complete`-Markers behalten, bei Gleichstand
entscheidet die Commit-ID. Der Build des aktuellen Deployments bleibt zusätzlich
geschützt, auch bei einem bewusst älteren Release; dann können mehr als drei bleiben.

Nur Verzeichnisse mit vollständiger 40-stelliger Commit-ID und gültigem Abschlussmarker
sind Kandidaten. Unbekannte und unvollständige Verzeichnisse bleiben erhalten und werden
gezählt. Symlink-Eltern, umgeleitete Kandidaten/Marker, abweichende Eigentümer, unsichere
Rechte und Mounts im Build-Baum führen zum Abbruch. Dateideskriptor-basierte Entfernung
folgt keinen internen Symlinks. Im Check Mode wird nur `would_remove` gemeldet; ein
fehlgeschlagenes Deployment oder dessen Recovery erreicht die Bereinigung nicht.
Ein Bereinigungsfehler nach erfolgreicher Aktivierung wird gemeldet, löst aber keinen
Rollback der gesunden Anwendung aus. `ua_cleanup_builds: false` deaktiviert die Funktion.

Runtime-Releases, `current`, Toolchain, laufender Checkout, Secrets, Recovery-Snapshots,
Backup-Dateien und Datenbanken liegen außerhalb dieses Löschbereichs. Diese Funktion
ist kein SQL-Cleanup und behebt keine volle Platte durch ungeprüftes Löschen.

## Isolierte, von Ansible verwaltete Toolchain

**CHANGES SYSTEM CONFIGURATION**, ausschließlich unter `/var/lib/uranus-admin/toolchain`.
Auf dem Zielhost ist keine manuelle Python-/uv-/Node-/pnpm-Installation mehr erforderlich.
`/usr/bin/python3`, `/usr/bin/node`, `/usr/bin/pnpm`, `/usr/local/bin/uv` und globale
Package-Manager-Zustände bleiben unverändert. Der vorhandene Ubuntu-Systeminterpreter
führt weiterhin Ansible-Module aus; er ist kein Python-Interpreter für das Release.
Die Controller-Aufrufe mit `uv run` bleiben wie unten beschrieben.

Quelle der angeforderten Versionen ist `release.json`: `python`, `uv`, `node`, `pnpm`.
Die geprüften Artefakte stehen in
[`toolchain-pins.json`](roles/uranus_admin/files/toolchain-pins.json), nicht nochmals in
Role-Defaults. Nur Ubuntu 24.04 auf `x86_64` wird unterstützt. Unbekannte Manifest-Versionen,
Architekturen, fehlende/ungültige Pins oder nicht passende Downloadquellen brechen ab.
`ua_python`, `ua_uv`, `ua_node`, `ua_pnpm` und der Build-PATH werden intern abgeleitet;
alte manuelle Inventory-/Extra-Var-Overrides entfernen. Abweichende Overrides werden verweigert.

| Tool                                                           | Offizielle versionierte Quelle                                                                                                                                                                              | SHA256 des Archivs                                                 |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| CPython 3.13.15, Astral python-build-standalone Build 20260807 | [install_only_stripped, GNU/Linux x86_64](https://github.com/astral-sh/python-build-standalone/releases/download/20260807/cpython-3.13.15%2B20260807-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz) | `faae10a9faa9bec06da009ac69326cc1d9691dc138fec6a1b69159dff1781f35` |
| uv 0.12.5                                                      | [Astral GitHub Release](https://github.com/astral-sh/uv/releases/download/0.12.5/uv-x86_64-unknown-linux-gnu.tar.gz)                                                                                        | `68a509da24b06b4223a1c0175fb5eb5bc79342b76cbeff0cfe51ac3f5b17b6b2` |
| Node 22.22.3                                                   | [Node.js Releasearchiv](https://nodejs.org/dist/v22.22.3/node-v22.22.3-linux-x64.tar.xz)                                                                                                                    | `2e5d13569282d016861fae7c8f935e741693c269101a5bebcf761a5376d1f99f` |
| pnpm 12.3.4                                                    | [pnpm GitHub Release, natives Linux-x64-Artefakt](https://github.com/pnpm/pnpm/releases/download/v12.3.4/pnpm-linux-x64.tar.gz)                                                                             | `9705e5704b4679fb503c963a18d1ac4f105e39aafafca8a2ed346facdf820cd0` |

Die GitHub-Hashes wurden gegen die veröffentlichten Release-Asset-Digests und lokal
gegen die heruntergeladenen Archive geprüft. Node wurde zusätzlich gegen das offizielle
[`SHASUMS256.txt`](https://nodejs.org/dist/v22.22.3/SHASUMS256.txt) geprüft.
Python ist ein portabler CPython-Build von Astral, kein Compiler-Build auf Production.
Die explizite `python_series`-Zuordnung pinnt Manifest-Serie `3.13` auf den konkreten
Patch `3.13.15` und Build `20260807`; die Versionsprüfung erwartet exakt `Python 3.13.15`.
Updates erfordern Review von Quelle, Hash und dieser Zuordnung. Alte Katalogeinträge und
Installationen müssen erhalten bleiben, solange ältere Releases sie referenzieren.

Finale ausführbare Pfade:

```text
/var/lib/uranus-admin/toolchain/python-3.13.15-20260807/bin/python3.13
/var/lib/uranus-admin/toolchain/uv-0.12.5/uv
/var/lib/uranus-admin/toolchain/node-22.22.3/bin/node
/var/lib/uranus-admin/toolchain/pnpm-12.3.4/pnpm
```

pnpm 12.3.4 ist ein natives Binary. Sein npm-Launcher würde ein weiteres Binary
nachladen. Deshalb installiert Ansible direkt das offizielle vollständige native
Release samt mitgelieferten Dateien, ohne npm-Install-Script oder Corepack-Bootstrap.
Build-Scripts erhalten den isolierten Node-Pfad an erster Stelle des PATH.
Das vorhandene pnpm-Lockfile enthält auch `packageManagerDependencies` mit Integritätswerten;
diese müssen erhalten bleiben. Ein frisches Testprojekt ohne diesen Lockfile-Teil würde
bereits zur Konfigurationsauflösung Registry-Zugriff benötigen.
`--pm-on-fail=error` und `--runtime-on-fail=error` verhindern alternative Runtime- oder
Package-Manager-Downloads. HOME/Cache/State liegen explizit unter
`/var/cache/uranus-admin-build`; Benutzer-Konfiguration wird nicht aus dem Operator-HOME
gelesen. Backend/Worker verwenden das verwaltete uv, das Frontend den verwalteten Node.
Die systemd-Units enthalten unveränderliche Versionspfade; ältere Releases bleiben lauffähig.
Vor der Runtime-DB-Verifikation wird auch der tatsächliche Basisinterpreter der Release-
Umgebung gegen den verwalteten Python-Pfad geprüft. Ein vorhandener `.complete`-Marker
berechtigt nicht zur Wiederverwendung einer Umgebung mit globalem oder anderem Python.
Bei Abweichung wird ohne Reparatur/Überschreiben abgebrochen; ein neues geprüftes Release
ist erforderlich.

Reihenfolge: Input-/Apply-Gates → Host-/OS-/lokale Speicher-/Nginx-Prüfung → Toolchain-Inspektion →
bei freigegebenem Echtlauf Provisionierung und Verifikation → unveränderter READ-ONLY-
DB-Preflight → Environment-Plan → Console-Plan/Provisionierung/READ-ONLY-Verifikation
→ lokaler Build/Runtime-Prüfung → Aktivierung/Recovery
→ nur bei Erfolg begrenzte Build-Aufbewahrung.
Ein Toolchain-Fehler erreicht weder DB-Prüfung noch Secret-Übernahme, Nginx-Mutation
oder Service-Stop. Die Activation-Recovery bleibt unverändert und greift auf keine DB zu.

`preflight.yml --check --diff` und `deploy.yml --check --diff` installieren nichts und
führen keine Download-Anfragen aus. Fehlende Tools werden als `missing -> would install`
gemeldet. Vorhandene Installationen werden auch im Check Mode vollständig geprüft.
Fehlende Tools sind kein Fehler; falscher Host/OS/Architektur, unsichere Pfade, falsche
Eigentümer/Rechte, ungültige Pins oder ein nicht beschreibbarer Zielpfad sind Fehler.
Auch `ua_action=inspect` ohne Check Mode provisioniert nichts.

`get_url` lädt nur fehlende, fest versionierte Archive mit HTTPS und festem SHA256 nach
`toolchain/archives/<Versionsverzeichnis>.tar`. Der lokale Ansible-Modulcode
[`uranus_toolchain.py`](roles/uranus_admin/library/uranus_toolchain.py) besitzt keinen
Downloader. Er extrahiert nach validierter Archivstruktur zunächst in ein neues
Staging-Verzeichnis unter derselben Toolchain und veröffentlicht das geprüfte Verzeichnis
per Rename. Die eigene Extraktion ist nötig, um Traversal, Spezialdateien, externe Links
und Links in Elternpfaden vor dem Schreiben abzulehnen und Rechte zu normalisieren.

Alle Verzeichnisse sind root:root 0755, ausführbare Dateien 0755, Daten/Archive 0644.
Die vier aufgerufenen Binaries müssen reguläre Dateien sein. Ausschließlich exakt im
gepinnten Archiv enthaltene relative interne Symlinks sind erlaubt; Archiv-Hardlinks
werden als unabhängige reguläre Dateien materialisiert. Vor jeder Ausführung werden
Archiv-SHA256, **alle** installierten Dateien, Dateitypen, Modi, Eigentümer und Linkziele
geprüft. Ein lokaler Completion-Marker allein ist kein Integritätsnachweis. Danach folgt
die exakte Versionsprüfung als `oklab`. uv darf den offiziellen Plattform-/Build-Suffix
anzeigen, aber keine abweichende semantische Version.

Ein zweiter unveränderter Lauf lädt nichts herunter, extrahiert nichts und meldet für
die Toolchain `changed=0`. Die vollständige Integritätsprüfung bleibt bewusst aktiv;
sie liest auch große Archiv-/Binary-Dateien. Unbekannte Dateien, unvollständige
Installationen, manipulierte Archive oder zurückgebliebene `.staging-*`-Verzeichnisse
führen zum Abbruch, ohne Überschreiben oder Cleanup. Bei einem unterbrochenen Bootstrap
müssen die Befunde explizit durch den Betreiber untersucht werden. Parallele Deployments
oder manuelle Änderungen während der Prüfung/Installation sind nicht unterstützt.

Ein schon vorhandenes `toolchain`-Verzeichnis mit `oklab:oklab` ist **nicht** vertrauenswürdig,
auch wenn es leer wirkt. Ansible übernimmt es nicht automatisch. Eigentümer und Inhalt
zunächst lesend mit `stat` und `ls -la` prüfen; eine notwendige manuelle Korrektur separat
bewerten. Der Guard nennt erwartete und tatsächliche numerische UID/GID.

## Normaler Deploy und optionales Notification-Management

Standard:

```yaml
ua_manage_notification_timer: false
```

Ein normales Deployment verändert weder Notification-Timer noch Notification-Service:
kein Stop, Disable, Enable oder Restart, auch nicht im Recovery. Die gemeinsam vom
bestehenden Notification-Service verwendete Legacy-Backend-`.env` bleibt einschließlich
ihrer Rechte unverändert. Damit wird auch vorhandene Zustellung nicht indirekt abgeschaltet.
Die neuen Backend-/Check-Worker-Units erhalten weiterhin nur die bereinigte
`/etc/uranus-admin/runtime.env`, niemals Migrator-/Operator-Credentials.
Eine eventuell noch unsichere Legacy-Konfiguration muss bewusst separat übernommen werden.

Nur mit beiden expliziten Flags:

```yaml
ua_manage_notification_timer: true
ua_disable_notification_timer_approved: true
```

wird der Timer gestoppt/deaktiviert, ein laufender Notification-Oneshot gestoppt und
seine Legacy-Environment-Datei bereinigt. `manage=true` ohne die zweite Zustimmung
verweigert den Echtlauf vor jedem Host-Eingriff. Die übrigen Apply-Gates gelten unverändert.
Bei erfolgreicher Aktivierung bleiben verwaltete Notifications deaktiviert; bei
fehlgeschlagener Aktivierung werden die ursprünglichen Zustände wiederhergestellt.

## Aktivierungsreihenfolge

Vor diesen Aktivierungsschritten: Host-/Source-/Admin-Preflight, Console-Plan,
Console-Provisionierung und separate READ-ONLY-Console-Verifikation vollständig
abschließen. Ein Console-Fehler verändert keine laufenden Services und aktiviert
keine Maintenance.

1. Release bauen, Runtime-Konfiguration/DSNs **READ ONLY** verifizieren und
   systemd-/Nginx-Kandidaten prüfen. Ein Kandidatenfehler stoppt vor Service-Eingriffen.
2. Geplante Dateizustände nach dem Build erneut prüfen; bei paralleler Veränderung abbrechen.
3. **CHANGES SYSTEM CONFIGURATION** — root-only Recovery-Kopien pro Versuch erstellen,
   bevor irgendein Service gestoppt oder eine verwaltete Konfiguration ersetzt wird.
4. Lauf-/Enablement-Zustände unmittelbar vor Aktivierung als Facts erfassen und ins
   Recovery-Manifest schreiben, einschließlich ursprünglichem Maintenance-Markerzustand.
   Übergangszustände, Maskierung oder nicht unterstützte
   Enablement-Arten führen zum Abbruch. Nginx muss bereits laufen.
5. Ein Handler fordert die Aktivierung an. Ein normaler `block`/`rescue` bereitet die
   [Wartungsseite](#wartungsmodus) vor, aktiviert den Marker und lädt nach `nginx -t`
   den gesicherten Proxy-Kandidaten. Erst nach Abwarten alter Nginx-Worker und
   öffentlicher 503-Verifikation stoppt er betroffene Services. Notification-Eingriffe
   sind zusätzlich durch beide Flags begrenzt. Der Handler selbst verändert keine Services.
6. Geprüfte Dateien installieren, gegebenenfalls `daemon-reload`, vollständiges `nginx -t`.
7. Betroffene App-Services starten; Nginx nur bei eigener Config-Änderung reloaden.
8. **READ ONLY** — lokal Backend `/health`, `/ready` und Frontend `/login` prüfen.
   Bei ursprünglich OFF: Maintenance deaktivieren, `nginx -t`, Reload und öffentliches
   HTTPS-GET `/login` prüfen. Ursprüngliches ON erhalten und öffentlich 503 verifizieren.
9. Erst danach `current` umstellen und `ua_activation_succeeded=true` setzen.

Fehler in Schritt 5–9 führen zum **SYSTEM ROLLBACK** unten. Auch ein fehlgeschlagenes
Nginx-Verify/Reload wird im normalen Aktivierungsblock aufgefangen. Es gibt keine später noch
wartenden einzelnen Restart-Handler, die nach der Recovery neue Services starten könnten.

Identische Artefakte/Dateien werden nicht neu gebaut oder geschrieben. Unveränderte,
laufende Services werden nicht neu gestartet. Ohne Aktivierungsbedarf entsteht kein
neuer Recovery-Snapshot; es laufen nur Healthchecks. Bereits gestoppte betroffene
App-Services werden bei Erfolg gestartet, bei Fehler dagegen in ihrem alten Zustand belassen.
Check-Jobs können durch Unterbrechung ihre Lease verlieren und regulär fehlschlagen;
kein automatisches Requeue oder Resetten. Ein unvollständiger Build wird nicht aktiviert;
keine automatische Löschung von Releases, unvollständigen Build-Resten oder Snapshots.

## Secrets und Production-Debug

Es werden keine neuen Passwörter erzeugt, keine Secrets aus Beispieldateien installiert
und keine vorhandenen Zugangsdaten rotiert. Der Console-Reader übernimmt sein separates
Secret aus der geschützten `operator.env` oder einer bereits expliziten Runtime-DSN;
Ansible setzt bei Neuanlage dessen SCRAM-Verifier. Bei Abweichung Abbruch statt Rotation. Beim ersten Lauf ist die bestehende Backend-
`.env` die Quelle; danach `/etc/uranus-admin/runtime.env`. Unbekannte Schlüssel,
Dubletten, Interpolation oder mehrdeutige Syntax führen zum Abbruch.

Die Werte werden mit `no_log: true` verarbeitet; Secret- und Altdatei-Diffs sind gesperrt.
Keine Ausführung mit `ANSIBLE_DEBUG`, fremden Debug-Callbacks oder Fact-Caching, keine
Rohvariablenausgabe. Standardmäßiges Fact-Caching wird nicht aktiviert. Auch bestehende
Units können Inline-Secrets enthalten, deshalb keine automatischen vollständigen Unit-Diffs.
Die neuen Templates sind vollständig im Repository prüfbar.

`DATABASE_URL` muss auf `uranus_reader`, `ADMIN_DATABASE_URL` auf `admin_user`, jeweils
lokales `oklab:5432`, zeigen. Runtime-Units entfernen zusätzlich privilegierte Variablen
mit `UnsetEnvironment`. Frontend erhält keine DB-DSNs. `operator.env` ist ein geschütztes
Archiv, kein automatisch benutzter CLI-Kontext. Nur der explizite Console-DSN-Schlüssel
wird bei unterstützenden Releases für die geschützte Console-Provisionierung übernommen;
Migrator-/Operator-Credentials bleiben außerhalb der Runtime. Ein späterer Wechsel zu Vault/SOPS ist
ein eigener, geprüfter Secret-Management-Schritt; nichts wird unverschlüsselt eingecheckt.

Mit `ua_debug: true` werden zusammen gesetzt:

```dotenv
APP_ENV=production
APP_DEBUG=true
ALLOW_PRODUCTION_DEBUG=true
LOG_LEVEL=DEBUG
DEV_AUTH_ENABLED=false
OPENAPI_ENABLED=false
NOTIFICATIONS_DELIVERY_ENABLED=false
```

Standard ist Debug aus. Debug-Tracebacks können sensible Exception-Details enthalten;
Journal-Zugriff und Debug-Dauer begrenzen. Die Flags öffnen weder Dev-Auth noch OpenAPI.
Im neuen Runtime-Environment bleibt Zustellung deaktiviert. Unverwaltete bestehende
Notifications behalten ihre bisherigen SMTP-Einstellungen und ihren Betriebszustand.

Der gemeinsame Linux-Account `oklab` bleibt ein verbleibendes Isolationsrisiko:
andere Prozesse dieses Accounts sind keine getrennte Vertrauensdomäne. Die Rolle
wechselt nicht stillschweigend Benutzer oder Ownership anderer Anwendungen.

HTTP und HTTPS verwenden `error_log /var/log/nginx/uranus-admin-error.log warn;`.
Das minimierte Access-Log bleibt ohne Querystrings. Nginx-Errorlogs können trotzdem
sensible Request-Informationen einschließlich Querystrings enthalten. Zugriff auf
berechtigte Betreiber begrenzen (beispielsweise 0640 mit passender Betreibergruppe),
begrenzte Aufbewahrung und sichere Rotation samt Wiederöffnung der Logs sicherstellen.
Keine Errorlog-Inhalte ungeprüft in Tickets oder CI-Ausgaben kopieren.

Im Repository gibt es keine bestehende Logrotate-Konfiguration. Die produktive
`/etc/logrotate.d/nginx` wurde für diese Nachbesserung mangels freigegebenem Live-Zugriff
nicht ausgelesen; ihre Regeln/Dateiabdeckung und Zugriffsrechte müssen vor einem später
freigegebenen Deployment lesend geprüft werden. Eine Wildcard wie `/var/log/nginx/*.log`
kann beide Dateien erfassen, ist hier aber nicht als produktiver Befund bestätigt.
Die Rolle installiert keine konkurrierende Rotation und verändert keine globale Nginx-Konfiguration.

Der Release-Bau bereitet Python-Abhängigkeiten mit
`uv run --locked --no-dev --no-env-file --python <Python-Pfad> python --version` vor.
Arbeitsverzeichnis ist der separate lokale Build; `UV_PROJECT_ENVIRONMENT` zeigt auf
`/var/lib/uranus-admin/releases/<commit>/backend/.venv`, damit dieser Pfad nie umgezogen wird.
Dieser Aufruf installiert nur die gesperrten Runtime-Abhängigkeiten und startet keine
Anwendung. `uv` verwaltet dabei intern weiterhin eine virtuelle Umgebung im Release;
ein vollständig venv-freier Python-Betrieb ist damit nicht gemeint. Anschließend wird
das Release wie bisher root-eigen und für die Dienste schreibgeschützt.
Backend, Check-Worker und die read-only Runtime-Verifikation verwenden dieselbe
vorbereitete Umgebung über `uv run --no-cache --no-sync --offline --no-python-downloads --no-env-file`.
Beim Start erfolgen weder Dependency-Sync noch Downloads oder zusätzliches Laden einer
`.env` durch uv. Fehlende Abhängigkeiten müssen beim Release-Bau behoben werden,
nicht durch einen Fallback beim Service-Start.

`--no-cache` verhindert den Zugriff auf den persistenten uv-Cache im Home-Verzeichnis.
Auch mit `--no-sync --offline` initialisiert uv sonst diesen Cache und kann unter
`ProtectHome=read-only` mit `Read-only file system` abbrechen. Stattdessen verwendet
uv ein temporäres Verzeichnis innerhalb des systemd-`PrivateTmp`. `ProtectSystem=strict`
und `ProtectHome=read-only` bleiben erhalten; es gibt keinen zusätzlichen schreibbaren
Home-, Release- oder Build-Cache-Pfad für die Dienste. Die vorbereitenden uv-Prüfaufrufe
verwenden dieselbe Cache-Option. Der lokale Regressionstest startet beide gerenderten
Python-Service-Befehle gegen harmlose Fixtures mit einem unbenutzbaren Home-Cache;
er ist kein vollständiger Test der systemd-Sandbox.

## Lokale Vorbereitung und freizugebender Dry Run

Alle Controller-Aufrufe laufen mit `uv run` aus dem Repository-Root. Es gibt keinen
manuellen `uv venv`-/`uv pip install`-Schritt und keine Aktivierung oder direkten Aufrufe
aus `ansible/.venv`. `uv` stellt Python 3.13 und die gepinnten Requirements in einer
verwalteten Cache-Umgebung bereit; `--no-project` verhindert die Verwendung einer
lokalen Projektumgebung. Die erste Ausführung benötigt Zugriff auf die Paketquellen.
Die Ansible-Collection wird weiterhin separat über `ansible-galaxy` installiert:

```sh
uv run --no-project --python 3.13 --with-requirements ansible/requirements-controller.txt ansible-galaxy collection install -r ansible/requirements.yml
uv run --no-project --python 3.13 python ansible/scripts/package_release.py --output /tmp/uranus-release.tar.gz
```

Der Packager ruft bei jedem Aufruf `main` frisch von `origin` ab und paketiert dessen
neuesten Commit. Der lokale Branch, ein veralteter lokaler `main` und uncommitted
Änderungen bestimmen das Release nicht. Schlägt der Fetch fehl, bricht der Packager
ab; es gibt keinen Fallback auf einen alten Stand. Der Checkout wird nicht gewechselt.
Eine bereits vorhandene Ausgabedatei wird weiterhin nicht überschrieben; beim nächsten
Release einen neuen Archivpfad wählen.

„Latest main“ gilt zum Zeitpunkt der Paketierung. Danach bleiben Commit und Archiv für
Dry Run und ausdrückliche Apply-Freigabe unveränderlich. Neue Commits auf `main` erfordern
ein neues Archiv und eine neue Prüfung/Freigabe; der Echtlauf lädt keinen anderen Stand
nach. Paketierung allein führt kein Deployment aus.

Der Packager verwendet ausschließlich committed Sources, gibt Commit, Archivpfad
und SHA256 aus und erstellt byteidentische Archive für denselben Stand. Diese drei
Werte in eine lokale Kopie von `inventory.example.yml` übernehmen. Lokales Inventory
ist gitignored. Keine Credentials in Inventory oder CLI-Argumenten. Bestehenden,
verifizierten SSH-Hostkey verwenden; niemals StrictHostKeyChecking deaktivieren.

`community.postgresql` benötigt auf dem Ziel unter `/usr/bin/python3` psycopg2 oder
psycopg3; der Console-Provisionierer benötigt psycopg2. Die Rolle installiert
dieses Paket nicht automatisch. Der Operator muss
über sudo als `postgres` lokal lesen, im freigegebenen Console-Schritt die isolierte
Infrastruktur provisionieren und im späteren Echtlauf Systemdateien verwalten
können. Bei Bedarf `--ask-become-pass`, kein Passwort im Inventory.
Die projektlokale `ansible.cfg` verwendet `/tmp` als Basis für private Ansible-Task-
Unterverzeichnisse. Dadurch benötigt `become_user: postgres` kein schreibbares
`/var/lib/postgresql/.ansible/tmp`. Eine entsprechende Temp-Fallback-Warnung ist kein
DB-Fehler und darf nicht durch pauschales Ändern von PostgreSQL-Verzeichnisrechten
„repariert“ werden. `ANSIBLE_CONFIG` wie unten setzen.

**READ ONLY — erst nach Freigabe der Prüfverbindung:**

```sh
export ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg"
uv run --no-project --python 3.13 --with-requirements ansible/requirements-controller.txt ansible-playbook -i ansible/inventory.local.yml ansible/preflight.yml --check --diff
uv run --no-project --python 3.13 --with-requirements ansible/requirements-controller.txt ansible-playbook -i ansible/inventory.local.yml ansible/deploy.yml --check --diff
```

Der zweite Aufruf zeigt Pfade, konkrete Restart-Liste, Nginx-Reload und Secret-/Timer-
Entscheidungen. **Danach STOPPEN und Ausgabe prüfen lassen.** `--diff` veröffentlicht
absichtlich weder Secrets noch Altdateien; für Inhalt-Review die Templates verwenden.
Check Mode baut keine Releases, validiert keine neu installierten Executables/DSNs,
schreibt keine Environment-Dateien und simuliert keinen erfolgreichen Service-Start.
Datei-Tasks können mangels Elternverzeichnis nur eingeschränkt simuliert werden.
Root-/Secret-Verzeichnis, Operator-Archiv, Frontend-Env-Modus, Timer und Release-Pointer
werden im Plan benannt, aber nicht durch Fake-Änderungen simuliert. Ansible kann
technische Transfer-/Tempdateien benötigen; READ ONLY meint hier Anwendungs-/DB-/Systemzustand.

Keine Tags/Skip-Tags, kein `--start-at-task`, keine Manipulation der Sicherheitsvariablen.
CLI-Freigabevariablen sind eine organisatorische Sperre, keine Sicherheitsgrenze gegen
einen privilegierten Betreiber, der das Playbook verändert oder Tasks überspringt.

Nach Prüfung und ausdrücklicher Echtlauf-Freigabe eine **lokale**, nicht eingecheckte
`ansible/approvals.local.yml` mit echten Referenzen anlegen:

```yaml
ua_apply_confirmation: "Ja, führe das Deployment jetzt aus."
ua_reviewed_dry_run: "<Datum und Referenz des geprüften Dry Runs>"
ua_maintenance_window: "<bestätigtes Zeitfenster>"
ua_backup_reference: "<geprüfter Backup-/Recovery-Nachweis>"
ua_manage_notification_timer: false
ua_secret_adoption_approved: true
# Zusätzlich bei einem Release mit SQL_CONSOLE_DATABASE_URL:
ua_sql_console_provision_approved: true
# Nur bei ausdrücklichem Notification-Management zusätzlich:
# ua_manage_notification_timer: true
# ua_disable_notification_timer_approved: true
```

Diese Angaben müssen tatsächlich zutreffen; nicht bloß befüllen, um Guards zu umgehen.
Sie sind keine automatische Prüfung der Backup-Güte. Erst dann:

```sh
uv run --no-project --python 3.13 --with-requirements ansible/requirements-controller.txt ansible-playbook -i ansible/inventory.local.yml ansible/deploy.yml -e @ansible/approvals.local.yml
```

## Wartungsmodus

Standardmäßig ist `ua_maintenance_page_enabled: true`. Der Wartungsmodus gehört zum
bewachten Playbook-Ablauf; es gibt keinen zusätzlichen manuellen Umschalt-Schritt.
Die unveränderten Freigaben und READ-ONLY-Preflights gelten weiterhin.

Reihenfolge bei einer erforderlichen Aktivierung:

1. Release bauen, Runtime und Konfigurationskandidaten prüfen.
2. Frischen Recovery-Snapshot einschließlich ursprünglichem Markerzustand erstellen.
3. Statische Wartungsdateien vollständig installieren, noch ohne Aktivierung.
4. Marker atomar anlegen (vorhandenen Inhalt erhalten). Den bereits geprüften,
   gesicherten Nginx-Kandidaten bei Bedarf vorziehen: Bei der ersten Übernahme kennt
   der alte VHost den Marker noch nicht. `nginx -t`, Reload.
5. Zuerst das Ende der vor dem Reload erfassten Nginx-Worker abwarten (maximal
   60 Sekunden pro Worker). Der Reload ist asynchron; alte Worker können noch
   die vorherige Proxy-Konfiguration bedienen. Auch alte, noch laufende Requests
   dürfen nicht durch den Service-Stopp abbrechen. Timeout bricht ohne App-Stopp ab,
   ohne Worker zu beenden oder andere Sites zu verändern. Anschließend öffentliches
   HTTPS-GET `/` auf **503**, festen HTML-Marker, escaped Titel, `Retry-After` und
   `Cache-Control: no-store` prüfen: maximal zehn Wiederholungen mit zwei Sekunden
   Abstand und zehn Sekunden Timeout pro Request. Nur der vollständige Vertrag
   gilt als Erfolg; auch eine 503-Seite mit falschem Inhalt oder Headern scheitert.
   Redirects werden nicht verfolgt, Zertifikate geprüft. Eine vorübergehende 302
   darf erneut geprüft werden, eine dauerhafte 302 löst Recovery ohne App-Stopp aus.
6. Optionale explizit verwaltete Notifications und betroffene App-Services stoppen,
   übrige Konfiguration installieren, geänderte Units neu laden, `nginx -t` ausführen,
   betroffene Services starten und geändertes Nginx reloaden.
7. Lokal `127.0.0.1:8011/health`, `/ready` und `127.0.0.1:3011/login` prüfen.
8. War Maintenance vorher OFF: Marker entfernen, `nginx -t`, Reload, öffentliches
   HTTPS-GET `/login` auf 200 prüfen. Jeder Fehler löst Activation-Recovery aus.
   War Maintenance vorher ON: Marker erhalten und öffentlich erneut 503 prüfen;
   der Login wird in diesem Fall ausschließlich lokal geprüft.
9. Erst danach `current` veröffentlichen und Aktivierung als erfolgreich markieren.

Ein unveränderter Lauf schaltet Maintenance nicht um und reloadet Nginx nicht.
Öffentliche Wartungstexte/Assets werden auch ohne Service-Umschaltung idempotent
aktualisiert; ein vorher aktiver Marker bleibt dabei erhalten.
`ua_maintenance_page_enabled: false` lässt den bisherigen Ablauf ohne Wartungsseite
zu; ein vorhandener aktiver Marker verhindert diese Deaktivierung ausdrücklich.

### Dateien, HTTP und öffentliche Angaben

| Pfad                                               | Eigentümer/Modus | Zweck                                             |
| -------------------------------------------------- | ---------------- | ------------------------------------------------- |
| `/var/lib/uranus-admin/maintenance/` und `assets/` | root:root 0755   | Nginx-lesbare statische Dateien                   |
| `maintenance/maintenance.html`                     | root:root 0644   | Gerendertes deutsches HTML                        |
| `maintenance/assets/lottie.min.js`                 | root:root 0644   | Lokal vendorte Lottie-Light-Runtime               |
| `maintenance/assets/maintenance.json`              | root:root 0644   | Kleine eigene Server-/Update-Animation            |
| `maintenance/assets/maintenance.js`                | root:root 0644   | Lokaler Initializer, Reduced-Motion-Unterstützung |
| `maintenance/assets/LICENSE.lottie-web.txt`        | root:root 0644   | MIT-Copyright-/Lizenzhinweis                      |
| `/var/lib/uranus-admin/maintenance/enabled`        | root:root 0644   | Einzige ON/OFF-Quelle                             |

Die relativen Dateizeilen liegen ebenfalls unter `/var/lib/uranus-admin/`.
Die App-Services können diese Dateien nicht schreiben. Der Marker liegt bewusst
außerhalb von `/etc/uranus-admin` (0700), damit Nginx keine Leserechte auf Secrets braucht.
Symlinks und ungeeignete Verzeichnisse/Marker werden abgewiesen.

Bei ON liefern `/`, `/login`, `/api/admin/…` und `/_nuxt/…` die interne statische Seite
mit **503 Service Unavailable**, `Retry-After: 300` (konfigurierbar durch
`ua_maintenance_retry_after`, 1–86400 Sekunden), `Cache-Control: no-store`,
`X-Robots-Tag: noindex, nofollow, noarchive` und den vorhandenen Sicherheitsheadern.
Die Fehlerseite wird nicht mit Status 200 ausgeliefert. Exakte Asset-Routen unter
`/__maintenance_assets/` funktionieren nur bei ON; unbekannte Assets und direkter
Zugriff auf `/__maintenance.html` ergeben 404. Bei OFF bleiben die Proxy-Routen erhalten.
HTTP leitet weiterhin auf HTTPS um. Sicherheitsbedingte Deny-/Rate-Limit-Antworten
bleiben bestehen.

Die strengere Maintenance-CSP erlaubt keine externen Ressourcen oder Verbindungen.
`connect-src 'self'` ist ausschließlich für die lokale Lottie-JSON-Anfrage nötig;
kein `unsafe-eval`, keine externen Fonts oder CDNs. Die eigene dekorative Animation
hat `aria-hidden="true"`; `prefers-reduced-motion` blendet sie aus und verhindert bzw.
pausiert die Wiedergabe. Alle Informationen stehen im HTML und funktionieren ohne JS.
[Quelle, feste Version, Hash und Lizenz](roles/uranus_admin/files/maintenance/README.md):
Lottie-Web 5.13.0 Light/SVG unter MIT mit installiertem Lizenzhinweis, eigene Animation
und Initializer unter Projektlizenz AGPL-3.0. Keine Drittgrafik unklarer Herkunft.

`ua_maintenance_public_title`, `ua_maintenance_public_message` und
`ua_maintenance_public_window` sind bewusst **öffentliche** Texte und werden HTML-escaped.
Beispiel: `ua_maintenance_public_window: "20.09.2026 · 13:30–14:00 Uhr"`.
Bei leerem Zeitraum entfällt der Abschnitt. Die interne Freigabevariable
`ua_maintenance_window` wird niemals in die Seite übernommen. Öffentliche Texte
enthalten keine Secrets oder internen Freigabereferenzen.

### Check Mode und Recovery

`--check --diff` meldet `maintenance_page`, `maintenance_marker`,
`maintenance_public_window`, `would_enable_before_service_stop`, `would_verify_http_503`
und `would_disable_after_healthchecks`. Der sichere Report enthält außerdem
`maintenance.enabled`, `public_window`, `activation_before_service_stop`,
`expected_status`, `retry_after` und `external_assets: false`. Er beschreibt den Plan,
keine erfolgte Verifikation. Check Mode erzeugt keinen Marker, stoppt keine Services
und führt keinen Nginx-Reload aus.

Die Recovery stellt zuerst einen möglicherweise schon entfernten Marker wieder her.
Ist die öffentliche Aktivierungsprüfung fehlgeschlagen, werden App-Services auch im
Rescue-Pfad **nicht** gestoppt. Nach begonnener Service-Umschaltung: betroffene neue
Services stoppen, bisherige Dateien/Metadaten und gegebenenfalls `current` restaurieren,
Units neu laden und restaurierte Nginx-Konfiguration prüfen. Alte Service-/Notification-
Zustände wiederherstellen, **erst dann** die alte Nginx-Konfiguration laden (diese kann
bei Erstübernahme noch ohne Maintenance-Unterstützung sein). Zuletzt den ursprünglichen
Markerzustand wiederherstellen. Das bestehende Recovery-Verhalten führt weiterhin
keine HTTP- oder DB-Readiness-Probes aus; vorher gestoppte Services bleiben gestoppt.
Der Snapshot enthält den ursprünglichen Markerzustand und -pfad im `manifest.json`.

Bei erfolgreicher Recovery wird OFF wieder OFF; vorheriges ON bleibt ON. Das Deployment
endet trotzdem failed. Scheitert Recovery, wird kein Marker blind entfernt; ein bereits
entfernter Marker wird nach Möglichkeit wieder angelegt. Ausgabe:
`SYSTEM RECOVERY FAILED. Maintenance mode remains active where activation was possible.`
Manueller Operator-Eingriff ist erforderlich. Der zuletzt geladene Wartungs-VHost bleibt
während der Dateirestaurierung aktiv. Ein Host-/Nginx-Ausfall oder verlorener Controller
kann durch diesen Mechanismus nicht zuverlässig aufgefangen werden.

**NO DATABASE ROLLBACK. Keine Datenbankänderungen:** Maintenance und Recovery führen
keine SQL-, Alembic-, PostgreSQL-, Grant- oder Daten-Restore-Aufrufe aus. Unveränderte
lokale `/ready`-Prüfungen gehören nur zum regulären Aktivierungs-Healthcheck.

Nur lesende Notfall-Diagnose, kein normaler Deployment-Umschaltweg:

```sh
test -f /var/lib/uranus-admin/maintenance/enabled && echo active || echo inactive
curl -I https://admin.kulturbytes.de/
```

## Automatische System-Recovery und Produktionsverifikation

**NO DATABASE ROLLBACK.** Der Rescue-Pfad ist auf `systemd`, Nginx, Runtime-/Legacy-
Environment, Dateimetadaten, Service-Zustand und den vorherigen `current`-Verweis begrenzt.
Er enthält keine PostgreSQL-Module, keine SQL-/Alembic-/Restore-Aufrufe, keine HTTP-
Readiness-Abfragen und keine Includes von DB-Tasks. `boundary.sql`, Runtime-Verifikation
und sämtliche read-only PostgreSQL-Preflights bleiben vor der Aktivierung.
Console DB infrastructure wird nicht destruktiv zurückgerollt: nach erfolgreichem
Console-Commit kein DROP VIEW, DROP ROLE oder DROP SCHEMA im System-Recovery.

Die Recovery stoppt zuerst betroffene neue App-Prozesse und stellt geänderte Altdateien
mit ihrem vorherigen Inhalt, Besitzer, Gruppe und Modus wieder her. Zuvor nicht existente
verwaltete Konfigurationsdateien werden gezielt entfernt (z. B. die neue `runtime.env`
bei der Erstübernahme); das ist kein allgemeiner Cleanup. Ebenso werden die vorherigen
Rechte der Legacy-Frontend-`.env` und ein gegebenenfalls bereits umgestellter `current`-
Verweis wiederhergestellt. Releases, Logs, Operator-Archiv und geschützte Recovery-
Verzeichnisse bleiben erhalten. Jeder Versuch verwendet einen eigenen Snapshot, auch
bei gleichem Release-SHA; alte Sicherungen werden nicht versehentlich als aktueller Zustand benutzt.

Danach: bei geänderten Units `daemon-reload`, restauriertes Nginx mit `nginx -t` prüfen,
nur vorher laufende betroffene App-Services wieder starten und erst danach bei Bedarf
das restaurierte Nginx reloaden. Anschließend den ursprünglichen Maintenance-Markerzustand
wiederherstellen.
Vorher gestoppte oder fehlgeschlagene Services bleiben gestoppt; Enabled/Disabled wird
zurückgesetzt. Der ursprüngliche systemd-Fehlerstatus selbst wird nicht künstlich reproduziert.
Beispiel: Backend/Frontend vorher aktiv, Check-Worker vorher gestoppt → nur Backend und
Frontend starten wieder. Unbetroffene Services werden nicht unterbrochen.

Nur bei ausdrücklich verwalteten Notifications werden deren ursprünglicher Service-
und Timer-Laufzustand sowie Timer-Enablement wiederhergestellt. Ein vorher statischer
Notification-Service bleibt statisch. Ein aktiver Timer bzw. ein unterbrochener Oneshot
kann dadurch wieder normale Arbeit ausführen; es gibt keine Queue-/Daten-Rücksetzung
oder Zusicherung genau-einmaliger Zustellung. Ohne Management bleiben beide unangetastet.

Wieder gestartete Anwendungen arbeiten mit ihren bisherigen Konfigurationen und können
normalerweise in `admin` schreiben. Die Recovery selbst greift auf keine Datenbank zu;
die technische SELECT-only-Grenze zum Live-Schema `uranus` wird nicht verändert.
Insbesondere beim ersten Übernahmeversuch kann die genaue Wiederherstellung auch bereits
bekannte Schwächen der vorherigen Environment-Dateien/Units zurückbringen. Es werden dabei
keine neuen DB-Rechte vergeben und keine alten Datenstände zurückgespielt.

Ein erfolgreich zurückgesetztes Deployment endet trotzdem **fehlgeschlagen**, mit Verweis
auf seinen Recovery-Snapshot. Scheitert die Recovery selbst, wird ebenfalls abgebrochen
und manuelle System-Recovery verlangt, ohne weitere Konfigurations-Fallbacks.
Der Maintenance-Marker bleibt dabei nach Möglichkeit aktiv. Ungültige restaurierte
Nginx-Konfiguration wird nicht reloadet; betroffene App-Services bleiben dann gestoppt.
Host-Ausfall, verlorene SSH-Verbindung, Controller-Abbruch und bestimmte Ansible-Syntax-
oder Unreachable-Fehler können nicht zuverlässig durch `rescue` aufgefangen werden.
Dafür bleiben Snapshot und Manifest verfügbar. Kein `force_handlers`, keine parallelen
Deployments oder manuellen Konfigurationsänderungen während der Aktivierung.

Nach erfolgreichem Deployment zusätzlich read-only prüfen: drei erwartete Units aktiv,
Notification-Zustand unverändert (oder bei explizitem Management Timer inaktiv/disabled),
Ports ausschließlich loopback, `/health` und `/ready` erfolgreich, HTTPS-/Cookie-/Header-
Verhalten. `/ready` beweist keine Worker-Liveness; bestehenden Queue-/Lease-Fortschritt
getrennt beobachten. Keine SMTP-Zustellung, neuen Jobs oder Auth-Retention als Smoke-Test.
Backup und Wiederherstellbarkeit bleiben eine separate Betriebsaufgabe.

## Tests

[`Deployment checks`](../.github/workflows/deployment-checks.yml) ist ausschließlich
lokale/CI-Validierung, kein Deployment-Workflow und besitzt keine Production-Credentials.

```sh
uv run --no-project --python 3.13 --with-requirements ansible/requirements-test.txt python -m unittest discover -s ansible/tests -v
uv run --no-project --python 3.13 --with-requirements ansible/requirements-controller.txt ansible-playbook -i ansible/inventory.example.yml ansible/deploy.yml --syntax-check
```

Die Toolchain-Tests verwenden ausschließlich synthetische lokale Archive und ein
lokales Ansible-Check-Mode-Szenario; CI lädt keine realen Toolchain-Artefakte herunter.
Sie prüfen exakte Versionen, Hashes, Eigentümer, Rechte, Symlinks, unbekannte Dateien,
Abbruch ohne Reparatur, Idempotenz, Pfadisolation und Reihenfolge vor dem DB-Preflight.
Der lokale Smoke-Test der vier oben gepinnten echten Archive ist zusätzlich erforderlich,
wenn Pins geändert werden.

Lokale Speicher-/Retention-Tests prüfen NFS-Abweisung, Symlink- und Mount-Grenzen,
Speicherreserve, reine Check-Mode-Planung, Aufbewahrung von drei Builds, Schutz des
aktuellen und unvollständiger Builds, Idempotenz und den Erhalt externer Daten bei
internen Symlinks. Ein echter uv-Fixture-Test entfernt das Build-Verzeichnis und startet
danach weiterhin erfolgreich die unabhängig vorbereitete Runtime-Umgebung.

Die reine Backend-Umgebung enthält keine Ansible-/PyYAML-/psycopg2-Testabhängigkeiten.
Alternativ zum obigen Controller-Testaufruf funktioniert ohne Änderung der Backend-Dependencies:

```sh
uv run --project backend --with-requirements ansible/requirements-test.txt python -m unittest discover -s ansible/tests -v
```

Ohne `ANSIBLE_TEST_DATABASE_URL` werden DB-Tests ausdrücklich übersprungen. Mit dieser
Variable akzeptieren sie nur eine **wegwerfbare lokale** DB mit Namen `*_test`, ohne
vorhandene `uranus`-/`admin`-Schemas und ohne Projektrollen. Der Test legt synthetische
Katalogobjekte/Rollen an; niemals gegen `oklab` oder eine produktive Instanz ausführen.
Für jeden kompletten Testlauf einen frischen Container verwenden. CI prüft PostgreSQL
16/PostGIS 3.4 und PostgreSQL 17/PostGIS 3.5 mit gepinnten Images. Die Nginx-Prüfung
verwendet ein temporäres Testzertifikat/unprivilegierte Loopback-Ports und einen lokalen Fixture-Proxy;
sie verbindet sich nicht mit Production.

Zusätzliche Tests führen echte Ansible-Handler/Blocks/Rescue und Dateioperationen in
temporären Verzeichnissen aus. Nur Host-I/O (systemd, Nginx-Aufruf, HTTP) ist simuliert;
Fehler bei Kandidatenprüfung, Verify/Reload und Healthchecks werden gezielt injiziert.
Sie prüfen Dateiwiederherstellung, frühzeitige Snapshots, Service-/Timer-Zustände,
Maintenance-Reihenfolge und Marker-Erhalt einschließlich Recovery-Fehlern sowie
spätes Setzen von `current`. Rescue-Includes werden rekursiv auf den erlaubten Scope geprüft.

Es gibt weiterhin keinen vollständigen Apply-/Idempotenzlauf auf einem systemd-Abbild des
Produktionshosts. Der freizugebende Dry Run und die tatsächlichen Ziel-Prerequisites
bleiben deshalb notwendige Schritte; lokale Tests ersetzen sie nicht.
