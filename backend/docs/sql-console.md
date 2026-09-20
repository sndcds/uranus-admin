# SQL Console Phase 3: Infrastruktur-Voraussetzung

## Status: Implementierung vor dem freien Executor gestoppt

Geprüfte Basis: `main` bei `e7a48b30bcbd1ddd6629c43474edd93b40a9ecfa`,
frisch abgerufen am 20.09.2026. Dieses Dokument ist der Infrastruktur-Follow-up
zur angeforderten interaktiven READ-ONLY-Konsole, **keine implementierte oder
deployte Phase 3**. Es wurden keine produktiven Datenbankrechte geprüft oder geändert.

Die Aufgabenbeschreibung verlangt ausdrücklich einen Stopp, wenn ein sicherer
freier Executor zusätzliche Produktionsrechte oder eine neue Datenbankrolle
voraussetzt. Die dokumentierte bestehende Reader-Konfiguration schützt geheime
Quellspalten nicht vor frei eingegebenen SELECT-Abfragen. Deshalb wird mit dieser
Konfiguration kein freier Executor eingeführt. Das Mockup bleibt die visuelle
Vorgabe für die spätere Umsetzung nach Abschluss dieses Follow-ups.

Phase 1 und Phase 2 bleiben bei registrierten Queries. Es gibt durch diesen PR
keine neue `/sql`-Seite, keinen WebSocket-Endpunkt, keine Editor-Dependency,
keine Migration und keine Rollen-, Grant-, Nginx- oder CSP-Änderung.

## Konkreter Befund

Die folgenden Nachweise stammen aus dem Repository, nicht aus einem Live-Audit:

| Nachweis                                                                                                                                                                                    | Konsequenz für frei eingegebenes SQL                                                                                      |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| [Provisionierungsvertrag](development.md) vergibt tabellenweites SELECT unter anderem auf `uranus.organization`, `uranus."user"` und `uranus.organization_member_link`.                     | Die Berechtigung umfasst auch geheime Spalten dieser Tabellen.                                                            |
| [Deployment-Prüfung](../../ansible/roles/uranus_admin/files/boundary.sql) verlangt mit `source_table_missing_or_unreadable` tabellenweites SELECT auf diesen Tabellen.                      | Eine Umstellung auf ausschließlich sichere Spaltengrants erfordert auch eine gezielte Änderung des Infrastrukturvertrags. |
| [Quellvertrag](../app/source_contract.py) enthält `organization_member_link.accept_token`; [Quality Rules](quality-rules.md) erlauben ausschließlich ein Token-Präsenzboolean als Ergebnis. | Lesen zur internen Prüfung bedeutet keine Berechtigung, den Tokenwert an den Browser auszugeben.                          |
| [Diagnose-Registry](../app/sql_diagnostics/registry.py) schließt unter anderem `password_hash`, `api_import_token`, `activate_token` und `accept_token` als Ergebnisfelder aus.             | Die bisherige Geheimnisgrenze besteht zusätzlich aus festen, geprüften SQL-Projektionen.                                  |
| [Executor](../app/sql_diagnostics/executor.py) prüft die Ergebnisspalten gegen das registrierte Rezept.                                                                                     | Dieser Schutz kann nicht unverändert auf beliebige Abfragen übertragen werden.                                            |
| [Settings](../app/config.py) und [Admin-Engine](../app/admin_database.py) enthalten keinen dedizierten Admin-Reader-Zugang.                                                                 | `ADMIN_DATABASE_URL` ist kein zulässiger Ersatz für eine freie Admin-Datasource.                                          |

