# Ansible-managed SQL Console database boundary

## Zuständigkeit und Status

Das `uranus-admin` Deployment verwaltet ausschließlich die isolierte SQL-Console-Infrastruktur
(Rollen, `uranus_console`-Schema, explizite Views und minimale Grants).
Es verändert keine Uranus-Domain-Daten oder Uranus-Tabellendefinitionen.
`sndcds/uranus` bleibt die authoritative Quelle für Basistabellen und Quell-DDL.
Admin-Alembic, API und Worker provisionieren keine Console-Infrastruktur.

Ansible provisioniert die SQL-Console-Infrastruktur vollständig. Es ist kein manueller
`psql`-Schritt für diese Rollen, Views, Grants oder die Passwortübernahme erforderlich.
Das setzt einen kompatiblen bestehenden Datenbankkatalog voraus: **PUBLIC TEMP wird
nur unter dem versionierten Allowlist-Vertrag reconciled; andere gemeinsame Rechte
werden nicht verändert**. Bei einem Blocker wird ohne Provisionierung und ohne
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

Der maschinenlesbare [Contract v3](../../ansible/roles/uranus_admin/files/sql_console_contract.json)
enthält Quellcommit, SHA256 der vier geprüften DDL-Dateien, Spaltenreihenfolge,
PostgreSQL-Typen, Basistabellen, Owner-Spaltengrants, Reader-Grants, Search Path und
die Allowlist für explizite Datenbank-TEMP-Grants.
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
NOREPLICATION, NOBYPASSRLS, NOINHERIT. Ausschließlich Owner des
Console-Schemas und seiner Views; USAGE auf `uranus`, SELECT auf den unten
aufgeführten Basisspalten. Kein Tabellen-SELECT, DML oder CREATE auf `uranus`.
Owner-Rechte auf den eigenen Console-Objekten enthalten naturgemäß deren
Verwaltung; sie verleihen keine Quellschreibrechte.

