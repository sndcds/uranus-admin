# Architektur: Kulturbytes Admin API

## Ziel und Entscheidung

Ein separates internes Backend bündelt Administration, Reporting und Qualitätsbefunde für
das zukünftige Nuxt-4-Admin. Die Aufgabenstellung entscheidet bewusst anders als Abschnitt 7
der Uranus-Dashboard-Empfehlung, der zunächst Go-Endpunkte im Kernbackend vorgeschlagen hat.
Die fachlichen Anforderungen der Empfehlung bleiben Grundlage; es entsteht keine zweite Domain-API.

## Verantwortlichkeiten

| System | Verantwortlich |
| --- | --- |
| Uranus (Go) | Domain-API, Businesslogik, reguläre Schreiboperationen, fachliche Validierung, effektive Org-/Partnerrechte, Projektionserneuerung |
| Admin API (FastAPI) | Systemweite lesende Queries, Dashboard-Aggregationen, Datenqualität, Findings; später Reviews, Check Runs und belegte Audit-/Activity-Daten |
| Nuxt Admin | Darstellung, Navigation, Filter und Interaktionen; kein DB-Zugriff und keine maßgebliche Autorisierung im Browser |

Event-/Venue-/Space-/Org-/User-/Membership-/Partner-Schreiblogik wird nicht in Python nachgebaut.
Spätere Aktionen müssen einen fachlich und sicherheitlich geprüften Uranus-Schreibpfad verwenden.
Die Analyse hat bestehende Lücken gefunden: Wiederverwendung bedeutet vorherige Prüfung von
Autorisierung, Validation, UUID-Schema und Projektionsnebenwirkungen. `URANUS_API_URL` ist
vorbereitet, erzeugt in Meilenstein 1 aber keine Netzwerkaufrufe.

## Struktur und technische Entscheidungen

Python 3.13, FastAPI/Pydantic v2, SQLAlchemy 2 Core, asyncpg und PostgreSQL/PostGIS.
Explizite SQL-Datei für die erste Regel statt vollständiger Uranus-ORM-Modelle.
Router beschreiben HTTP-Verträge; Services legen Reporting-Semantik fest und mappen Ergebnisse;
Repositories kapseln gebundene SQL-Abfragen. Kein generisches Repository-Framework.
Der gemeinsame Finding-Service bedient beide Listenendpunkte. Eine zusätzliche leere
`repositories/findings.py` oder ein leeres `processes.py` wäre derzeit ohne Nutzen und fehlt bewusst.

Strict mypy prüft Anwendung und Migrationen: passend zu Python-Annotierungen, ohne zusätzliche
Node-Laufzeit. Ruff prüft Stil/Imports und formatiert. uv.lock fixiert Laufzeit- und Testpakete.
Async nur für I/O; Mapping und Periodenberechnung bleiben synchron.

