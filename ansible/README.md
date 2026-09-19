# Vorsichtiges Deployment für admin.kulturbytes.de

Diese Rolle übernimmt die **bereits vorhandene** Installation auf `webserver`.
Sie ist kein Datenbank-Bootstrap und kein allgemeines Server-Provisioning.
Alle PostgreSQL-Tasks sind **READ ONLY**. Es gibt keine Migration, keinen Grant,
keine Rollenanlage und keinen Restore, auch keinen entsprechenden Fehler-Fallback.
Ein fehlendes Objekt oder ein unpassender Berechtigungs-/Migrationsstand bedeutet Abbruch.

Die Implementierung darf lokal geprüft werden. Ein produktiver Check Mode benötigt
eine gesonderte Freigabe; ein Echtlauf zusätzlich die ausdrückliche Bestätigung
`Ja, führe das Deployment jetzt aus.` nach Prüfung seines Dry Runs.
Diese Rolle erteilt diese Freigaben nicht selbst. `mach weiter` genügt nicht.

## Berücksichtigter Befund

Die Bestandsaufnahme vom 19. September 2026 ist eine Momentaufnahme, keine Garantie
für einen späteren Lauf. Grundlage des Anwendungsstands:
`0d2c70896d9bb8522ff79162981f0802596e5fb6` auf `main`.

| Befund                                                                                | Umsetzung / verbleibende Grenze                                                                                                                                                             |
| ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ubuntu 24.04.4, systemd 255.4, Nginx 1.24                                             | Preflight verlangt Ubuntu 24.04/systemd 255; vollständiges `nginx -t`; keine Paket-/OS-Upgrades.                                                                                            |
| PostgreSQL 16.15, PostGIS 3.4.2; Client 17.0                                          | Bestehender lokaler Socket, Datenbank `oklab`; keine Extension-Änderung. Tests zusätzlich mit PostgreSQL 17.                                                                                |
| `uranus` gehört `oklab`, `admin` gehört `admin_migrator`                              | Live-Quelle bleibt unverändert. Ownership/effektive Rechte werden geprüft. Linux-User `oklab` ist nicht die DB-Verbindungsrolle.                                                            |
| `admin.alembic_version = 0011`, 16 Admin-Tabellen                                     | Head/Grant-Matrix stammen aus dem ausgewählten Release. Abweichung stoppt, ohne automatische Migration.                                                                                     |
| Reader besitzt SELECT auf 72 Quellobjekten, keine Sequenzrechte                       | Mindestens die 19 benötigten Quellobjekte werden geprüft. Bestehende weitere Leserechte bleiben erhalten; kein pauschales SELECT auf Sequenzen.                                             |
| Vier getrennte App-Rollen, keine Memberships, keine privilegierten Attribute          | Attribute, Memberships in beide Richtungen, Ownership, Tabellen-/Spaltenrechte und indirekte Schreibmöglichkeiten werden erneut geprüft.                                                    |
| App-Rollen haben CONNECT/TEMP, kein Datenbank-CREATE                                  | TEMP wird nicht pauschal über PUBLIC entzogen. Das wäre ein eigener, serverweiter Berechtigungsvorschlag.                                                                                   |
| Backend, Frontend, Check-Worker existieren und laufen                                 | Nur diese drei bekannten Services werden übernommen. Keine zusätzlichen Service-Namen.                                                                                                      |
| Notification-Timer ist aktiv, Notification-Service ist ein stündlicher Oneshot        | Echtlauf verlangt gesonderte Zustimmung zum Stoppen/Deaktivieren. Er wird nie automatisch wieder eingeschaltet.                                                                             |
| Kein URL-/Geocode-Service gefunden                                                    | Keine Installation oder Aktivierung dieser Worker.                                                                                                                                          |
| Bisherige `.env`-Dateien sind 0664, Backend enthält auch privilegierte Variablennamen | Werte wurden beim Audit nicht veröffentlicht. Übernahme liest sie geschützt, erhält Passwörter und trennt Runtime/Operator; keine Behauptung, dass alle gefundenen Variablen befüllt waren. |
| Check-Worker startet bisher über `uv run`, ohne EnvironmentFile                       | Direkter Python-Aufruf aus dem fertigen Release, explizites Runtime-EnvironmentFile; kein Dependency-Sync beim Service-Start.                                                               |
| Frontend-Dev-Token-Flag true, vertrauenswürdiger Ingress nicht konfiguriert           | Flag explizit false; Nitro vertraut ausschließlich dem lokalen Nginx-Peer `127.0.0.1`. Das alte Flag allein bewies keinen Production-Auth-Bypass.                                           |
| Nginx und Apache aktiv                                                                | Nur den bestehenden Admin-Vhost und einen eigenen Logformat-Snippet verwalten. Apache, andere Sites, TLS-Zertifikate und Rate-Zonen bleiben bestehen.                                       |
| Nginx-Limits ohne expliziten 429-Status, Headerverlust im Fehler-Location             | Request-/Connection-Limits liefern 429; vollständige Security-Header auch dort.                                                                                                             |
| Globales Access-Log enthält rohe Requests/Querystrings                                | Eigenes minimiertes Admin-Access-Log. Vhost-Error-Log wird wegen möglicher Rohrequests nach `/dev/null` geleitet; siehe Abwägung unten.                                                     |
| CSP ohne Nonce-System, bereits ohne unsafe-eval                                       | Bestehende CSP erhalten, nicht vorzeitig entfernen.                                                                                                                                         |
| Kein bestätigtes Wartungsfenster, kein bestätigtes DB-Backup                          | Echtlauf bleibt gesperrt, bis beides angegeben und tatsächlich geprüft wurde. Ein vorhandener dpkg-Backup-Timer ist kein PostgreSQL-Backup.                                                 |

