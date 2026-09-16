# Admin-Verträge nach Review (2026-09-14)

Fachliche Referenz: [Uranus-Empfehlung](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/docs/admin-dashboard-empfehlung.md).
Quellabgleich: [dev-Verifikation](source-verification.md). Der OpenAPI-Snapshot liegt unter
`frontend/docs/openapi.json`; Pydantic und Zod bilden den gleichen Antwortvertrag ab.

## Finding Identity Contract

`entity_key` ist ein nicht leerer String (max. 1024 Zeichen), kein universeller UUID-Typ.
Venue/Event/Org/Space/User/Date/Image verwenden ihre kanonische UUID-Zeichenfolge;
Event-Links ihre dezimale ID, Lizenzen ihren Textschlüssel. Zusammengesetzte Schlüssel:

- Partner: `partner-request:<from_org_uuid>:<to_org_uuid>`.
- Membership: `membership:<org_uuid>:<user_uuid>`.
- Image-Link: `image-link:<context>:<context_uuid>:<identifier>`; Textbestandteile percent-encoded.

Finding-ID: `rule:entity_type:entity_key:field`, wobei jeder Bestandteil separat percent-encoded
wird (UTF-8; RFC-3986-unreserved bleiben unverändert). Dadurch kollidieren Doppelpunkte und
Prozentzeichen innerhalb von Schlüsseln nicht mit Trennzeichen. Bestehende Venue-Finding-IDs
bleiben bytegleich, beispielsweise `venue_missing_geolocation:venue:<uuid>:point`.

`entity_id` bleibt als **deprecated**, nullable UUID-Ausgabealias erhalten: bei UUID-Schlüsseln
die bisherige UUID, sonst NULL. Neue Clients müssen `entity_key` verwenden; alte Clients können
nicht sämtliche neuen Objektarten als UUID lesen. Die bestehende TEXT-Spalte heißt physisch
weiter `admin.finding.entity_id`, SQLAlchemy verwendet dafür den Key `entity_key`. Kein Rename,
keine Datenumschreibung und keine Cross-Schema-FKs sind für diese Umstellung nötig.

Organisation/Name dürfen NULL sein, wenn keine eindeutige oder existente Zuordnung belegt ist.
Eine fehlende Organisation wird nicht erfunden. Ein Finding ohne bekannte Adresse hat ein leeres
Adressobjekt mit NULL-Feldern. Nicht ereignisbezogene Regeln haben keine Terminanzahlen.

## Priority Contract

Diskrete Priorität (kleiner ist wichtiger):

| priority | Bedeutung |
| --- | --- |
| 1 | Fehler, veröffentlicht und bald |
| 2 | Fehler, veröffentlicht |
| 3 | Sonstige Fehler |
| 4 | Warnung mit kommenden Terminen |
| 5 | Sonstige Warnung |
| 6 | Hinweis |

`priority_score = (7 - priority) * 1000 + 200 * published + 400 * published_soon + 100 * upcoming_dates`.
Höhere Scores stehen zuerst, danach die lexikographische stabile Finding-ID. Kein zusätzlicher
Sortierschlüssel aus der Regel, der Anzahl betroffener Termine oder einem erfundenen Erstfund.
Venue-SQL und Python verwenden dieselben zentralen Gewichte. Der diskrete Wert bleibt für alte
Clients erhalten; `priority_reasons` enthält `severity_error`, `severity_warning` oder `severity_info`
sowie die zutreffenden Gründe `published`, `published_soon`, `upcoming_dates`.

Veröffentlichung setzt für Termine sowohl freigegebenen Elternstatus als auch effektiven
Terminstatus voraus (`released`/`rescheduled`; `inherited` erbt). „Bald“ und „kommend“ verwenden
die bestehende Reporting-Zeitzone und das exklusive `UPCOMING_DAYS`-Ende. Venue-/Space-/Org-URLs
verwenden die betroffenen kommenden Termine. Event-URLs berücksichtigen den Eventstatus.
`urgent_findings` zählt Priorität 1/2 sowie Findings mit `published_soon`, regelübergreifend.

## Action Contract