Engine/Pool werden im FastAPI-Lifespan erstellt und beim Shutdown entsorgt; kein importseitiger
Verbindungsaufbau, keine versteckte globale DB-Verbindung. Pro Request explizite read-only
REPEATABLE READ-Transaktion, Poolgrenzen sowie Verbindungs-/Statement-Timeouts.
Technische Referenzen: [FastAPI Lifespan](https://fastapi.tiangolo.com/advanced/events/),
[SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html),
[Alembic Schemafilter](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#omitting-schema-names-from-the-autogenerate-process).

## Findings und Priorität

Ein Finding identifiziert Regel, Objekt, Feld, Severity, Priorität, Organisation und den
Beobachtungszeitpunkt. Die ID `rule:entity_type:entity_id:field` ist stabil; keine zufällige ID
pro Request. Der aktuell implementierte Venue-Vertrag verwendet UUIDs. Die persistente Tabelle
verwendet Textschlüssel, damit später zusammengesetzte Membership-/Partner-Schlüssel möglich sind.

| Severity | Bedeutung |
| --- | --- |
| error | Widersprüchliche oder praktisch nicht nutzbare Daten |
| warning | Wahrscheinlicher administrativer Handlungsbedarf |
| info | Optionale Ergänzung / Hinweis |

Prioritäten, kleinere Zahl zuerst:

1. Fehler an veröffentlichten, bald stattfindenden Inhalten.
2. Fehler an veröffentlichten Inhalten.
3. Fehler an Entwürfen bzw. ohne belegte Veröffentlichung.
4. Warnungen mit kommenden Terminen.
5. Sonstige Warnungen.
6. Hinweise.

Die erste Regel erzeugt ausschließlich Warnungen. Innerhalb Priorität 4 stehen viele baldige
veröffentlichte Termine vor späteren veröffentlichten und sonstigen kommenden Terminen.
`urgent_findings` zählt aktuell Venues mit mindestens einem baldigen veröffentlichten Termin;
es ist ausdrücklich kein systemweiter Fehlerzähler aller künftigen Regeln.
`UPCOMING_DAYS=14` steuert die baldige Relevanz. Definitionen und Statusgrenzen siehe Analyse.

Alle Ergebnisse eines Requests haben denselben `last_seen_at`-Beobachtungszeitpunkt. Severity und
Zeitpunkt sind bei dieser einzelnen Live-Regel konstant, daher ordnet SQL die variablen Teile
Priorität/Relevanz und Venue-UUID. Das entspricht dem vollständigen Schlüssel
Severity → Priorität → Relevanz → last_seen_at → ID. Bei späterer Regelkombination muss der
Gesamtschlüssel auf die vereinigte Menge angewendet werden. Pagination ist innerhalb eines
Snapshots stabil; separate Requests können wegen Datenänderungen abweichen.

## Live-Modus und eigenes Admin-Schema

Meilenstein 1 liest Befunde live. `first_seen_at` bleibt NULL, `last_seen_at` ist die aktuelle
Beobachtung. Es gibt weder erfundene Erstfunde noch rückdatierte Check Runs.
`check_status=null`, `mode=live`. `status=open` bedeutet einen aktuell erkannten, noch nicht
persistenten Befund. Filter auf reviewed/ignored/resolved liefern eine leere **Live-Menge**,
keine Aussage über gespeicherte frühere Reviews. Persistente Zustände sind noch nicht angebunden.

Alembic-Revision `0001` bereitet vor:

- `admin.check_run`: UUID, Start/Ende als timestamptz, running/success/failed, Regel-/Befundanzahl,
  sanitisiertes Fehlerfeld.
- `admin.finding`: stabile ID, Regel/Severity/Objekt/Feld/Meldung, erste/letzte Beobachtung,
  resolved_at, JSONB-Metadaten; einfacher Reviewstatus, reviewed_by/reviewed_at, ignored_until/comment.
- `admin.alembic_version`: ausschließlich Migrationsbuchhaltung.

Kein separates `finding_state` für den Anfang: eine Zeile pro stabiler Befundidentität genügt.
Keine Domain-Kopien und keine Cross-Schema-FKs, die eine Uranus-Löschung blockieren könnten.
`reviewed_by` ist eine spätere Referenz auf belegte Uranus-Identität, keine neue Benutzerverwaltung.
Die Tabellen bleiben im aktuellen API-Betrieb unbeschrieben und werden nicht automatisch angelegt.

Ein späterer Lauf darf Befunde erst nach vollständiger erfolgreicher Regelprüfung schließen.
Fehlgeschlagene/partielle Läufe bedeuten keine Fehlerfreiheit. Für mehrere Regeln muss die
Regelabdeckung des Runs explizit ergänzt werden; die bisherige rule_count reicht dafür nicht.
Eine Review-State-Machine, Scheduler oder Background Worker gehört nicht zu Meilenstein 1.

**Migrationsgrenze:** nur `admin`-Metadata, Schema- und Objektfilter bei Autogenerate,
explizites `schema="admin"` in allen Operationen, Versionstabelle ebenfalls in `admin`.
Ein separater, auf dieses Schema beschränkter Migrationsaccount ist die verbindliche DB-Grenze
auch gegenüber später versehentlich handgeschriebenem DDL. Kein `DROP SCHEMA CASCADE` im
Migrationscode; Downgrade entfernt nur die eigenen zwei Tabellen. Die Testfixture beweist
Upgrade/Downgrade und unveränderte Uranus-Strukturen mit einem eingeschränkten Migrationsaccount.

## Zeiträume, Security und Fehler

Intern UTC mit aware datetimes. „Today“ beginnt um Mitternacht in `ADMIN_TIMEZONE` und endet
am Abfragezeitpunkt; `24h`/`7d` sind gleitende 24/168 Stunden. Intervalle sind `[from_at,to_at)`.
Die Source-Zeitzone ist getrennt; UTC wurde vom Betreiber ausdrücklich bestätigt und ist
der Default. Die UTC-Query vergleicht direkt gegen naive UTC-Grenzen, ohne Spaltenfunktion. Fehlende Bild-Timestamps werden separat gezählt.

Alle Admin-Routen verwenden zentral `get_current_admin`. Standardmäßig gesperrt; lokale
Development-Authentifizierung nur explizit und in Production unzulässig. Kein Cookie-Vertrauen,
keine eigenen Konten. Die sichere Uranus-Anbindung bleibt Meilenstein 2.
CORS erlaubt nur konfigurierte konkrete Origins und GET/Authorization; keine Wildcards.
Health/Readiness sind öffentlich, Readiness verrät keine Verbindungsdetails. OpenAPI ist nur
explizit in Development/Test verfügbar. Debug aktiviert niemals Client-Stacktraces.

Fehler: `{"error":{"code":"invalid_input","message":"…"}}`, Status 401, 403, 422,
500/503 je Ursache. Keine SQL-Parameter, Tokens oder Roh-Validation-Inputs im Fehlertext.
JSON-Logs enthalten Route-Template, Methode, Status und Dauer sowie Fehlerklasse oder Regelcode.
Keine Querystrings, Requestbodies, IPs, E-Mails, DB-URLs oder Exception-Texte. Uvicorn-Rohzugriffslogs
werden abgeschaltet. Quality-Abfragen protokollieren ihre Dauer, keine Datensatznamen.

## Weitere Regeln und Erweiterung

Die folgenden Regeln sind **nur geplant**. Jede benötigt belegte Feld-/Statussemantik,
einen eigenen Repository-Query, Service-Mapping in das Finding-Modell und PostgreSQL-Tests.

| Bereich | Geplante Prüfungen |
| --- | --- |
| Venue | Koordinatenbereiche, unvollständige Adresse, Web-/Ticketlink, Schließung vor Eröffnung |
| Space | Name/Link, negative Fläche/Kapazität, Sitzplätze > Gesamtkapazität, Raumtyp |
| Event | Titel, Termine, Links, wirksamer Ort/valide Online-Alternative, Raum-Venue-Konsistenz, Preis-/Altersgrenzen, Hauptbild, Beschreibung |
| Event Date | Ende vor Start, Overrides, Ticketlink; Ganztag/fehlende Uhrzeiten/über Mitternacht beachten |
| Organization | Name/Weblink/Kontakt, Organisationsbeziehungen, Betreuung und JSON-Semantik |
| User | lange nicht aktiviert, Mail-Syntax; keine Login-Inaktivität aus modified_at |
| Team | alte Einladung, Mitglied ohne Rechte, Rechte ohne Membership; Nullrechte nicht automatisch Fehler |
| Partner | alte pending-Anfrage, Selbstanfrage, ungültige Referenz; korrekte Grant-Richtung |
| Images | verwaistes Bild, fehlende Datei, Alt-Text/Herkunft/Lizenz, Maße; Schonfrist/optionale Angaben berücksichtigen |

URL-/Dateierreichbarkeit ist eine separate spätere Prüfung mit SSRF-Schutz und Rate-/Zeitlimits;
sie wird jetzt nicht ausgeführt. Optionale fehlende Inhalte sind niemals pauschal `error`.

## Aktivität, offene Vorgänge und Meilenstein 2

`GET /api/v1/dashboard/activity` ist als zukünftiger API-Vertrag reserviert, noch nicht registriert:
Ereignisart, Objektidentität, belegter Zeitpunkt, Quelle, optional belegter Akteur; stabile
Sortierung nach Zeitpunkt und ID. Initial sind nur reale Neuanlagen darstellbar. NULL-Zeitpunkte
werden getrennt behandelt, Änderungen/Löschungen/Annahmen erst mit belastbarem Auditlog.
Ein leerer Erfolgs-Endpoint würde Vollständigkeit vortäuschen und wird nicht ausgeliefert.

Auch `open_processes` fehlt bewusst in der Summary. `pending`, `has_joined=false` und
`is_active=false` sind erkennbare Zustände, aber noch keine fachlich priorisierten, altersbewerteten
Vorgangslisten. Counts und Listen werden gemeinsam ergänzt, keine erfundenen Summen.

Reihenfolge Meilenstein 2:

1. Globale Adminrechte und Uranus-Authentifizierung verbindlich definieren und integrieren.
2. Den bestätigten Backup-/UTC-Vertrag bei Deployment erneut auf Änderungen prüfen; Space-Vererbung klären.
3. Findings/Check Runs persistent nutzen, Regelabdeckung und Reviews hinzufügen.
4. Weitere kleine Qualitätsregeln mit geprüfter Severity ergänzen.
5. Activity nur aus belegten Ereignissen; Partneranfragen und Teameinladungen als offene Vorgänge.
6. Nuxt-4-Admin anbinden; zentrale filterbare Arbeitsliste, danach ggf. Suche/CSV/Bulk.
