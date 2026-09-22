# Finding SQL Diagnostics – Phase 1

Systemadmins können für gespeicherte Findings die registrierte Quellprüfung ansehen,
eine psql-fähige Fassung kopieren und aktuelle Quelldaten ausdrücklich abfragen.
Die Diagnose verändert weder Finding-Status noch Prüflaufhistorie. Auch behobene Befunde
bleiben diagnostizierbar: `matched=false` bedeutet, dass aktuelle Daten die Regel nicht
mehr erfüllen. Bei entferntem Quelldatensatz ist `matched=null`.

## Architektur und API

`app/sql_diagnostics/` enthält unveränderliche Recipe-Modelle, die feste Registry,
Parameterprüfung, Literal-Rendering, strukturierte Python-Auswertungen und den Executor.
`app/api/sql_diagnostics.py` lädt ID, Regel, Objekttyp, Objektschlüssel, Feld und letzten
Beobachtungszeitpunkt serverseitig aus der Admin-Ablage. Keine Browser-Metadaten als Quelle.

- `GET /api/v1/findings/sql-diagnostic?finding_id=...`: Definition, SQL, Copy-SQL,
  Parameter, Spalten, Erklärung; **keine Quellquery**.
- `POST /api/v1/findings/sql-diagnostic/execute`: JSON ausschließlich
  `{"finding_id": "<persisted finding ID>"}`. Keine SQL-, Parameter- oder Limit-Overrides.
  Unbekannte Body-Felder und Queryparameter werden abgewiesen.

Beide Endpunkte verwenden `get_current_admin`; Cookie-POSTs verlangen exakte Origin
und `X-Admin-CSRF: 1`. Nitro erlaubt nur feste Pfade, Methoden und typisierte Bodies.
Antworten sind `private, no-store`. Der eigenständige SQL Editor lädt beim Öffnen des
großen Modals und führt nur über „Abfrage ausführen“ aus. Beim Schließen werden
Ergebnisse verworfen. Der sichtbare SQL-Text bleibt unveränderlich und wird nie gesendet.

Persistierte Finding-Responses enthalten `sql_diagnostic_available`. Die bestehende
Registry prüft Regel, Typ, Feld und Identität ohne Quellquery; gespeicherte
Display-Metadaten können dieses Flag nicht überschreiben. Live-Findings liefern false.
Auch `resolved` Findings behalten die Diagnoseaktion. Keine neue Route, Migration oder
Änderung am Execute-Vertrag. [Frontend und Dependency-Audit](../../frontend/docs/sql-editor.md).

## Sicherheitsmodell

- Ausschließlich die Source-Engine aus `DATABASE_URL` mit eingeschränkter Reader-Rolle.
  Die Admin-Verbindung liest nur die Finding-Identität.
- Separate `REPEATABLE READ, READ ONLY`-Transaktion; immer **ROLLBACK**, auch bei Fehlern.
  Die Datenbankrolle bleibt die primäre Sicherheitsgrenze.
- `statement_timeout=5000ms`, `lock_timeout=1000ms`,
  `idle_in_transaction_session_timeout=10000ms`; acht Sekunden Gesamtdeadline im Executor.
- Fest gebundenes SQL-Limit 50, harte Obergrenze 100. Pilot-Identitäten liefern höchstens
  eine Zeile. Maximal 4096 Zeichen pro Textzelle und 256 KiB Ergebnisdaten; sonst Fehler.
- Feste explizite Projektionen, Tabellen und SQL-Ausdrücke. UUIDs und Composite Keys
  werden streng geparst. `finding.field` ist nur Lookup in einer festen URL-Feld-Allowlist.
- Copy-SQL verwendet den SQLAlchemy-PostgreSQL-Literal-Compiler, keine Textersetzung.
  Erlaubt: UUID, int, string, bool, date, datetime. Andere Parametertypen werden abgewiesen.
  Copy-SQL setzt PostgreSQLs übliches `standard_conforming_strings=on` voraus.
  Die tatsächliche Ausführung verwendet ausschließlich gebundene Werte, nie Copy-SQL.
- Keine Migration, Tabellenänderung, Grants oder neue Rolle außerhalb isolierter Tests.
  Keine Anwendungsschreibzugriffe auf `uranus`.

## Sensitive Data Policy und Fehler

