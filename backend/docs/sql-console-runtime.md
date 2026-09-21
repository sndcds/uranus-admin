# Phase 3: interaktive READ-ONLY SQL Console

Phase 3 verwendet Contract v6 / Function Policy v3.
Es gibt **keinen Write Mode**, kein Commit, keine gespeicherten Scripts, keine
serverseitige SQL-History und keine Phase-4-Funktion. Dieser PR deployt nichts.
Die Produktionsfreigaben der [DB-Infrastruktur](sql-console-infrastructure.md)
gelten weiter; synthetische Tests sind kein Produktionsnachweis.

## Datenumfang seit Contract v6

Die freie System-Admin-Console liest absichtlich alle Tabellen und Spalten in `uranus.*`,
einschließlich sensibler Token- und Passwort-Hash-Werte. `SELECT *` ist erlaubt; keine
Projektionspflicht oder Maskierung. Beispiel: `SELECT * FROM uranus.event LIMIT 50;`.
`admin.*` und Systemkatalog-Relationen bleiben für User-SQL verboten. Die DB erzwingt
weiterhin fehlende Schreib-/Eskalationsrechte; die AST ergänzt den Katalogschutz.
Legacy-Views bleiben erhalten, sind aber keine Datenquelle der freien Console.
[Grants, Owner, Default Privileges und RLS-Stop](sql-console-infrastructure.md).
Phase 1/2 behalten ihre bisherigen Ausführungspfade. Keine Phase 4.

## Architektur und Authentifizierung

Browser `/sql` oder Finding-Workspace → Same-Origin-WebSocket
`/api/admin/api/v1/sql-console/ws` → feste Nitro-Route → FastAPI
`/api/v1/sql-console/ws` → **ausschließlich** `SQL_CONSOLE_DATABASE_URL`.
Normale HTTP-Requests an den WebSocket-Pfad ermöglichen keine SQL-Ausführung.
Die bestehenden registrierten Diagnose-/Provenance-Endpunkte bleiben unverändert
in ihrer Ausführungssemantik; sie akzeptieren weiterhin keine freien SQL-Texte.

Vor dem Upgrade überprüft FastAPI das vorgesehene HttpOnly-Sessioncookie über
`session_identity`: aktive Sitzung, Credential-Version, absolute/Idle-Expiry,
Widerruf und aktueller System-Admin-Grant. Vor **jeder** weiteren Query wird dies
wiederholt. Keine Bearer-, API-Key- oder Dev-Token-Authentifizierung am WebSocket.
Fehlende Sitzung: 401; fehlender Grant/Origin: 403; fehlende Console-DSN: 503.
Nach einem bereits erfolgten Upgrade signalisieren 4401/4403 verlorene Auth/Rechte.
Die UI prüft vor dem Ausführen zusätzlich über den bestehenden HTTP-Sessionpfad,
weil Browser den HTTP-Status einer abgewiesenen WebSocket-Verbindung verbergen.

`Origin` muss exakt und einmal `AUTH_PUBLIC_ORIGIN` entsprechen, auch beim lokalen
Entwickeln. Fehlende, abweichende oder mehrfache Origins werden abgewiesen.
Der Browser braucht keinen CSRF-Header für diesen WebSocket; die verpflichtende
Origin- und Cookie-Prüfung schützt den Upgrade. HTTP-CSRF-Verhalten bleibt erhalten.
Keine Query-Parameter, Credentials oder SQL in URLs. Nitro übernimmt ausschließlich
das erwartete Sessioncookie und Origin; kein beliebiger Host, Pfad, Header oder
Redirect. Upstream TLS-Zertifikate werden normal verifiziert.

## Protokoll v1

Text-JSON mit `v: 1` und einer UUID als `request_id`. Zusätzliche Felder sind
verboten. Pydantic: `app/sql_console/protocol.py`; Browser/Proxy-Zod:
`frontend/shared/sql-console.ts`. Das WebSocket-Protokoll ist kein OpenAPI-Endpunkt;
der HTTP-OpenAPI-Snapshot enthält die ergänzte servereigene `console_sql`-Definition.

