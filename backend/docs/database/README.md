# Admin-Datenbankdokumentation

Der [Generator](../../scripts/generate_database_docs.py) dokumentiert ausschließlich
das PostgreSQL-Schema `admin`. Drei Dateien haben unterschiedliche Aufgaben:

- **`admin-migrations.sql`**: vollständige Alembic-Migrationshistorie bis zum Head.
- **`admin-schema.sql`**: finales, flaches PostgreSQL-Schema aus der SQLAlchemy-Metadata.
- **`admin-schema.dbml`**: finales Schema für den Import in **dbdiagram.io**.

Finales SQL, DBML und ER-Diagramme stammen aus `app.admin_tables.metadata`.
Uranus-Tabellen werden absichtlich weder modelliert noch reflektiert oder migriert.
Auch für Spalten wie `entity_key` oder `organization_id` werden keine Beziehungen
zu Uranus erfunden. Es werden weder Anwendungsdaten noch Secrets gelesen.

## Lokal erzeugen

Python 3.13 und uv sowie das Systempaket **Graphviz** (Programm `dot`, mit SVG-/PDF-
Unterstützung) werden benötigt. Es gibt keine zusätzlichen Python-Abhängigkeiten.
Unter Debian/Ubuntu:

```sh
cd backend
uv sync --locked
sudo apt install graphviz fonts-dejavu-core
uv run python scripts/generate_database_docs.py
```

Ein Befehl erzeugt beide SQL-Dateien, DBML, DOT, SVG und PDF. Fehlendes `dot`, fehlgeschlagene Programme,
ungültige Metadata oder leere Ausgaben führen zu einem Fehlerstatus. Ausgaben werden
zunächst temporär erzeugt und erst nach erfolgreicher Generierung übernommen.
Alembic-Diagnosen werden ausgegeben; die SQL-Ausgabe wird in die Datei geschrieben.

Optionen (vom Verzeichnis `backend/` aus):

```sh
uv run python scripts/generate_database_docs.py --output-dir /tmp/admin-database-docs
uv run python scripts/generate_database_docs.py --only auth --skip-pdf
uv run python scripts/generate_database_docs.py --only workflow --skip-migrations
uv run python scripts/generate_database_docs.py --skip-schema-sql --skip-dbml
```

`--only` akzeptiert `full`, `auth`, `quality`, `workflow`, `notifications` und
`geocoding`. Ohne diese Option entstehen alle Ansichten. SQL und DBML werden auch bei
`--only` erzeugt. `--skip-migrations`, `--skip-schema-sql` und `--skip-dbml` überspringen
die jeweilige Datei. `--skip-ddl` bleibt als alter Alias für `--skip-migrations`
erhalten; es überspringt ausschließlich die Migrationshistorie. Head und Metadata
werden immer validiert.
Relative Ausgabepfade beziehen sich auf das aktuelle Arbeitsverzeichnis; der
Standardpfad ist unabhängig davon `backend/docs/database/`.
Übersprungene oder nicht ausgewählte Dateien eines früheren Laufs bleiben erhalten;
für ein reines Teilpaket ein leeres `--output-dir` verwenden.

## Quellen und Darstellung

Intern läuft mit dem Python-Interpreter der aktiven Umgebung das Äquivalent von:

```sh
ADMIN_MIGRATION_DATABASE_URL="postgresql+asyncpg://dummy:dummy@localhost/dummy" \
uv run alembic upgrade head --sql
```

Das Script setzt diese Dummy-URL selbst und reicht keine Datenbankzugänge oder
Anwendungskonfiguration aus der aufrufenden Umgebung an Alembic weiter. `.env` wird
nicht geladen. Der Offline-Modus benötigt und öffnet keine Datenbankverbindung.
`migrations/env.py`, Schema-Grenzen, Rollen und Grants bleiben unverändert.

`admin-migrations.sql` ist das vollständige Upgrade-SQL von `base` bis `head`, **kein
bereinigter Dump des Endzustands**: Es enthält auch historische ALTER-Anweisungen,
Admin-Datenmigrationen und die Alembic-Versionstabelle. Es wird nur erzeugt, nie
ausgeführt. Vorhandene PostGIS-Typen sind wie in den Migrationen vorausgesetzt;
der Generator installiert keine Datenbankerweiterungen.

