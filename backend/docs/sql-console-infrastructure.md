# Ansible-managed SQL Console database boundary

## Zuständigkeit und Status

Das `uranus-admin` Deployment verwaltet ausschließlich die isolierte SQL-Console-Infrastruktur
(Rollen, `uranus_console`-Schema, explizite Views und minimale Grants).
Es verändert keine Uranus-Domain-Daten oder Uranus-Tabellendefinitionen.
`sndcds/uranus` bleibt die authoritative Quelle für Basistabellen und Quell-DDL.
Admin-Alembic, API und Worker provisionieren keine Console-Infrastruktur.

Ansible provisioniert die SQL-Console-Infrastruktur vollständig. Es ist kein manueller
`psql`-Schritt für diese Rollen, Views, Grants oder die Passwortübernahme erforderlich.
Das setzt einen kompatiblen bestehenden Datenbankkatalog voraus: **gemeinsame PUBLIC-
Rechte werden nicht verändert**. Bei einem Blocker wird ohne Provisionierung und ohne
App-Aktivierung abgebrochen. Ein isoliertes Testsystem ist kein Produktionsnachweis.

Phase 3 mit frei eingegebenem SQL bleibt unimplementiert: kein `/sql`, Editor, WSS,
Executor, Streaming oder Cancel. Phase 4 Write Mode ist außerhalb dieses PRs.

Erneut gegen das Repository geprüft am 20.09.2026:

- Admin-Basis: `e7a48b30bcbd1ddd6629c43474edd93b40a9ecfa`.
- Frisch abgerufenes `sndcds/uranus/main`:
  [`7ae87ea7fe39692c1f3dcc3a5621f6c9e7bb574d`](https://github.com/sndcds/uranus/tree/7ae87ea7fe39692c1f3dcc3a5621f6c9e7bb574d/ddl).
  Der bestehende Audit umfasst 72 DDL-Dateien; die vier Projektionen und fünf
  ausgeschlossenen Secretspalten wurden erneut gegen diesen Stand geprüft.
- Keine Produktionsverbindung und keine Quellwerte gelesen.

Der maschinenlesbare [Contract v1](../../ansible/roles/uranus_admin/files/sql_console_contract.json)
enthält Quellcommit, SHA256 der vier geprüften DDL-Dateien, Spaltenreihenfolge,
PostgreSQL-Typen, Basistabellen, Owner-Spaltengrants, Reader-Grants und Search Path.
Ansible und Tests verwenden dieselbe Datei. Die Dateihashes dokumentieren den
Repository-Audit; der Live-Preflight vergleicht Katalogtypen, nicht einen behaupteten
Produktions-Git-SHA. Neue Basisspalten erweitern den Vertrag niemals automatisch.

## Threat Model und Ursache des ersten Security-Stops

Ein angemeldeter Systemadmin darf künftig SQL verändern. Deshalb dürfen auch
unerwartete SELECT-Ausdrücke, Aliase, Subqueries, Ganzzeilen-JSON und später
hinzugefügte Quellspalten keine geheimen Werte zugänglich machen. Die Grenze muss
auch ohne App-Parser und ohne Ergebnisnamenfilter gelten.

Der bestehende `uranus_reader` erhält laut Provisionierungsvertrag tabellenweites
SELECT, unter anderem auf `organization`, `user` und `organization_member_link`.
Die [Deployment-Prüfung](../../ansible/roles/uranus_admin/files/boundary.sql)
verlangt dieses Tabellenrecht für die benötigten Quelltabellen. Heute schützen
zusätzlich feste [Recipe-Projektionen](../app/sql_diagnostics/registry.py) und
deren [Executor-Prüfung](../app/sql_diagnostics/executor.py) vor Secret-Ausgabe.
Diese bestehende Rolle wird nicht zu einer freien Console-Rolle umfunktioniert.

Ein READ-ONLY-Snapshot verhindert keine bereits erlaubten Lesezugriffe. Tabellen-
und Spaltenrechte sind additiv; ein Spaltenentzug beseitigt kein vorhandenes
Tabellenrecht. Ebenso summieren sich direkte, geerbte und PUBLIC-Rechte.
[PostgreSQL: GRANT](https://www.postgresql.org/docs/17/sql-grant.html).

## Quell-Audit: Ausschlüsse und semantische Bewertung

Die Namenssuche nach `token`, `secret`, `password`, `credential` und `key` wurde
über die 72 DDL-Dateien ergänzt um eine Prüfung der betroffenen Tabellen sowie
der Text-, URL- und JSON-Projektionen. Es wurden keine Produktionswerte gelesen.

| Quellbereich                                                                                                                                                             | Bewertung für den Console-Vertrag                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `organization.api_import_token`                                                                                                                                          | Secret, ausgeschlossen.                                                                                                                                                             |
| `user.password_hash`, `user.activate_token`                                                                                                                              | Auth-Geheimnisse, ausgeschlossen; zunächst keine User-Projektion.                                                                                                                   |
| `organization_member_link.accept_token`                                                                                                                                  | Einladungssecret, ausgeschlossen. Ein Präsenzboolean der registrierten Diagnose ist keine Freigabe des Werts.                                                                       |
| `password_reset.token`                                                                                                                                                   | Secret; ganze Tabelle ausschließen. Der tatsächliche DDL-Spaltenname ist `token`, nicht `password_reset_token`.                                                                     |
| `refresh_token`                                                                                                                                                          | Laut DDL Session-/Revocation-Metadaten mit `jti` und `family_uuid`, **kein gespeicherter Tokensecretwert**. Trotzdem keine Console-Freigabe dieser Auth-Tabelle.                    |
| `license.key`, `link_type.key`, weitere Vokabular-`key`-Spalten                                                                                                          | Fachliche Schlüssel, nicht allein aufgrund des Namens Geheimnisse. Eine Freigabe benötigt trotzdem einen expliziten Projektionsvertrag.                                             |
| `pluto_cache.receipt`                                                                                                                                                    | Semantik einer potenziellen Zugriffsinformation nicht durch DDL geklärt; ausschließen, nicht als harmlosen Beleg erklären.                                                          |
| URLs: etwa `event.source_link`, `online_link`, `ticket_link`, `registration_link`, `event_date.ticket_link`, `venue.web_link`, `organization.web_link`, `event_link.url` | Können Zugangsdaten, private Einladungslinks oder eingebettete Tokens enthalten. Initial vollständig ausschließen; Namenfilter oder Entfernen nur der Query-Parameter genügt nicht. |
| Freitext: etwa `title`, `name`, `description`, `custom`, `style`, `search_text`, Nachrichten, `social_post_destination.error`                                            | Ein unbeschränktes Textfeld kann hineinkopierte Geheimnisse enthalten. Für die erste minimale Projektion ausschließen; DDL allein beweist keine bereinigten Inhalte.                |
| JSON: `organization.notifications`, `member_of_orgs`, `pluto_image.exif`, Portal-Konfigurationen, `display_preset.options`                                               | Keine ungeprüfte Ganzobjektfreigabe. Initial ausschließen; spätere Einzelwerte benötigen einen geprüften Inhaltsvertrag.                                                            |
| Vorhandene `event_projection` / `event_date_projection`                                                                                                                  | Die DDL beschreibt Projektionstabellen mit weiteren Text-/URL-/JSON-Inhalten; sie sind keine automatisch sicheren Console-Views.                                                    |
| Admin-Auth, Session-Digests, SMTP-/DB-Credentials                                                                                                                        | Vollständig außerhalb der Console-Freigabe. Aus fehlenden entsprechenden Spalten im Uranus-DDL folgt keine globale Abwesenheit solcher Geheimnisse.                                 |

## Verwalteter Vertrag

`uranus_console_owner`: NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE,
NOREPLICATION, NOBYPASSRLS, NOINHERIT bei Neuanlage. Ausschließlich Owner des
Console-Schemas und seiner Views; USAGE auf `uranus`, SELECT auf den unten
aufgeführten Basisspalten. Kein Tabellen-SELECT, DML oder CREATE auf `uranus`.
Owner-Rechte auf den eigenen Console-Objekten enthalten naturgemäß deren
Verwaltung; sie verleihen keine Quellschreibrechte.

`uranus_console_reader`: LOGIN, dieselben negativen privilegierten Attribute und
NOINHERIT bei Neuanlage. CONNECT auf der ausgewählten DB, USAGE auf `uranus_console`,
SELECT auf genau vier Views. Kein CREATE/TEMP, kein Zugriff auf `uranus`/`admin`,
keine Basistabellen-/Spalten-/Sequenzrechte, Memberships oder Grant Options.
`rolinherit` allein ist ohne Membership kein Rechtezuwachs. Memberships werden
in beiden Richtungen abgewiesen. Der Reader ist niemals Objekt-Owner.

| Verwaltete View               | Explizite Basisspalten                                                                                                                  |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `uranus_console.event_date`   | `uuid`, `event_uuid`, `venue_uuid`, `space_uuid`, `release_status`, `start_date`, `start_time`, `end_date`, `end_time`, `all_day`       |
| `uranus_console.event`        | `uuid`, `org_uuid`, `venue_uuid`, `space_uuid`, `created_at`, `modified_at`, `release_date`, `release_status`, `min_price`, `max_price` |
| `uranus_console.venue`        | `uuid`, `org_uuid`, `created_at`, `modified_at`, `opened_at`, `closed_at`                                                               |
| `uranus_console.organization` | `uuid`, `created_at`, `modified_at`, `holding_org_uuid`, `nonprofit`                                                                    |

Diese Liste ist zugleich die exakte Owner-SELECT-Spaltenliste pro Basistabelle.
Die Views enthalten keine Ausdrücke, Casts, Funktionen, Sternprojektionen oder
ungeprüften Text-/URL-/JSON-Felder. Es gibt keine User-View und vorerst auch keine
`organization_member_link`-View; der Owner braucht daher kein `accept_token`-Recht.

Die Typen sind im Contract explizit: UUID, naive Quell-Timestamps, date, time,
boolean, double precision und das vorhandene Enum `uranus.event_release_status`.
Die Enum-I/O muss PostgreSQLs `enum_in`/`enum_out` verwenden. Domains, fremde
Typ-I/O, Quell-Views und RLS auf den vier Basistabellen werden abgewiesen.

**View-Rechtesemantik:** Eine `security_invoker`-View benötigt passende Rechte des
Aufrufers auf den Basistabellen und passt damit nicht zum gewünschten Modell ohne
Basistabellenrechte. Normale PostgreSQL-Views prüfen diese Rechte dagegen beim
View-Owner. Das ist nicht mit einer `SECURITY DEFINER`-Funktion gleichzusetzen.
[PostgreSQL: CREATE VIEW](https://www.postgresql.org/docs/17/sql-createview.html).
Für den View-only-Zugang ist diese begrenzte Owner-Prüfung notwendig:
Der separate NOLOGIN-Owner darf selbst nur die freigegebenen Basisspalten lesen,
keine Geheimnisse und keine Daten schreiben. Er darf kein Superuser oder mächtiger
Quellowner sein. Der Reader darf die Owner-Rolle nicht übernehmen. Keine
SECURITY-DEFINER-Funktion, keine beliebigen SQL-Parameter in privilegierten Helfern.

Views, verschachtelte Views, Regeln, RLS, verwendete Typen/Operatoren und Funktionen
sind Teil des Reviews. `security_barrier` kann bei Zeilenfiltern sinnvoll sein,
ersetzt aber weder die Spaltenprojektion noch die Prüfung der Abhängigkeiten.
Festgelegt ist `search_path=pg_catalog,uranus_console` mit schemaqualifizierten
Console-Abfragen. `uranus`, `public` und `$user` gehören nicht in diesen Pfad;
der Pfad allein verbietet aber keine schemaqualifizierten Zugriffe.

## Plan, Apply und unabhängige Verifikation

Die drei eigenen Taskbereiche sind
[sql_console_plan.yml](../../ansible/roles/uranus_admin/tasks/sql_console_plan.yml),
[sql_console_provision.yml](../../ansible/roles/uranus_admin/tasks/sql_console_provision.yml)
und [sql_console_verify.yml](../../ansible/roles/uranus_admin/tasks/sql_console_verify.yml).
Der begrenzte [Ansible-Modulcode](../../ansible/roles/uranus_admin/library/uranus_sql_console.py)
verbindet ausschließlich lokal als `postgres` nach `oklab`. Er besitzt keine
beliebige SQL-, Rollen-, Datenbank- oder Host-Option.

Reihenfolge: Host/System-Preflight einschließlich bestehender Toolchain-Prüfung →
unveränderter READ-ONLY-Source/Admin-Preflight → geschützter Environment-Plan →
Console-Katalogplan → freigegebene Console-Provisionierung → separate READ-ONLY-
Console-Verifikation → Release-Build → tatsächliche Runtime-DSN-Verifikation →
Maintenance ON → App-Aktivierung → Healthchecks → Maintenance OFF gemäß bisheriger
Marker-Erhaltungsregel → Erfolg. Console-Fehler erreichen weder Build noch Maintenance.

Die Capability stammt aus `SQL_CONSOLE_DATABASE_URL` in den Environment-Keys des
SHA256-geprüften Release-Manifests. Das neue optionale Secret-Setting markiert
Unterstützung, ohne einen Executor einzuführen. Ältere Releases benötigen die
Infrastruktur nicht, erhalten keine Console-DSN und löschen vorhandene Objekte nicht.

Die vier bestehenden Apply-Gates (`ua_apply_confirmation`, `ua_reviewed_dry_run`,
`ua_maintenance_window`, `ua_backup_reference`) und Secret-Adoption bleiben gültig.
Zusätzlich benötigt ein unterstützender Release `ua_sql_console_provision_approved: true`.
Inspect und Check Mode planen ohne diese zusätzliche Freigabe; sie provisionieren nichts.

Der Plan und der separate Verifier laufen in echten READ-ONLY/REPEATABLE-READ-
Transaktionen, mit 10 Sekunden Statement- und 2 Sekunden Lock-Timeout. Apply
prüft erneut, serialisiert Console-Applies mit einem Transaktions-Advisory-Lock,
führt ausschließlich eigene DDL/Grants aus und prüft vor Commit erneut.
Die unabhängige Verifikation öffnet anschließend eine neue READ-ONLY-Verbindung.
Parallele manuelle Katalogänderungen sind nicht unterstützt.

Fehlende Rollen, Schema, Views und erlaubte Grants werden angelegt. `pg_get_viewdef`
wird mit den expliziten Projektionen verglichen (beide PostgreSQL-16/17-
Deparserformen, nur Whitespace normalisiert). Definition und View-Optionen werden
mit CREATE OR REPLACE auf den Vertrag zurückgeführt. Falsche Spalten/Typen,
Owner, Zusatzrechte, mächtige Rollen oder Memberships sind harte Blocker, keine
stille Übernahme fremder Infrastruktur. `unexpected_sql_console_object` verhindert
automatisches Löschen fremder Views, Funktionen, Typen oder anderer Schemaobjekte.
Keine Default-Grants für zukünftige Objekte.

Die Katalogprüfung umfasst Rollenattribute, Ownership, effektive PUBLIC-/direkte
Schema-/DB-/Tabellen-/Spalten-/Sequenzrechte einschließlich MAINTAIN ab PG17,
Grant Options, exakte View-Spalten/-Typen/-Definitionen/-Owner und minimale
Owner-Spaltengrants. Die fünf Secretspalten werden zusätzlich mit
`has_column_privilege` geprüft, ohne Werte zu lesen. Effektives CREATE/TEMP wird
mit `has_database_privilege` geprüft. Die echte Runtime-Anmeldung muss `oklab`,
`uranus_console_reader` und exakt `pg_catalog, uranus_console` liefern.

## PUBLIC TEMP und Function-/Extension-Grenze

PostgreSQL-Rechte sind additiv. Ein REVOKE nur vom Reader kann PUBLIC TEMP nicht
aufheben. [PostgreSQL: GRANT](https://www.postgresql.org/docs/17/sql-grant.html).
Ansible liest daher die effektive Datenbank-ACL und berichtet `public_temp` sowie
`temp_login_roles`: alle Loginrollen mit effektivem TEMP, einschließlich Superusern.
Bei PUBLIC TEMP lautet der Blocker
`public_temp_requires_external_review_no_automatic_revoke`. **Kein pauschales
REVOKE FROM PUBLIC, kein versteckter Override und kein Ersatz durch READ ONLY.**

Die bekannte Bestandsaufnahme nennt TEMP für vier App-Rollen, aber keinen
belegten PUBLIC-ACL-Ursprung. Dieser PR liest Production nicht; konkrete betroffene
Anwendungen lassen sich nicht aus Rollennamen allein ableiten. Ein freigegebener
Katalogplan muss diese Zuordnung mit dem Betreiber klären. Scheitert eine sichere
gemeinsame Rechtepolitik, ist eine getrennte Console-Datenbank mit ausschließlich
bereinigten Projektionen und kontrollierten Defaults der isolierte Folgeentwurf.
Das Playbook baut diese Alternative nicht heimlich auf.

Dasselbe Prinzip gilt für gemeinsame Funktions-/Extension-Rechte. Der Vertrag
benötigt keine eigenen Funktionen. Zugängliche SECURITY-DEFINER-Funktionen,
Nicht-Core-Funktionen (auch als STABLE/IMMUTABLE deklarierte), bekannte gefährliche
Core-Datei-/Large-Object-Funktionen, dblink, fremde Extensions, Foreign-Server-
Rechte/User-Mappings, Large-Object-Rechte, Event-Trigger und ungeprüfte Default-ACLs
blockieren. Zusätzliche Systemkatalog-Grants und PUBLIC-Zugriffe auf Passwort-,
Verbindungs- oder Statistikwerte werden ebenfalls abgewiesen. Es werden keine
Funktionsrechte anderer Anwendungen verändert.
`plpgsql` und `postgis` dürfen installiert sein; ihre Installation ist keine
pauschale EXECUTE- oder Tabellenfreigabe für die Console. Insbesondere PostGIS-
PUBLIC-Metadaten/-Funktionen können zusätzliche Blocker auslösen.

Die Tests verwenden eine neue lokale Datenbank mit ausdrücklich isolierten
Fixture-Defaults. Nur dort werden PUBLIC TEMP sowie zusätzliche Tabellen- und
Funktionsrechte entzogen. Tests stellen diese Rechte gezielt wieder her und
prüfen den Abbruch ohne Provisionierung. Diese Fixtures sind kein Deployment-SQL
und keine Bestätigung eines kompatiblen Produktionskatalogs.

Kein Anspruch auf magische Vollständigkeit: Katalog-/PostgreSQL-Funktionen wie
`set_config`, `pg_sleep`, Advisory Locks und intern autorisierte Backend-Signale
sind zusätzlich im späteren AST-/Function-Denylist-Vertrag zu begrenzen, ebenso
Ergebnismengen, Laufzeit und Parallelität. DB Boundary bleibt die primäre
Vertraulichkeits- und Berechtigungsgrenze; Phase 3 bleibt READ ONLY.

## Secrets, Runtime und Recovery

`SQL_CONSOLE_DATABASE_URL` ist ein eigenes Secret in der geschützten bestehenden
`operator.env` (root:root 0600), danach auch in `runtime.env` (root:root 0600).
Eine bereits vorhandene explizite Runtime-DSN wird erhalten und beim geschützten
Secret-Adoptionsschritt zusätzlich im Operator-Archiv gesichert. So bleibt sie auch
bei einem späteren Release ohne Console-Capability verfügbar. Andere archivierte
Werte werden nicht ersetzt; abweichende Console-Werte führen zum Abbruch. Es gibt keine
Credentials im Inventory, Git, `-e` oder Reports. Keine Ableitung aus `DATABASE_URL`
oder `ADMIN_DATABASE_URL`; fehlt die DSN, scheitert die Planung.

Das Passwort muss ein separates, ausreichend langes ASCII-Secret sein (mindestens
24 druckbare Zeichen ohne Leerzeichen; reservierte URL-Zeichen percent-encodieren).
Die neue Rolle erhält einen lokal erzeugten SCRAM-SHA-256-Verifier dieses Passworts.
Bei bestehender Rolle wird der gespeicherte Verifier geschützt verglichen; bei
Abweichung Abbruch statt Rotation. Es gibt keinen bei jedem Deploy neu erzeugten
Zufallsschlüssel. Secret-Tasks sind `no_log`, Diffs unterdrückt; der DB-Schreibschritt
unterdrückt zusätzlich Statement-/Parameter-/Sampling-Logs seiner Transaktion.
Keine Passwörter, DSNs, Verifier oder Driver-Exceptions im Report.

Die Runtime-Prüfung stellt mit dieser eigenen DSN eine begrenzte read-only
Verbindung her und kontrolliert echte Identität, Search Path und CREATE/TEMP.
Frontend erhält keine Console-DSN. `SQL_CONSOLE_ADMIN_DATABASE_URL` bleibt ein
optionaler Folgeauftrag ohne Fallback zu `ADMIN_DATABASE_URL`.

System recovery bleibt systemd/Nginx/runtime-bezogen. Console DB infrastructure
wird nicht destruktiv zurückgerollt. Ein späterer Aktivierungsfehler führt nicht
zu DROP VIEW/ROLE/SCHEMA; erfolgreich provisionierte Infrastruktur bleibt sicher
und idempotent bestehen. Ein Fehler innerhalb der Provisionierung verwirft deren
noch unbestätigte Transaktion; das ist kein nachträglicher Deployment-DB-Rollback.

## Tests und Phase-3-Freigabekriterien

[Console-Tests](../../ansible/tests/test_sql_console.py) verwenden denselben
Contract und denselben Provisionierer auf PostgreSQL 16/PostGIS 3.4 und PostgreSQL
17/PostGIS 3.5 in der bestehenden CI-Matrix. Nur lokale Wegwerfcontainer,
synthetische Daten und abgesicherte `*_test`-Datenbanken sind erlaubt.

Getestet werden echte READ-ONLY-Planung, Ansible `--check --diff` ohne Änderung,
separate Approval-Sperre, erster Apply, zweiter Apply `changed=0`, erfolgreiche
Anmeldung und exakter Search Path. Direkter Secretzugriff, Alias, Ausdruck,
`to_jsonb`, CTE/Subquery, Writes, CREATE/TEMP und Rollenwechsel müssen mit `42501`
scheitern; sichere Views liefern genau ihre Spalten. Weitere Fälle: neue
Basisspalte, View-Drift/Reconcile, mächtige Attribute, Memberships, fehlende und
zusätzliche Grants, PUBLIC TEMP, Funktionen/Extensions, Sequenzen/Large Objects,
fremde Console-Objekte ohne Löschung, fehlende DSN ohne Fallback und alte Releases.

Vor Phase 3 müssen diese Gates bestehen und zusätzlich ein autorisierter
Produktions-Preflight mit Datum, Contract-Version, PostgreSQL-/Extension-Versionen
und Ergebnisreferenz vorliegen. Dieser PR enthält keine Deployment-Freigabe,
keinen Produktionsnachweis und keine Anwendung für frei eingegebenes SQL.