Ein identischer Head ist **kein vollständiger struktureller Schema-Diff**. Der
Preflight prüft Objektbestand, Rechte und gefährliche Abhängigkeiten; die spätere
Release-Prüfung zusätzlich den Source-Spaltenvertrag. Die Rolle behauptet weder
eine geprüfte Backup-Wiederherstellung noch erfolgreiche SMTP-Zustellung.

## Datenbankgrenzen und Grants

**Keine der folgenden Berechtigungen wird von Ansible gesetzt.** Die Tabelle beschreibt
die bereits erwarteten Grenzen. Bei fehlenden oder zusätzlichen kritischen Rechten
ist ein separat geprüfter SQL-Plan nötig; die Rolle repariert nichts automatisch.

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
`search_path` wird nicht verändert. Counts können durch legitime parallele Live-
Schreibvorgänge schwanken und beweisen deshalb keinen unveränderten Datenbestand.

**Geplante schreibende SQL-Kommandos: keine.** Nach Wiederanlauf kann der vorhandene
Check-Worker bereits eingereihte Aufträge bearbeiten und dabei bestimmungsgemäß
in `admin` schreiben (**CHANGES ADMIN SCHEMA ONLY**, normales Runtime-DML).
Er erhält keine Rechte zum Schreiben in `uranus`.

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