PostgreSQL erlaubt den Zugriff auf eine Spalte, wenn SELECT auf der gesamten
Tabelle **oder** auf dieser Spalte besteht. Ein Spalten-REVOKE beseitigt kein
tabellenweites SELECT. Siehe [PostgreSQL 17: GRANT, Notes](https://www.postgresql.org/docs/17/sql-grant.html#SQL-GRANT-NOTES).
Eine [READ-ONLY-Transaktion](https://www.postgresql.org/docs/17/sql-set-transaction.html)
beschränkt Schreiboperationen, aber entfernt keine Leseberechtigung für Geheimnisse.

Eine SELECT-Allowlist und eine Denylist gefährlicher Funktionen reichen daher
allein nicht aus. Auch eine Prüfung der **Ergebnisspaltennamen** reicht nicht:
Aliase können Namen ändern, Ausdrücke und Ganzzeilen-JSON können Werte in einer
anders benannten Spalte transportieren. Das bestehende `SENSITIVE_FIELDS` ist
ein Schutz für kontrollierte Recipes, kein vollständiger Datenflussprüfer für
beliebiges PostgreSQL. Eine Beschränkung auf vollständig geprüfte Abfrageformen
wäre ein eigenes Sicherheitsdesign; sie wird hier nicht als Ersatz für die
geforderte primäre Datenbankgrenze eingeführt.

## Lokaler Nachweis und seine Grenzen

Am 20.09.2026 wurde ein temporärer PostgreSQL-17.10-Cluster mit deaktiviertem
TCP-Listener und eigenem Unix-Socket gestartet. Die neu erstellte Datenbank
`sql_console_boundary_test` hatte zunächst kein `uranus`-Schema. Der Versuch
verwendete ausschließlich eine synthetische Membership-Tabelle, einen künstlichen
Token und eine nicht privilegierte Reader-Rolle mit dem dokumentierten
tabellenweiten SELECT. Es wurde kein Quelldump importiert.

Alle vier Prüfungen bestätigten den Befund in
`REPEATABLE READ, READ ONLY`-Transaktionen mit abschließendem ROLLBACK:

1. `has_column_privilege` bestätigte SELECT auf der geheimen Spalte.
2. Ein direkter Vergleich bestätigte den Zugriff auf den synthetischen Tokenwert.
3. Derselbe Vergleich funktionierte nach Umbenennung der Ergebnisspalte per Alias.
4. Derselbe Vergleich funktionierte über Ganzzeilen-`to_jsonb`.

Die Ausgabe enthielt ausschließlich Prüfergebnisse und die PostgreSQL-Version,
keine Tokenwerte. Cluster und temporäre Dateien wurden anschließend entfernt.
Dies belegt das Verhalten der dokumentierten Berechtigungen, **nicht** die
tatsächlichen Produktionsgrants. Der Versuch ist keine hinzugefügte automatisierte
Regressionssuite und ersetzt keinen späteren Test des freien Executors.

## Separater Infrastruktur-Follow-up

Der Datenbankbetreiber muss zunächst einen für interaktives SQL geeigneten
Lesevertrag bereitstellen und mit reinen Katalogabfragen verifizieren. Keine
automatische Provisionierung durch API, Worker oder Admin-Migrationen.

1. **Uranus-Konsole:** Bevorzugt eine separate, eingeschränkte Reader-Identität mit
   eigener DSN bereitstellen. Sie darf nur freigegebene Spalten oder geprüfte
   Projektionen lesen; geheime Token-, Passwort- und Credentialwerte müssen auf
   Datenbankebene unlesbar bleiben. Die bestehende Reader-Rolle wird weiterhin für
   registrierte interne Prüfungen benötigt, etwa für das Token-Präsenzboolean.
   Eine Änderung dieser Rolle ist alternativ möglich, verlangt aber eine Prüfung
   sämtlicher bestehenden Verbraucher und des Deployment-Preflights.
2. **Sichere Projektionen:** Falls Views benötigt werden, gehören deren Definition
   und Rechte in einen gesondert autorisierten, vom Uranus-Betreiber verantworteten
   Infrastruktur-/Quellvertrag. Admin-Code und Admin-Migrationen erzeugen keine
   Uranus-Views. Ein Presence-Boolean darf durch eine geprüfte Projektion verfügbar
   sein; der Token selbst bleibt unzugänglich. Ebenso sind potenziell sensible
   URL-, Freitext- und JSON-Inhalte in den freigegebenen Projektionen zu bewerten.
3. **Effektive Rechte:** Direkte Rechte, `PUBLIC`, Rollenmitgliedschaften, mögliche
   Rollenwechsel, Ownership, CREATE/TEMP, Sequenzen, Large Objects, ausführbare
   Funktionen und Extensions prüfen. Keine Schreibrechte, privilegierten Rollen
   oder ausführbaren Eskalationspfade. Ein Rollenname allein ist kein Nachweis.
   Views und Funktionen dürfen die Lesesperren nicht umgehen.
4. **Admin-Konsole:** Optional einen eigenständigen Admin-Reader mit freigegebenen
   Projektionen bereitstellen. Authentifizierungsdaten und andere Geheimnisse
   bleiben ausgeschlossen. Bis dahin ist diese Datasource nicht verfügbar.
   Sie fällt niemals auf den schreibberechtigten `admin_user` zurück.
5. **Ansible und Secrets:** Rollen-/Grant-Vertrag, Metadaten-Preflight, getrennte
   Secret-Verteilung und Tests in einem eigenen Infrastruktur-Change anpassen.
   Keine bestehenden Produktionsrollen oder Grants aus diesem PR verändern.

## Freigabekriterien für die anschließende App-Implementierung

Vor Freigabe werden effektive Rechte mit einem autorisierten Reader anhand der
Produktionskataloge nachgewiesen, ohne Geheimniswerte abzufragen. Schreib- und
Exfiltrationsversuche gehören ausschließlich in eine wegwerfbare Testdatenbank.
Die Tests müssen auch bei umgangenem App-Validator belegen:

- freigegebene SELECT-Abfragen funktionieren;
- direkte und indirekte Abfragen geheimer Spalten werden von PostgreSQL abgewiesen;
- INSERT, UPDATE und CREATE TABLE scheitern an Rolle beziehungsweise Transaktion;
- keine Eskalation über Rollen, Funktionen, Views oder geerbte Rechte;
- kein Fallback einer fehlenden Console-DSN auf einen mächtigeren Zugang.

Danach bleibt der vollständige Phase-3-App-Scope umzusetzen: gemeinsamer editierbarer
CodeMirror-Editor im Mockup-Modal und auf `/sql`, Finding-Kontext links, Parameter
und Ergebnisse rechts, Tabellen-/JSON-Ansicht und CSV aus bereits empfangenen Rows.
Die Phase-1-Regelauswertung darf eine geänderte freie Query nicht bewerten.

Der geplante Transport ist ein ausschließlich dafür allowlisteter Same-Origin-
WebSocket mit versioniertem Protokoll, Admin-Cookie, aktueller Systemadmin-Prüfung
und exakter Origin-Prüfung. Parser/AST-Allowlist, eine aktive Query pro Verbindung,
echter DB-Abbruch bei Cancel/Disconnect, begrenzte Connections, Cursor-Batches mit
Backpressure, sichere Fehlermeldungen und Audit ohne SQL/Rows bleiben erforderlich.
Die angeforderten Grenzen sind 5 Sekunden Statement-Timeout, 8 Sekunden
Gesamtdeadline, 50 Standardzeilen und maximal 500 Zeilen, 32 KiB SQL, 16 KiB je
Zelle und 1 MiB serialisierte Ergebnisse. **Diese Grenzen und dieser Transport
sind Anforderungen, noch keine implementierten Console-Garantien.**

Die spätere Nginx-Location muss Upgrade gezielt behandeln, Maintenance respektieren
und die Same-Origin-CSP im Produktionsbrowser nachweislich erfüllen. Die App-PR
benötigt dann die vollständigen Backend-, Frontend-, E2E-, Screenshot- und
Deployment-Tests aus der Aufgabenbeschreibung.

Die Datenbankrolle bleibt die primäre Sicherheitsgrenze. Phase 3 darf ausschließlich
READ-ONLY SQL unterstützen. Phase 4 mit Schreibzugriff bleibt außerhalb dieses
Follow-ups und benötigt ein eigenes Sicherheitsreview.