`action` ist nullable. Angeboten werden nur **view**-Ziele auf vorhandene Admin-Seiten:
`activity`, `partner_requests`, `team_invitations`, `user_activation`. Die API erzeugt `href`
selbst aus Route und kodiertem Schlüssel; Activity-Ziele enthalten zusätzlich `entity_type`.
Zod vergleicht den gesamten Link mit der aus den strukturierten Feldern berechneten URL.
Beliebige URLs, fremde Origins, Query-Erweiterungen und erratene Domain-Edit-Routen werden abgelehnt.
Venue und Event öffnen die Activity-Detailauswahl. Für License/Event-Link/Image-Link fehlen eigene
Oberflächen, daher NULL. Edit-Ziele bleiben bis zu einer autorisierten Uranus-Anbindung ausgesetzt.
Bilder ohne Erstellungszeitpunkt bleiben in der separaten undatierten Liste, ohne falschen Zeitlink.

## Activity Timestamp Semantics

`GET /api/v1/dashboard/activity` liest ausschließlich Neuanlagen aus neun Quelltabellen.
`entity_type`: `organization`, `venue`, `space`, `event`, `event_date`, `user`, `partner_request`,
`team_membership`, `image`. Alle Filter werden serverseitig angewendet, Werte SQL-gebunden.

- `period=today|24h|7d`: wie Summary. Today beginnt um lokale Mitternacht; 24h/7d sind echte
  gleitende 24/168 Stunden. Ohne Zeitfilter Standard 24h.
- Alternativ `from_at`/`to_at` mit Offset, Intervall `[from_at,to_at)`. Kein Mischen mit `period`.
- `entity_type`, `entity_key`, `organization_id`, `page`, `page_size` (max. 100).
- `entity_key` ohne Zeitfilter sucht über alle bekannten Zeitpunkte und ermöglicht Direktlinks.
- `timestamp_state=unknown` liefert nur NULL-Zeitpunkte, nach Typ/Schlüssel geordnet; Zeitfilter
  werden dabei mit 422 abgelehnt. `unknown_timestamp_count` zählt die undatierten Objekte im
  gewählten Objekt-/Organisationsfilter unabhängig vom datierten Zeitfenster.
- Datierte Liste: `created_at DESC, entity_type, entity_key`. Count und Seite teilen den
  read-only REPEATABLE READ-Snapshot. Separate Seitenabrufe können gleichzeitige Neuanlagen sehen;
  Offset-Pagination behauptet keinen über mehrere Requests festgehaltenen Snapshot.

Source-Zeitzone ist getrennt von Reporting-Zeitzone. UTC war vom Betreiber bestätigt und bleibt
Default; abweichende Installationen müssen den Speichervertrag explizit konfigurieren.
Naive Quelldaten werden damit nach timestamptz umgerechnet. Eine lokale DST-Doppelstunde bleibt
bei unbekanntem ursprünglichem Offset grundsätzlich mehrdeutig.

Membership-`created_at` heißt weiterhin **created_at**, niemals joined_at. Partnerstatus beschreibt
den jetzigen Zustand, keinen Entscheidungszeitpunkt. User-`modified_at` wird gar nicht selektiert;
es gibt weder last_login noch last_active. NULL-Bildzeitpunkte werden nicht ersetzt.

Orgfilter: direkte Eigentümer, Space über Venue, Termin über Event, Partner über beide Seiten,
User über vorhandene Memberships, Bilder über Org-/Venue-/Event-Bildlinks. User und mehrfach nutzbare
Bilder erhalten keine willkürlich ausgewählte Eigentümerorganisation. Portal-Bildzuordnungen sind
wegen des ungeklärten Zielschemas nicht Teil dieses Orgfilters.

## Operational Queues

`GET /api/v1/work-queues/{partner_requests|team_invitations|user_activation}` mit Org-/Schlüssel-/
Status-/Mindestalterfilter und Pagination. Alter absteigend, unbekanntes Alter separat zuletzt,
danach Entity-Key; die Anzeige nennt `age_basis`.

