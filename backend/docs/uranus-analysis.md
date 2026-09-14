# Analyse des Uranus-Repositories

## Grundlage und Aussagegrenze

Vollständig gelesen: [`docs/admin-dashboard-empfehlung.md`](https://github.com/sndcds/uranus/blob/7feb47e319145b383d46616026f27fe9d6626d63/docs/admin-dashboard-empfehlung.md).
Analysiert wurde der saubere lokale Checkout `/home/awendelk/git/uranus`, Commit
`7feb47e319145b383d46616026f27fe9d6626d63`, 13.09.2026. Die Empfehlung selbst bezieht
sich auf `b257ae9`. Kein Zugriff auf die laufende produktive Datenbank. Nach der Repository-Analyse wurde der vom
Betreiber bereitgestellte Live-Backup zusätzlich in einer isolierten lokalen Datenbank geprüft;
die nachfolgende Ergänzung beschreibt diese maßgebliche Schemaquelle. CI benutzt synthetische Fixtures.
Die DDL-Exporte warnen ausdrücklich vor unvollständigen Datenbankdefinitionen.

Untersucht: README, DDL aller unten aufgeführten Tabellen, `uranus-api.go`, Auth-Middleware,
Claims/Login/Refresh, Permission-Bits und SQL-Rechteauflösung, Event-Erstellung und -Updates,
Terminerstellung/-Updates, Venue/Space/Organization-Handler, Teameinladung, Partneranfrage
und -entscheidung, Pluto-Verknüpfungen, URL-/Datumsvalidierung, öffentliche Event-Abfragen
und Projektionsaktualisierung. Die nachstehenden relativen Quellpfade beziehen sich auf diesen Commit.

## Architektur

Uranus ist eine Go-HTTP-API mit Gin, pgx/pgxpool, PostgreSQL/PostGIS und integrierter
Pluto-Bildverwaltung. SQL-Dateien verwenden Schema-Platzhalter und gebundene PostgreSQL-Parameter.
Fachobjekte stehen in `uranus`; `event_projection` und `event_date_projection` sind abgeleitete
Lesemodelle. `RefreshEventProjections` aktualisiert abhängige Projektionen innerhalb vorhandener
Schreibpfade. Diese Nebenwirkungen gehören zu Uranus, nicht in eine zweite Python-Business-API.
Die Uranus-README nennt noch Vue3/`uranus-dashboard`; die aktuelle Nuxt-4-Zielarchitektur stammt
aus der Aufgabenstellung. Das Frontend wurde nicht untersucht.

## Maßgeblicher Abgleich mit dem Live-Backup

Der Betreiber stellte anschließend `uranus-26-09-14-030001.sql` bereit und bestätigte
**UTC als Speicherkonvention** für `timestamp without time zone`. Der Dump stammt laut Header
aus PostgreSQL 16.15 und enthält das Schema `uranus`, einschließlich Daten, Enums, Funktionen,
Indizes und Constraints. Für diese Umsetzung ist der Backup bei Schemaabweichungen maßgeblich.
Der Originaldump bleibt unverändert und ist durch `.gitignore` vom Projekt ausgeschlossen.

Die lokale Prüfung nutzte PostgreSQL 17/PostGIS auf Port 55439 in einer separaten Datenbank
`kulturbytes_admin_snapshot`. PostgreSQL-Owner des Produktivsystems wurden beim lokalen Import
ausgelassen; Domain-Daten einschließlich COPY-Bytes und Timestamps blieben unverändert.
Außerhalb des Dump-Schemas benötigte Erweiterungen PostGIS, pg_trgm, pgcrypto und unaccent
wurden nur lokal bereitgestellt. Kein Restore in eine laufende Uranus-Instanz.

Ergebnisse des Schemaabgleichs:

- Die neun verwendeten Tabellen und sämtliche abgefragten Spalten stimmen mit dem Query-Vertrag überein.
- `organization.member_of_orgs` ist nur im Repository-DDL vorhanden, **nicht im Live-Backup**.
  Das Feld wird von keiner implementierten Abfrage verwendet. Eine spätere Qualitätsregel
  dafür darf nicht auf diesem Backup-Schema vorausgesetzt werden.
- Die sieben Release-Enum-Werte sind vollständig bestätigt. Auch Price-/Ticket-Enums
  stehen im Dump; die Testfixture übernimmt sie vollständig statt vermuteter Teilmengen.
- Partneranfragen besitzen weiterhin keine FKs; Membership/Partner bleiben Paar-Identitäten.
  `event_date.event_uuid` bleibt nullable. Es wurde keine globale Adminrolle entdeckt.
- Der widersprüchliche `venue.scope`-Default ist auch im Backup bestätigt.
- `update_modified_at()` setzt CURRENT_TIMESTAMP. Es gibt weiterhin keinen belegten Login-
  oder Einladungsannahmezeitpunkt.
- Alte Funktionen `check_event_date_space_venue` und `set_default_event_date_venue`
  referenzieren noch Integer-/`*_id`-Spalten, sind im Dump aber **nicht als Trigger registriert**.
  Sie belegen daher keine aktive zusätzliche Venue-/Space-Validierung.
- Der registrierte Event-Suchtrigger verwendet `unaccent_immutable` außerhalb des exportierten
  Schemas. Die Lesefunktionen benötigen diese Funktion nicht; ein eigenständiger vollständiger
  Uranus-Schreibbetrieb lässt sich aus diesem Schema-Backup allein nicht herstellen.

Die CI-Schemafixture ist jetzt ein reiner DDL-Ausschnitt dieses Backups: neun Tabellen,
Enums, Constraints, Indizes, keine Produktionszeilen/Owner/ACLs und keine Suchtrigger.

Lesender API-Abgleich am 14.09.2026 um ca. 12:05 UTC mit eigenem SELECT-Account:

| Messung im Backup-Snapshot | Ergebnis |
| --- | ---: |
| Venues / Events / Event Dates insgesamt | 240 / 564 / 991 |
| Venue-Befunde ohne Geoposition | 6 Warnungen |
| Davon mit baldigen veröffentlichten Terminen | 0 |
| Neue Datensätze im damaligen 7d-Fenster | 76 |
| Davon Org / Venue / Space / Event / Termin | 5 / 2 / 0 / 12 / 15 |
| Davon User / Partneranfrage / Membership / Bild | 6 / 3 / 8 / 25 |
| Neue Datensätze today / 24h | 0 / 0 |
| Bilder ohne created_at | 0 |

Alle fünf implementierten GET-Endpunkte lieferten 200; beide Befundlisten meldeten dieselben
sechs Ergebnisse, bestätigt durch eine unabhängige direkte NULL/EMPTY-Zählung.
EXPLAIN ANALYZE der Qualitätsquery: sechs Zeilen, Planung ca. 0,58 ms, Ausführung ca. 0,92 ms
im lokalen Snapshot. Diese Werte beschreiben den Backup und den konkreten Abfragezeitpunkt,
nicht den späteren Livezustand oder eine Produktions-Performancegarantie.

## Identitäten, Beziehungen und Zeitfelder

Quelle: `ddl/<Tabellenname>.ddl`. `created_at` ist jeweils `timestamp without time zone`,
mit `CURRENT_TIMESTAMP` als Default, soweit nicht anders vermerkt.

| Tabelle | Schlüssel | Beziehungen | Zeitfelder / Einschränkungen |
| --- | --- | --- | --- |
| `organization` | `uuid` PK | created/modified_by → user; holding_org_uuid → organization, SET NULL | created_at NOT NULL; modified_at nullable; member_of_orgs ist JSONB ohne belegte Struktur |
| `venue` | `uuid` PK | org_uuid NOT NULL → organization CASCADE; Ersteller/Bearbeiter → user | created_at NOT NULL; modified_at nullable; opened_at/closed_at DATE |
| `space` | `uuid` PK | venue_uuid NOT NULL → venue CASCADE; Org indirekt über Venue | created_at NOT NULL; modified_at nullable |
| `event` | `uuid` PK | org_uuid NOT NULL → organization CASCADE; venue_uuid/space_uuid nullable, SET NULL | created_at NOT NULL; modified_at nullable; release_date DATE |
| `event_date` | `uuid` PK | event_uuid nullable → event CASCADE; venue_uuid/space_uuid nullable, SET NULL | created_at NOT NULL; modified_at nullable; start_date NOT NULL, optionale start_time/end_date/end_time/entry_time, duration/all_day |
| `user` | `uuid` PK; email/username unique | keine belegte globale Rolle | created_at NOT NULL; modified_at nullable; is_active boolean; kein last_login_at/activated_at |
| `organization_member_link` | UNIQUE(org_uuid,user_uuid), kein separater PK | beide FKs; invited_by_user_uuid → user SET NULL | created_at NOT NULL; modified_at/invited_at nullable; has_joined NOT NULL; kein joined_at |
| `organization_partner_request` | UNIQUE(from_org_uuid,to_org_uuid), kein separater PK | im Export keine FKs zu Org/User | created_at NOT NULL; status Text default pending; kein Entscheidungszeitpunkt |
| `organization_access_grants` | UNIQUE(src_org_uuid,dst_org_uuid), beide nullable | Org-FKs CASCADE; permissions bigint | keine Zeitstempel; Export führt FKs doppelt auf |
| `user_organization_link` | kein PK/unique-Paar | user_uuid/org_uuid NOT NULL mit FKs; permissions bigint | keine Zeitstempel; Mehrfachzuordnungen möglich |
| `user_venue_link`, `user_space_link`, `user_event_link` | im DDL keine eindeutige Paar-Constraint | direkte Benutzerrechte auf jeweiliges Objekt | keine Auditzeitpunkte |
| `pluto_image` | `uuid` PK | created_by → user SET NULL | created_at und modified_at nullable; expiration_date DATE |
| `pluto_image_link` | UNIQUE(context,context_uuid,identifier) | pluto_image_uuid nullable FK; context_uuid polymorph ohne Ziel-FK | kein Zeitstempel |

`organization`, `venue`, `space`, `event`, `event_date`, `user`, Membership und Pluto Image
haben im DDL Update-Trigger für `modified_at`. Die Repository-Exporte beschreiben die Funktion nicht; der Live-Backup bestätigt
`NEW.modified_at = CURRENT_TIMESTAMP`. Es gibt keine belegte Änderungshistorie.

**Nicht ableitbar:** Login-Aktivität aus `user.modified_at`, Einladungsannahme aus Membership-
`created_at`, Bildzuordnungszeit aus Bild-`created_at`, Ablehnungshistorie gelöschter Partneranfragen.
`sql/admin-get-org-members.sql` benennt die ersten beiden Werte irreführend als
`last_active_at`/`joined_at`; diese Aliase werden nicht übernommen. Neue Termine eines alten
Events sind eigenständige neue Datensätze. NULL-Zeitstempel werden nicht ersetzt oder sortiert.

## Events, Veröffentlichung und effektiver Ort

`event.release_status` hat Default `draft`, `event_date.release_status` Default `inherited`;
beide verwenden `uranus.event_release_status`. Die Repository-DDLs exportieren den Enum nicht; der nachgereichte Live-Backup bestätigt vollständig: `draft`, `review`, `inherited`, `released`, `cancelled`, `deferred`,
`rescheduled`. Die Schemafixture übernimmt diese Werte aus dem Backup.

Venue je Termin: `COALESCE(event_date.venue_uuid, event.venue_uuid)`.
Keine Ableitung aus einem Space und keine Gleichsetzung von Event- und Venue-Organisation.
Partnernutzung über Organisationsgrenzen ist fachlich vorgesehen.

Effektiver Release-Status: Terminstatus, außer NULL/`inherited`, dann Eventstatus.
`sql/get-events-projected.sql` filtert den **Elternstatus** auf
`released`, `cancelled`, `deferred`, `rescheduled`; nicht einfach nur auf den effektiven Status.
Damit ist eine einzelne Terminfreigabe bei einem Draft-Elternevent kein Beleg für öffentliche
Sichtbarkeit. `release_date` wird dort nicht als zusätzliche Schranke verwendet.

**Widerspruch bei Spaces:** `sql/get-events-projected.sql` erbt mit
`COALESCE(edp.space_uuid, ep.space_uuid)`. `sql/get-event-dates.sql` verwendet dagegen
bei gesetztem Termin-Venue ausschließlich `ed.space_uuid`, sonst `e.space_uuid`.
Die Projektionsroutine speichert die rohen Termin-Overrides. Die Venue-Regel benötigt keine
Space-Auslegung; eine künftige Raumkonsistenzregel braucht vorher einen einheitlichen Vertrag.

Die erste Regel verwendet folgende ausdrücklich festgelegte Reporting-Semantik:

- „Kommend“: Startdatum nach dem heutigen Event-Kalendertag, oder heute mit noch nicht
  vergangener Startzeit. Ganztägige Termine und Termine ohne Uhrzeit bleiben heute enthalten.
  Bereits begonnene mehrtägige Veranstaltungen werden nicht als „kommend“ gezählt.
- `EVENT_TIMEZONE` (initial Europe/Berlin) ist eine Reporting-Einstellung, keine aus dem Schema
  belegte Zeitzone pro Veranstaltungsort. DST-Doppelstunden lokaler Terminzeiten sind nicht eindeutig.
- Alle kommenden Termine zählen in `upcoming_event_date_count`, auch Entwürfe und Absagen.
- Für erhöhte Veröffentlichungsrelevanz müssen **Elternstatus und effektiver Terminstatus**
  `released` oder `rescheduled` sein. `cancelled`/`deferred` können öffentlich angezeigt werden,
  werden konservativ nicht als bevorstehende Durchführung gewertet.
- „Bald“: Startdatum im halboffenen Bereich `[heutiges Datum, heutiges Datum + UPCOMING_DAYS)`;
  Default 14. Zusätzliche Uhrzeitprüfung wie oben. Das sind Kalendertage, kein 336-Stunden-SLA.

Diese Semantik bewertet Handlungsbedarf; sie behauptet keine identische Sichtbarkeit in jedem
Portal, dessen zusätzliche Filter hier nicht ausgewertet werden.

## Authentifizierung und Autorisierung

Quellen: `app/utils.go`, `app/middleware.go`, `api/admin_login.go`, `app/permissions.go`,
`sql/admin-get-user-org-permissions.sql`, `sql/admin-get-user-effective-venue-permissions.sql`,
`sql/admin-get-user-event-permissions.sql`, `uranus-api.go`.

Uranus verwendet HS256-JWTs mit `user_uuid`, `token_type`, `iat`, `exp`.
Login prüft Passwort und `is_active`; Refresh prüft `token_type=refresh` und aktive User.
Die Middleware akzeptiert Bearer oder Cookie `access_token`, beschränkt auf HS256,
fordert `token_type=access` und nicht leere User-UUID. Sie prüft den aktiven DB-Status nicht
bei jeder Access-Token-Verwendung. Ausgestellte Tokens enthalten keine belegten Rollen,
Scopes, Audience oder Issuer; insbesondere keinen Systemadmin-Claim.

Organisationsrechte sind bigint-Bitmasken (z.B. Teamverwaltung Bit 6, Event bearbeiten Bit 25,
Event freigeben Bit 27). Die Organisationsrechteabfrage verlangt `has_joined=true`.
Venue-Rechte kombinieren direkte und Organisationsrechte per bitweisem OR; die untersuchte
Venue-Abfrage verlangt dabei keinen Membership-Join. Die Eventabfrage liest Organisationsrechte
ebenfalls ohne Membership-Join. `LIMIT 1` bei nicht eindeutig abgesicherten Rechtepaaren kann
Mehrfachzeilen verdecken. Die Auth-Middleware allein ist keine systemweite Autorisierung.

Keine explizite Superadmin-/Systemadmin-Rolle im untersuchten Code/DDL gefunden. Org-Rechte
dürfen nicht zu globalen Rechten hochgestuft werden. Deshalb Meilenstein 1: zentrale Dependency,
produktiver Zugriff gesperrt, nur expliziter Development-Override. JWTs wären mit dem gemeinsamen
HS256-Schlüssel technisch prüfbar; dieser gibt dem Admin-Dienst aber auch Signierfähigkeit.
Für Meilenstein 2 bevorzugt einen Uranus-Verifikations-/Autorisierungsvertrag oder asymmetrische
Signaturen prüfen; Rollenprüfung und aktuelle Deaktivierung gehören in diesen Vertrag.

## Team und Partner

`api/admin_org_team_invite.go` verwendet Einladungs-JWTs und Membership-Status; das ist keine
globale Admin-Berechtigung. Mitgliedschaft und Rechte werden getrennt gespeichert.
Offene Einladung bedeutet `has_joined=false`, deren Alter ggf. `invited_at`; ein NULL-Wert
bleibt unbekannt. Welche Einladungen „alt“ sind, ist eine offene Produktentscheidung.

Partneranfragen A → B werden durch `api/admin_insert_org_partner_request.go` angenommen,
indem ein Grant `src_org_uuid=B`, `dst_org_uuid=A`, `permissions=0` angelegt wird. Nullrechte
sind dabei bewusst zulässig. Ablehnen löscht die Anfrage. Relevante Handler enthalten noch
TODOs zur Rechteprüfung. Neue Admin-Schreibaktionen müssen diese Pfade vor Wiederverwendung
prüfen und nötige Korrekturen in Uranus vornehmen; die Existenz eines Endpoints belegt nicht
automatisch eine vollständige Absicherung.

## Validierung und Bilder

`app/validate.go`: optionale nicht leere Strings, URLs, Datums-/Zeitformate.
`ValidateOptionalUrl` trimmt, fordert Schema/Host und ein case-sensitives `http://`/`https://`-
Präfix. Es ist kein flächendeckend durchgesetzter Schreibvertrag. Event-Erstellung prüft u.a.
Source-/Online-Link, Sprache, Kapazität, Release-Status und Termine; Feld-Updates für Org/Venue
und Event-Links verwenden den Validator nicht durchgehend. Event-Date-Updates validieren
teilweise nur Pflichtwerte; ältere registrierte Handler enthalten noch `event_id`/`venue_id`/`id`
statt der heutigen UUID-Spalten (`admin_upsert_event_date.go`, `admin_update_event_release.go`).
Diese Pfade sind vor späteren Domain-Aktionen einzeln zu prüfen, nicht blind zu proxyen.

Pluto enthält Dateinamen, MIME, Maße, Alt-Text, Beschreibung, EXIF, Urheber/Lizenz, Fokus und
AI-Label. Die polymorphen Links benötigen Kontext-/Identifier-Prüfung und einen Existenzabgleich.
Der generische Upload-Handler unterstützt Org/Venue/Event/Portal; Space ist dort auskommentiert.
Eine DB-Zeile beweist keine existierende Datei. Meilenstein 1 ruft keine URLs oder Bilddateien ab.

## PostgreSQL/PostGIS und Performance

`venue.point` ist `geometry(Point,4326)`, nullable. `ST_IsEmpty` ergänzt die NULL-Prüfung.
`venue.building` ist `geometry(Geometry,4326)`, Organisationen besitzen ebenfalls einen Punkt.
SQL-Abfragen nutzen ST_X/ST_Y und Projektionen. Ein SRID belegt keine geographische Plausibilität;
fehlende Geoposition bleibt eine Warnung, kein automatisch unbrauchbarer Datensatz.

Vorhandene relevante Indizes: Venue-PK und GiST(point), Event-PK und venue_uuid/release_status,
Event-Date-PK und event_uuid/venue_uuid. In den Exporten fehlen insbesondere created_at-Indizes,
event_date.start_date und verbreitete org_uuid-/space.venue_uuid-Indizes.
GiST(point) ist kein Garant für einen schnellen NULL/EMPTY-Scan.

Die Qualitätsquery aggregiert Termine genau einmal nach effektivem Venue; keine N+1-Abfragen,
keine Bild-/Mitgliedschafts-Joins, die Zähler vervielfachen. Count/Page laufen im selben
REPEATABLE READ-Snapshot. Live-Queries scannen für Count und Page zweimal; bewusst kleiner
Start ohne Cache. Bei großen Datenmengen persistente Prüfläufe und tatsächliche Pläne prüfen.

Nach ausdrücklicher UTC-Bestätigung durch den Betreiber vergleichen Zeitfilter direkt
`created_at >= :start_at AND created_at < :end_at` gegen naive UTC-Grenzen. Dadurch bleiben
normale created_at-Indizes nutzbar, sofern vorhanden. Nur für abweichend konfigurierte lokale
Speicherzeitzonen verwendet der Fallback `created_at AT TIME ZONE :source_timezone`. Eine lokale Zeit während der Herbst-Doppelstunde kann ohne
Offset grundsätzlich nicht eindeutig rekonstruiert werden.

Der Integrationstest führt `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` gegen Minimalfixtures aus.
Das prüft die Ausführbarkeit; es ist keine belastbare Produktionskapazitätsmessung. Kein Uranus-
Index wurde verändert. Konkrete spätere Kandidaten stehen in
[future-uranus-improvements.md](future-uranus-improvements.md).

## Nachprüfung und Umsetzung des Reviews

Die Nachprüfung gegen aktuellen Remote-dev **733c54133362460353400eb96c60a0cdb9f8450a**,
implementierte Regeln sowie verbliebene Unsicherheiten stehen in
[source-verification.md](source-verification.md). Die ursprünglichen Aussagen dieses Dokuments
über geplante Activity-/Persistenzfunktionen beschreiben den früheren Stand; aktuelle API-,
Prioritäts-, Historien- und Autorisierungsverträge stehen in [contracts.md](contracts.md).
Die öffentliche COALESCE-Space-Vererbung wird jetzt ausdrücklich als eigener geprüfter
Darstellungspfad bewertet, ohne eine Vereinheitlichung der Uranus-Handler zu behaupten.
