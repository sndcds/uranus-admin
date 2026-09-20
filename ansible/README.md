# Vorsichtiges Deployment für admin.kulturbytes.de

Diese Rolle übernimmt die **bereits vorhandene** Installation auf `webserver`.
Sie ist kein Datenbank-Bootstrap und kein allgemeines Server-Provisioning.
Alle PostgreSQL-Tasks sind **READ ONLY**. Es gibt keine Migration, keinen Grant,
keine Rollenanlage und keinen Datenbank-Restore, auch keinen entsprechenden Fehler-Fallback.
Der automatische Fehlerpfad stellt ausschließlich Systemkonfiguration und Service-Zustände wieder her.
Ein fehlendes Objekt oder ein unpassender Berechtigungs-/Migrationsstand bedeutet Abbruch.

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
| App-Rollen haben CONNECT/TEMP, kein Datenbank-CREATE                                  | TEMP wird nicht pauschal über PUBLIC entzogen. Das wäre ein eigener, serverweiter Berechtigungsvorschlag.                                                                                                                                                       |
| Backend, Frontend, Check-Worker existieren und laufen                                 | Nur diese drei bekannten Services werden übernommen. Keine zusätzlichen Service-Namen.                                                                                                                                                                          |
| Notification-Timer ist aktiv, Notification-Service ist ein stündlicher Oneshot        | Standard: unverändert. Nur explizites Notification-Management mit zweiter Zustimmung stoppt/deaktiviert ihn; Recovery stellt dann seinen vorherigen Zustand wieder her.                                                                                         |
| Kein URL-/Geocode-Service gefunden                                                    | Keine Installation oder Aktivierung dieser Worker.                                                                                                                                                                                                              |
| Bisherige `.env`-Dateien sind 0664, Backend enthält auch privilegierte Variablennamen | Werte wurden beim Audit nicht veröffentlicht. Übernahme liest sie geschützt, erhält Passwörter und trennt neue Runtime/Operator; Legacy-Backend-Env nur bei Notification-Management bereinigen; keine Behauptung, dass alle gefundenen Variablen befüllt waren. |
| Check-Worker startet bisher über `uv run`, ohne EnvironmentFile                       | `uv run --no-sync --offline --no-python-downloads --no-env-file` aus dem fertigen Release, explizites Runtime-EnvironmentFile; kein Dependency-Sync beim Service-Start.                                                                                         |
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