Partnerliste enthält alle aktuellen Anfragen, optional Statusfilter. Nur `pending`/`accepted`
sind durch aktuellen Handlercode belegt. Grant für Anfrage A → B wird in Richtung B → A geprüft.
Nullrechte gelten nicht als Fehler. Accepted ohne Grant ist ein Hinweis, weil der Grant später
entfernt worden sein könnte. Gelöschte Ablehnungen werden nicht rekonstruiert.

Einladungsliste enthält `has_joined=false`; Alter nur aus `invited_at`, bei NULL unbekannt.
Aktivierungsliste enthält `is_active=false`; Alter nur aus `created_at`, keine Inaktivitätsaussage.
Zukünftige Zeitpunkte erhalten kein künstliches Alter 0, sondern unbekanntes Alter.
Schwellen: `PENDING_AGE_DAYS=14`, `ACTIVATION_AGE_DAYS=7`, jeweils strikt älter als die Schwelle.
Scans decken auch beigetretene Memberships und aktive User ab, damit erledigte Zustände durch
Recheck auflösbar sind, obwohl sie nicht mehr in den offenen Vorgangslisten stehen.

## Check Run / Resolve Semantics

`POST /api/v1/check-runs` führt einen vollständigen synchronen Scan durch. `GET /api/v1/check-runs`
listet Läufe mit Start/Ende, Status, Regel-/Befundzahl und sanitisiertem Fehlertext. Erfolgreiche
Läufe speichern pro Regel die konkret erfassten `(entity_type,entity_key)`-Paare in `rule_results`.
Ein GET auf die Live-Findings speichert weiterhin nichts.

Ablauf: exklusiven PostgreSQL-Advisory-Lock erwerben, running-Zeile committen, separate read-only
Domain-Transaktion auswerten, dann Findings und erfolgreichen Laufabschluss in **einer**
Admin-Transaktion committen. Gleichzeitige Scans/Reviews erhalten 409. Bei Prozessabbruch bleibt
ein running-Lauf zurück; der nächste Lockinhaber markiert ihn als fehlgeschlagen. Daraus folgt
keine automatische Behebung. Ein HTTP-Timeout ist ebenfalls kein Beleg, dass ein Lauf abgeschlossen ist.

Ein Scanfehler bricht die gesamte Übernahme ab. Bereits ausgewertete Teilregeln werden nicht als
Gesamterfolg ausgegeben; bestehende Findings bleiben unverändert. Ein Lauf muss genau die vollständige erwartete Regelmenge erfolgreich liefern; auch eine
leere oder abgeschnittene Ergebnisliste gilt als fehlgeschlagen. Der Persistenzbaustein
verweigert Resolution zusätzlich, sobald ein RuleResult fehlgeschlagen ist. Das ist bewusst konservativer
als ein Teilabschluss einzelner Regeln.

Ein Finding wird nur resolved, wenn der ganze Lauf erfolgreich war, seine konkrete Regel erfolgreich
war, sein Objekt in deren Coverage steht und die Finding-ID nicht erneut erzeugt wurde. Nicht
mehr vorhandene Objekte werden ohne belegte Coverage **nicht** automatisch geschlossen.
Upsert anhand der stabilen ID bewahrt first_seen_at. last_seen_at wird bei erneuter Beobachtung
aktualisiert; resolved_at nur bei belegter Behebung. Wiederkehrende Fehler öffnen dieselbe ID erneut.
Keine rückdatierte Historie, kein Ersatz von Source-Timestamps durch Scanzeitpunkte.

`GET /api/v1/findings` verwendet standardmäßig `mode=persisted`: gespeicherte Beobachtungen
und Zustände, mit SQL-seitigen Filtern, Sortierung, COUNT und Pagination. Nur explizites
`mode=live` startet einen vollständigen Diagnose-Scan ohne Persistierung. Die UI nutzt
gespeicherte Befunde; eine Live-Diagnose muss im Quellenfilter gewählt werden. Ohne
`ADMIN_DATABASE_URL` liefert der Standardabruf 503 `admin_storage_unconfigured`, ohne
stillschweigenden Live-Fallback. Historische Daten werden nicht als frischer Live-Scan ausgegeben. Es gibt
aktuell eine Zeile pro Finding plus Run-Coverage, **kein vollständiges Ereignisjournal jeder
Feldänderung oder jedes früheren Reviews**.

