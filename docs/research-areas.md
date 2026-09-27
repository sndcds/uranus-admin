# Research areas: Gemeinden / Kommunen

Research Part A ergänzt die Recherche um persistierte administrative Grenzen.
OpenStreetMap liefert die Geografie, die eigene Nominatim-Instanz erschließt sie,
PostGIS ordnet Uranus-Veranstaltungsorte zu. Normale Research-Requests verwenden
nur gespeicherte Daten; ein Nominatim-Ausfall betrifft ausschließlich den Import.

## Quelle und Grenzen der Discovery

Production verwendet ausschließlich:

```dotenv
NOMINATIM_BASE_URL=https://nominatim.oklabflensburg.de
```

Es gibt keine zweite Provider-Konfiguration und keinen öffentlichen Fallback.
`NominatimClient` übernimmt Timeout, Antwortgrößenlimit, Punktlimit, Content-Type,
Redirect-Verbot, deaktivierte Environment-Proxies und sichere Fehler. Der Import
prüft zusätzlich die genaue eigene Origin. Development/Test unterstützen für
Fixture-Tests `https://provider.test` beziehungsweise `http://127.0.0.1:8080`.

`/search` entdeckt Kandidaten; `/lookup?osm_ids=R…` liefert die Grenze mit
`format=jsonv2`, `addressdetails=1`, `extratags=1`, `polygon_geojson=1`.
Nur Relationen mit `class`/`category=boundary` und `type=administrative` sind geeignet.
Place-Nodes und POIs sind keine Gemeinden.

