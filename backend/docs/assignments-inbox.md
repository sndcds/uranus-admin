# Assignments und Admin Inbox

## Identität und Status

Admin-Zuständigkeiten gehören ausschließlich in `admin.assignment`. Das Ziel ist eine aktive
Zeile aus `admin.auth_account`, die weiterhin durch `admin.auth_system_admin` global berechtigt
ist. Uranus-User und Admin-Konto sind getrennte Identitäten; es gibt kein implizites Mapping.

Eine Aufgabe identifiziert entweder `finding_id` oder das Paar `workflow_type`/`workflow_key`.
Finding-Assignments übernehmen `entity_type` und `entity_key` aus dem gespeicherten Finding.
Bei Workflow-Assignments leitet der Server die Entity-Identität aus dem gespeicherten Geocoding-
Request bzw. der Notification-Delivery ab und weist abweichende Clientwerte zurück. Nur weiterhin
bearbeitbare Workflowzustände sind zuweisbar. Partielle Unique-Indizes erlauben pro Identität höchstens ein aktives
Assignment (`open`, `in_progress`). Geschlossene historische Zeilen bleiben erhalten.

Writes benötigen die aktuelle `version`. Der Server sperrt die Zeile, vergleicht die Version und
antwortet bei Konflikt mit 409, ohne Daten zu überschreiben. `done` und `cancelled` setzen
`completed_at`; eine Wiederöffnung leert nur diesen aktuellen Abschluss. Jede Änderung fügt in
derselben Transaktion eine Version in `assignment_event` ein. Diese Historie ist append-only.

## Inbox-Aggregation

`GET /api/v1/inbox` aggregiert mit einer festen Anzahl Admin-DB-Abfragen:

- aktive Assignments, bei Finding-Aufgaben zusammen mit Finding-Schweregrad und Nachricht;
- offene/in Bearbeitung befindliche sowie zurückgestellte Findings ohne aktives Assignment;
- Geocoding-Requests in `candidate`, `ambiguous`, `not_found` oder `failed`;
- Notification-Deliveries in `failed` oder `permanent_failure`.

Ein aktives Assignment für dieselbe Finding- oder Workflow-Identität unterdrückt den unzugewiesenen
Eintrag. Es entstehen keine Abfragen pro Zeile. Nach der paginierten Admin-Abfrage lädt genau eine
gebündelte read-only Uranus-Projektion die aktuellen Entitätsnamen, Organisationskontexte und
kanonischen Admin-Actions der sichtbaren Seite. Fehlende Source-Datensätze behalten nur den bereits
gespeicherten sicheren Fallbacknamen und erhalten keine erfundene Action. Kandidatenzahlen werden
für die aktuelle Geocoding-Generation in der Admin-Abfrage aggregiert. Filter und Seitengröße werden serverseitig
begrenzt. `mine` wird aus dem authentifizierten Subject `admin:<UUID>` bestimmt; der lokale
Development-Principal besitzt absichtlich keine dauerhafte persönliche Identität. Heute fällige
und überfällige Aufgaben verwenden `ADMIN_TIMEZONE` und echte Zeitzonen-Grenzen.

Notification-Empfänger, Snapshot-Inhalte, Providerfehler, Geocoding-Rohfehler, Passworthashes,
Sessions und andere Secrets werden weder ausgewählt noch zurückgegeben. `href` stammt aus einer
geschlossenen Menge interner Ziele und wird im Frontend nochmals mit Zod validiert.
Finding-Aufgaben verlinken unabhängig von einer Zuweisung auf
`/findings?entity_key=…&rule=…`. Das gilt auch für Termine und andere Entitäten ohne
eigene Detailseite oder aktuelle Source-Präsentation; `entity_action` darf dabei `null` sein.

## Migration und Grants

Revision `0013` folgt `0012` und erstellt `assignment` und `assignment_event` einschließlich
Foreign Keys, Constraints und Indizes. Sie verändert keine Uranus-Tabelle. Vor dem Deployment
API und Worker koordinieren, als `admin_migrator` auf den aktuellen Head migrieren und danach
die releasegebundene Grant-Matrix anwenden:

```sql
GRANT SELECT, INSERT, UPDATE ON admin.assignment TO admin_user;
GRANT SELECT, INSERT ON admin.assignment_event TO admin_user;
REVOKE UPDATE, DELETE, TRUNCATE, TRIGGER ON admin.assignment_event FROM admin_user;
```

Die Runtime besitzt kein Schema-CREATE, kein DDL, kein DELETE und keine Owner-Mitgliedschaft.
Das Deployment prüft Migration-Head, Tabellenumfang und effektive Privilegien vor Aktivierung.
Ein fehlender Grant wird nicht zur Laufzeit repariert. Ein Downgrade von `0013` auf `0012` entfernt beide Tabellen und
damit ihre Admin-Workflow-Historie; er ist nur nach ausdrücklicher Sicherungs-/Downtime-Planung
für eine geeignete Test- oder Wiederherstellungssituation vorgesehen.

## Wiedervorlage (Phase 4.3)

Audit-Ausgangspunkt: `main` bei `fb96af4f9295893bcefc45489d2fd0c1dc6109dd`.
Finding-Reviews setzen bereits `status=snoozed` und ein zukünftiges aware `snoozed_until`.
Sie schreiben ein `finding_event(kind=reviewed)` mit Review-Snapshot. Finding-Filter beziehen
sich weiterhin auf den gespeicherten Status; `active_only` bedeutet nicht behoben und schließt
Snoozes ein. Bisher öffnete erst ein erfolgreicher Recheck einen abgelaufenen Snooze erneut
(`finding_event(kind=reopened)`); die Inbox schloss unzugewiesene Snoozes pauschal aus und
berücksichtigte sie bei zugewiesenen Findings nicht. Diese Inbox-Lücke ist nun geschlossen.
Review-API, Finding-Filter und Recheck-Historie bleiben unverändert.