## Review Workflow

`PATCH /api/v1/finding-reviews` mit `finding_id`, `status` und optionalen Metadaten.
Zulässige menschliche Ziele: `open`, `in_progress`, `snoozed`, `exception`. Snooze braucht ein
zukünftiges aware `snoozed_until`; Ausnahme einen nicht leeren `exception_reason`.
`assigned_to` muss ein existierender Uranus-User sein, ohne dadurch Rechte zu erhalten.
Kommentar und Grund sind begrenzt. `resolved` kann nicht manuell gesetzt werden; bereits resolved
Findings werden erst durch einen erneuten Befund geöffnet.

`reviewed_subject` speichert den authentifizierten Principal. Der Development-Principal heißt
`development-only`, ist kein Uranus-User und erzeugt deshalb kein erfundenes `reviewed_by`-UUID.
`reviewed_at`, assigned_to, comment und Reviewgrund bleiben dokumentierte Metadaten.
Ändert ein Review die Zuweisung/den Kommentar nicht explizit, bleiben diese erhalten.

Alte Foundation-Werte `reviewed` und `ignored` bleiben lesbar: reviewed bedeutet menschlich gesichtet,
ignored eine frühere Unterdrückung, beides kein fachlicher Behebungsbeleg. Neue Reviews verwenden
die oben genannten Zustände. Alle Zustände bleiben ohne Statusfilter sichtbar. Abgelaufene Snoozes
öffnen beim nächsten erfolgreichen Recheck; relevante Änderungen der Finding-Evidenz öffnen
Ausnahmen/ignored erneut. Aging allein ist keine Änderung; Quellfingerprints vermeiden das
Speichern roher ungültiger URL-Werte. Die aktuelle Review-Metadatenzeile ersetzt kein Auditlog.

## Markierungen und Notizen an Datensätzen

Markierungen sind unabhängige menschliche Anliegen in `admin.record_mark`; mehrere Anliegen
pro Datensatz sind möglich. Sie benötigen keinen gespeicherten Prüflauf und verändern keine
Uranus-Daten oder automatische Finding-Prioritäten. Unterstützt sind alle neun Activity-Typen
sowie `event_link`, `license` und `image_link` mit deren bestehenden stabilen Schlüsseln.
Beim Anlegen wird die Quelle auf Existenz geprüft und ihr Anzeigename als Momentaufnahme
gespeichert. Auch Datensätze ohne Erstellungszeitpunkt lassen sich markieren. Bestehende
Markierungen bleiben bei gelöschter oder nicht erreichbarer Quelle lesbar und bearbeitbar.

- `GET /api/v1/record-marks`: Liste; Filter `entity_type`, `entity_key`, `status`, `urgency`,
  `reason`, `sort`, `page`, `page_size`. Standardstatus `active` umfasst offen und in Bearbeitung;
  `all` enthält auch erledigte Anliegen. Sortierung `urgency` ordnet dringend, hoch, normal,
  danach Erstellungszeit absteigend und UUID; alternativ `newest`.
- `POST /api/v1/record-marks`: `entity_type`, `entity_key`, `reasons`, optional `reason_detail`,
  `urgency` (Standard `normal`) und `note`; Antwort 201 mit Markierung und Verlauf.
- `GET /api/v1/record-marks/{uuid}`: Markierung einschließlich chronologischem Verlauf.
- `PATCH /api/v1/record-marks/{uuid}`: aktuelle `version`, `reasons`, `reason_detail`,
  `urgency`, `status` und optional eine **neue** `note`. Status: `open`, `in_progress`, `done`.
  Ein veralteter Stand liefert 409 `mark_conflict`, ohne Änderungen oder zusätzliche Notiz.

Gründe (Mehrfachauswahl, mindestens einer, ohne Duplikate): `questionable_content`, `low_quality`,
`incorrect`, `incomplete`, `outdated`, `duplicate`, `spam`, `unsuitable`, `rights_privacy`,
`technical`, `other`. `other` erfordert eine Erläuterung. Erläuterungen sind auf 2000,
Notizen auf 4000 Zeichen begrenzt; reine Leerzeichen sind kein Inhalt.