| Pfad                                                                       | Aktion                                                                                                                                                                                                  |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/opt/uranus-admin/releases/<commit>/`                                     | Neues getrenntes Release mit Backend-venv und gebautem Nitro-Server; nach Build root-owned. Vorheriges Checkout wird nicht überschrieben.                                                               |
| `/opt/uranus-admin/releases/<commit>/.complete`                            | SHA256 des fertig gebauten Archivs; vorhandene abweichende Marker führen zum Abbruch.                                                                                                                   |
| `/opt/uranus-admin/releases/<commit>/deployment/`                          | Prüfprogramme und nichtgeheime Konfigurationskandidaten.                                                                                                                                                |
| `/opt/uranus-admin/current`                                                | Verweis auf zuletzt erfolgreich aktiviertes Release, erst nach Healthchecks geändert. Units verwenden feste Release-Pfade.                                                                              |
| `/var/cache/uranus-admin-build/`                                           | Build-Cache von uv/pnpm, Benutzer `oklab`. Kein Laufzeit-Schreibpfad des Services.                                                                                                                      |
| `/etc/uranus-admin/`                                                       | root:root, 0700.                                                                                                                                                                                        |
| `/etc/uranus-admin/runtime.env`                                            | root:root, 0600; systemd liest und übergibt ausschließlich Runtime-Konfiguration.                                                                                                                       |
| `/etc/uranus-admin/operator.env`                                           | root:root, 0600; vorhandene Migrator-/Operator-/Dev-Token-Einträge gesichert, nie in Units geladen. Unterschiedliche bereits gesicherte Werte führen zum Abbruch.                                       |
| `/etc/uranus-admin/recovery/<commit>/attempt-<zufall>/`                    | Frischer root-only Snapshot pro Aktivierungsversuch: geänderte Altdateien und Manifest mit Existenz, Ownership, Modi, Service-Zuständen und vorherigem current-Verweis. Kein DB-Backup.                 |
| `/home/oklab/build/uranus-admin/backend/.env`                              | Standard unverändert, weil der bestehende Notification-Service sie liest. Nur mit beiden Notification-Flags bereinigen und auf root:root 0600 setzen; Altdatei im Recovery-Snapshot.                    |
| `/home/oklab/build/uranus-admin/frontend/.env`                             | Inhalt erhalten, root:root 0600.                                                                                                                                                                        |
| `/etc/systemd/system/uranus-admin-{backend,frontend,check-worker}.service` | Bekannte Units mit festen Release-Pfaden aktualisieren. UMask 0027; Python-Dienste starten über `uv run --no-sync --offline --no-python-downloads --no-env-file python`, keine Installation beim Start. |
| `/etc/nginx/sites-available/uranus-admin`                                  | Bestehenden Vhost aktualisieren. Der vorhandene sites-enabled-Symlink muss bereits genau hierhin zeigen.                                                                                                |
| `/etc/nginx/conf.d/uranus-admin-logging.conf`                              | Eigenes Access-Logformat ohne Querystring, Referer, Cookies, User-Agent oder fremdes X-Forwarded-For.                                                                                                   |
| `/var/log/nginx/uranus-admin-access.log`                                   | Nginx schreibt das dedizierte Log; vorhandene Nginx-Logrotation muss diesen `*.log`-Pfad erfassen.                                                                                                      |

Zusätzlich schreibt Nginx `/var/log/nginx/uranus-admin-error.log` mit Level `warn`
für HTTP und HTTPS. Die Rolle verändert keine globale Logrotate-Konfiguration.

Der neue Release-Pfad ist eine bewusst zu prüfende Änderung gegenüber dem bestehenden
Checkout unter `/home/oklab/build`. Keine automatische Release-/Cache-/Backup-Bereinigung.
Ausreichend freien Speicher bereitstellen. Ansible installiert und prüft die benötigte
isolierte Toolchain selbst; globale Runtime-Versionen werden nicht ersetzt oder verwendet.
Der Build lädt gesperrte Dependencies, kann also Paketregistry-Zugriff benötigen.
Das Artefakt enthält `pnpm-workspace.yaml` einschließlich der erlaubten Build-Scripts.
Keine Secrets, Tests oder Test-Fixtures gelangen in das Release-Archiv.

## Isolierte, von Ansible verwaltete Toolchain

**CHANGES SYSTEM CONFIGURATION**, ausschließlich unter `/opt/uranus-admin/toolchain`.
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
/opt/uranus-admin/toolchain/python-3.13.15-20260807/bin/python3.13
/opt/uranus-admin/toolchain/uv-0.12.5/uv
/opt/uranus-admin/toolchain/node-22.22.3/bin/node
/opt/uranus-admin/toolchain/pnpm-12.3.4/pnpm
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

Reihenfolge: Input-/Apply-Gates → Host-/OS-/Nginx-Prüfung → Toolchain-Inspektion →
bei freigegebenem Echtlauf Provisionierung und Verifikation → unveränderter READ-ONLY-
DB-Preflight → Environment-Plan → Release-Bau/Runtime-Prüfung → Aktivierung/Recovery.
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

1. Release bauen, Runtime-Konfiguration/DSNs **READ ONLY** verifizieren und
   systemd-/Nginx-Kandidaten prüfen. Ein Kandidatenfehler stoppt vor Service-Eingriffen.
2. Geplante Dateizustände nach dem Build erneut prüfen; bei paralleler Veränderung abbrechen.
3. **CHANGES SYSTEM CONFIGURATION** — root-only Recovery-Kopien pro Versuch erstellen,
   bevor irgendein Service gestoppt oder eine verwaltete Konfiguration ersetzt wird.
4. Lauf-/Enablement-Zustände unmittelbar vor Aktivierung als Facts erfassen und ins
   Recovery-Manifest schreiben. Übergangszustände, Maskierung oder nicht unterstützte
   Enablement-Arten führen zum Abbruch. Nginx muss bereits laufen.
5. Ein Handler fordert die Aktivierung an. Anschließend stoppt ein normaler
   `block`/`rescue` nur betroffene Services; Notification-Eingriffe sind zusätzlich
   durch beide Flags begrenzt. Der Handler selbst verändert keine Services.
6. Geprüfte Dateien installieren, gegebenenfalls `daemon-reload`, vollständiges `nginx -t`.
7. Betroffene App-Services starten; Nginx nur bei eigener Config-Änderung reloaden.
8. **READ ONLY** — Backend `/health`, `/ready` und HTTPS-HEAD `/login` prüfen.
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
keine automatische Löschung von Releases, Build-Resten oder Snapshots.

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
Dieser Aufruf installiert nur die gesperrten Runtime-Abhängigkeiten und startet keine
Anwendung. `uv` verwaltet dabei intern weiterhin eine virtuelle Umgebung im Release;
ein vollständig venv-freier Python-Betrieb ist damit nicht gemeint. Anschließend wird
das Release wie bisher root-eigen und für die Dienste schreibgeschützt.
Backend, Check-Worker und die read-only Runtime-Verifikation verwenden dieselbe
vorbereitete Umgebung über `uv run --no-sync --offline --no-python-downloads --no-env-file`.
Beim Start erfolgen weder Dependency-Sync noch Downloads oder zusätzliches Laden einer
`.env` durch uv. Fehlende Abhängigkeiten müssen beim Release-Bau behoben werden,
nicht durch einen Fallback beim Service-Start.

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
psycopg3. Die Rolle installiert dieses Paket nicht automatisch. Der Operator muss
über sudo als `postgres` lokal lesen und im späteren Echtlauf Systemdateien verwalten
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
# Nur bei ausdrücklichem Notification-Management zusätzlich:
# ua_manage_notification_timer: true
# ua_disable_notification_timer_approved: true
```