`admin-schema.sql` kompiliert `CreateSchema`, `CreateTable` und `CreateIndex` mit dem
SQLAlchemy-PostgreSQL-Dialekt. Tabellen stehen in stabiler Abhängigkeitsreihenfolge,
danach folgen gegebenenfalls zyklische Fremdschlüssel und schließlich Indizes.
Alle aktuellen Spalten, PKs, FKs, UNIQUE-/CHECK-Constraints und Server-Defaults stehen
direkt im finalen `CREATE TABLE`. PostgreSQL-Typen, GiST-Indizes und partielle Indizes
bleiben erhalten. Nur echte tabellenübergreifende Zyklen oder explizites `use_alter`
erfordern nachgelagerte FK-Anweisungen. Selbstreferenzen bleiben inline, insbesondere
`notification_delivery.retry_of_delivery_id → notification_delivery.id`.
Das finale SQL ist eine Schemabeschreibung, kein Deployment-Ersatz: Es enthält keine
Betreiber-Grants, keine Datenmigrationen und keine Alembic-Versionstabelle.

## Import in dbdiagram.io

```sh
cd backend
uv run python scripts/generate_database_docs.py
```

Danach `docs/database/admin-schema.dbml` öffnen und den Inhalt in den DBML-Editor von
[dbdiagram.io](https://dbdiagram.io) einfügen bzw. als DBML importieren.
**`admin-schema.dbml` ist das empfohlene Importformat. `admin-migrations.sql` ist
NICHT für dbdiagram.io vorgesehen**: Historische CREATE-/ALTER-Folgen können dort
unvollständige Tabellen und ungültige Referenzen ergeben.

Die [DBML-Syntax](https://dbml.dbdiagram.io/docs/) bildet jede Admin-Tabelle und jeden
FK-Constraint genau einmal ab. Zusammengesetzte Primär- und Unique-Schlüssel stehen
in `indexes`, zusammengesetzte Fremdschlüssel in gemeinsamen Ref-Blöcken. Refs sind
deterministisch je Ausgangstabelle nummeriert und erhalten DELETE-/UPDATE-Aktionen.
Es werden stets Datenbank-Spaltennamen verwendet, z. B. `finding.entity_id` statt
des Python-Keys `entity_key`. Beispiel der erzeugten Selbstreferenz:

```dbml
Ref notification_delivery_fk_1: admin.notification_delivery.retry_of_delivery_id > admin.notification_delivery.id [delete: restrict]
```

DBML enthält Spaltentypen, Nullability, Server-Defaults, Schlüssel sowie reguläre
Indizes. Partielle Indizes und PostgreSQL-spezifische Indexmethoden wie GiST stehen
als SQL in Tabellen-Notes, da DBML diese nicht verlustfrei abbildet. Insbesondere
wird bedingte Eindeutigkeit nicht als uneingeschränktes `unique` dargestellt.
CHECK-Constraints werden in DBML ausgelassen; vollständig stehen sie im finalen SQL.

## Reproduzierbarkeit und ER-Darstellung

Tabellen, Constraints und Kanten werden stabil sortiert, Spalten behalten die
Metadata-Reihenfolge. SQL und DOT enthalten keine Generierungszeit. Für identische
Migrationen und gesperrte Python-Abhängigkeiten ist die SQL-Ausgabe reproduzierbar.
Graphviz-Version und installierte Schriftarten können das Layout und die binären
PDF-/SVG-Ausgaben zwischen Systemen verändern.

DOT verwendet HTML-Tabellen, `rankdir=LR`, PostgreSQL-Datentypen und explizite
`NULL`-/`NOT NULL`-Angaben. `PK1`, `PK2` usw. kennzeichnen geordnet die Spalten des
gemeinsamen Primärschlüssels. `FK` markiert Fremdschlüssel. Die Pfeilspitze zeigt
auf die referenzierte Spalte, auch bei Selbstreferenzen. `F1.1`, `F1.2` usw.
identifizieren zusammengehörige Teile eines zusammengesetzten Fremdschlüssels
innerhalb der Ausgangstabelle. `U1`, `U2` usw. gruppieren Spalten eines UNIQUE-
Constraints je Tabelle. Lange CHECK-Ausdrücke und Indizes (auch partielle UNIQUE-
Indizes) stehen ausschließlich in der SQL-Datei.

Die Teilansichten sind zentral in `DIAGRAM_GROUPS` konfiguriert. Workflow enthält
zusätzlich die direkt referenzierten Tabellen `finding` und `auth_account`.
Kanten erscheinen nur, wenn beide Tabellen zur Ansicht gehören. Es gibt keine
automatisch ergänzten oder aus Spaltennamen abgeleiteten Beziehungen.
PDF und SVG sind vektorbasiert; die Gesamtübersicht benötigt beim Drucken ein
großes Blatt oder Posterdruck. Für kleinere Ausdrucke die thematischen Ansichten
verwenden; die Diagramme werden nicht auf eine unlesbar kleine A4-Seite skaliert.

Graphviz wird für jede DOT-Datei so aufgerufen:

```sh
dot -Tsvg docs/database/admin-er-full.dot -o docs/database/admin-er-full.svg
dot -Tpdf docs/database/admin-er-full.dot -o docs/database/admin-er-full.pdf
```

## Dateien

| Dateiname                              | Inhalt                                                                 |
| -------------------------------------- | ---------------------------------------------------------------------- |
| `admin-migrations.sql`                 | Vollständiges Alembic-Upgrade-SQL mit historischer CREATE-/ALTER-Folge |
| `admin-schema.sql`                     | Finales, flaches PostgreSQL-Schema aus der Metadata                    |
| `admin-schema.dbml`                    | Finales Schema zum Import in dbdiagram.io                              |
| `admin-er-full.{dot,svg,pdf}`          | Alle Admin-Tabellen aus der Metadata                                   |
| `admin-er-auth.{dot,svg,pdf}`          | Konten, Sessions, Admin-Grants, Login-Limits                           |
| `admin-er-quality.{dot,svg,pdf}`       | Prüfläufe, Findings/-Historie, Markierungen/-Historie, URL-Prüfungen   |
| `admin-er-workflow.{dot,svg,pdf}`      | Zuweisungen/-Historie mit Finding- und Kontoreferenzen                 |
| `admin-er-notifications.{dot,svg,pdf}` | Benachrichtigungen, Zustellungen und Zustellpositionen                 |
| `admin-er-geocoding.{dot,svg,pdf}`     | Gebiets-Cache, Geocoding-Aufträge und Kandidaten                       |

Die Alembic-Versionstabelle erscheint nur in `admin-migrations.sql`, weil sie
nicht Teil der Anwendungs-Metadata ist. Alle generierten Dateien sind per
[`.gitignore`](../../../.gitignore) ausgeschlossen. Versioniert werden Generator,
Tests, Workflow und diese Anleitung. Es gibt keine automatischen Artefakt-Commits.

## GitHub Actions

Der Workflow [Database docs](../../../.github/workflows/database-docs.yml) läuft bei
Pushes auf `main` und Pull Requests mit Änderungen an:

- `backend/migrations/**`, `backend/alembic.ini`
- `backend/app/admin_tables.py`, `backend/app/geo_types.py`
- `backend/scripts/generate_database_docs.py`
- `backend/pyproject.toml`, `backend/uv.lock`
- `backend/tests/test_database_docs.py` und dem Workflow selbst

Manuell: Im Repository **Actions → Database docs → Run workflow** öffnen, Branch
wählen und starten. Der manuelle Start ist verfügbar, sobald der Workflow auf dem
Default-Branch liegt. Alternativ mit GitHub CLI:

```sh
gh workflow run database-docs.yml --ref main
```

Nach erfolgreichem Lauf in dessen Zusammenfassung das Artifact
**uranus-admin-database-docs** herunterladen (Aufbewahrung: 30 Tage). Jeder Lauf
prüft sämtliche erwarteten Dateien auf Existenz und Inhalt. Der Job nutzt nur
`contents: read`, benötigt keine Secrets, startet kein PostgreSQL und schreibt
nicht ins Repository. Neue Läufe desselben Branches ersetzen ältere laufende Jobs.

## Konsistenz und Grenzen

Der Generator führt `alembic heads` aus und verlangt genau einen Head. Alle
Admin-Tabellen müssen ladbar sein, alle FK-Ziele auflösbar und ebenfalls in `admin`,
alle konfigurierten Gruppenmitglieder vorhanden. Regressionstests prüfen unter
anderem zusammengesetzte Schlüssel, Selbstreferenzen und die Schema-Grenze.

Diese Offline-Prüfungen beweisen **keine vollständige Übereinstimmung** zwischen
Metadata und Migrationen. `alembic check` benötigt eine reale, migrierte Datenbank
und wird daher hier nicht ausgeführt. Die bestehenden PostgreSQL/PostGIS-
Integrationstests prüfen die Migrationen einschließlich `alembic check` separat.
Die Dokumentation beschreibt den Repository-Stand, keinen verifizierten Live-Stand.