**Zwei unabhängige Ebenen:** Finding-Snooze ist fachlicher Review-Zustand. Assignment-Snooze
ist organisatorisches Admin-Metadatum und verändert weder Finding-Status noch Review-Actor.
`assignment.status` bleibt `open`/`in_progress`. Weder Ebene bedeutet resolved, done,
cancelled oder reviewed. Die Inbox unterdrückt den deduplizierten Task, solange entweder
`finding.status=snoozed AND finding.snoozed_until>observed_at` oder der Assignment-Zeitpunkt
in der Zukunft liegt. Bei zwei aktiven Snoozes ist der spätere Zeitpunkt maßgeblich.
Bei Gleichheit oder Ablauf erscheint die Aufgabe wieder in der aktiven Inbox. GET verändert
keine Zeile, erzeugt keine Ereignisse und benötigt keinen Hintergrundjob. Ein abgelaufener
Finding-Snooze kann daher in der Finding-Liste noch den gespeicherten Status `snoozed` tragen.

`PATCH /api/v1/assignments/{id}` unterstützt Teiländerungen, beispielsweise
`{"version":3,"snoozed_until":"2026-09-25T07:00:00Z"}`; `null` hebt die organisatorische
Wiedervorlage auf. Nicht gesendete Felder bleiben erhalten. Mindestens eine Änderungsspalte
ist erforderlich; `status` und `assigned_to_admin_id` dürfen nicht null sein. Der Server prüft
Version (409), weiterhin gültigen Admin/Task, offene Assignment-Status sowie einen aware
Zeitpunkt `now < snoozed_until <= now + 365 Tage` (422). Geschlossene Assignments können auch
nicht gleichzeitig wieder geöffnet und gesnoozed werden. Abschließen/Abbrechen leert die
organisatorische Wiedervorlage im selben Snapshot. Ein identischer PATCH erzeugt keine Version.

`assignment_event.kind=updated` bleibt das bestehende Audit-Modell. Jede tatsächliche Änderung
erhöht die Version und schreibt den kompletten Snapshot einschließlich `snoozed_until`, Actor,
Status, Assignee und Fälligkeit atomar append-only. Die Timeline vergleicht aufeinanderfolgende
Snapshots vor der Pagination und präsentiert `assignment_snoozed` bzw. `assignment_unsnoozed`.
Es gibt kein erfundenes Ablauf-Ereignis.

`attention=snoozed` zeigt ausschließlich aktive Wiedervorlagen, sortiert nach dem effektiven
`snoozed_until ASC`, dann stabiler Task-ID. Alle anderen Attention-Filter schließen diese Tasks
aus. Aktive Reihenfolge: kritisch, überfällig, heute fällig, Schweregrad, Fälligkeit,
Aktualisierung, stabile ID. Die globalen Counts `critical`, `mine`, `unassigned`, `due_today`,
`overdue` zählen nur die aktive Population; `snoozed` zählt die gesamte deduplizierte
Wiedervorlagen-Population, unabhängig von Filtern/Seite. Ein gemeinsamer Beobachtungszeitpunkt
und ein REPEATABLE READ-Snapshot gelten für Seite und Counts. `InboxItem.snoozed_until` ist
nur der aktive effektive Zeitpunkt, `finding_snoozed_until` bezeichnet den fachlichen
Review-Zeitpunkt und `assignment.snoozed_until` den unveränderten organisatorischen Zeitstempel.

`/admins` und `/inbox` liefern `admin_timezone` aus `ADMIN_TIMEZONE` (Standard Europe/Berlin).
Die gemeinsame Oberfläche berechnet Morgen/+3/+7 als lokalen Kalendertag um 09:00 Uhr,
auch über Monats-/Jahres- und DST-Grenzen. Benutzerdefinierte Zeiten gehören zur angezeigten
Admin-Zeitzone, nicht zur Browser-Zeitzone. Nicht existierende lokale Minuten werden abgewiesen;
bei einer doppelten Herbst-Minute gilt das frühere Vorkommen. Gesendet/gespeichert wird ein
UTC-Zeitpunkt. Die bestehende End-of-day-Fälligkeit bleibt davon unabhängig.

Revision `0014` folgt `0013` und ergänzt ausschließlich nullable `timestamptz`-Spalten auf
`assignment` und `assignment_event`. Bestehende Zeilen/Events erhalten NULL, keine Datenkorrektur.
Runtime-Grants und Tabellenumfang bleiben gleich; kein DELETE, neues Schema oder Uranus-DDL.
Vor Aktivierung von Backend/Frontend muss als Migrator auf den aktuellen Head migriert werden.
Der Deployment-Upgrade-Vertrag enthält das im isolierten PostgreSQL reproduzierte Inventar von
`0013`; auch die früher geprüften Ursprünge bleiben unterstützt. Die SQL-Konsole liest nur
`uranus.*` und benötigt keine geänderte Freigabe. Downgrade `0014 → 0013` entfernt die beiden
Snooze-Spalten und verliert deren Metadaten, erhält aber sämtliche Event-Zeilen und Versionen.
Vor einem solchen Rollback Snooze-Daten sichern und den passenden Anwendungscode aktivieren.
