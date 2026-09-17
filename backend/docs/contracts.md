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

`POST /api/v1/check-runs` committet einen `queued`-Job und liefert HTTP 202 mit dessen UUID.
`GET /api/v1/check-runs` listet Läufe; `GET /api/v1/check-runs/{uuid}` liefert den aktuellen
Status (`queued`, `running`, `success`, `failed`), Zeiten, Regel-/Befundzahl und sicheren Fehlertext.
`started_at` ist die Einreihungszeit. Nur `success` belegt den atomar gespeicherten vollständigen
Scan. Der separate Worker hält den Source-Snapshot read-only. Ein HTTP-Abbruch beendet keinen Job.

Claim und Queue-Zugriff sind kurze PostgreSQL-Transaktionen. Eine partielle Unique-Constraint
(Index) erlaubt höchstens einen queued/running-Job. Der Worker erneuert eine befristete Lease;
seine zufällige Worker-ID dient als Fencing-Token bei der finalen Ergebnisspeicherung. Kein
Session-/Workflow-Lock wird während des Source-Scans gehalten. Erst die kurze Persistenzphase
serialisiert mit Reviews und liest deren **aktuellen** Workflow-Zustand. Kommentare, Zuweisungen,
Review-Autoren und Zeitstempel werden nicht durch Snapshotwerte überschrieben. Bestehende
Snooze-/Exception-Reopen-Regeln bleiben erhalten. Bei Lease-Verlust darf ein alter Worker keine
Findings speichern. Nach Crash markiert der nächste Worker abgelaufene running-Jobs als failed;
ein bewusst neuer Start ist erforderlich. Queued-Jobs bleiben über Restarts ausführbar.
Erfolgreiche Läufe speichern pro Regel die erfassten Entity-Schlüssel in `rule_results`.
Live-Findings-GETs speichern weiterhin nichts.

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
für alle Upstream-Aufrufe; Browser wartet maximal 12 Sekunden. Scans laufen im separaten Worker.
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

Check-Start und Statusabfrage benötigen keinen langen HTTP-Timeout: Nitro 10 Sekunden,
Browser 12 Sekunden. Doppelter Start liefert 409. Reviews sind während der Scanphase möglich;
nur konkurrierende kurze Review/Persistenzphasen können einen Review-Konflikt erzeugen.
Die UI pollt aktive Läufe alle zwei Sekunden und beendet Polling bei Abschluss, Fehler,
Auth-Verlust oder Verlassen der Seite. Ein queued-Job ohne laufenden Worker bleibt queued.

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
strings). `email` is an additional nullable string, deliberately exposed **only for user
items in this system-admin-protected response**, as requested for account administration.
Other entity types do not expose user email, including membership rows. No full user objects,
password hashes, activation tokens, file paths or credentials are embedded.
`location` is an optional nullable `{latitude, longitude}` object for organizations, read
from their WGS84 `point` (`ST_Y` = latitude, `ST_X` = longitude). Missing, empty, non-finite
or out-of-range coordinates yield null; addresses are never geocoded.
The existing filters, pagination, `created_at`, `action.href` and unknown-timestamp semantics
are unchanged. Preview enrichment runs **after SQL pagination**, with one batch query for
all page identities: three existing count/page queries plus one enrichment query (zero for an
empty page). UUID joins retain the source UUID indexes; next-date lookup uses the existing
`event_date(event_uuid)` index. Reverse image contexts are aggregated once for the page.

| Type | Preview |
| --- | --- |
| organization | City, available street/house number/address addition/postal code/city/country, WGS84 location and `main_logo`; no standalone public organization route is established |
| venue | Address, `main_photo` then `main_logo`, public venue link |
| space | Parent venue name; no invented image relation or standalone public route |
| event | Subtitle, next upcoming public-status date, `main` image; public link only when a supported date exists |
| event_date | Actual event date/time (unknown time stays unknown), effective venue/space, parent event image |
| user | Display name/username, activation status, email and a public avatar candidate URL; no Pluto image relationship is assumed |
| partner_request | Existing directed from/to names and status |
| team_membership | Existing user/organization, invited/joined status; optional explicitly labelled `invited_at`, never a fabricated joined timestamp |
| image | Image itself; linked name only if exactly one distinct context/target exists |