| Pfad                                                                       | Aktion                                                                                                                                                            |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/opt/uranus-admin/releases/<commit>/`                                     | Neues getrenntes Release mit Backend-venv und gebautem Nitro-Server; nach Build root-owned. Vorheriges Checkout wird nicht überschrieben.                         |
| `/opt/uranus-admin/releases/<commit>/.complete`                            | SHA256 des fertig gebauten Archivs; vorhandene abweichende Marker führen zum Abbruch.                                                                             |
| `/opt/uranus-admin/releases/<commit>/deployment/`                          | Prüfprogramme und nichtgeheime Konfigurationskandidaten.                                                                                                          |
| `/opt/uranus-admin/current`                                                | Verweis auf zuletzt erfolgreich aktiviertes Release, erst nach Healthchecks geändert. Units verwenden feste Release-Pfade.                                        |
| `/var/cache/uranus-admin-build/`                                           | Build-Cache von uv/pnpm, Benutzer `oklab`. Kein Laufzeit-Schreibpfad des Services.                                                                                |
| `/etc/uranus-admin/`                                                       | root:root, 0700.                                                                                                                                                  |
| `/etc/uranus-admin/runtime.env`                                            | root:root, 0600; systemd liest und übergibt ausschließlich Runtime-Konfiguration.                                                                                 |
| `/etc/uranus-admin/operator.env`                                           | root:root, 0600; vorhandene Migrator-/Operator-/Dev-Token-Einträge gesichert, nie in Units geladen. Unterschiedliche bereits gesicherte Werte führen zum Abbruch. |
| `/etc/uranus-admin/recovery/<commit>/`                                     | Einmalige root-only Sicherung vorheriger verwalteter Dateien, inklusive möglicherweise enthaltener Secrets. Nicht als DB-Backup verwenden.                        |
| `/home/oklab/build/uranus-admin/backend/.env`                              | Durch dieselbe bereinigte Runtime-Konfiguration ersetzt, root:root 0600; privilegierte Einträge werden vorher gesichert.                                          |
| `/home/oklab/build/uranus-admin/frontend/.env`                             | Inhalt erhalten, root:root 0600.                                                                                                                                  |
| `/etc/systemd/system/uranus-admin-{backend,frontend,check-worker}.service` | Bekannte Units mit festen Release-Pfaden aktualisieren. UMask 0027; Worker startet direkt `.venv/bin/python`, keine Installation beim Start.                      |
| `/etc/nginx/sites-available/uranus-admin`                                  | Bestehenden Vhost aktualisieren. Der vorhandene sites-enabled-Symlink muss bereits genau hierhin zeigen.                                                          |
| `/etc/nginx/conf.d/uranus-admin-logging.conf`                              | Eigenes Access-Logformat ohne Querystring, Referer, Cookies, User-Agent oder fremdes X-Forwarded-For.                                                             |
| `/var/log/nginx/uranus-admin-access.log`                                   | Nginx schreibt das dedizierte Log; vorhandene Nginx-Logrotation muss diesen `*.log`-Pfad erfassen.                                                                |

Der neue Release-Pfad ist eine bewusst zu prüfende Änderung gegenüber dem bestehenden
Checkout unter `/home/oklab/build`. Keine automatische Release-/Cache-/Backup-Bereinigung.
Ausreichend freien Speicher und eine bereits vorhandene Toolchain bereitstellen:
Python 3.13, uv 0.12.5, Node 22.22.3, pnpm 12.3.4; Pfade in den Role-Defaults prüfen.
Der Build lädt gesperrte Dependencies, kann also Paketregistry-Zugriff benötigen.
Das Artefakt enthält `pnpm-workspace.yaml` einschließlich der erlaubten Build-Scripts.
Keine Secrets, Tests oder Test-Fixtures gelangen in das Release-Archiv.

**CHANGES SYSTEM CONFIGURATION** — nach erfolgreichem Build/Prüfung und erst im
freigegebenen Wartungsfenster:

1. Bestehenden Notification-Timer stoppen/deaktivieren, laufenden Oneshot stoppen.
2. Nur Services anhalten, deren Unit/Runtime-Datei geändert wird oder die bereits
   gestoppt sind. Check-Jobs können hierbei ihre Lease verlieren und regulär fehlschlagen;
   es gibt kein automatisches Requeue oder Resetten.
3. Vorherige Dateien root-only sichern, privilegierte Secrets schützen, geprüfte Dateien installieren.
4. Handler: vollständiges `nginx -t`; bei Unit-Änderungen `daemon-reload`;
   betroffene drei Services starten/enable; Nginx nur bei eigener Config-Änderung reloaden.
5. **READ ONLY** — Backend `/health`, `/ready` und HTTPS-HEAD `/login` prüfen.
   Kein Login-Versuch, Scan, Notification-Retry oder SMTP-Test.
6. Release-Pointer setzen. Keine automatische Rücksetzung bei Fehlern; Diagnose und
   gezielter System-Rollback benötigen eine eigene Entscheidung.

Identische Artefakte/Dateien werden nicht neu gebaut oder geschrieben. Unveränderte,
laufende Services werden nicht neu gestartet. Handler starten auch einen schon zuvor
gestoppten betroffenen Service. Ein unvollständiger Build wird nicht aktiviert; bei
teilweise root-owned Resten ist eine gesonderte Prüfung nötig, keine automatische Löschung.

## Secrets und Production-Debug

Es werden keine neuen Passwörter erzeugt, keine Secrets aus Beispieldateien installiert
und keine vorhandenen Zugangsdaten rotiert. Beim ersten Lauf ist die bestehende Backend-
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
Archiv, kein automatisch benutzter CLI-Kontext. Ein späterer Wechsel zu Vault/SOPS ist
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
Bestehende SMTP-Einstellungen werden erhalten, aber Zustellung bleibt deaktiviert.

Der gemeinsame Linux-Account `oklab` bleibt ein verbleibendes Isolationsrisiko:
andere Prozesse dieses Accounts sind keine getrennte Vertrauensdomäne. Die Rolle
wechselt nicht stillschweigend Benutzer oder Ownership anderer Anwendungen.

Nginx kann seine Error-Logs nicht mit einem eigenen bereinigten Format ausgeben.
Der Admin-Vhost verwendet deshalb `error_log /dev/null`, um rohe Queries dort zu
vermeiden. Das reduziert Proxy-Fehlerdiagnostik; Status-/Timing-Access-Logs, App-Journal
und Konfigurationsprüfungen bleiben. Globales Logging vor Auswahl eines Vhosts und
andere virtuelle Hosts sind damit nicht vollständig abgedeckt.

## Lokale Vorbereitung und freizugebender Dry Run

Controller Python 3.12+; Beispiel aus dem Repository-Root:

```sh
uv venv ansible/.venv
uv pip install --python ansible/.venv/bin/python -r ansible/requirements-controller.txt
ansible/.venv/bin/ansible-galaxy collection install -r ansible/requirements.yml
python3 ansible/scripts/package_release.py --revision <geprüfter-voller-commit> --output /tmp/uranus-release.tar.gz
```

Der Packager verwendet ausschließlich committed Sources, gibt Commit, Archivpfad
und SHA256 aus und erstellt byteidentische Archive für denselben Stand. Diese drei
Werte in eine lokale Kopie von `inventory.example.yml` übernehmen. Lokales Inventory
ist gitignored. Keine Credentials in Inventory oder CLI-Argumenten. Bestehenden,
verifizierten SSH-Hostkey verwenden; niemals StrictHostKeyChecking deaktivieren.

`community.postgresql` benötigt auf dem Ziel unter `/usr/bin/python3` psycopg2 oder
psycopg3. Die Rolle installiert dieses Paket nicht automatisch. Der Operator muss
über sudo als `postgres` lokal lesen und im späteren Echtlauf Systemdateien verwalten
können. Bei Bedarf `--ask-become-pass`, kein Passwort im Inventory.

**READ ONLY — erst nach Freigabe der Prüfverbindung:**

```sh
export ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg"
ansible/.venv/bin/ansible-playbook -i ansible/inventory.local.yml ansible/preflight.yml --check --diff
ansible/.venv/bin/ansible-playbook -i ansible/inventory.local.yml ansible/deploy.yml --check --diff
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
ua_disable_notification_timer_approved: true
ua_secret_adoption_approved: true
```

Diese Angaben müssen tatsächlich zutreffen; nicht bloß befüllen, um Guards zu umgehen.
Sie sind keine automatische Prüfung der Backup-Güte. Erst dann:

```sh
ansible/.venv/bin/ansible-playbook -i ansible/inventory.local.yml ansible/deploy.yml -e @ansible/approvals.local.yml
```

## Rollback und Produktionsverifikation

Ein Rollback betrifft ausschließlich Anwendung/Systemkonfiguration, niemals die
Live-Datenbank: kein Downgrade, Restore, `stamp`, DROP, DELETE oder Reset.
Vorhandene Releases und root-only Dateisicherungen bleiben erhalten. Bei einem Fehler
können Services bereits gestoppt oder neue Dateien installiert sein; Ansible ist keine
Transaktion. Kein `force_handlers` und kein automatisches Starten ungeprüfter Dateien.

Für einen genehmigten Rollback zuerst betroffene Prozesse/Dateien und Fehlerphase
ermitteln. Ein bereits mit dieser Rolle installiertes, schema-kompatibles vorheriges
Release kann nach erneutem Preflight/Dry Run ausgewählt werden. Dessen Artefakt muss
denselben aktuellen DB-Head erwarten. Danach die geprüften Units aktivieren; keine
gespeicherten Queue-/History-Daten rücksetzen.

Beim ersten Rollback zum alten Checkout **nicht blind** `.env` oder alte Units aus
`recovery/` zurückkopieren: dadurch würden privilegierte Variablen wieder in die Runtime
gelangen. Sichere Units auf den alten Codepfad mit `/etc/uranus-admin/runtime.env`
ausrichten und vorher prüfen. Der Notification-Timer bleibt deaktiviert, bis seine
Wiederaufnahme ausdrücklich genehmigt ist. Wiederherstellung von Systemdateien muss
mit `systemd-analyze verify`/`nginx -t` und den gleichen Healthchecks geprüft werden.

Nach Deployment zusätzlich read-only prüfen: drei erwartete Units aktiv, Timer
inaktiv/disabled, Ports ausschließlich loopback, `/health` und `/ready` erfolgreich,
HTTPS-/Cookie-/Header-Verhalten. Ein erfolgreicher `/ready` beweist keine Worker-
Liveness: Lease-/Queue-Fortschritt des bereits vorhandenen Check-Workers getrennt
beobachten, ohne automatisch einen neuen Job einzureihen. Keine SMTP-Zustellung
oder Auth-Retention als Smoke-Test. Backup und Wiederherstellbarkeit bleiben eine
separate Betriebsaufgabe.

## Tests

[`Deployment checks`](../.github/workflows/deployment-checks.yml) ist ausschließlich
lokale/CI-Validierung, kein Deployment-Workflow und besitzt keine Production-Credentials.

```sh
uv pip install --python ansible/.venv/bin/python -r ansible/requirements-test.txt
ansible/.venv/bin/python -m unittest discover -s ansible/tests -v
ansible/.venv/bin/ansible-playbook -i ansible/inventory.example.yml ansible/deploy.yml --syntax-check
```

Ohne `ANSIBLE_TEST_DATABASE_URL` werden DB-Tests ausdrücklich übersprungen. Mit dieser
Variable akzeptieren sie nur eine **wegwerfbare lokale** DB mit Namen `*_test`, ohne
vorhandene `uranus`-/`admin`-Schemas und ohne Projektrollen. Der Test legt synthetische
Katalogobjekte/Rollen an; niemals gegen `oklab` oder eine produktive Instanz ausführen.
Für jeden kompletten Testlauf einen frischen Container verwenden. CI prüft PostgreSQL
16/PostGIS 3.4 und PostgreSQL 17/PostGIS 3.5 mit gepinnten Images. Die Nginx-Prüfung
verwendet ein temporäres Testzertifikat/unprivilegierte Ports, startet keinen Webservice.

Es gibt noch keinen vollständigen Apply-/Idempotenzlauf auf einem systemd-Abbild des
Produktionshosts. Der freizugebende Dry Run und die tatsächlichen Ziel-Prerequisites
bleiben deshalb notwendige Schritte; lokale Tests ersetzen sie nicht.