Passworthashes, Import-/Aktivierungs-/Annahme-/Reset-/Sessiontoken, SMTP- und
Datenbankzugangsdaten sind keine Ergebnisfelder. Registry und Frontend-Contract begrenzen
Projektionen; zusätzliche Ergebnisspalten werden abgewiesen. Die Mitgliedschaftsquery
projiziert ausschließlich `accept_token_present`, niemals den Tokenwert.
URL-Werte mit `@`, Query oder Fragment werden vollständig verdeckt, da sie Zugangsdaten
oder Tokens enthalten können. Die bestehenden URL-Helper prüfen intern die Originalwerte.
Es erfolgen keine externen HTTP-/DNS-Anfragen.

Auditlogs enthalten nur Admin-Subject, Recipe-ID, Finding-ID-SHA256, Dauer, Zeilenzahl
und feste Kategorie. Keine Rows, E-Mail-Werte, SQL-Literale, DSNs oder Driver-Meldungen.
Exceptions werden ohne Verkettung bereinigt, auch bei Debug-Logging. Timeout: HTTP 504;
sonstige Ausführungsfehler: 503; unbekannte Recipe/fehlendes Finding: 404; inkompatible
Identität: 422. Unbekannte Regeln führen keine Source-Query aus.

## Gleiche Regelsemantik

Datumsdiagnosen verwenden `date_issues()`. Preis, Mitgliedschaft und fehlender Terminort
verwenden gemeinsame reine Helper mit den Qualitätsregeln. Venue verwendet denselben
`POINT_MISSING_SQL`-Ausdruck. URL nutzt `url_problem()`, Ort nutzt
`effective_location()`/`valid_online()`. Ein Date-Venue beendet die Event-Space-Vererbung.
Die Terminquery verwendet LEFT JOIN und erhält so auch die Python-Semantik bei fehlendem
Parent. SQL zeigt Quelldaten, die UI kennzeichnet die Auswertung ausdrücklich als Python.

Partnerdiagnosen verwenden `QUEUE_SQL['partner_requests']` und denselben
`partner_long_pending()`-Helper wie die Queue. Strenger Vergleich
`created_at < now - PENDING_AGE_DAYS`, mit `URANUS_TIMESTAMP_TIMEZONE` für naive Quellzeit;
keine abweichende Rundung der Altersberechnung.

## Erweiterung und Grenzen

Neue Recipes brauchen explizite Projektionen, Finding-Typ-/Feld-Allowlists, verifizierte
Quellverträge und gemeinsame Auswertungshelper sowie Matching-/Nicht-Matching- und
Sicherheitsregressionen. Fixtures sind kein Live-Schema-Beleg. Diese Piloten verwenden
bereits vorhandene Repository-Spalten/Joins; Produktion wurde für diesen PR nicht abgefragt.

Registry und Executor können später weitere Recipes und Endpoint SQL Provenance tragen.
Eine freie SQL-/WSS-Konsole braucht ein separates Sicherheitsdesign. Phase 1 enthält
keine freie Queryausführung und keine WebSockets.

## Pilotqueries

`diagnostic_limit` ist serverseitig 50. UUIDs stammen ausschließlich aus dem Finding-Key;
Composite Keys haben exakt das registrierte Präfix und zwei UUID-Komponenten.

### `event_date_end_before_start`

Enddatum vorhanden und Enddatum < Startdatum.

```sql
SELECT uuid, event_uuid, start_date, start_time, end_date, end_time,
all_day, release_status::text
FROM uranus.event_date WHERE uuid = :entity_key
LIMIT :diagnostic_limit
```

### `event_date_same_day_end_before_start`

Gleiches Start- und Enddatum; beide Zeiten vorhanden; Endzeit < Startzeit.

```sql
SELECT uuid, event_uuid, start_date, start_time, end_date, end_time,
all_day, release_status::text
FROM uranus.event_date WHERE uuid = :entity_key
LIMIT :diagnostic_limit
```

### `event_date_without_location`

Python: wirksames Venue fehlt und valid_online(online_link) ist falsch. Die bestehende Ortsvererbung gilt.

```sql
SELECT d.uuid, d.event_uuid, d.venue_uuid AS date_venue_uuid,
d.space_uuid AS date_space_uuid, e.venue_uuid AS event_venue_uuid,
e.space_uuid AS event_space_uuid, e.online_link
FROM uranus.event_date d LEFT JOIN uranus.event e ON e.uuid = d.event_uuid
WHERE d.uuid = :entity_key
LIMIT :diagnostic_limit
```