Beim Übergang nach `done` setzt der Server `completed_at` und `completed_by` aus Serverzeit
und authentifiziertem Principal. Weitere Notizen ändern diese Abschlussangaben nicht.
Wiederöffnung nach `open` oder `in_progress` leert die aktuellen Abschlussfelder; frühere
Abschlüsse samt Autor, Zeitpunkt und Abschlussnotiz bleiben im Verlauf erhalten. Eine erneute
Erledigung erhält neue Abschlussangaben. Andere Anliegen desselben Datensatzes bleiben unverändert.

Jede Änderung fügt atomar einen Eintrag in `admin.record_mark_event` hinzu: Version, Autor,
Zeitpunkt, Art (`created`, `updated`, `completed`, `reopened`), optionale Notiz und damalige
Gründe, Erläuterung, Dringlichkeit sowie Status. Die API bietet kein Überschreiben oder Löschen
alter Einträge. Änderungen ohne geänderte Felder oder neue Notiz erzeugen keinen Verlaufseintrag.
Clients dürfen Autoren, Zeitstempel und Ereignisse nicht vorgeben. Die Entwicklung verwendet
den vorhandenen Principal `development-only`; Production verwendet `admin:<eigene Konto-UUID>`.

Die Ablage benötigt Migration `0003` und die zusätzlichen Runtime-Grants aus
[development.md](development.md). Ohne Admin-Ablage liefern diese Endpunkte 503
`admin_storage_unconfigured`. Nuxt erlaubt ausschließlich die dokumentierten Methoden,
Filter und UUID-Pfade; Schreibdaten werden vor dem Weiterleiten validiert.

## Auth / Authorization Boundary

Alle Verwaltungsrouten verwenden dieselbe zentrale Admin-Dependency. Die eigenständige
Authentifizierung verwendet `admin.auth_account` und widerrufbare Sitzungen; ausschließlich
`admin.auth_system_admin` erteilt globale Rechte. Uranus-Identitäten, Organisationsrechte und
Uranus-Statusdaten werden dafür nicht verwendet. Ohne Credential 401, ungültige/abgelaufene
Sitzung oder inaktives Konto 401, aktives Konto ohne globale Vergabe 403 `admin_access_denied`.
Der vollständige [Auth-Vertrag](authentication.md) beschreibt Login/Logout, CSRF, Ablauf,
503-Fehler und die eigene Audit-Identität `admin:<UUID>`. Development-Override bleibt nur in
development/test erlaubt.

`DATABASE_URL` bleibt SELECT-only und erzwingt read-only REPEATABLE READ-Transaktionen.
Optionales `ADMIN_DATABASE_URL` ist eine eigene Rolle mit SELECT/INSERT/UPDATE ausschließlich auf
Admin-Tabellen. Vor Verwendung lehnt die Anwendung Superuser/CREATEROLE sowie vorhandene
Uranus-Schreibrechte (auch Spaltengrants) ab. Der Betreiber muss diese Rechte wirksam beschränken;
Migrationen verwenden unverändert eine separate Migrations-DSN. Es gibt keine Startmigration.

Nuxt erlaubt nur die bekannten GET-Routen sowie POST check-runs und PATCH finding-reviews.
Reviewbodies werden strikt mit Zod validiert. Nur das vorgesehene Sitzungscookie sowie Auth-/Origin-/CSRF-Header werden kontrolliert
weitergereicht; keine beliebigen Cookies/Headers, Redirects oder fremden Ziel-Origins. Bekannte API-Fehlercodes werden nur aus strengem JSON
mit zum Code passendem Status übernommen, niemals Rohmeldungen/Tracebacks. Timeout: 10 Sekunden
für Reads, 120 Sekunden für synchrone Admin-Schreibvorgänge; Browser wartet entsprechend länger.
CORS erlaubt diese Methoden nur für ausdrücklich konfigurierte Origins und Bearer-Header.
Keine Domain-Schreiboperation, automatische URL-Reparatur oder externe Dateiabfrage entsteht daraus.