```json
{"v":1,"type":"execute","request_id":"00000000-0000-4000-8000-000000000001","sql":"SELECT uuid FROM uranus.event LIMIT 50;","params":{},"row_limit":50}
{"v":1,"type":"ack","request_id":"00000000-0000-4000-8000-000000000001","batch":1}
{"v":1,"type":"cancel","request_id":"00000000-0000-4000-8000-000000000001"}
```

`params` ist leer; freie Bind-Parameter sind in Phase 3 nicht verfügbar.
Servernachrichten besitzen dieselben Basisfelder:

| type        | Zusätzliche Felder                                              |
| ----------- | --------------------------------------------------------------- |
| `started`   | –                                                               |
| `columns`   | `columns: string[]` (eindeutige Anzeigenamen)                   |
| `rows`      | `batch: number`, `rows: object[]`                               |
| `complete`  | `row_count`, `duration_ms`, `truncated`                         |
| `error`     | sicherer `code`, optional `position` (1-basiert), `duration_ms` |
| `cancelled` | `duration_ms`                                                   |

Genau eine aktive Query pro Socket. Ein zweites Execute liefert `busy` für dessen
Request-ID. Eine ACK bestätigt ausschließlich den gerade ausstehenden Batch;
falsche/vorauseilende/doppelte ACKs schließen die Verbindung. Terminalmeldungen
werden erst nach Rollback/Close gesendet. Kein Ergebnis folgt auf `cancelled`.
Idle-Sockets werden nach 60 Sekunden geschlossen; Execute verbindet bei Bedarf neu.

## SQL- und DB-Sicherheitsgrenze

