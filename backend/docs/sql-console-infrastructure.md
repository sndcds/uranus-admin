# SQL Console: Übergabe der Datenbankgrenze an den Uranus-Betreiber

## Status und Zuständigkeit

**Implementierungsstopp an der Repository-Grenze.** Dieser PR dokumentiert die
Infrastruktur-Voraussetzungen; er provisioniert keine Console-Rolle, Views oder
Grants und behauptet keine nachgewiesene neue PostgreSQL-Sicherheitsgrenze.
Phase 3 mit freiem SQL, WebSocket, Editor und Executor bleibt unimplementiert.

Geprüft am 20.09.2026:

- `uranus-admin/main`: `e7a48b30bcbd1ddd6629c43474edd93b40a9ecfa`.
- [Uranus-Quell-DDL](https://github.com/sndcds/uranus/tree/7ae87ea7fe39692c1f3dcc3a5621f6c9e7bb574d/ddl):
  alle 72 DDL-Dateien aus `sndcds/uranus/main` bei
  `7ae87ea7fe39692c1f3dcc3a5621f6c9e7bb574d`, ausschließlich Repository-Inhalte.
- Keine Produktionsverbindung, kein Auslesen von Datensätzen oder Secretwerten.
  Repository-DDL ist kein Nachweis des aktuellen Produktionskatalogs.

Die im Auftrag genannte Eingangsdatei
`backend/docs/sql-console-phase-3-infrastructure.md` existiert weder auf dieser
Admin-Basis noch in der verfügbaren lokalen Git-Historie. Die tatsächlichen
Grundlagen sind die [SQL-Diagnostics](sql-diagnostics.md), der
[Quellvertrag](../app/source_contract.py) und die unten genannten Betriebsverträge.

Der Auftrag verlangt bei externer Source-Infrastruktur ausdrücklich einen Stopp
mit dokumentierter Übergabe. Die Prüfung ergibt:

| Verantwortung                                                | Nachweis und Übergabe                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Uranus-Tabellen und sourceabhängige Projektionen             | Repository **[sndcds/uranus](https://github.com/sndcds/uranus/tree/7ae87ea7fe39692c1f3dcc3a5621f6c9e7bb574d)**, insbesondere `ddl/` und der dortige `migrations/`-Vertrag. Der Uranus-Maintainer muss die versionierten Projektionen und deren Ownership verantworten.                                                                                  |
| Produktionsrollen, Rechte und gemeinsame PostgreSQL-Defaults | **Uranus-/PostgreSQL-Datenbankbetreiber**. Der [dokumentierte Betriebsstand](../../ansible/README.md) nennt `oklab` als Owner des Schemas `uranus`. Rollenanlage und Änderungen an gemeinsamen Rechten benötigen zusätzlich einen dafür berechtigten DB-Operator. Dies ist keine Freigabe, `oklab` oder einen Superuser als Console-Login zu verwenden. |
| Admin-Anwendungsdeployment                                   | Dieses Repository: [Ansible](../../ansible/README.md) hat ausschließlich lesende PostgreSQL-Tasks. [boundary.sql](../../ansible/roles/uranus_admin/files/boundary.sql) prüft vorhandene Rechte; der [Regressionstest](../../ansible/tests/test_deployment.py) schützt den lesenden Taskumfang. Es gibt keinen bestehenden Console-Provisionierungsweg.  |
| Spätere Einbindung des freigegebenen Vertrags                | `uranus-admin`: dedizierte DSN, Katalog-Preflight und Tests erst auf Grundlage des vom Uranus-Betreiber gelieferten Vertrags. Keine Ersatz-Provisionierung in Admin-Alembic oder im normalen Deployment.                                                                                                                                                |

Die [manuellen Provisionierungsbeispiele](development.md) für bestehende Rollen
sind Betreiberanweisungen, kein bereits autorisierter Console-Provisionierungsweg.
Im geprüften Uranus-Tree wurde kein `CODEOWNERS` und kein eigenes Ansible-/Console-
Provisionierungspaket gefunden. Ein Personenname oder zusätzliches Infrastruktur-
Repository lässt sich daraus nicht verifizieren. Der Uranus-Betreiber muss seinen
konkreten Ausführungsweg benennen; dieser PR erfindet ihn nicht und ändert das
andere Repository nicht.

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

## Architekturvorschlag für den zuständigen Betreiber

**Vorgeschlagen, nicht provisioniert:** ein separates Schema `uranus_console`,
eine Loginrolle `uranus_console_reader` und ein eng berechtigter
NOLOGIN-View-Owner, beispielsweise `uranus_console_owner`. Der bisherige
`uranus_reader` bleibt für kontrollierte interne Queries bestehen.

Der Reader erhält ausschließlich CONNECT, USAGE auf dem Console-Schema und SELECT
auf exakt freigegebenen Views. Kein Basistabellen-SELECT, keine Spaltengrants auf
Basistabellen, kein Zugriff auf `admin`, keine Ownership, Grant Options oder
Memberships. NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS;
kein CREATE, TEMP, Sequence- oder Large-Object-Recht. Ein SELECT-only-View-Grant
muss auch automatisch aktualisierbare Views gegen DML absichern.

Folgende Spalten sind ein **minimaler Vorschlag für das Owner-Review**, keine
bereits freigegebene oder getestete View-Registry. Alle existieren in der geprüften
Quell-DDL; Namen, Titel, URLs, JSON und sonstiger Freitext fehlen absichtlich:

| Vorgeschlagene View           | Explizite Basisspalten                                                                                                                  |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `uranus_console.event_date`   | `uuid`, `event_uuid`, `venue_uuid`, `space_uuid`, `release_status`, `start_date`, `start_time`, `end_date`, `end_time`, `all_day`       |
| `uranus_console.event`        | `uuid`, `org_uuid`, `venue_uuid`, `space_uuid`, `created_at`, `modified_at`, `release_date`, `release_status`, `min_price`, `max_price` |
| `uranus_console.venue`        | `uuid`, `org_uuid`, `created_at`, `modified_at`, `opened_at`, `closed_at`                                                               |
| `uranus_console.organization` | `uuid`, `created_at`, `modified_at`, `holding_org_uuid`, `nonprofit`                                                                    |

View-Definitionen müssen jede Spalte auflisten, ohne `SELECT *`, Ganzzeilen-Casts
oder dynamische SQL-Funktionen. Neue Basisspalten werden dadurch nicht automatisch
freigegeben. Nach finalem Review ist dieser Vertrag mit Datentypen, Abhängigkeiten,
Definitionen und Versionskennung im Owner-Repository einzufrieren.

**View-Rechtesemantik:** Eine `security_invoker`-View benötigt passende Rechte des
Aufrufers auf den Basistabellen und passt damit nicht zum gewünschten Modell ohne
Basistabellenrechte. Normale PostgreSQL-Views prüfen diese Rechte dagegen beim
View-Owner. Das ist nicht mit einer `SECURITY DEFINER`-Funktion gleichzusetzen.
[PostgreSQL: CREATE VIEW](https://www.postgresql.org/docs/17/sql-createview.html).
Für den vorgeschlagenen View-only-Zugang ist diese begrenzte Owner-Prüfung notwendig:
Der separate NOLOGIN-Owner darf selbst nur die freigegebenen Basisspalten lesen,
keine Geheimnisse und keine Daten schreiben. Er darf kein Superuser oder mächtiger
Quellowner sein. Der Reader darf die Owner-Rolle nicht übernehmen. Keine
SECURITY-DEFINER-Funktion, keine beliebigen SQL-Parameter in privilegierten Helfern.

Views, verschachtelte Views, Regeln, RLS, verwendete Typen/Operatoren und Funktionen
sind Teil des Reviews. `security_barrier` kann bei Zeilenfiltern sinnvoll sein,
ersetzt aber weder die Spaltenprojektion noch die Prüfung der Abhängigkeiten.
Geplant ist `search_path=pg_catalog,uranus_console` mit schemaqualifizierten
Console-Abfragen. `uranus`, `public` und `$user` gehören nicht in diesen Pfad;
der Pfad allein verbietet aber keine schemaqualifizierten Zugriffe.

## Function-/Extension-Audit und PUBLIC-Blocker

Die Repository-DDL ist kein vollständiger Produktions-Funktions-/ACL-Katalog.
Der aktuelle Preflight prüft zugängliche SECURITY-DEFINER-Funktionen, beweist aber
keine vollständige Console-Funktionsgrenze. Der Betreiber muss alle Überladungen,
direkten/geerbten/PUBLIC-Rechte, Schemazugänge, Funktionsabhängigkeiten und
Extension-/FDW-Zugriffe rein anhand von Katalogen prüfen.

Mindestens zu bewerten: `pg_read_file`, `pg_read_binary_file`, `pg_ls_dir`,
`pg_stat_file`, `pg_sleep` und Varianten, `pg_terminate_backend`,
`pg_cancel_backend`, `set_config`, `lo_import`, `lo_export`, weitere Large-Object-
Operationen, `dblink*`, Foreign Server/User Mappings, serverseitige Datei-/Programm-
Zugriffe sowie Extensions mit externen Seiteneffekten. Ein EXECUTE-Grant und eine
zusätzliche interne Privilegienprüfung sind unterschiedliche Grenzen; beide sind
zu dokumentieren. Keine pauschale Aussage, jede installierte Funktion sei nutzbar.

PostgreSQL vergibt standardmäßig unter anderem TEMP auf Datenbanken und EXECUTE
auf Funktionen an PUBLIC. Ein REVOKE nur von `uranus_console_reader` entfernt
diese Rechte **nicht**. [PostgreSQL: Privileges](https://www.postgresql.org/docs/17/ddl-priv.html).
Der dokumentierte Admin-Betriebsstand nennt bestehende TEMP-Rechte bereits explizit.
Es gibt keinen rollenbezogenen negativen Grant als Abzug von PUBLIC.

Deshalb muss der Datenbankbetreiber eine gemeinsame Rechteänderung mit vollständiger
Bestandsaufnahme und Erhalt der nötigen Rechte anderer Anwendungen genehmigen,
oder eine getrennte Console-Datenbank mit ausschließlich bereinigten Projektionen
und kontrollierten Defaults vorsehen. Eine getrennte Datenbank wird hier ebenfalls
nicht aufgebaut. **Keine pauschalen Produktions-REVOKEs, kein stilles Akzeptieren
gefährlicher effektiver Rechte und keine vorgetäuschte Isolation durch search_path.**

## Console-DSNs und Admin-Datasource

`SQL_CONSOLE_DATABASE_URL` bleibt ein geplanter separater Secret-Eingang;
`SQL_CONSOLE_ADMIN_DATABASE_URL` ist ein späterer optionaler Vertrag. Dieser
Dokumentations-PR fügt keine Settings, Engines oder DSN-Fallbacks hinzu.

Für die spätere Implementierung gilt: fehlende oder unsichere Console-DSN bedeutet
Datasource unavailable. Niemals auf `DATABASE_URL`, `ADMIN_DATABASE_URL`,
Migrator- oder Operator-Credentials zurückfallen. Die Identität und effektiven
Rechte der tatsächlich verbundenen Rolle müssen geprüft werden.

Eine Admin-Console-Rolle bleibt ein separater Follow-up. Auch Findings, Notizen,
Evidenz und Audit-Inhalte können freie Texte enthalten und brauchen explizite
Projektionen. `admin_user` ist keine zulässige Console-Rolle.

## Katalog-Preflight: erforderlicher Vertrag, noch kein Prüfprogramm

Erst nach dem versionierten Owner-Vertrag kann ein Preflight dessen konkrete
Views und Abhängigkeiten verlässlich prüfen. Ein jetzt erfundener Sollzustand
wäre kein Nachweis der produktiven Grenze. Der spätere Preflight muss bei jeder
Unsicherheit abbrechen und ausschließlich gebundene Katalog-/Privilege-Abfragen
in einer begrenzten READ-ONLY-Transaktion verwenden:

1. Verbundene Console-Identität, erwartete Datenbank, Rollenattribute,
   Memberships einschließlich möglicher Rollenwechsel und Ownership prüfen.
2. Effektives CONNECT/USAGE/SELECT und das Fehlen von CREATE/TEMP, DML, MAINTAIN,
   Sequenz-, Large-Object- und Grant-Option-Rechten einschließlich PUBLIC prüfen.
3. Mit `has_table_privilege`, `has_any_column_privilege` und
   `has_column_privilege` jeglichen unerlaubten Basiszugriff erkennen; explizit
   auch die ausgeschlossenen Secretspalten prüfen, ohne deren Werte zu lesen.
4. View-Objekttyp, Owner, exakte Spalten/Typen, Definition und Abhängigkeiten gegen
   den freigegebenen Vertrag vergleichen. Ein harmloser Alias kann einen Secret-
   Ausdruck verstecken; ein Spaltennamenvergleich allein ist nicht ausreichend.
5. View-Owner ebenfalls auf minimale Basisrechte prüfen; Rules, RLS, Funktionen,
   Operatoren, Extensions, FDWs und Default-ACLs in die Kontrolle einbeziehen.
6. Fehlende Objekte, unvollständige Katalogsicht oder unbekannte Abhängigkeiten
   als unavailable behandeln. Keine automatische Reparatur oder Grants.

Lesbarkeit der freigegebenen Views wird im Produktions-Preflight anhand der
Privilegien geprüft; tatsächliche Ergebnisabfragen und Angriffe bleiben Teil
der synthetischen Testdatenbank. Keine Secretabfragen in Production, auch nicht
mit LIMIT oder unter dem Vorwand eines Smoke-Tests.

## Tests und Freigabekriterien

**Neue Boundary-Tests: noch nicht implementiert oder bestanden.** Wegen des
Ownership-Stopps gibt es hier keine Ersatz-Testfixture, die als implementierter
Source-Vertrag ausgegeben wird. Im Owner-Change müssen automatische Tests auf
einer frischen, wegwerfbaren lokalen `*_test`-Datenbank den tatsächlichen
Provisionierungsvertrag anwenden. Ausschließlich synthetische Daten verwenden.

| Test mit umgangenem App-Validator                                          | Erforderliches PostgreSQL-Ergebnis                                                    |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Freigegebene Projektion, einschließlich `SELECT *` auf einer sicheren View | Erfolg; nur die explizit freigegebenen Felder.                                        |
| Direkter `accept_token`-/`password_hash`-Zugriff                           | `insufficient_privilege` / SQLSTATE `42501`.                                          |
| Secret unter Alias `harmless`                                              | Ebenfalls `42501`.                                                                    |
| Ausdruck wie `upper(accept_token)`                                         | Ebenfalls `42501`.                                                                    |
| `to_jsonb(t)` auf sensibler Basistabelle                                   | Ebenfalls `42501`; JSON einer sicheren View enthält keine Secrets.                    |
| Secret in Subquery oder CTE                                                | Ebenfalls `42501`.                                                                    |
| INSERT, UPDATE, DELETE, CREATE TABLE, temporäres CREATE                    | Abweisung bereits durch effektive Rollenrechte, zusätzlich READ-ONLY-Snapshot testen. |
| SET ROLE zu Reader-, Owner-, Admin- oder anderen mächtigeren Rollen        | `42501`.                                                                              |
| Gefährliche Funktion, Extension oder manipulierte View                     | Kein Zugriff/keine Seiteneffekte; Preflight lehnt unerwartete Fähigkeiten ab.         |
| Neue Basisspalte, PUBLIC-Grant, Membership oder View-Drift                 | Keine automatische Freigabe; Preflight meldet den Vertragsbruch.                      |
| Fehlende Console-DSN bei gleichzeitig gesetzten Runtime-DSNs               | Keine Verbindung zu einem Runtime-Zugang; unavailable.                                |

Der lokale Vorversuch mit der **alten** dokumentierten Reader-Berechtigung hat
bereits gezeigt, dass direkter Tokenvergleich, Alias und Ganzzeilen-JSON in einer
READ-ONLY-Transaktion möglich sind. Er lief ausschließlich mit synthetischen Daten
in einem temporären PostgreSQL-17.10-Cluster. Das ist ein Nachweis des Problems,
**kein** erfolgreicher Test der vorgeschlagenen neuen Grenze.

Phase 3 bleibt gesperrt, bis der Betreiber den Source-/Rollenvertrag versioniert
hat, die obigen automatisierten Angriffs- und Regressionstests bestehen und ein
autorisierter Produktions-Katalogaudit mit Datum, Vertragsversion, PostgreSQL-/
Extension-Versionen und Ergebnisreferenz vorliegt. Dieser PR enthält weder diesen
Produktionsnachweis noch eine Deployment-Freigabe.
