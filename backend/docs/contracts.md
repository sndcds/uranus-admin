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
Gesamterfolg ausgegeben; bestehende Findings bleiben unverändert. Auch der Persistenzbaustein
verweigert Resolution, sobald ein RuleResult fehlgeschlagen ist. Das ist bewusst konservativer
als ein Teilabschluss einzelner Regeln.

Ein Finding wird nur resolved, wenn der ganze Lauf erfolgreich war, seine konkrete Regel erfolgreich
war, sein Objekt in deren Coverage steht und die Finding-ID nicht erneut erzeugt wurde. Nicht
mehr vorhandene Objekte werden ohne belegte Coverage **nicht** automatisch geschlossen.
Upsert anhand der stabilen ID bewahrt first_seen_at. last_seen_at wird bei erneuter Beobachtung
aktualisiert; resolved_at nur bei belegter Behebung. Wiederkehrende Fehler öffnen dieselbe ID erneut.
Keine rückdatierte Historie, kein Ersatz von Source-Timestamps durch Scanzeitpunkte.

`GET /api/v1/findings?mode=persisted` liefert gespeicherte Beobachtungen und Zustände; Standard
bleibt `mode=live`. Historische Daten werden nicht als frischer Live-Scan ausgegeben. Es gibt
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

## Auth / Authorization Boundary

Alle neuen Routen verwenden dieselbe zentrale Admin-Dependency. Ohne Credential 401; ein
unverifiziertes Uranus-Login begründet weiterhin **keine globale Adminrolle**. Produktive Auth
bleibt gesperrt, bis Uranus einen expliziten globalen Autorisierungsvertrag bereitstellt.
Development-Override ist nur in development/test erlaubt.

`DATABASE_URL` bleibt SELECT-only und erzwingt read-only REPEATABLE READ-Transaktionen.
Optionales `ADMIN_DATABASE_URL` ist eine eigene Rolle mit SELECT/INSERT/UPDATE ausschließlich auf
Admin-Tabellen. Vor Verwendung lehnt die Anwendung Superuser/CREATEROLE sowie vorhandene
Uranus-Schreibrechte (auch Spaltengrants) ab. Der Betreiber muss diese Rechte wirksam beschränken;
Migrationen verwenden unverändert eine separate Migrations-DSN. Es gibt keine Startmigration.

Nuxt erlaubt nur die bekannten GET-Routen sowie POST check-runs und PATCH finding-reviews.
Reviewbodies werden strikt mit Zod validiert. Cookies, beliebige Headers, Redirects und fremde
Ziel-Origins werden nicht weitergereicht. Bekannte API-Fehlercodes werden nur aus strengem JSON
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