## Ausführung und Grenzen

Live-Regeln und Arbeitslisten laden derzeit die benötigten Quellspalten in einen konsistenten
Snapshot und paginieren nach globaler Filterung/Sortierung. Das ist für den vorhandenen kleinen
Bestand nachvollziehbar, kein belegter Skalierungsbenchmark. Vor großen Installationen Querypläne,
Speicherverbrauch und Scanzeit messen; ggf. persistente Listen bevorzugen und SQL-Pagination
weiter ausbauen. Keine spekulativen Uranus-Indizes oder Constraints werden angelegt.
Scheduler, vollständiges Auditjournal, externe Erreichbarkeitschecks, Geocoding, Merges und
fachliche Edit-Endpunkte sind nicht enthalten.


## Operative GETs und Scan-Kosten

Auch `GET /api/v1/dashboard/summary` verwendet standardmäßig gespeicherte Qualität; nur
`mode=live` führt einen Vollscan aus. Die Neuanlagenzähler bleiben lesende Source-Aggregate.
Gespeicherte Qualitätszähler enthalten alle noch nicht `resolved` gesetzten Befunde einschließlich
Snooze/Exception; die Regelliste enthält die dort vertretenen Regeln. Ein leerer Speicher beweist
keinen sauberen Datenbestand. Prüfläufe und deren Status sind unter `/check-runs` sichtbar.
`observed_at` eines Listenabrufs ist dessen Abrufzeit, `last_seen_at` die tatsächliche Beobachtung.
Snoozes werden erst beim nächsten erfolgreichen Recheck geöffnet, nicht durch einen GET.

`POST /api/v1/check-runs` bleibt synchron (HTTP 200 mit abgeschlossenem Run). Der Proxy wartet
für Schreibaufrufe bis zu 120 Sekunden; Timeout/Verbindungsabbruch garantiert weder Abschluss
noch Abbruch. Vor erneutem Start den Laufstatus prüfen. Ein zusätzlicher aktiver Lauf/Review
wird mit 409 abgewiesen. Session-Locks werden im finally freigegeben; bei I/O-Fehler oder
Cancellation während Lock-Verwaltung wird die Verbindung aus dem Pool entfernt.

Der Kernscan liest weiterhin explizit ausgewählte Spalten vollständiger Quelltabellen. UUID-Indizes,
Termine je Event und aggregierte Relevanz je Event/Termin/effektivem Venue/Space/Organisation
entstehen einmal pro Snapshot. Danach benötigen Relevanzabfragen konstante Zeit; insbesondere
werden Termine nicht je Venue/Space/Organisation oder URL-Feld erneut durchlaufen. Indexaufbau, Relevanzarbeit
und Speicherbedarf wachsen linear mit Quelle und Befunden bei fester Regelanzahl; Sortierung
und Datenbankarbeit kommen hinzu. Im
Aktivierungs-Scan werden Organisationszuordnungen einmal in SQL gruppiert und stabil sortiert.

Work-Queue-GETs wenden Status-, Organisations-, Schlüssel- und Altersfilter, Sortierung,
COUNT/LIMIT/OFFSET in PostgreSQL an. Python erhält nur die angeforderte Seite. Sortierung bleibt
Alter in vollständigen Tagen absteigend, unbekanntes/zukünftiges Alter zuletzt, danach kanonischer
Schlüssel (C-Kollation). `invited_at` bleibt die Altersbasis für Einladungen; `created_at` für
Aktivierung beschreibt ausschließlich das Alter seit Erstellung. Grant-Richtung bleibt
`src=to_org_uuid`, `dst=from_org_uuid`. Vollscans lesen auch saubere/erledigte Queue-Zeilen,
damit deren Coverage für eine belegte Resolution erhalten bleibt.

Ein Background Worker (`POST → 202 + run_id`, `GET /check-runs/{id}`), Streaming/Batches für
sehr große Vollscans und produktive Lastmessungen sind Folgearbeit. Dieser PR führt weder
Worker noch neue Uranus-Indizes ein. PostgreSQL kann für COUNT/Sortierung weiterhin viele
Zeilen lesen; begrenzte API-Seitengröße ist keine konstante Datenbanklaufzeit.