### User avatars and organization locations

Uranus stores avatars in its profile-image directory, not in `uranus.user` or a Pluto link.
The verified public route is `/api/user/:userUuid/avatar/:size`
(`uranus/uranus-api.go`, `api/get_user_avatar.go`, `api/admin_update_user_avatar.go`).
Allowed sizes are 64, 128, 256 and 512; a missing file returns 404. For user items,
`image_url` uses `https://api.kulturbytes.de/api/user/<user_uuid>/avatar/128`.
The browser loads it lazily and falls back to the user icon on error. The existing modal
uses the 512px version. No per-user profile/HEAD request or filesystem lookup is added;
the returned URL is a candidate, not proof that an avatar exists. As with Pluto URLs,
only the configured public instance enables avatar URLs. Zod permits this exact route;
no arbitrary image hosts or token query parameters are accepted.

Organization logos and venue thumbnails get the same padding inside their thumbnail button and retain their native ratio.
Their source coordinates become an OpenStreetMap marker link through the single frontend
`activityMapUrl()` helper, following the documented
[OpenStreetMap marker URL format](https://wiki.openstreetmap.org/wiki/Browsing#Other_URL_tricks).
Only validated numeric coordinates enter the fixed `https://www.openstreetmap.org/` URL.
The link opens a new tab with `noopener noreferrer`; no map tiles, geocoding, or map scripts
are loaded. Existing image CSP permissions for `https://api.kulturbytes.de` also cover avatars;
no CSP expansion is required.

Public URL generation is enabled only when `URANUS_API_URL` identifies
`https://api.kulturbytes.de` (a trailing slash is accepted). This is an operator assertion that
the source data belongs to this public instance; local/unrelated snapshots get null URLs.
No network introspection or per-row HTTP requests are made. Missing/stale files use the UI's
icon fallback. Public images use `https://api.kulturbytes.de/api/image/<uuid>?width=320`.
For image rows, `entity_key` is exactly `pluto_image.uuid`; the preview selects the same UUID
without requiring an image-link row. A null or malformed image UUID yields `image_url = null`.
The central Pluto `image_url()` helper validates UUIDs and encodes only `width=320` with `urlencode`.
No `ratio` or height is sent: Pluto preserves the original aspect ratio.
Only established image identifiers are selected, not arbitrary stored URLs or file names.
The 320px-wide thumbnails are displayed at 96px wide on mobile and 128px on desktop, with
`loading="lazy"`, `decoding="async"`, a descriptive alt label and an icon fallback on errors.
The frontend also accepts the former 160px square and 320px/16:9 URLs during a rolling deployment;
new Pluto URLs use width=320 without cropping. No additional JSON requests are made per row.
Clicking a thumbnail opens the shared `AppModal` dialog, also used by finding details.
Only then does the browser load a 1280px-wide, uncropped Pluto image (512px for avatars). The central frontend
`activityImagePreviewUrl()` helper accepts only validated public thumbnail URLs and changes
the width or permitted avatar size without exposing an arbitrary image host. Escape or the close button dismisses
the modal and restores keyboard focus to its trigger. Images fit the viewport without cropping;
a failed large preview shows an error while preserving the rest of the Activity row.

### Public route matrix

| Entity type | `public_url` |
| --- | --- |
| venue | `https://kulturbytes.de/de/ort/<slug-or-UUIDv7>` |
| event | `https://kulturbytes.de/de/veranstaltung/<event_uuid>/<next-public-date-UUIDv7>`; null without a supported upcoming public date |
| event_date | `https://kulturbytes.de/de/veranstaltung/<event_uuid>/<date-UUIDv7>` when event and effective date status are public |
| organization, space, user, partner_request, team_membership, image | null; no standalone public detail route in the verified client |

There is no single-identifier `/event/<uuid>` detail page in this client. The German locale
prefix and date identifier are required. The image API URL is a thumbnail, not a public
HTML detail page. A unique linked object is shown as image context; ambiguous links do not
invent an owner or primary object. Missing `created_at` remains unknown.

Routing evidence inspected at implementation time:

- [Kulturbytes client 0971931 (verified 2026-09-16)](https://github.com/sndcds/kulturbytes-client/tree/0971931d586416a3bab701e02c8c188022a40e2e):
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

## Entity-Relationship Graph

`GET /api/v1/graph/search` searches safe entity names/UUIDs (`q`: 2–120 trimmed characters,
`limit`: 1–20, optional `entity_type` and `organization_id`). `GET /api/v1/graph` requires
`root_type` and UUID `root_key`, accepts `depth=1..3` (default 2) and optional `relation_type`.
Both use existing system-admin authorization, read-only transactions and statement timeouts.
Graph responses contain `root`, typed `nodes`, typed `edges`, `truncated`, `max_nodes=100`,
`max_edges=200`; search returns `items`. Identity is `type:uuid`. A missing root returns 404.
No email, credentials or full entity records are exposed.

See the [relationship contract and source table](../../frontend/docs/entity-relationship-graph.md)
for all six node types, twelve relations, bounded traversal, public-link rules, and UI behavior.
Pending invitations and partner requests are distinct from joined memberships and corroborated
accepted partnerships. Effective date locations share the established Activity SQL semantics.

## Entity creation statistics

`GET /api/v1/statistics/entities` is admin-only and uses the existing read-only snapshot.
It returns seven zero-filled time series, current/optional previous totals, exact half-open
bounds and seven recent entities. Default `period=24h&interval=auto`; presets also support
`7d`, `30d`, `90d`. Custom requires offset-aware `from_at` and `to_at` (at most 365 days).
Intervals are `auto`, `15m`, `1h`, `6h`, `1d`, bounded at 500 buckets. Optional `compare=previous`
uses the immediately preceding equal-duration range. Invitations use the latest stored
`invited_at`, which can move on reinvitation; they are not a historical send log. Dashboard
membership creation retains `created_at`. Activity's opt-in `creation_basis=statistics`
restricts its sources to the same seven types and uses invitation timestamps for memberships.
Default `creation_basis=record` is unchanged. Exact timestamp matrix, DST behavior, response,
NULL handling and performance limitations: [Statistics](../../frontend/docs/statistics.md).

### Dashboard check history

Persisted dashboard responses include `check_status.latest_run` and
`check_status.last_successful_run`, each nullable. These summaries expose run UUID,
status, start/finish timestamps, rule count and finding count. Latest run is ordered
by start time then UUID descending; last success by finish time then UUID descending.
A later failed/queued/running run never hides the previous success. These are current
history values, independent of the selected new-record period. With no stored runs,
both are null; explicit live diagnostic mode returns `check_status: null`.

### Domain record lists and details

`GET /api/v1/{section}` and `GET /api/v1/{section}/{uuid}` exist for six explicit
sections: `events`, `venues`, `spaces`, `organizations`, `users`, `images`.
Lists accept `q` (literal substring of name/UUID and additionally username for users,
maximum 200 characters), `organization_id`,
`status`, `page`, `page_size` (1–100); order is case-folded name with C collation,
then UUID. Details accept `related_page` (25 related rows per page). Missing UUIDs
return `404 record_not_found`. All endpoints share the system-admin dependency.

Responses reuse safe Activity fields and public preview URLs, with an explicit
`facts` model for source counts/context. Optional `finding_count` excludes resolved
findings; `mark_count` counts stored marks. Both are null when admin storage is not
configured, never fabricated zeroes. Source counts include the complete source
state, not a selected time window. Relations reuse verified graph relationships
and image contexts; counts/pages come from SQL. A bounded number of batch queries
serves each page; no per-row API requests or per-row database round trips.

Canonical Action hrefs now target these six detail routes, including images without
creation timestamps. Existing structured `route=activity` remains compatible; older
clients should upgrade their internal URL validator before deploying the new backend.
Composite keys and event dates retain existing Activity/queue targets. Findings accept
an exact `entity_key` filter in addition to `entity_type`.

### Domain create authorization prerequisite (#15)

Current repository verification (2026-09-17): Uranus default branch **main**, commit
[`74fef734ca916ecd04aef9d7d3013c1cd918d6dc`](https://github.com/sndcds/uranus/tree/74fef734ca916ecd04aef9d7d3013c1cd918d6dc).
This supersedes the earlier write-contract review at `12ec7608`. Source inspection
is not evidence that these handlers are deployed or compatible with the live schema.
No Uranus server or production database was contacted.

#### Proven authentication and routing

[`uranus-api.go`](https://github.com/sndcds/uranus/blob/74fef734ca916ecd04aef9d7d3013c1cd918d6dc/uranus-api.go)
mounts `/api/admin` with `app.JWTMiddleware`. The middleware accepts an Authorization
Bearer access token or an `access_token` cookie. `app/jwt.go` verifies HS256 with the
Uranus signing key, required expiry and registered claims; the middleware requires
`token_type=access` and a nonzero user UUID. Refresh tokens are not access credentials.
It puts the authenticated Uranus UUID into `user-uuid`; handlers obtain that identity
through `h.userUuid(gc)`.

`POST /api/login` checks the existing Uranus user/password and active state; refresh
checks the active user and rotates registered refresh tokens. Access tokens remain
valid until expiry (new tokens at most 900 seconds); middleware does not perform a
fresh active-user check on every request. These are ordinary **Uranus user sessions**,
not a delegated service identity. Independent `admin.auth_account` sessions cannot
be passed through as Uranus tokens. No passwords or signing keys should be copied
into this application. See the reviewed upstream
[authentication contract](https://github.com/sndcds/uranus/blob/74fef734ca916ecd04aef9d7d3013c1cd918d6dc/docs/authentication.md).

#### Operation matrix: present upstream does not mean enabled here

All paths below are relative to `/api/admin`. Reviewed handlers are under `api/` at
the pinned commit. **Every create/update capability remains disabled in uranus-admin.**

| Operation | Proven route / handler | Actual authorization/audit observations |
| --- | --- | --- |
| Create organization | POST `/org/create`, `admin_create_org.go` | Ordinary authenticated Uranus user; body `org_name`; stores created_by and grants the creator org-admin membership/permissions. No delegated admin actor |
| Create venue | POST `/venue/create`, `admin_create_venue.go` | Body org_uuid/venue_name/scope; checks `UserPermAddVenue` in the organization; stores created_by |
| Create space | POST `/space/create`, `admin_create_space.go` | Body org_uuid/venue_uuid/space_name; checks `UserPermAddSpace` for supplied org. The adapter must not assume that this proves the supplied venue belongs to that org |
| Create event | POST `/event/create`, `admin_create_event.go` | Checks `UserPermChooseAsEventOrg` AND `UserPermAddEvent`; a supplied venue also needs `UserPermChooseVenue`. Typed upstream payload includes org_id/org_key, language, release state, title/description, dates etc. SQL still names organization_id/venue_id/space_id and RETURNING id; do not assume compatibility with exported UUID schema |
| Edit organization | PUT `/org/:orgUuid/fields`, `admin_update_org_fields.go` | Explicit field model; inspected handler has no object/organization permission check beyond JWT middleware. Not safe to expose as an authorized admin adapter |
| Edit venue | PUT `/venue/:venueUuid/fields`, `admin_update_venue_fields.go` | Explicit fields and modified_by from JWT; inspected handler has no object permission check before update |
| Edit space | PUT `/space/:spaceUuid/fields`, `admin_update_space_fields.go` | Resolves owning org from the stored space and checks `UserPermEditSpace` |
| Edit event | PUT `/event/:eventUuid/fields`, `admin_update_event_fields.go` | Gets stored org permissions; explicitly checks `UserPermReleaseEvent` only when release_status is supplied. A general field-edit permission is not established by that check. Separate date/type/link/venue/etc handlers need their own review before exposure |
| Users | PUT `/user/profile`, `/user/settings`; avatar routes | Self-service routes are not an arbitrary-system-user editing contract; no generic admin user create/edit capability enabled |
| Images | PUT/DELETE `/image/:context/:contextUuid/:identifier`; Pluto routes receive JWT middleware | Context-bound media operations are not a generic system-wide image-create authorization contract; no adapter enabled |

No request idempotency key, If-Match/version precondition or delegated actor/scoped
service-credential mechanism was found in the reviewed route/middleware/handler code.
Transactions alone do not establish idempotency or prevent lost updates. Existing
created_by/modified_by fields refer to a Uranus user, not an independent admin subject.
The organization import token generated at creation is not consumed as a general
`/api/admin` credential. Localhost-only internal maintenance routes are not an
alternative authorization mechanism and must never be used by this adapter.

#### Decision: case B, no authorized delegation contract

Search/review covered router registration, middleware/claims/token issuance, permission
helpers, create/update handlers, API-token/import-token uses, service/machine identity,
impersonation/delegation and concurrency mechanisms. No supported bridge from our
independent admin identity was found. An upstream TODO or a missing permission check
is not authorization. Create/Edit stays disabled; #15 remains open.

No new credential settings, network client, proxy write routes, capability endpoint
or create forms are added. The current UI capability set is empty. `URANUS_API_URL`
is the existing server-side base URL; an eventual implementation should reuse it if
it targets the same service, but configuring it alone never grants write authority.

#### Prepared adapter interface (design only; not an implemented upstream API)

This describes the integration boundary to agree with Uranus before code is wired:

| Port | Required contract |
| --- | --- |
| `capabilities(principal, target)` | Return only operations explicitly authorized for this actor AND organization/entity scope; unavailable or unverified delegation means no capabilities |
| `authorize(principal, operation, target)` | Obtain an expiring, revocable upstream-verifiable delegation binding the independent admin subject to the deliberately approved Uranus actor and scope; no browser-supplied user/org assertion suffices |
| `create_<entity>(delegation, typed_input)` | Separate Pydantic input per supported operation, exact allowed upstream fields and validated UUID result; no arbitrary path/body passthrough |
| `update_<entity>(delegation, entity_id, typed_patch, precondition)` | Recheck stored object ownership/permission upstream and enforce an agreed conflict/version policy; absence of a safe contract keeps that operation disabled |

The future adapter receives no source-DB write handle. Credentials stay server-side,
secret values use SecretStr, errors/logs redact credentials and raw upstream bodies.
An authorization refusal stays 401/403; missing/conflicting/invalid records map to
404/409/422; unavailable or invalid upstream responses to sanitized 502/503. Preserve
Origin/X-Admin-CSRF, proxy body limits and exact method/path allowlists. No automatic
POST retry; disable form submission in flight. Enable forms and canonical-detail
redirects only after the adapter's real capability is verified.

#### Upstream companion recommendation

Proposed issue: **Define scoped delegated domain writes for independent admin clients**.
Before integration, Uranus must provide and test:

1. An explicit actor/delegation issuance, validation, expiry/revocation and scope
   contract; independent admin status must never silently imply organization rights.
2. Consistent object authorization on every enabled create/update endpoint, including
   venue→org consistency and generic organization/venue/event field edits.
3. A tested payload/result contract compatible with the authoritative schema, plus
   idempotency or documented no-retry behavior and update conflict semantics.
4. Audit attribution distinguishing the initiating admin and approved Uranus actor,
   without inventing parallel domain history in uranus-admin.
5. Denied/expired/revoked/wrong-scope/changed-owner tests and sanitized error behavior.

This is a recommendation, not a new Uranus implementation, issued credential, or
claim that delegation exists. Both upstream contract approval and deployment evidence
are prerequisites to activate even one create/edit capability here.

### Additive cursor pagination

Activity and persisted findings support `cursor=start&page_size=25`, followed by
`cursor=<next_cursor>` with the same filters. Do not send `page` with `cursor`.
Offset navigation remains the frontend default. `cursor_pagination` contains
`page_size`, `has_more`, `next_cursor`; a null next cursor ends the stream. Legacy
`pagination` counts remain present for compatibility; its page number is not a
cursor page counter. Live findings do not support cursors.

Cursors are versioned base64url JSON with endpoint and filter-scope validation.
Activity includes UTC created time plus entity type/key (descending time, ascending
identity); unknown timestamps use identity only. The original time window is carried
forward, even when the clock advances. Persisted findings use descending effective
priority score and ascending C-collated finding ID, exactly as offset ordering.
Invalid encoding, version, endpoint, filters or values returns sanitized 422.
No cursor grants permission: normal auth and every filter apply to every page.
Inserts before the cursor do not duplicate/skip unchanged original rows. This is not
a database snapshot across HTTP requests: deletions and changed ordering attributes
(such as reprioritized findings) can change the stream and require restarting it.

### URL observations

The optional `app.url_check_worker` maintains `admin.url_check`; syntax checks remain
local and deterministic. No new browser network endpoint is exposed. Repeated real
network/HTTP failures can create warning rule `url_unreachable` in the existing
persisted finding stream. 401/403/429, SSRF rejection, excessive bodies and redirect
limits remain diagnostic observations, not definitive broken-link findings. A later
2xx resolves only that source field. The current core check-run count still describes
core rules; asynchronous URL observations have their own timestamps and TTLs.

Record-mark list/detail responses additionally expose optional `action` using the
same canonical Action model for the six domain sections. Historical notes stay on
`/marks/{id}`; “Datensatz öffnen” links back to the source detail. Unsupported mark
entity types have no invented domain target.

### Logo quality rules and overview counts

| rule | entity | severity | Bedeutung |
| --- | --- | --- | --- |
| venue_missing_logo | venue | warning | Kein main_logo vorhanden |
| organization_missing_logo | organization | warning | Kein main_logo vorhanden |
| logo_unsupported_format | venue/organization | info | Logo ist weder PNG noch WebP |

`main_logo` is the required logo. `dark_theme_logo` / `light_theme_logo` are optional
variants. A matching `pluto_image_link` must use the owner's context and UUID and
reference an existing `pluto_image`. A dangling main-logo link yields one missing-logo
warning per owner plus the separate existing broken-image finding. It never yields a
format finding. Avatar, main_photo, gallery photos, events and portals are excluded.

Allowed MIME types: `image/png`, `image/webp`. The authoritative source is
`pluto_image.mime_type`, never `file_name` / `gen_file_name`. NULL, empty and whitespace-only
MIME values are unknown and generate no format finding. Comparison uses
`mime_type.strip().lower()`, so `IMAGE/PNG` and ` image/webp ` are accepted. Other
nonempty normalized values generate info, with `field=<identifier>.mime_type`. Metadata
contains `identifier`, the original `mime_type`, `allowed_mime_types`, `image_uuid`
and the existing source fingerprint.

Missing-logo identity retains `<rule>:<entity_type>:<uuid>:main_logo`, with
`field=main_logo` and metadata `expected_identifier=main_logo`. Format findings use
`main_logo.mime_type`, `dark_theme_logo.mime_type` or `light_theme_logo.mime_type`
as their field. Identity follows the normal `rule:entity_type:entity_key:field` contract,
with each component URL-encoded as before. Example:
`logo_unsupported_format:venue:<uuid>:main_logo.mime_type`.
This keeps the ID consistent with the existing database uniqueness constraint
`UNIQUE(rule, entity_type, entity_key, field)`; there is no separate identity override.
Each problematic variant contributes one finding to `rule_counts`, even for the same owner.
No migration is needed for this unmerged rule; old local experimental findings are not
part of the production compatibility contract.
The owner is the Finding entity, so canonical Actions use `/venues/<uuid>` or
`/organizations/<uuid>` and existing entity finding filters/counts work unchanged.
The shared priority model uses publication/upcoming relevance without severity
escalation: missing logos are warning, formats info.

All owner rows enter rule coverage, even when no logo link remains. A successful
complete registered scan resolves repaired missing logos, corrected formats and
removed bad variants. Failed/incomplete runs resolve nothing. Review states and
stable identity follow existing persistence semantics. No source writes or migrations
are introduced.

Dashboard `quality.rule_counts` is an additive map of rule code to nonnegative count.
Live mode counts the current scan; persisted mode groups existing findings by rule,
excluding resolved entries but including other review states. Registered rules without
current findings have zero counts. The map includes any additional stored rules;
`quality.rules` keeps its existing semantics (all scanned rules in live mode, rules with
active stored findings in persisted mode). Counts describe current inventory, not proof
that a new rule has already run; consult `check_status` for scan history.

`QualityOverview` groups the three rules under “Logos & Bilder”, using shared list rows
and severity badges. Counts link to `/findings?rule=...`, additionally `entity_type` for
missing-logo rules, preserving live/persisted mode. A missing map from an older backend
is displayed as unavailable, never as zero. Empty inventory retains the three zero-count
links. Loading, stale-data errors and retry use the existing dashboard store/RequestState.
