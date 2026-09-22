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
- offene/in Bearbeitung befindliche Findings ohne aktives Assignment;
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
Ein fehlender Grant wird nicht zur Laufzeit repariert. Downgrade entfernt beide Tabellen und
damit ihre Admin-Workflow-Historie; er ist nur nach ausdrücklicher Sicherungs-/Downtime-Planung
für eine geeignete Test- oder Wiederherstellungssituation vorgesehen.