[pglast](https://pglast.readthedocs.io/en/latest/parser.html) verwendet den
PostgreSQL-Parser (libpg_query, PostgreSQL 17). Genau ein `SelectStmt` ist erlaubt,
inklusive CTEs, Subqueries und Mengenoperationen. Rekursive AST-Prüfung sperrt auch
schreibende CTEs, SELECT INTO, Locking-Klauseln und freie Parameter. Nicht-Query-
Statements werden generell abgewiesen, nicht über eine unvollständige Regex-Liste.
Relationen außerhalb `uranus` (einschließlich `admin`, `public`, `uranus_console` und
Systemkatalogen) sind zusätzlich gesperrt; unqualifizierte Tabellen und lexikalisch
sichtbare CTEs bleiben möglich, auch CTE-Namen mit `pg_`-Präfix. Unqualifizierte
`pg_*`-Relationen außerhalb eines solchen CTE-Gültigkeitsbereichs sind gesperrt. Eine ergänzende App-Privacy-Sperre verbietet
`pg_stat_get_*` und SQL/XML-Wrapper `query_to_*`, `table_to_*`, `schema_to_*`,
`database_to_*`, `cursor_to_*`: sie könnten sonst Querytexte anderer Sitzungen mit
derselben DB-Identität offenlegen oder SQL in Stringargumenten verstecken. Diese
zusätzliche Begrenzung ist ausdrücklich eine Runtime-Policy, keine Behauptung über
weitergehende ACLs des unveränderten DB-Contracts.

### Audit dynamischer SQL- und Privacy-Funktionen (PostgreSQL 16/17)

Die ergänzende zentrale Policy in `app/sql_console/policy.py` sperrt außerdem
**`ts_stat` und `ts_rewrite`**. Der äußere AST enthält bei diesen Aufrufen nur
`FuncCall` und Stringargumente; das darin versteckte SQL wird nicht als eigener
Query-Baum geprüft. PostgreSQL führt es intern aus. READ ONLY verhindert dabei
keine Offenlegung von Querytexten anderer Sitzungen derselben DB-Identität.

Gezielt geprüft anhand der PostgreSQL-Dokumentation für
[16](https://www.postgresql.org/docs/16/textsearch-features.html) und
[17](https://www.postgresql.org/docs/17/textsearch-features.html):

| Funktionsgruppe | Befund / Runtime-Policy |
| --- | --- |
| `ts_stat(text)` / `ts_stat(text, text)` | Führt SQL-Text aus und liefert dessen Lexeme; beide Überladungen neu gesperrt. |
| `ts_rewrite(tsquery, text)` | Führt eine SQL-Abfrage nach Ersetzungsregeln aus; Name neu gesperrt. Konservativ ist auch die reine Drei-`tsquery`-Überladung gesperrt, entsprechend der bestehenden namensbasierten Policy. |
| `query_to_xml*` | SQL-Text-Ausführung; durch `query_to_` bereits gesperrt, einschließlich XML-Schema-Varianten. |
| `table_to_xml*`, `schema_to_xml*`, `database_to_xml*` | Indirekter Zugriff auf Relationsinhalte/-definitionen über Namen bzw. `regclass`; bestehende Präfixsperren bleiben erhalten. |
| `cursor_to_xml*` | Liest Cursorinhalte/-definitionen; bestehende `cursor_to_`-Sperre bleibt erhalten. |
| `pg_stat_get_activity`, `pg_stat_get_backend_activity` | Können fremde Sitzungstexte derselben Rolle offenlegen; bereits durch `pg_stat_get_` gesperrt. |
| `current_query`, `pg_cursor`, `pg_prepared_statement` | Beziehen sich auf die eigene Sitzung; kein zusätzlicher fremder Session-SQL-Pfad. Keine neue Namenssperre. |
| `to_tsvector`, `to_tsquery`, `plainto_tsquery`, `querytree` | Verarbeiten Textsuchdaten, keinen SQL-Text; bleiben erlaubt. |

Quellen: [SQL/XML-Mapping](https://www.postgresql.org/docs/17/functions-xml.html#FUNCTIONS-XML-MAPPING),
[Activity-Funktionen](https://www.postgresql.org/docs/17/monitoring-stats.html),
[Core-Funktionskatalog](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/include/catalog/pg_proc.dat).
Dies ist ein gezielter Core-Audit, keine Freigabe beliebiger Extensions oder
benutzerdefinierter Wrapper. Die bestehenden dblink-/Datei-/Contrib-/Custom-Sperren
aus dem DB-Contract bleiben unverändert.

Tests prüfen `function_denied`, Schemaqualifikation, Groß-/Kleinschreibung,
gequotete Namen, beide `ts_stat`-Überladungen, Verschachtelung und Abweisung vor
dem Verbindungsaufbau. Literale, Kommentare, Aliase und harmlose Textfunktionen
bleiben erlaubt. Gequotete Großbuchstaben bezeichnen in PostgreSQL zwar einen
anderen Namen; die Policy sperrt diese Schreibweise zusätzlich konservativ.
DB-Rolle, Ansible-Contract, Grants und DSN-Auswahl werden nicht verändert.

`function_policy.json` ist eine kontrolliert abgeleitete statische Teilmenge des
Ansible-DB-Contracts: verbotene Namen/Präfixe, geprüfte gesperrte Signaturen,
Custom Functions und View-Namen. Der Drift-Test berechnet sie aus dem DB-Contract
neu und verlangt exakte Gleichheit. Bei einer Contract-Änderung muss der Export
bewusst aktualisiert werden. Kein Frontend entscheidet über Berechtigungen.
Die AST-Denylist sperrt unter anderem Sleep, Datei-/Large-Object-/dblink-Funktionen,
Backend-Signale, Config-, Notify-, Advisory-Lock-, WAL-/Replication-Funktionen,
gefährliche PostGIS- und geprüfte Custom-/Contrib-Funktionen. Die AST-Liste sperrt
konservativ ganze Namen; der DB-Preflight berücksichtigt dagegen die **exakten
Signaturen**, weil sichere Überladungen im DB-Contract erlaubt sein können.

Die Datenbank bleibt die **primäre** Sicherheitsgrenze. Der Runtime-Preflight prüft
auf jeder neuen Verbindung `current_user` **und** `session_user` als
`uranus_console_reader`, den Search Path `pg_catalog, uranus`, fehlendes
CREATE/TEMP, mächtige Rollenattribute/Memberships, Objekt-Ownership, Schema-CREATE,
unerlaubte Uranus-Schreib-/Grant-Rechte, Admin-Rechte und effektives EXECUTE der gesperrten Funktionen.
Er verlangt USAGE auf Uranus, Tabellen-SELECT auf allen dynamisch inventarisierten
Tabellen, konsistente Schema-/Tabellen-/DB-Owner und exakt schema-lokale SELECT-Defaults
dieses Owners. RLS, indirekte Relationen, Sequenzrechte und unerwartete Default Privileges
führen zu `unsafe_identity`. PG17-MAINTAIN wird über die tatsächliche ACL mit erfasst. Er ersetzt
nicht das vollständige versionierte Provisionierungs-/Katalog-Audit.
Keine Rollen-/Grant-Reparatur durch die Anwendung. Keine Fallback-DSN.

Jede Ausführung verwendet eine eigene asyncpg-Verbindung ohne Pool. `ConsoleConnection`
führt die unveränderte asyncpg-Typkatalogabfrage ohne dessen internes `set_config`-JIT-
Wrapping aus; `jit=off` wird als Startup-Setting gesetzt. So funktioniert die Typ-Erkennung
für Enums, Arrays und PostGIS ohne zusätzliche EXECUTE-Rechte. Die bestehende
Result-Serialisierung (einschließlich Platzhalter für nicht unterstützte native Typen) bleibt unverändert. Der schmale private Treiber-
Hook ist durch echte Typ-Integrationstests abgesichert und muss bei asyncpg-Upgrades
mitgeprüft werden. `set_config` bleibt sowohl DB-seitig als auch in der AST gesperrt.

Ablauf:

1. DSN-Identität und AST prüfen.
2. `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`.
3. `SET LOCAL statement_timeout = '5s'`, `lock_timeout = '1s'`,
   `idle_in_transaction_session_timeout = '8s'`; UTC Session-Zeit.
4. DB-Identität prüfen, Statement vorbereiten, Cursor lesen.
5. **Immer ROLLBACK**, auch nach erfolgreichem SELECT, danach Close.

## Limits, Streaming und Abbruch

| Grenze         | Wert                                                                      |
| -------------- | ------------------------------------------------------------------------- |
| SQL            | 32 KiB UTF-8, vor Parsing/Execution                                       |
| Statement      | 5 Sekunden, DB-seitig                                                     |
| Gesamtdeadline | 8 Sekunden für Verbindung/Prüfung/Execution/Fetch/Serialisierung/ACK      |
| Zeilen         | 50 Standard, 500 Maximum; eine zusätzliche Probezeile wird nie übertragen |
| Zelle          | 16 KiB JSON inklusive Truncation-Marker                                   |
| Gesamtergebnis | höchstens 1 MiB mit konservativem Framing-Budget                          |
| Batch          | höchstens 25 Zeilen und 64 KiB Row-JSON                                   |
| Projektion     | höchstens 128 Spalten                                                     |
| Parallelität   | `SQL_CONSOLE_MAX_CONNECTIONS`, Standard 4, fail fast                      |

Der vorhandene Service startet **einen** Uvicorn-Prozess. Die globale Console-
Parallelitätsgrenze gehört diesem Prozess; zusätzliche API-Worker/Replikate sind
für diese Konfiguration nicht freigegeben. Eine verteilte Limitierung wäre vor
einer solchen Skalierung nötig. Nitro begrenzt zusätzlich die WebSocket-Verbindungen.

DB-Fetch liest jeweils eine Zeile; es gibt kein `fetchall` und keine unbeschränkte
Producer-Queue. Nach jedem Batch wartet der Server auf genau eine Browser-ACK.
Die UI sendet sie nach Verarbeitung und Vue-Render (`nextTick`). Auch der Proxy
prüft Frame-/Sendepuffergrenzen; er quittiert niemals selbst. Ein langsamer Client
hält höchstens einen unquittierten Batch und unterliegt derselben 8s-Deadline.
Eine einzelne Zeile, die trotz Zellkürzung den Batch übersteigt, beendet das Ergebnis
mit `truncated`; Spaltenprojektion reduzieren. Kürzungen sind sichtbar.

Cancel-Button, erster Escape-/Schließen-Versuch bei laufender Modalabfrage,
Disconnect, Deadline und Shutdown canceln den überwachten Query-Task.
asyncpg sendet dabei einen echten PostgreSQL-CancelRequest. Rollback wartet auf den
Abbruch; Cleanup hat zusätzlich höchstens eine Sekunde, dann wird die Verbindung
terminiert. Keine Connection wird mit laufender Query wiederverwendet. Der zweite
Escape nach abgeschlossenem Cancel schließt das Modal und stellt den Fokus zurück.

## Ergebnisse, Fehler und Audit

JSON erhält null/boolean/sichere integer/finite float. Bigints außerhalb des
JavaScript-Integerbereichs sowie Decimal/UUID werden verlustfrei als Strings
übertragen, Datum/Zeit/Timestamp als ISO-Strings, Enum/Text als Strings. Nichtfinite
Floats sind Strings. Nicht unterstützte Array-/Composite-/Binary-/Treiberobjekte
werden als `[unsupported result type]` dargestellt; keine beliebige Python-Repr.
Eine große Textzelle wird `{ "value": "…", "truncated": true }`.

Fehler übertragen nur feste Kategorien (Syntax/Objekt, Permission, Timeout,
Funktionssperre, Limit, Protokoll, Busy, Verbindungsverfügbarkeit). Keine Driver-
Message, SQL-Literale, DSN, Passwort oder Traceback. Eine sichere PostgreSQL-
Fehlerposition markiert CodeMirror und setzt den Fokus dorthin.

`admin.sql_console` schreibt `sql_console_query` in das vorhandene strukturierte
Log/Audit-Sink: UTC-Zeitstempel, Admin-Subject, UUID-Request-ID, Dauer, Status,
Zeilenzahl, SHA-256 des SQL. Cancel/Timeout haben eigene Statuswerte. Keine Rows,
SQL-Texte oder Parameter. Es entsteht keine neue Admin-Tabelle oder Migration.
Dauerhafte Aufbewahrung/Rotation erfolgt über den vorhandenen Logbetrieb; dies ist
keine SQL-History. PostgreSQL-eigene Statement-/Error-Logs sind separat Betreiber-
konfiguriert und dürfen bei Aktivierung keine sensitiven SQL-Literale aufzeichnen;
die Runtime erhält dafür keine erweiterten SET-/Logging-Berechtigungen.

## Frontend und visuelle Parität

`SqlWorkspace` ist das gemeinsame zweispaltige Layout für Finding, Datenherkunft
und `/sql`; mobil einspaltig. `SqlQueryPanel`, Parameter, Ergebnistabelle und
JSON-Ansicht werden wiederverwendet. CodeMirror wird nur clientseitig und erst beim
Öffnen des Bearbeitungsmodus dynamisch importiert. Kein `window` im SSR-Import.

Die verbindliche, aus PR #77 extrahierte Definition ist
`frontend/app/components/sql/sql-theme.css`. Readonly und Editable verwenden **denselben
Prism-SQL-Tokenizer**, dieselben `.token`-Klassen und CSS-Variablen. Das
[CodeMirror-Layoutmapping](https://codemirror.net/examples/styling/) in
`sql-codemirror.ts` referenziert ausschließlich diese Tokens: keine zweite Palette,
kein Default-/Fremdtheme. Auditiert: Slate-900/100-Panel, Slate-800-Rand, 8px Radius,
Tailwind-Monospace, 12px/20px, Gewicht 400, normale Laufweite, vertikal 12px,
Code-Innenabstand 16px, Gutter 12px. Scrollbars bleiben nativ. Auswahl und Cursor
haben gemeinsame Tokens; die optionale aktive Zeile bleibt transparent.

`sql-formatter` mit bestehendem PostgreSQL-Dialekt bewahrt Literale, quoted
Identifiers, Parameter, Casts und Kommentare. Vier Spaces, selektierte Spalten
jeweils eine Zeile, eingerücktes ON/AND/OR, CTE/CASE/Subqueries und Zielbreite 110.
Soft-Wrap bricht an Wortgrenzen; lange unteilbare Identifiers werden horizontal
zugänglich, niemals mitten im Wort getrennt.

`rawSql` ist ausschließlich der Text im Editor. `formattedSql` wird separat für
Initialdarstellung, Formatieren und Copy berechnet. Nur der Format-Button übernimmt
diesen Text in `rawSql`. Execute sendet ausschließlich `rawSql`, nie DOM/HTML.
Copy liefert formatiertes Plain SQL, CSV nur bereits empfangene Rows. JSON verwendet
den bisherigen eigenen JSON-Tokenizer. Es gibt keine persistente Query-History.

Findings laden weiterhin die registrierte Definition serverseitig. Das additive
`console_sql` verwendet vorhandenes sicheres serverseitiges Literal-Rendering und
AST-basiertes Rendering ohne Umschreiben der `uranus.*`-Relationen.
Die originale Phase-1-Query und deren Execution bleiben erhalten. Parameter sind im Console-Modus als
**ursprüngliche Startwerte** beschriftet. Nach Editing erscheint
„Benutzerdefinierte Abfrage“, mit ausdrücklichem Hinweis, dass keine Befundregel
bewertet wird; Originalwiederherstellung ist möglich.

## Betrieb und Verifikation

Nginx erhält ausschließlich eine exakte WebSocket-Location mit Upgrade/Connection;
Maintenance, Rate Limits und Security Headers entsprechen der vorhandenen API-
Location. CSP bleibt `connect-src 'self'`, ohne externe WSS-Origin oder Wildcard.
Backend/Frontend gemeinsam ausrollen und betroffene Services neu starten, erst nach
bestehenden Operator-Freigaben. Kein Production-Deployment ist Teil dieses PRs.

Tests: AST/Contract-Drift, Protokoll/Origin/Session, Zell-/Zeilen-/Resultlimits,
Audit ohne SQL, Rollback/Cancel/Shutdown und ACK-Batching; Integration mit dem echten
Ansible-Provisionierer auf dem gepinnten PG17/PostGIS-Testimage, einschließlich
Query-Abbruch in `pg_stat_activity`. Playwright verwendet eine kontrollierte
WebSocket-Fixture durch den echten Nitro-Proxy; dies ersetzt keine DB-Integration.
Die vollständigen Workspace-Screenshot-Baselines stammen aus dem Production-Build
(Dev-/Production-CSS kann sonst um einzelne Layout-Pixel abweichen). Der isolierte
SQL-Panel-Test vergleicht Readonly und Editable in beiden Builds mit **derselben**
Baseline und verlangt zusätzlich identische berechnete Tokenfarben, Typographie,
Hintergrund, Gutterbreite und Textposition. Baselines unter
`frontend/tests/e2e/sql-console.spec.ts-snapshots/` schützen Finding, `/sql`, Running,
Result und Error; alle sichtbaren Daten sind kontrollierte Testfixtures.
Production-E2E prüft CSP/SSR. Die lokale Browserberechtigung im CSP-Test ist nur für
den Playwright-Loopback-Server erforderlich; sie ändert keine App-/Nginx-Policy.

## Lokaler Start und abgewiesener Handshake

Ohne `SQL_CONSOLE_DATABASE_URL` ist HTTP 503 beim Upgrade beabsichtigt. Die
Console verwendet keinen anderen Account. Die DSN darf nur auf eine separat
provisionierte Console-Verbindung als `uranus_console_reader` zeigen. Es werden
keine lokalen oder produktiven Credentials automatisch ergänzt.

`uv run python -m app` wählt den WebSocket-Treiber und seine Grenzen explizit.
Bei direktem Uvicorn-Start dieselben Optionen verwenden:

```sh
uv run --env-file .env uvicorn app.main:app --reload --ws wsproto --no-access-log --ws-max-size 200000
```

Uvicorn 0.53s automatisch gewählter SansIO-Treiber meldet nach vollständig
versendeten HTTP-Ablehnungen fälschlich `ASGI callable returned without completing
handshake`. Der explizite, nicht abgekündigte `wsproto`-Treiber bewahrt 401/403/503 ohne diesen
Fehlalarm. Uvicorn ab 0.53 begrenzt hier die Frame-Größe und pausiert TCP-Lesen,
bis die Anwendung Nachrichten verarbeitet. Regressionstests verwenden echte lokale
TCP-/WebSocket-Verbindungen, einschließlich erfolgreicher Übertragung und Oversize-Abbruch.
`sql_console_handshake_denied` protokolliert nur die sichere Fehlerkategorie:
`database_unavailable` bei fehlender Console-DSN, `admin_auth_unconfigured` bei
fehlendem Auth-Speicher oder die entsprechende Auth-/Origin-Kategorie. Keine DSN,
Cookies oder SQL-Texte werden geloggt.