### `event_price_without_currency`

Mindestens ein Preis ist gesetzt und blank(currency) ist wahr (NULL, leer oder nur Whitespace).

```sql
SELECT uuid, title, release_status::text, min_price, max_price,
currency, price_type::text
FROM uranus.event WHERE uuid = :entity_key
LIMIT :diagnostic_limit
```

### `venue_missing_location`

point IS NULL OR ST_IsEmpty(point), wie in der Qualitätsprojektion.

```sql
SELECT uuid, name, org_uuid, street, house_number, postal_code, city, country,
state, osm_id, ST_AsText(point) AS point, (point IS NULL OR ST_IsEmpty(point)) AS point_missing
FROM uranus.venue WHERE uuid = :entity_key
LIMIT :diagnostic_limit
```

### `membership_joined_accept_token_present`

has_joined und accept_token_present sind wahr. Tokenwerte werden niemals ausgewählt.

```sql
SELECT m.org_uuid, o.name AS organization_name, m.user_uuid, m.has_joined,
(m.accept_token IS NOT NULL AND btrim(m.accept_token) <> '') AS accept_token_present
FROM uranus.organization_member_link m
LEFT JOIN uranus.organization o ON o.uuid = m.org_uuid
WHERE m.org_uuid = :org_uuid AND m.user_uuid = :user_uuid
LIMIT :diagnostic_limit
```

### `partner_long_pending`

Python: status = pending und created_at älter als PENDING_AGE_DAYS; URANUS_TIMESTAMP_TIMEZONE interpretiert die Quellzeit.

```sql
SELECT from_org_uuid, from_name AS from_org_name, to_org_uuid, to_name AS to_org_name,
user_id, user_exists, status, created_at, grant_exists
FROM (
SELECT p.from_org_uuid, p.to_org_uuid, p.from_user_uuid AS user_id, p.status, p.created_at,
 f.name AS from_name, t.name AS to_name,
 COALESCE(COALESCE(NULLIF(u.display_name,''),NULLIF(u.username,''),NULLIF(u.email,''),
                   u.uuid::text),p.from_user_uuid::text) AS user_name,
 COALESCE(u.display_name,u.username) AS review_user_name,
 u.uuid IS NOT NULL AS user_exists,
 EXISTS(SELECT 1 FROM uranus.organization_access_grants g
        WHERE g.src_org_uuid=p.to_org_uuid AND g.dst_org_uuid=p.from_org_uuid) AS grant_exists
FROM uranus.organization_partner_request p
LEFT JOIN uranus.organization f ON f.uuid=p.from_org_uuid
LEFT JOIN uranus.organization t ON t.uuid=p.to_org_uuid
LEFT JOIN uranus."user" u ON u.uuid=p.from_user_uuid
) partner
WHERE from_org_uuid = :from_org_uuid AND to_org_uuid = :to_org_uuid
LIMIT :diagnostic_limit
```

### `url_syntax.event`

Python: url_problem() prüft das gespeicherte Finding-Feld. Keine DNS- oder HTTP-Anfrage. Zugangsdaten und sensible URL-Parameter werden verdeckt.

```sql
SELECT uuid, title, source_link, online_link, ticket_link, registration_link FROM uranus.event WHERE uuid = :entity_key
LIMIT :diagnostic_limit
```

### `url_syntax.venue`

Python: url_problem() prüft das gespeicherte Finding-Feld. Keine DNS- oder HTTP-Anfrage. Zugangsdaten und sensible URL-Parameter werden verdeckt.

```sql
SELECT uuid, name, web_link, ticket_link FROM uranus.venue WHERE uuid = :entity_key
LIMIT :diagnostic_limit
```

### `url_syntax.organization`

Python: url_problem() prüft das gespeicherte Finding-Feld. Keine DNS- oder HTTP-Anfrage. Zugangsdaten und sensible URL-Parameter werden verdeckt.

```sql
SELECT uuid, name, web_link FROM uranus.organization WHERE uuid = :entity_key
LIMIT :diagnostic_limit
```

[SQL / Datenherkunft – registrierte Queries, Sicherheitsmodell und Coverage](sql-provenance.md).