## Activity previews and public links

Activity items optionally add `image_url`, `public_url`, `subtitle`, and `address` (nullable
strings). No full entity objects, email addresses, file paths or credentials are embedded.
The existing filters, pagination, `created_at`, `action.href` and unknown-timestamp semantics
are unchanged. Preview enrichment runs **after SQL pagination**, with one batch query for
all page identities: three existing count/page queries plus one enrichment query (zero for an
empty page). UUID joins retain the source UUID indexes; next-date lookup uses the existing
`event_date(event_uuid)` index. Reverse image contexts are aggregated once for the page.

| Type | Preview |
| --- | --- |
| organization | City and `main_logo`; no standalone public organization route is established |
| venue | Address, `main_photo` then `main_logo`, public venue link |
| space | Parent venue name; no invented image relation or standalone public route |
| event | Subtitle, next upcoming public-status date, `main` image; public link only when a supported date exists |
| event_date | Actual event date/time (unknown time stays unknown), effective venue/space, parent event image |
| user | Existing display name/username and activation status only |
| partner_request | Existing directed from/to names and status |
| team_membership | Existing user/organization, invited/joined status; optional explicitly labelled `invited_at`, never a fabricated joined timestamp |
| image | Image itself; linked name only if exactly one distinct context/target exists |

Public URL generation is enabled only when `URANUS_API_URL` identifies
`https://api.kulturbytes.de` (a trailing slash is accepted). This is an operator assertion that
the source data belongs to this public instance; local/unrelated snapshots get null URLs.
No network introspection or per-row HTTP requests are made. Missing/stale files use the UI's
icon fallback. Public images use `https://api.kulturbytes.de/api/image/<uuid>?width=160&ratio=1%3A1`.
Only established image identifiers are selected, not arbitrary stored URLs or file names.

Routing evidence inspected at implementation time:

- [Kulturbytes client ec8c059](https://github.com/sndcds/kulturbytes-client/tree/ec8c0597598d3ba0e404bc276493ba96cb25b8b2):
  `nuxt.config.ts` (`strategy: prefix`, German locale),
  `app/pages/venue/[venue_identifier].vue` → `/de/ort/<identifier>`,
  `app/pages/event/[event_uuid]/[date_identifier].vue` → `/de/veranstaltung/<event>/<date>`.
- [Uranus 12ec760](https://github.com/sndcds/uranus/tree/12ec7608d55aed3cf86724ce47d275f9d49e46b2):
  `sql/get-venue.sql` accepts a slug or UUIDv7; `api/api_utils.go` accepts UUIDv7 date identifiers.
  To avoid ambiguous/generated time slugs, unsupported date identifiers get no public link.
  `api/get_event.go` establishes public statuses released/cancelled/deferred/rescheduled;
  both event and effective date status must be public. Events without an upcoming public date
  get no link. Date time selection uses `EVENT_TIMEZONE`, not creation time.
- Uranus `api/api_image_helper.go`, `sql/get-event.sql` and Pluto v0.5.6 `RegisterRoutes`:
  organization/venue/event image links, UUID-based public GET route without auth middleware.
  No public space image relationship is assumed. Event-date venue overrides stop inheritance
  of the event-level space, matching the requested effective-location contract.

The frontend accepts only these fixed public origins/path shapes, uses lazy thumbnails with
anonymous CORS and no referrer, and opens public pages with `noopener noreferrer`. Internal
admin links continue to use `action.href`; RecordMarkLink remains available for every row.

A local `EXPLAIN (ANALYZE, BUFFERS)` on disposable PostgreSQL 17/PostGIS 3.5 with 1,000
additional events, 5,000 dates and 1,000 linked images enriched 50 selected events in
1.714 ms (planning 2.684 ms). The plan used `idx_event_date_event_uuid`,
`image_context_identifier_unique` and entity primary-key indexes. This is a synthetic
preview-query measurement, not a production latency promise or a benchmark of the existing
count/page queries. No production data or schema was changed.
