# Entity Timeline

`GET /api/v1/entities/{entity_type}/{entity_key}/timeline` liefert für `event`,
`organization`, `venue`, `space`, `user` und `image` eine gemeinsame Chronologie. Der Endpoint
ist wie alle `/api/v1`-Routen authentifiziert. `entity_key` ist hier eine UUID; unbekannte
Entitäten liefern den bereinigten Fehler `record_not_found`.

Das Backend liest die Uranus-Quelle weiterhin ausschließlich über die READ ONLY-Verbindung und
aggregiert sie mit Admin-Auditdaten. Es gibt pro Seite je eine begrenzte Source- und Admin-Abfrage,
keine Abfrage pro Timeline-Zeile. Sortiert wird nach `occurred_at DESC` und anschließend nach der
stabilen, namespaced Event-ID. Ein opaker, an Entity-Typ, Entity-Key und Seitengröße gebundener
Cursor setzt diese Ordnung fort; `page_size` liegt zwischen 1 und 50.

## Belegte Quellen

- Source-Erstellung und Source-Änderung verwenden nur tatsächlich vorhandene `created_at` bzw.
  `modified_at`. Der Änderungszeitpunkt behauptet keine Kenntnis geänderter Felder.
- Teameinladungen verwenden ausschließlich `invited_at`; Partneranfragen ihr `created_at`.
- `admin.finding_event` hält Erkennung, Review, erneutes Auftreten und Resolution append-only fest.
- `assignment_event` liefert versionierte Admin-Zuweisungen samt Actor und Snooze-Snapshot.
  Aufeinanderfolgende Snapshots werden vor Cursor/Limit verglichen: Setzen/Ändern erscheint als
  `assignment_snoozed`, Aufheben als `assignment_unsnoozed`. Gespeichert bleibt `kind=updated`;
  Abschluss/Abbruch behalten ihre eigenen Event-Arten. Der Zeitpunkt der Wiedervorlage steht
  in der Summary in `ADMIN_TIMEZONE`. Ablauf erzeugt kein künstliches Ereignis.
- `record_mark_event`, Notification Deliveries, URL-Observations sowie Geocoding Requests und
  deren bestes bzw. leeres Ergebnis liefern ihre eigenen gespeicherten Zeitpunkte.

Ein fehlender Zeitpunkt wird nicht ersetzt und das betreffende Ereignis nicht chronologisch
einsortiert. Historische Findings werden durch Migration `0012` nur aus vorhandenen
`first_seen_at`, `reviewed_at` und `resolved_at` zurückgefüllt. Der Snapshot beschreibt dabei den
bei der Migration erhaltenen Finding-Inhalt; er rekonstruiert keine unbekannte Vergangenheit.

Responses enthalten eine geschlossene `kind`-Union, kurze Textfelder, Actor und typisierte,
nicht geheime Metadaten. Drill-downs sind ausschließlich interne, serverseitig erzeugte Ziele.
Die Frontend-Zod-Schicht prüft Pfad, UUID und erlaubte Query-Namen erneut. Timeline-Abfragen
akzeptieren weder URLs noch SQL und starten keine externe Netzwerkaktivität.

## Migration und Rechte

Revision `0012` folgt Head `0011`, erstellt `admin.finding_event` und ergänzt für die
Notification-Zuordnung den Index `(entity_type, entity_key)`. Die Tabelle
gehört `admin_migrator`; `admin_user` benötigt `SELECT, INSERT`, aber kein `UPDATE`, `DELETE`,
`TRUNCATE` oder `TRIGGER`. Sie ist Teil der Runtime-Boundary-Prüfung. Vor Deployment zuerst als
Migrator auf `0012` migrieren, danach die aus `RUNTIME_GRANTS` erzeugten expliziten Grants
anwenden und die Runtime-Grenze prüfen. Ein Downgrade auf `0011` löscht nur diese abgeleitete
Historientabelle; die aktuellen Findings bleiben erhalten.

Für die aktuellen Assignment-Snapshots ist zusätzlich Migration `0014` erforderlich;
[Migration, unveränderte Grants und Rollback-Grenzen](assignments-inbox.md#wiedervorlage-phase-43).