`uranus_console_reader`: LOGIN, dieselben negativen privilegierten Attribute und
NOINHERIT. CONNECT auf der ausgewählten DB, USAGE auf `uranus_console`,
SELECT auf genau vier Views. Kein CREATE/TEMP, kein Zugriff auf `uranus`/`admin`,
keine Basistabellen-/Spalten-/Sequenzrechte, Memberships oder Grant Options.
Auch bestehende Rollen müssen `rolinherit=false` haben; andernfalls
`unsafe_role_inherit:<role>` ohne automatische Reparatur. Memberships werden
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
führt Console-DDL und die Grants/Revoke des versionierten Vertrags aus und prüft
vor Commit erneut.
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
Contract v3 enthält `database_temp_roles` mit genau den vier bestehenden App-Rollen:
`uranus_reader`, `admin_user`, `admin_migrator`, `admin_auth_operator`. Ansible liest
vor jeder Änderung die Datenbank-ACL und prüft zusätzlich die effektiven Rechte mit
`has_database_privilege`. Der geheimnisfreie Plan berichtet `public_temp`, alle
Loginrollen mit effektivem TEMP (`temp_login_roles`) sowie `temp_inventory`:
direkte Grants einschließlich Grant Options, PUBLIC-Verbraucher, transitive
Membership-Pfade mit `pg_has_role(..., 'MEMBER'/'USAGE'/'SET')` und privilegierte Rollen.
Siehe [PostgreSQL: Rechteprüfung](https://www.postgresql.org/docs/17/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE).

Nur wenn alle betroffenen normalen Loginrollen dem versionierten Vertrag entsprechen,
darf Ansible PUBLIC TEMP automatisch reconciliieren. Superuser und der Datenbank-Owner
mit eigener TEMP-ACL sind keine von PUBLIC abhängigen Verbraucher; sie werden separat
inventarisiert und ihre eigenen Rechte bleiben erhalten. Ein nicht privilegierter
Owner ohne eigene TEMP-ACL blockiert, statt unbemerkt TEMP zu verlieren. Bestehende
Console-Rollen sind ausschließlich Entzugsziele; ihre Attribute und Memberships
müssen weiterhin den strengen Console-Vertrag erfüllen.

In derselben abgesicherten Console-Provisionierungstransaktion:

1. Fehlende explizite TEMP-Grants ausschließlich an die vier vorhandenen LOGIN-App-Rollen.
2. `REVOKE TEMPORARY ... FROM PUBLIC` ausschließlich bei bestandenem Katalogplan.
3. Rollen/Views/übrige Console-Grants gemäß bestehendem Vertrag provisionieren.
4. Gesamte Grenze erneut prüfen: PUBLIC TEMP aus, beide Console-Rollen effektiv TEMP-frei,
   alle vier App-Rollen mit explizitem und effektivem TEMP, keine weiteren Änderungen nötig.
5. Erst dann Commit; jeder Fehler davor rollt auch die TEMP-ACL vollständig zurück.

Unbekannte Verbraucher führen zu `unexpected_public_temp_consumer:<role>`, unerlaubte
direkte Grants zu `unexpected_direct_temp_grantee:<role>`. Zusätzliche Grant Options
und sämtliche ungeprüften Membership-Pfade zu bestehenden oder geplanten TEMP-Quellen
blockieren ebenfalls. Das umfasst NOLOGIN-Gruppen und indirekte SET-ROLE-Pfade auch
bei NOINHERIT. Keine automatische Allowlist-Erweiterung, kein stiller Rechteentzug.
Check Mode zeigt `temp_reconcile.allowed`, `would_grant_explicit` und
`would_revoke_public_temp`, verändert aber nichts. Der zweite Apply hat `changed=0`.

Für einen kompatiblen, versionierten Produktionszustand ist kein manueller psql-Schritt
mehr nötig. Dieser PR liest Production nicht und bestätigt deshalb keinen konkreten
Produktionskatalog.

Der versionierte Function-/Extension-Vertrag in Contract v3 ersetzt den pauschalen
Nicht-Core-/OID-Blocker. `function_policy` Version 1 bindet die Freigabe an die beiden
gepinnten CI-Images, PostgreSQL-Major, konkrete Extension-Version und reproduzierbare
SHA-256-Katalog-Fingerprints. Aktuell geprüft sind PostgreSQL 16/PostGIS **3.4.3** und
PostgreSQL 17/PostGIS **3.5.2**, jeweils mit `plpgsql` 1.0. Die zusätzlichen Major-/Minor-
Grenzen erlauben keine automatische Freigabe neuer Patchstände: neue Versionen oder
abweichende Kataloge benötigen einen überprüften Contract-Commit. Dies ist keine
Aussage über die Kompatibilität eines ungeprüften Produktionskatalogs.

Der Fingerprint umfasst die genaue Funktionsmenge mit schemaqualifizierten Signaturen,
Argumenten, Definitionen, Sicherheitsattributen, Sprache, C-Bibliothek und
Extension-Zugehörigkeit über `pg_depend`/`pg_extension`; Aggregate einschließlich ihrer
Implementierungsabhängigkeiten. OIDs und ACLs gehören nicht zum Fingerprint. Ownership
und ACLs werden separat geprüft: Extension- und Funktionsowner müssen privilegierte
Installationsrollen sein, dürfen niemals Console-Rollen sein, und Extension-Funktionen
müssen ihrem Extension-Owner gehören. Der alte Test `oid >= 16384` entfällt vollständig.

Zwei Klassen:

- **A:** geprüfter Core sowie konkret fingerprintgebundene PostGIS-Funktionen mit
  IMMUTABLE/STABLE, erwarteter Extension, Schema `public`, überprüfter Sprache und
  bei C-Funktionen `$libdir/postgis-3`. Kein SECURITY DEFINER und kein Treffer der
  zusätzlichen Namens-/Pfad-Denylist. PUBLIC EXECUTE bleibt hier unverändert.
  Die drei exakt geprüften `plpgsql`-Sprachhandler bilden einen eigenen Contract;
  dies ist keine allgemeine Freigabe für VOLATILE-Funktionen.
- **B:** alle geprüften PostGIS-VOLATILE-Funktionen einschließlich DDL-/Upgrade-Helfern,
  zusätzlich `ST_EstimatedExtent`/`_postgis_index_extent` wegen Statistik-/Indexzugriffen,
  `AddGeometryColumn`, `ST_FromFlatGeobufToTable` und `ST_FindExtent` wegen DDL/dynamischem
  Tabellen-SQL sowie `ST_Transform*`, `ST_InverseTransformPipeline` und deren C-Helfer
  wegen frei steuerbarer PROJ-/Grid-Parameter, sowie die expliziten
  Core-Dateisystem-/Server-/Large-Object-/Session-/Signalling-/Advisory-Lock- und
  Replikationspfade, Statistik-Reset, Konfigurationsdatei- und Indexwartungshelfer. Unter anderem bleiben `set_config`, `pg_sleep*`, `pg_cancel_backend`,
  `pg_terminate_backend`, `lo_*`, `loread`, `lowrite` und Dateifunktionen für beide
  Console-Rollen ohne EXECUTE. Erreichbare SECURITY-DEFINER- oder dblink-Funktionen,
  unbekannte Extensions und unbekannte Nicht-Core-Funktionen bleiben Blocker;
  sie werden niemals allein aufgrund einer Eigenschaft wie STABLE übernommen.
  Auch eine private ACL legitimiert keine unbekannte Implementierung, die etwa über
  Typ-/Operatorabhängigkeiten erreichbar werden könnte.

Die konkreten B-Signaturen, ursprüngliches PUBLIC EXECUTE, Definition-Hashes und
bestehende privilegierte Grantees stehen in `function_policy.catalogs`. Von 777
PostGIS-Funktionen in 3.4.3 sind 95 eingeschränkt (79 VOLATILE plus 16 weitere Signaturen); von 776 in 3.5.2
sind es 86 (70 VOLATILE plus 16).
Die konservativen zusätzlichen Ausschlüsse gelten auch für STABLE/IMMUTABLE:
[ST_FromFlatGeobufToTable](https://postgis.net/docs/ST_FromFlatGeobufToTable.html)
erzeugt Tabellen; [Transform-Pipelines](https://postgis.net/docs/ST_TransformPipeline.html)
nehmen unter anderem Grid-Dateiparameter an. Solche Aufrufe werden nicht allein wegen
der Volatility-Deklaration freigegeben. Der Core-Vertrag enthält 153 beziehungsweise
158 eingeschränkte Signaturen (davon 96 beziehungsweise 101 ursprünglich PUBLIC).
Nur die darin ausdrücklich als ursprünglich PUBLIC ausführbar verzeichneten
Funktionen dürfen automatisch reconciled werden. Vorher nicht öffentliche
Dateifunktionen erhalten keine App-Grants; vorhandene geprüfte `pg_monitor`-Grants
bleiben unverändert. Unerwartetes PUBLIC EXECUTE auf solchen privilegierten Funktionen
führt zu `unexpected_public_execute:<signature>`.

EXECUTE-Reconcile liest dieselben vier App-Rollen über
`preserve_role_contract: database_temp_roles`, ohne zweite hardcodierte Rollenliste.
Vor Änderungen werden direkte ACLs, effektives EXECUTE aller LOGIN-Rollen und beider
Console-Rollen sowie transitive Membership-/SET-ROLE-Pfade inventarisiert. Auch ein
fehlendes Schema-USAGE dient nicht als Ausnahme: Aufrufe über qualifizierte Namen,
Operatoren oder vorhandene Ausdrucksabhängigkeiten dürfen die Grenze nicht umgehen.
Superuser und der Funktionsowner behalten ihre intrinsischen Rechte. Unbekannte
Verbraucher (`unexpected_execute_consumer:<signature>:<role>`), zusätzliche direkte
Grantees, Grant Options und ungeprüfte Membership-Pfade blockieren den gesamten Apply.

Innerhalb derselben abgesicherten Console-Provisionierungstransaktion:

1. Nur bei vollständig bestandenem Plan bestehendes PUBLIC EXECUTE der konkreten
   B-Signatur durch fehlende explizite Grants an die vier App-Rollen erhalten.
2. PUBLIC EXECUTE genau dieser Signatur entziehen; keine Console-EXECUTE-Grants.
3. Den vollständigen Vertrag erneut prüfen: beide Console-Rollen ohne B-EXECUTE,
   bestehende App-/privilegierte Rechte erhalten, keine weiteren Änderungen nötig.
4. Erst dann Commit. Jeder Fehler rollt EXECUTE, TEMP und Console-Objekte gemeinsam
   zurück. Ein erneuter Apply bleibt `changed=0`.

Fehlt PUBLIC EXECUTE bereits, müssen die vertraglichen Erhaltungsgrants schon vorhanden
sein. Andernfalls wird mit `missing_preserved_execute:<signature>` abgebrochen, statt
zuvor entfernte Rechte neu einzuführen. Direkt erteilte Console-Grants werden ebenfalls
abgewiesen, nicht still bereinigt. Keine generelle Shared-Database-Reparatur und keine
Änderung von CONNECT, CREATE, Extensions oder sonstigen PUBLIC-Grants durch diesen
Reconcile. Check Mode zeigt `execute_inventory` und unter `execute_reconcile.changes`
für jede betroffene Signatur die erhaltenen Rollen, fehlenden expliziten Grants und den
geplanten PUBLIC-Entzug. Normale Extension-Berichte nennen Version, Status und Anzahlen,
keine Liste aller erlaubten Funktionen. Blocker nennen konkrete Signaturen; Änderungen
an der geprüften Funktionsmenge/Definition führen zusätzlich zu einem Katalog-Blocker.

Die drei normalen PostGIS-Metadatenobjekte `spatial_ref_sys`, `geometry_columns` und
`geography_columns` dürfen ihr vorhandenes SELECT behalten. Extension-Zugehörigkeit,
Owner, Spalten/Typen, View-Definitionen und Optionen sind ebenfalls fingerprintgebunden;
keine Writes oder Grant Options. Das gibt keine Uranus-/Admin-Datenrechte frei.
`public` wird nicht in den Console-Search-Path aufgenommen: er bleibt
`pg_catalog, uranus_console`. Eine sichere schemaqualifizierte Funktion wie
`public.st_x(public.st_point(1,2))` ist weiterhin ausführbar.

Die Fixture installiert PostGIS unverändert: keine pauschalen Funktions- oder
Tabellen-REVOKEs zur Vorbereitung. Der echte Provisionierer stellt die geprüfte Grenze
her. Nur das Test-Cleanup setzt nach tatsächlich committenden Subprozess-Tests die
gezielt veränderten ACLs auf ihren ursprünglichen Fixture-Zustand zurück.

Für ein reproduzierbares Review erzeugt
[`audit_sql_console_functions.py`](../../ansible/tests/audit_sql_console_functions.py)
einen **Kandidaten**, niemals eine automatische Contract-Aktualisierung. In jedem
gepinnten CI-Image eine neue lokale `*_test`-Datenbank FROM `template0` anlegen und nur
PostGIS installieren; dann mit expliziter synthetischer Test-URL aus dem Repository:

```sh
uv run --no-project --python 3.13 \
  --with-requirements ansible/requirements-test.txt \
  python ansible/tests/audit_sql_console_functions.py
```

Das Skript verlangt `ANSIBLE_TEST_DATABASE_URL`, lokalen Host, Test-Datenbanknamen,
keine Anwendungsschemas und ausschließlich `plpgsql`/`postgis`. Es liest ausschließlich
Kataloge in READ ONLY; Funktionsdefinitionen werden serverseitig gehasht, nicht geloggt.
Ein neuer Kandidat benötigt Signatur-/Definitions-/Quellenreview und Tests, bevor seine
Freigaben in den versionierten Contract übernommen werden.

FDW-/Foreign-Server-/User-Mapping-Pfade, Large-Object-Rechte, Event-Trigger, ungeprüfte
Default-ACLs, zusätzliche Systemkatalog-Grants und Zugriffe auf Passwort-, Verbindungs-
oder Statistikwerte bleiben abgewiesen. Die DB Boundary ist die primäre Rechte- und
Vertraulichkeitsgrenze, kein Anspruch auf vollständige Verhinderung jedes Seiteneffekts.
Phase 3 bleibt getrennt und READ ONLY; sie benötigt zusätzlich AST-Validierung,
Function-Denylist, Ressourcen-/Timeout-/Zeilen-/Parallelitätsgrenzen. Dieser PR fügt
keinen freien SQL-Executor hinzu.

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
zusätzliche Grants, unbekannte TEMP-Verbraucher, INHERIT-Rollen, Funktionen/Extensions, Sequenzen/Large Objects,
fremde Console-Objekte ohne Löschung, fehlende DSN ohne Fallback und alte Releases.

Vor Phase 3 müssen diese Gates bestehen und zusätzlich ein autorisierter
Produktions-Preflight mit Datum, Contract-Version, PostgreSQL-/Extension-Versionen
und Ergebnisreferenz vorliegen. Dieser PR enthält keine Deployment-Freigabe,
keinen Produktionsnachweis und keine Anwendung für frei eingegebenes SQL.