**Nominatim ist kein vollständiger Gemeindekatalog.** Seine Suche liefert höchstens
zehn gerankte Treffer pro Begriff. Ein Operator wählt deshalb explizit Suchbegriffe
oder bekannte OSM-Relationen. Ein Importlauf garantiert keine Vollständigkeit eines
Bundeslands. Es gibt weder Overpass-Zugriffe noch eine automatische Europa-Suche.
Siehe den [Nominatim-Suchvertrag](https://nominatim.org/release-docs/5.0/api/Search/).

## Länderspezifische Regeln und Scope

Die zentrale Definition steht in `backend/app/research/areas.py`.

| Land             | Fachliche Ebene        | Regulärer OSM admin_level | Zulässige Regionscodes            |
| ---------------- | ---------------------- | ------------------------: | --------------------------------- |
| Deutschland (DE) | municipality           |                         8 | DE-SH, DE-HH, DE-MV, DE-NI, DE-HB |
| Dänemark (DK)    | municipality / kommune |                         7 | DK-83                             |

Das sind Schleswig-Holstein, Hamburg, Mecklenburg-Vorpommern, Niedersachsen,
Bremen und Region Syddanmark. Die Scope-Prüfung verlangt den **exakten Code aus
`address["ISO3166-2-lvl4"]`**, das passende ISO-Land und die explizit ausgewählte
Region. Freie `state`-/`city`-Strings, Namen und Bounding-Boxen genügen nicht.
Fehlt die administrative ISO-Hierarchie, wird die Relation abgewiesen. Diese
Hierarchie wurde an der eigenen Instanz überprüft; Übersetzungen von Ortsnamen
beeinflussen die Entscheidung nicht. Es gibt keinen unscharfen Ersatz bei fehlenden Tags.

Nach ausdrücklicher fachlicher Freigabe bestehen 17 identitätsgebundene Ausnahmen:

| Kommune          | Relation | Ebene | Amtlicher Gemeindeschlüssel | Region |
| ---------------- | -------: | ----: | --------------------------- | ------ |
| Flensburg        |    27020 |     6 | 01001000                    | DE-SH  |
| Kiel             |    27021 |     6 | 01002000                    | DE-SH  |
| Hamburg          |    62782 |     4 | 02000000                    | DE-HH  |
| Bremen (Stadt)   |    62559 |     6 | 04011000                    | DE-HB  |
| Bremerhaven      |    62658 |     6 | 04012000                    | DE-HB  |
| Lübeck           |    27027 |     6 | 01003000                    | DE-SH  |
| Neumünster       |    62528 |     6 | 01004000                    | DE-SH  |
| Braunschweig     |    62531 |     6 | 03101000                    | DE-NI  |
| Salzgitter       |    62659 |     6 | 03102000                    | DE-NI  |
| Wolfsburg        |    62418 |     6 | 03103000                    | DE-NI  |
| Delmenhorst      |    62414 |     6 | 03401000                    | DE-NI  |
| Emden            |    62562 |     6 | 03402000                    | DE-NI  |
| Oldenburg (Oldb) |    62409 |     6 | 03403000                    | DE-NI  |
| Osnabrück        |    62631 |     6 | 03404000                    | DE-NI  |
| Wilhelmshaven    |    62444 |     6 | 03405000                    | DE-NI  |
| Rostock          |    62405 |     6 | 13003000                    | DE-MV  |
| Schwerin         |    62685 |     6 | 13004000                    | DE-MV  |

Relation, Land, Region, Ebene und `de:amtlicher_gemeindeschluessel` müssen gemeinsam
passen. Das Bundesland Bremen (R62718, Level 4) ist **keine** Gemeinde. Andere
kreisfreie Städte werden nicht automatisch zu Gemeinden umklassifiziert; weitere
Ausnahmen benötigen eine geprüfte Erweiterung dieser Tabelle. Die tatsächlich
beobachtete OSM-Ebene bleibt gespeichert. Siehe [OSM-Grenzmodell](https://wiki.openstreetmap.org/wiki/DE:Grenze).

## Datenmodell und Lebenszyklus

Migration `0016`, ausgehend vom überprüften Head `0015`, legt ausschließlich
`admin.research_area` an:

- UUID `id`: stabile interne ID, beim ersten Import erzeugt.
- `area_type`: Text mit Check für `region`, `district`, `municipality`; der Import
  erzeugt in Part A ausschließlich `municipality`.
- `country_code`, `region_code`, `name`, `display_name`.
- `osm_type='R'`, `osm_id` als positives bigint, `osm_admin_level`;
  Unique Constraint über `(osm_type, osm_id)`.
- `geometry(MultiPolygon,4326)` und `centroid(Point,4326)`.
- `source='osm'`, `retrieved_at`, `created_at`, `updated_at` als aware Timestamps.

Nominatim-`place_id` ist keine fachliche Identität und wird nicht benötigt.
`retrieved_at` bezeichnet den Abruf, **nicht** den letzten OSM-Edit. Ein solcher
Quellzeitstempel wird nicht erfunden. Der API-Bounding-Box-Wert wird aus der
persistierten Geometrie berechnet.

GeoJSON wird vor SQL auf Struktur, geschlossene Ringe, endliche WGS84-Koordinaten
und das bestehende Punktlimit geprüft. Polygon wird zu MultiPolygon normalisiert.
PostGIS prüft `ST_IsValid`; ungültige Polygone werden abgewiesen. Anders als beim
älteren Operations-Geo-Cache gibt es hier kein `ST_MakeValid` und keine stille
Reparatur. `ST_PointOnSurface` erzeugt den innerhalb der Fläche liegenden
Labelpunkt; dessen Coverage wird zusätzlich per Constraint abgesichert.

GiST liegt auf der Geometrie; ein B-Tree auf `(country_code,area_type)` unterstützt
die Gebietsauswahl. Für die begrenzte Substring-Namenssuche wird kein wirkungsloser
B-Tree oder neues `pg_trgm` eingeführt. Listen liefern maximal 50 Gebiete ohne
Polygon; das Detail enthält eine durch das Import-Punktlimit begrenzte Grenze.

Wiederholter Import aktualisiert Namen/Geometrie bei Änderungen, bewahrt UUID und
`created_at` und setzt `updated_at` nur bei Inhaltsänderungen. `ST_Equals` vermeidet
Änderungen durch reine Ringreihenfolge. Unveränderte Abrufe aktualisieren nur
`retrieved_at`. Fehlende Treffer löschen oder deaktivieren **keine** vorhandene
Gemeinde. Der letzte Abruf bleibt sichtbar; Part A hat keine automatische Retention.
Eine neue History-Tabelle und ein Assignment-Cache sind nicht erforderlich.

## Operator-Import

Keine HTTP-Import-Route, kein Scheduler, kein dauerhafter Worker. Auf einem
Operator-Host aus `backend/`, mit bewusst ausgewähltem Admin-Ziel und bestehenden
Operator-Credentials:

```sh
uv run python -m app.research.areas plan --region DE-SH --query Flensburg --query Harrislee
uv run python -m app.research.areas plan --region DK-83 --osm-id 1928254
# Erst nach Prüfung des Plans auf demselben Ziel:
uv run python -m app.research.areas apply --region DE-SH --osm-id 27020
```

`--query` und `--osm-id` sind wiederholbar; maximal 100 Eingaben beziehungsweise
100 eindeutige Relationen je Lauf. Der gesamte Geometriebatch darf das bestehende
`NOMINATIM_MAX_RESPONSE_BYTES` nicht überschreiten. Größere Bestände in explizite
kleinere Batches teilen. Provider-Aufrufe nutzen das bestehende Request-Pacing.

Der Operator verwendet `ADMIN_AUTH_MANAGEMENT_DATABASE_URL` und den bestehenden
`admin_auth_operator`, der zusätzlich nur SELECT/INSERT/UPDATE auf `research_area`
erhält. Es werden keine Runtime-, Migrator- oder Uranus-Schreibcredentials benötigt.
Die unabhängige Rollenprüfung verweigert Source-Schreibrechte, Besitzrechte und DDL.

Plan und Apply melden Land/Region sowie `found`, `new`, `updated`, `unchanged`,
`rejected`. Apply protokolliert den vollständigen Plan **vor** der ersten Mutation.
Zunächst wird der gesamte Provider-Batch geladen. Bei Provider-Ausfall wird kein
Teilbestand geschrieben. Danach laufen Klassifikation und Upserts in einer kurzen
Admin-Transaktion mit Advisory Lock. Positiv flächige Überlappungen zwischen
verschiedenen Gemeinden werden abgewiesen, gemeinsame Grenzen bleiben zulässig.
Bei Konflikten gewinnt der zuerst akzeptierte Eintrag; der Plan macht Ablehnungen
sichtbar. Geometry, Provider-JSON, Credentials und DSNs erscheinen nicht in Logs.

## Lokaler BKG-Gemeindekatalog

Die bereitgestellte Datei `vg250_ebenen_0101/verwaltungsgebiete.xlsx` ist ein
BKG-Verzeichnis mit Stand **01.01.2026**. Der Offline-Konverter liest ausschließlich
`VGTB_VZ_GEM`: Gemeindename, achtstelligen AGS und Bundesland. Er bewahrt führende
Nullen, verweigert Duplikate/Formeln und begrenzt ZIP-/XML-Größen. Keine Geometrie
oder Koordinaten werden übernommen. Gemeindefreie Gebiete werden ausgeschlossen.

```sh
uv run python -m app.research.catalog /path/to/verwaltungsgebiete.xlsx --output /path/to/gemeinden.csv
uv run python -m app.research.areas plan --region DE-SH --catalog /path/to/gemeinden.csv --offset 0 --limit 25
# Den geprüften Batch anschließend mit apply statt plan übernehmen.
```

Die Datei enthält im Scope **2770 Gemeinden**: SH 1104, HH 1, NI 939, HB 2,
MV 724. Zusätzlich vorhandene 25 gemeindefreie Gebiete in Niedersachsen werden
nicht importiert. Dies sind **Katalogzahlen, keine Nominatim-Import-Ergebnisse**.

Je Eintrag sucht Nominatim nach Name/Region (bei fehlendem Treffer einmal nur nach
dem Namen, weiterhin mit Länderfilter) und muss exakt denselben
`de:amtlicher_gemeindeschluessel` liefern. Genau eine administrative Relation
muss passen; bereits einzeln verifizierte Stadt-Ausnahmen werden direkt per Relation
nachgeschlagen und müssen ebenfalls den AGS des Katalogeintrags bestätigen; Lookup prüft den AGS erneut zusammen mit Land, Scope, Ebene und
Geometrie. Namensähnlichkeit genügt nie. `--offset`/`--limit` beziehen sich auf die
nach AGS sortierten Einträge der ausgewählten Region. Fehlende, umgeschlüsselte,
mehrdeutige oder noch nicht freigegebene Stadt-Ausnahmen werden abgewiesen.
Katalog und Original-Workbook werden nicht ins Repository kopiert.

## Gesamten Scope importieren

Der Sammelbefehl verarbeitet den deutschen BKG-Katalog und die **22 Kommunen in
Region Syddanmark** sequenziell. Die dänische Liste folgt dem amtlichen
[Regionen-/Kommunenverzeichnis von Danmarks Statistik](https://www.dst.dk/da/Statistik/dokumentation/nomenklaturer/nuts).
Die Codes sind mit [SOP_KOMKOD](https://www.dst.dk/da/Statistik/dokumentation/Times/sociale-pensioner/sop-komkod)
abgeglichen. Dessen zusätzliche Verwaltungswerte (etwa Ausland, Danmark und
Christiansø) sind keine Gemeinden und werden nicht übernommen. Die OSM-Relationen
sind im kleinen expliziten Katalog `app/research/scope.py` festgehalten; die
normalen Lookup-Prüfungen für Land, Ebene, Region und Geometrie gelten weiterhin.
Es gibt keinen öffentlichen Geocoder-Fallback.

```sh
# backend/, mit Operator-Konfiguration. Zuerst den obigen BKG-Konverter ausführen.
uv run python -m app.research.scope plan --german-catalog /path/to/gemeinden.csv > /path/to/areas-plan.jsonl
# Erst nach Prüfung der Zählwerte und Ablehnungen:
uv run python -m app.research.scope apply --german-catalog /path/to/gemeinden.csv > /path/to/areas-apply.jsonl
# Optional nur eine Region:
uv run python -m app.research.scope plan --region DK-83
```

Jede Gemeinde verwendet dieselben Rollen-, Identitäts-, Geometrie- und
Überlappungsprüfungen wie der Einzelimport. Pro Gemeinde gibt es eine begrenzte
Transaktion; ein gesamter Scope-Lauf ist **nicht atomar**. Bei einem Providerfehler
stoppt der Lauf, bereits erfolgreich übernommene Gemeinden bleiben bestehen.
Ein erneuter Apply ist idempotent. Alternativ erlauben `--offset` und `--limit`
eine gezielte Fortsetzung, mit unverändertem Katalog und derselben Regionsauswahl.
Die Reihenfolge ist `(region_code, municipality_code)`; der ausgegebene Offset
ist nullbasiert. Den letzten gemeldeten Offset beim Wiederanlauf zu wiederholen
ist sicher. stdout enthält JSONL mit einzelnen Ergebnissen und regionalen Summen,
stderr die sicheren Betriebslogs. Keine Geometrien oder Zugangsdaten im Report.
Exit 0: alle ausgewählten Einträge geprüft; Exit 2: Lauf beendet, aber Ablehnungen;
Exit 1: Konfigurations-/Infrastrukturfehler. Ablehnungen sind niemals ein Nachweis
vollständiger geografischer Abdeckung. Spätere Einträge können im Apply zusätzliche
Überlappungen mit zuvor importierten Grenzen zeigen; der Apply-Report ist maßgeblich.

Am 27.09.2026 waren 21 dänische Kommunen über die eigene Instanz verifizierbar.
Aabenraa (amtlicher Code 580, OSM R1928466) fehlte auch im direkten Lookup und bleibt
im Katalog als sichtbare Ablehnung. Die Relation ist zusätzlich in
[Wikidata Q21152](https://www.wikidata.org/wiki/Q21152) referenziert; Geometrie wird
auch dafür ausschließlich über die eigene Nominatim-Instanz bezogen. Das ist eine
Provider-Datenlücke, keine Erlaubnis zum Import einer Stadt-/POI-Geometrie.

## Amtliche Einwohnerzahlen

Nach fachlicher Freigabe ergänzt ein **separater Offline-Operatorimport** die
Einwohnerzahlen aus BKG VG250-EW. Die bereitgestellte zweite Datei hat Stand
**31.12.2024**, nicht 2026. Verifiziert wurden beispielsweise Flensburg 96326
und Kiel 252668; diese Werte sind keine Test-Fixtures oder Schätzungen.
Quelle und Nutzungsbedingungen: [BKG VG250-EW](https://gdz.bkg.bund.de/index.php/default/verwaltungsgebiete-1-250-000-mit-einwohnerzahlen-stand-31-12-vg250-ew-31-12.html).

```sh
uv run python -m app.research.population plan /path/to/vg250-ew/verwaltungsgebiete.xlsx --region DE-SH --offset 0 --limit 25
# Nach Prüfung desselben lokalen Batches: apply statt plan.
```

Der Parser liest den Stichtag vom Deckblatt und ausschließlich `ADE=6` aus
`VGTB_ATT_VG`, niemals die gleichnamigen Kreis-/Land-Zeilen. AGS, Einwohnerzahl
`EWZ` und Name müssen gültig und eindeutig sein; fehlende Werte werden nicht zu
Null. Nur bereits importierte DE-Gemeinden mit exakt passendem, aus OSM geprüftem
`municipality_key` sind aktualisierbar. Mehrdeutige und fehlende Zuordnungen werden
gezählt und abgewiesen. Es gibt keinen Namensabgleich als Ersatz, keine automatische
Gebietsreform-Umrechnung und keine dänischen Einwohnerzahlen aus dieser Datei.

`admin.research_area` speichert optional `population_count`, `population_date`,
`population_source='bkg_vg250_ew'`, `population_name`, SHA-256 der lokalen Datei und
`population_imported_at`; ein Constraint verlangt vollständige Provenienz.
Die Geometrie bleibt OSM. Wiederholungen sind idempotent; ältere Stichtage dürfen
neuere nicht überschreiben. Ein späterer OSM-AGS-Wechsel entfernt die nicht mehr
zuordenbare Einwohnerangabe. Ein unveränderter AGS bewahrt sie. Kein Nominatim-
oder sonstiger Netzwerkrequest ist für diesen Offline-Import erforderlich.

Das Dossier zeigt Zahl, Stichtag, amtlichen Namen sowie © BKG, Bezugsjahr,
verlinkte `dl-de/by-2-0` und Datenquellen. Der historische Gebietsstand kann von
der aktuellen OSM-Grenze abweichen; deshalb werden keine Pro-Kopf-Raten oder
Bevölkerungsdichten berechnet. Quellenzahlen bleiben unverändert.

## Rollen, Migration und Deployment

Runtime/API: SELECT auf `research_area`; INSERT/UPDATE/DELETE oder geerbte
Besitzrechte führen zum Runtime-Boundary-Fehler. Journalist und Systemadmin dürfen
Gebiete über dieselbe Research-Leseautorisierung abfragen. Nur der separate
Operator darf importieren. Migrations- und Runtimeprozesse importieren nicht automatisch.

Nach Migration durch `admin_migrator` werden durch den Betreiber provisioniert:

```sql
GRANT SELECT ON admin.research_area TO admin_user;
GRANT SELECT, INSERT, UPDATE ON admin.research_area TO admin_auth_operator;
```

`RUNTIME_GRANTS`, `OPERATOR_GRANTS` und Ansible-Boundary/Bootstrap-Verträge enthalten
diese Matrix. Der neue Upgrade-Ausgangspunkt 0015 wurde in einer wegwerfbaren
PostGIS-Datenbank migriert und katalogbasiert gefingerprintet. Die bestehenden
Upgrade-Ausgangspunkte bleiben erhalten. Erst Migration und Grants, dann passende
Backend-/Frontend-Versionen starten. Downgrade entfernt nur den importierten
Gebietsbestand; deshalb vor Downgrade sichern. Es gibt keine Uranus-DDL/DML.

## Spatial SQL und Ereignissemantik

Source und Admin bleiben getrennte Verbindungen mit getrennten Rechten. Ein
Gebietsfilter lädt genau eine gespeicherte Grenze als EWKB aus Admin und bindet
sie in der Source-Query. Ein Cross-Schema-Join würde unzulässige zusätzliche
Readerrechte voraussetzen; deshalb wird der bestehende Geo-Scope-Stil verwendet:

```sql
v.point && ST_GeomFromEWKB(:area_wkb)
AND ST_Covers(ST_GeomFromEWKB(:area_wkb), v.point)
```

Der vorhandene Source-GiST auf `venue.point` kann genutzt werden; der Admin-GiST
unterstützt Import-Überlappungsprüfung und spätere Punktabfragen. Es gibt keine
neuen Source-Indizes und keine Polygonladung pro Treffer. Kleine Testtabellen
können berechtigt einen Seq Scan wählen; EXPLAIN mit deaktiviertem Seq Scan prüft
zusätzlich die Indexfähigkeit. Kein Cache ohne vorherige Messung.

Grenzpunkte gehören durch `ST_Covers` zum Gebiet. Geteilte Grenzen können zu zwei
Gemeinden passen; daraus wird keine künstliche eindeutige Zuordnung erzeugt.

Events werden über **denselben passenden Termin** zeitlich und räumlich gefiltert.
`EFFECTIVE_VENUE_SQL` und `EFFECTIVE_SPACE_SQL` aus `repositories/location.py`
bleiben maßgeblich: Date-Venue überschreibt Event-Venue; ein Venue-Override
unterbricht Event-Space-Vererbung. Ohne Venue-Override bleibt Date-Space vor
Event-Space maßgeblich. Punkte stammen aus dem effektiven Venue, niemals aus
Nominatim-Vorschlägen. Mehrörtige Events dürfen in mehreren Gemeindefiltern erscheinen.
Die Trefferzeile zeigt den frühesten passenden öffentlichen Termin; Monatszahlen
zählen unterschiedliche Events pro Monat, nicht Termine.

Organisationen werden ausschließlich über passende öffentliche Event-Termine
zugeordnet. Aktivität ist kein Nachweis eines Organisationssitzes. Bei aktivem
Area-Filter zeigt die Venue-Liste auch Orte ohne Event-Aktivität, solange keine
zusätzlichen zeitlichen/Event-Filter gesetzt sind. Solche Filter verlangen eine
passende öffentliche Veranstaltung. Ohne Area bleibt der bisherige Vertrag erhalten.

## API und UI

- `GET /api/v1/research/areas`: `q`, `country_code`, `area_type`, `page`, `page_size`.
  `q` sucht literal im Namen und erlaubt die exakte interne UUID zur Labelauflösung.
- `GET /api/v1/research/areas/{id}`: Municipality-Dossier, Grenzgeometrie,
  Event-/Venue-/Organisation-Seiten, Monatsaktivität, Top-10-Orte/-Organisationen/-Kategorien.
- `area_id` ergänzt Search, Collections, Entity-Dossiers und Export additiv.
  `city` bleibt kompatibel; beide Filter werden per AND kombiniert.

Die suchbare Auswahl „Gemeinde / Kommune“ zeigt Land und Region. Sie lädt höchstens
zehn Treffer nach Eingabe und verwendet keine vollständige Gemeindeliste. Auswahl,
Zeitraum und weitere Filter stehen in der URL. CSV verwendet unverändert denselben
Research-Query- und Source-Snapshot-Pfad. Ein Link führt zum Dossier unter
`/research/areas/{id}`; ein weiterer zurück zur gefilterten Event-Liste samt CSV.
Ein eigener Sidebar-Eintrag ist nicht nötig.

Das responsive Dossier zeigt echte Zählwerte, Aktivität, Nutzung und die Grenze
mit den Venue-Punkten dieser Ergebnisseite. `PointMap`/`ResearchMap` und Leaflet
werden wiederverwendet; der Server liefert Polygon und Bounding-Box. Leere Gebiete
zeigen weiterhin die Grenze. Kategorien nutzen die zentrale Kulturbytes-Palette.
OSM-Attribution bleibt sichtbar; Quellen nennen OpenStreetMap über die eigene
Nominatim-Instanz, Relation und Abrufzeit. Einwohnerzahlen stammen optional aus einem gesonderten BKG-Import mit Stichtag und
Quelle. Keine geschätzten Flächen oder journalistischen Bewertungen.

## Bekannte Grenzen und Folgearbeit

- Discovery ist gezielt und unvollständig, kein amtliches Gemeindeverzeichnis.
- Fehlende ISO-Hierarchie, zu große oder ungültige Geometrie und nicht freigegebene
  Stadt-Ausnahmen werden abgewiesen; der Import erweitert seinen Scope nicht selbst.
- Keine automatische Entfernung historischer Grenzen. Veraltete Abrufzeiten
  bleiben sichtbar und verlangen eine explizite Operator-Prüfung.
- Kein automatischer öffentlicher Fallback und kein Reverse-Geocoding pro Venue.
- Admin-Grenze und Source-Snapshot stammen aus getrennten Datenbanken; die pro
  Request einmal aufgelöste Grenze bleibt für alle Source-Abfragen konstant.
- Gespeicherte Suchen, Preferences, Watches, Push und Notifications sind nicht
  enthalten. Sie können später stabile Area-UUIDs referenzieren, ohne Uranus zu ändern.