Diese Angaben müssen tatsächlich zutreffen; nicht bloß befüllen, um Guards zu umgehen.
Sie sind keine automatische Prüfung der Backup-Güte. Erst dann:

```sh
uv run --no-project --python 3.13 --with-requirements ansible/requirements-controller.txt ansible-playbook -i ansible/inventory.local.yml ansible/deploy.yml -e @ansible/approvals.local.yml
```

## Automatische System-Recovery und Produktionsverifikation

**NO DATABASE ROLLBACK.** Der Rescue-Pfad ist auf `systemd`, Nginx, Runtime-/Legacy-
Environment, Dateimetadaten, Service-Zustand und den vorherigen `current`-Verweis begrenzt.
Er enthält keine PostgreSQL-Module, keine SQL-/Alembic-/Restore-Aufrufe, keine HTTP-
Readiness-Abfragen und keine Includes von DB-Tasks. `boundary.sql`, Runtime-Verifikation
und sämtliche read-only PostgreSQL-Preflights bleiben unverändert vor der Aktivierung.

Die Recovery stoppt zuerst betroffene neue App-Prozesse und stellt geänderte Altdateien
mit ihrem vorherigen Inhalt, Besitzer, Gruppe und Modus wieder her. Zuvor nicht existente
verwaltete Konfigurationsdateien werden gezielt entfernt (z. B. die neue `runtime.env`
bei der Erstübernahme); das ist kein allgemeiner Cleanup. Ebenso werden die vorherigen
Rechte der Legacy-Frontend-`.env` und ein gegebenenfalls bereits umgestellter `current`-
Verweis wiederhergestellt. Releases, Logs, Operator-Archiv und geschützte Recovery-
Verzeichnisse bleiben erhalten. Jeder Versuch verwendet einen eigenen Snapshot, auch
bei gleichem Release-SHA; alte Sicherungen werden nicht versehentlich als aktueller Zustand benutzt.

Danach: bei geänderten Units `daemon-reload`, restauriertes Nginx mit `nginx -t` prüfen,
bei Bedarf reloaden und nur vorher laufende betroffene App-Services wieder starten.
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
und manuelle System-Recovery verlangt, ohne weitere Fallbacks. Ungültige restaurierte
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
verwendet ein temporäres Testzertifikat/unprivilegierte Ports, startet keinen Webservice.

Zusätzliche Tests führen echte Ansible-Handler/Blocks/Rescue und Dateioperationen in
temporären Verzeichnissen aus. Nur Host-I/O (systemd, Nginx-Aufruf, HTTP) ist simuliert;
Fehler bei Kandidatenprüfung, Verify/Reload und Healthchecks werden gezielt injiziert.
Sie prüfen Dateiwiederherstellung, frühzeitige Snapshots, Service-/Timer-Zustände und
spätes Setzen von `current`. Rescue-Includes werden rekursiv auf den erlaubten Scope geprüft.

Es gibt weiterhin keinen vollständigen Apply-/Idempotenzlauf auf einem systemd-Abbild des
Produktionshosts. Der freizugebende Dry Run und die tatsächlichen Ziel-Prerequisites
bleiben deshalb notwendige Schritte; lokale Tests ersetzen sie nicht.
