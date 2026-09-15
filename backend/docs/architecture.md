# Architektur

Nuxt → begrenzter HTTP-Proxy → FastAPI → Uranus-PostgreSQL/PostGIS (SELECT).
FastAPI verwendet zusätzlich optional ein eigenes `admin`-Schema für Prüfläufe und Reviews.
Fachliche Änderungen bleiben autorisierten Uranus-Schreibpfaden vorbehalten; deren Authentifizierung,
Berechtigung und Projektionsaktualisierung werden hier nicht nachgebaut.

- `api/`: HTTP-Verträge und zentrale Auth-Dependency.
- `schemas/`: Pydantic-Modelle, Finding-Identität, Priority-/Action-/Zeitverträge.
- `repositories/`: explizite, parametrisierte Queries gegen bestätigte Quelltabellen.
- `services/quality/`: zentrale Priorität, deterministische Regeln und Scan-Zusammenstellung.
- `services/checks.py`: Transaktionen, Coverage, Idempotenz und Recheck-/Reviewzustände.
- `admin_tables.py` und Alembic: ausschließlich Admin-Metadaten, keine Domain-FKs.

Alle Source-Abfragen laufen in read-only REPEATABLE READ-Transaktionen. Engine/Pool entstehen
im Lifespan. Pool-/Statement-/Verbindungstimeouts und versteckte SQL-Parameter bleiben erhalten.
Nur die separate, auf Admin beschränkte Verbindung darf Historie und Reviews schreiben.
Globale produktive Autorisierung bleibt bis zum expliziten Uranus-Vertrag gesperrt.

Verbindliche Details: [Verträge](contracts.md), [aktuelle Quellverifikation](source-verification.md),
[ursprüngliche Uranus-Analyse](uranus-analysis.md), [Entwicklung](development.md).

Die globale Finding-Liste sortiert über alle Regeln nach Score/ID und paginiert danach.
Der spezielle Venue-Endpoint behält seine gebundene SQL-Pagination mit identischem Score.
Activity paginiert direkt im SQL-Snapshot. Arbeitslisten und Live-Regeln verwenden derzeit
vollständige kleine Quellmengen; Skalierungsgrenzen sind im Vertragsdokument ausdrücklich benannt.

Logs enthalten Route-Template, Methode, Status, Dauer und Fehlerklasse; keine Querystrings,
Tokens, SQL-Parameter, Roh-Validation-Inputs oder Exceptiontexte. Infrastrukturfehler werden
sanitisiert als 503 geliefert. Kein Debug-Stacktrace, keine externen URL-Aufrufe, keine
Startmigration und keine Domain-Schreiboperation entstehen durch die neuen Funktionen.
