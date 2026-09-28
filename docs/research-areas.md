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

Für deutsche `CatalogEntry`-Imports ersetzt `VERIFIED_MUNICIPALITY_RELATIONS`
in `backend/app/research/areas.py` die unzuverlässige Namenssuche bei exakt diesen AGS:

| AGS      | Gemeinde              | Relation |
| -------- | --------------------- | -------: |
| 01057001 | Ascheberg (Holstein)   |   310405 |
| 01057004 | Behrensdorf (Ostsee)   |   288915 |
| 01057030 | Hohwacht (Ostsee)      |   288939 |
| 01061044 | Horst (Holstein)       |   447194 |

Die Relationen wurden laut bereitgestellter Verifikation per exaktem AGS-Tag in
Overpass gefunden; für die ersten drei liegt außerdem eine Bestätigung des eigenen
Nominatim-Lookups vor. Horst ist lokal durch synthetische Lookup-Vertragstests
abgesichert; diese sind kein Live-Nachweis. Bei jedem Import bleibt für alle vier
der normale `boundary_record()`-Lookup mit `municipality_item()`/`boundary()`
verpflichtend: Relation, administrative Grenze, DE, DE-SH, Ebene 8, exakter AGS und
Polygon/MultiPolygon. Auch die nachgelagerte PostGIS-Geometrieprüfung bleibt erhalten.
Das Mapping ersetzt nur Discovery und gewährt keine Validierungsausnahme.
`CITY_EXCEPTIONS` bleibt unverändert; andere reguläre Gemeinden verwenden weiter
die bestehende Discovery. Es gibt keinen zusätzlichen Runtime-Provider.

**Nominatim ist kein vollständiger Gemeindekatalog.** Seine Suche liefert höchstens
zehn gerankte Treffer pro Begriff. Ein Operator wählt deshalb explizit Suchbegriffe
oder bekannte OSM-Relationen. Ein Importlauf garantiert keine Vollständigkeit eines
Bundeslands. Es gibt weder Overpass-Zugriffe noch eine automatische Europa-Suche.
Siehe den [Nominatim-Suchvertrag](https://nominatim.org/release-docs/5.0/api/Search/).

## Länderspezifische Regeln und Scope

Die zentrale Definition steht in `backend/app/research/areas.py`.

Der unterstützte Eingangsscope ist **Deutschland + Dänemark vollständig**:
alle Gemeinden des amtlichen deutschen BKG-Katalogs und alle 98 dänischen Kommunen.
Reguläre OSM-Ebenen: DE `admin_level=8`, DK `admin_level=7`.

| Region | Name                   | Amtlicher DE-Länderschlüssel / DK-Kommunenanzahl |
| ------ | ---------------------- | -----------------------------------------------: |
| DE-SH  | Schleswig-Holstein     |                                               01 |
| DE-HH  | Hamburg                |                                               02 |
| DE-NI  | Niedersachsen          |                                               03 |
| DE-HB  | Bremen                 |                                               04 |
| DE-NW  | Nordrhein-Westfalen    |                                               05 |
| DE-HE  | Hessen                 |                                               06 |
| DE-RP  | Rheinland-Pfalz        |                                               07 |
| DE-BW  | Baden-Württemberg      |                                               08 |
| DE-BY  | Bayern                 |                                               09 |
| DE-SL  | Saarland               |                                               10 |
| DE-BE  | Berlin                 |                                               11 |
| DE-BB  | Brandenburg            |                                               12 |
| DE-MV  | Mecklenburg-Vorpommern |                                               13 |
| DE-SN  | Sachsen                |                                               14 |
| DE-ST  | Sachsen-Anhalt         |                                               15 |
| DE-TH  | Thüringen              |                                               16 |
| DK-81  | Nordjylland            |                                               11 |
| DK-82  | Midtjylland            |                                               19 |
| DK-83  | Syddanmark             |                                               22 |
| DK-84  | Hovedstaden            |                                               29 |
| DK-85  | Sjælland               |                                               17 |

Die Scope-Prüfung verlangt den **exakten Code aus
`address["ISO3166-2-lvl4"]`**, das passende ISO-Land und die explizit ausgewählte
Region. Freie `state`-/`city`-Strings, Namen und Bounding-Boxen genügen nicht.
Fehlt die administrative ISO-Hierarchie, wird die Relation abgewiesen. Diese
Hierarchie wurde an der eigenen Instanz überprüft; Übersetzungen von Ortsnamen
beeinflussen die Entscheidung nicht. Es gibt keinen unscharfen Ersatz bei fehlenden Tags.

Am 28.09.2026 wurden die 107 Stadt-/Stadtstaat-Einträge des BKG-Katalogs mit
AGS-Endung `000` einzeln gegen die eigene Nominatim-Instanz geprüft: exakter AGS,
Land, Region, administrative Relation, Ebene und Geometrie im direkten Lookup.
Damit sind folgende **identitätsgebundene** Ausnahmen bestätigt; die AGS-Endung
selbst ist ausdrücklich **keine** Importregel:

| Kommune                    | Relation | Ebene | Amtlicher Gemeindeschlüssel | Region |
| -------------------------- | -------: | ----: | --------------------------- | ------ |
| Flensburg                  |    27020 |     6 | 01001000                    | DE-SH  |
| Kiel                       |    27021 |     6 | 01002000                    | DE-SH  |
| Lübeck                     |    27027 |     6 | 01003000                    | DE-SH  |
| Neumünster                 |    62528 |     6 | 01004000                    | DE-SH  |
| Hamburg                    |    62782 |     4 | 02000000                    | DE-HH  |
| Braunschweig               |    62531 |     6 | 03101000                    | DE-NI  |
| Salzgitter                 |    62659 |     6 | 03102000                    | DE-NI  |
| Wolfsburg                  |    62418 |     6 | 03103000                    | DE-NI  |
| Delmenhorst                |    62414 |     6 | 03401000                    | DE-NI  |
| Emden                      |    62562 |     6 | 03402000                    | DE-NI  |
| Oldenburg (Oldb)           |    62409 |     6 | 03403000                    | DE-NI  |
| Osnabrück                  |    62631 |     6 | 03404000                    | DE-NI  |
| Wilhelmshaven              |    62444 |     6 | 03405000                    | DE-NI  |
| Bremen                     |    62559 |     6 | 04011000                    | DE-HB  |
| Bremerhaven                |    62658 |     6 | 04012000                    | DE-HB  |
| Düsseldorf                 |    62539 |     6 | 05111000                    | DE-NW  |
| Duisburg                   |    62456 |     6 | 05112000                    | DE-NW  |
| Essen                      |    62713 |     6 | 05113000                    | DE-NW  |
| Krefeld                    |    62748 |     6 | 05114000                    | DE-NW  |
| Mönchengladbach            |    62410 |     6 | 05116000                    | DE-NW  |
| Mülheim an der Ruhr        |    62385 |     6 | 05117000                    | DE-NW  |
| Oberhausen                 |    62734 |     6 | 05119000                    | DE-NW  |
| Remscheid                  |    62455 |     6 | 05120000                    | DE-NW  |
| Solingen                   |    62699 |     6 | 05122000                    | DE-NW  |
| Wuppertal                  |    62478 |     6 | 05124000                    | DE-NW  |
| Bonn                       |    62508 |     6 | 05314000                    | DE-NW  |
| Köln                       |    62578 |     6 | 05315000                    | DE-NW  |
| Leverkusen                 |    62449 |     6 | 05316000                    | DE-NW  |
| Bottrop                    |    62634 |     6 | 05512000                    | DE-NW  |
| Gelsenkirchen              |    62522 |     6 | 05513000                    | DE-NW  |
| Münster                    |    62591 |     6 | 05515000                    | DE-NW  |
| Bielefeld                  |    62646 |     6 | 05711000                    | DE-NW  |
| Bochum                     |    62644 |     6 | 05911000                    | DE-NW  |
| Dortmund                   |  1829065 |     6 | 05913000                    | DE-NW  |
| Hagen                      |  1800297 |     6 | 05914000                    | DE-NW  |
| Hamm                       |    62499 |     6 | 05915000                    | DE-NW  |
| Herne                      |    62396 |     6 | 05916000                    | DE-NW  |
| Darmstadt                  |    62581 |     6 | 06411000                    | DE-HE  |
| Frankfurt am Main          |    62400 |     6 | 06412000                    | DE-HE  |
| Offenbach am Main          |    62695 |     6 | 06413000                    | DE-HE  |
| Wiesbaden                  |    62496 |     6 | 06414000                    | DE-HE  |
| Hanau                      |   535895 |     6 | 06415000                    | DE-HE  |
| Kassel                     |    62598 |     6 | 06611000                    | DE-HE  |
| Koblenz                    |    62512 |     6 | 07111000                    | DE-RP  |
| Trier                      |   172679 |     6 | 07211000                    | DE-RP  |
| Frankenthal (Pfalz)        |    62573 |     6 | 07311000                    | DE-RP  |
| Kaiserslautern             |    62652 |     6 | 07312000                    | DE-RP  |
| Landau in der Pfalz        |    62391 |     6 | 07313000                    | DE-RP  |
| Ludwigshafen am Rhein      |    62347 |     6 | 07314000                    | DE-RP  |
| Mainz                      |    62630 |     6 | 07315000                    | DE-RP  |
| Neustadt an der Weinstraße |    62724 |     6 | 07316000                    | DE-RP  |
| Pirmasens                  |    62642 |     6 | 07317000                    | DE-RP  |
| Speyer                     |    62352 |     6 | 07318000                    | DE-RP  |
| Worms                      |    62453 |     6 | 07319000                    | DE-RP  |
| Zweibrücken                |    62719 |     6 | 07320000                    | DE-RP  |
| Stuttgart                  |    62375 |     6 | 08111000                    | DE-BW  |
| Heilbronn                  |    62751 |     6 | 08121000                    | DE-BW  |
| Baden-Baden                |    62340 |     6 | 08211000                    | DE-BW  |
| Karlsruhe                  |    62518 |     6 | 08212000                    | DE-BW  |
| Heidelberg                 |    62487 |     6 | 08221000                    | DE-BW  |
| Mannheim                   |    62691 |     6 | 08222000                    | DE-BW  |
| Pforzheim                  |    62471 |     6 | 08231000                    | DE-BW  |
| Freiburg im Breisgau       |    62768 |     6 | 08311000                    | DE-BW  |
| Ulm                        |    62495 |     6 | 08421000                    | DE-BW  |
| Ingolstadt                 |    62381 |     6 | 09161000                    | DE-BY  |
| München                    |    62428 |     6 | 09162000                    | DE-BY  |
| Rosenheim                  |  2168233 |     6 | 09163000                    | DE-BY  |
| Landshut                   |    62484 |     6 | 09261000                    | DE-BY  |
| Passau                     |    62629 |     6 | 09262000                    | DE-BY  |
| Straubing                  |    62636 |     6 | 09263000                    | DE-BY  |
| Amberg                     |    62772 |     6 | 09361000                    | DE-BY  |
| Regensburg                 |    62411 |     6 | 09362000                    | DE-BY  |
| Weiden i.d.OPf.            |    62554 |     6 | 09363000                    | DE-BY  |
| Bamberg                    |    62525 |     6 | 09461000                    | DE-BY  |
| Bayreuth                   |    62640 |     6 | 09462000                    | DE-BY  |
| Coburg                     |    62717 |     6 | 09463000                    | DE-BY  |
| Hof                        |    62589 |     6 | 09464000                    | DE-BY  |
| Ansbach                    |    62654 |     6 | 09561000                    | DE-BY  |
| Erlangen                   |    62403 |     6 | 09562000                    | DE-BY  |
| Fürth                      |    62374 |     6 | 09563000                    | DE-BY  |
| Nürnberg                   |    62780 |     6 | 09564000                    | DE-BY  |
| Schwabach                  |    62720 |     6 | 09565000                    | DE-BY  |
| Aschaffenburg              |    62532 |     6 | 09661000                    | DE-BY  |
| Schweinfurt                |    62534 |     6 | 09662000                    | DE-BY  |
| Würzburg                   |    62464 |     6 | 09663000                    | DE-BY  |
| Augsburg                   |    62407 |     6 | 09761000                    | DE-BY  |
| Kaufbeuren                 |    62349 |     6 | 09762000                    | DE-BY  |
| Kempten (Allgäu)           |    62701 |     6 | 09763000                    | DE-BY  |
| Memmingen                  |    62590 |     6 | 09764000                    | DE-BY  |
| Berlin                     |    62422 |     4 | 11000000                    | DE-BE  |
| Brandenburg an der Havel   |    62470 |     6 | 12051000                    | DE-BB  |
| Cottbus                    |    62430 |     6 | 12052000                    | DE-BB  |
| Frankfurt (Oder)           |    62523 |     6 | 12053000                    | DE-BB  |
| Potsdam                    |    62369 |     6 | 12054000                    | DE-BB  |
| Rostock                    |    62405 |     6 | 13003000                    | DE-MV  |
| Schwerin                   |    62685 |     6 | 13004000                    | DE-MV  |
| Chemnitz                   |    62594 |     6 | 14511000                    | DE-SN  |
| Dresden                    |   191645 |     6 | 14612000                    | DE-SN  |
| Leipzig                    |    62649 |     6 | 14713000                    | DE-SN  |
| Dessau-Roßlau              |    62526 |     6 | 15001000                    | DE-ST  |
| Halle (Saale)              |    62638 |     6 | 15002000                    | DE-ST  |
| Magdeburg                  |    62481 |     6 | 15003000                    | DE-ST  |
| Erfurt                     |    62745 |     6 | 16051000                    | DE-TH  |
| Gera                       |    62671 |     6 | 16052000                    | DE-TH  |
| Jena                       |    62693 |     6 | 16053000                    | DE-TH  |
| Suhl                       |    62450 |     6 | 16054000                    | DE-TH  |
| Weimar                     |    62493 |     6 | 16055000                    | DE-TH  |

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

Der am 28.09.2026 geladene bundesweite Workbook enthält **10.747 Gemeinden**:
SH 1104, HH 1, NI 939, HB 2, NW 396, HE 421, RP 2300, BW 1101, BY 2056,
SL 52, BE 1, BB 413, MV 724, SN 418, ST 218, TH 601. Die zusätzlich enthaltenen
192 gemeindefreien Gebiete werden ausgeschlossen. Dies sind **Katalogzahlen,
keine Nominatim-Import-Ergebnisse**. Eine zuvor für Norddeutschland konvertierte
CSV muss aus dem bundesweiten Workbook neu erzeugt werden; fehlende ausgewählte
Regionen führen zu einem sichtbaren Konfigurationsfehler.

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

Der Sammelbefehl verarbeitet den deutschen BKG-Katalog und alle **98 dänischen Kommunen in fünf Regionen** sequenziell. Die dänische Liste folgt dem amtlichen
[Regionen-/Kommunenverzeichnis von Danmarks Statistik](https://www.dst.dk/da/Statistik/dokumentation/nomenklaturer/nuts).
Die Codes sind mit [SOP_KOMKOD](https://www.dst.dk/da/Statistik/dokumentation/Times/sociale-pensioner/sop-komkod)
abgeglichen. Dessen zusätzliche Verwaltungswerte (etwa Ausland, Danmark und
Christiansø) sind keine Gemeinden und werden nicht übernommen. Die OSM-Relationen
sind im expliziten Katalog `app/research/danish_catalog.py` festgehalten und mit dem
[OSM-Relationsverzeichnis](https://wiki.openstreetmap.org/w/index.php?title=Denmark/Da:Administrative_boundaries&oldid=1281923)
abgeglichen; die
normalen Lookup-Prüfungen für Land, Ebene, Region und Geometrie gelten weiterhin.
Auch Einzelimporte akzeptieren für DK ausschließlich eine zur Region passende
Relation aus diesem Katalog. Es gibt keinen öffentlichen Geocoder-Fallback.

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

### Verifikation und sichtbare Lücken (28.09.2026)

Ein echter `scope plan` mit eingeschränkter Operatorrolle gegen eine **leere,
wegwerfbare PostGIS-Testdatenbank** und die eigene produktive Nominatim-Instanz
hat alle 98 dänischen Einträge geprüft: 96 `new`, zwei `rejected`.
Die expliziten Relationen fehlen im direkten Lookup:

| Region | Code | Kommune  | Relation | Ergebnis                                                |
| ------ | ---- | -------- | -------: | ------------------------------------------------------- |
| DK-81  | 787  | Thisted  |  2095303 | `rejected`, Relation im eigenen Provider nicht gefunden |
| DK-83  | 580  | Aabenraa |  1928466 | `rejected`, Relation im eigenen Provider nicht gefunden |

Keine Ersatzrelation, kein Stadt-/POI-Polygon und kein öffentlicher Provider wurde
verwendet. Die übrigen Kommunen bleiben unabhängig davon importierbar. Diese
Prüfung verändert keine Produktionsdaten und behauptet keinen Produktivimport.
Ein weiterer echter Plan prüfte alle 107 oben genannten DE-Sonderfälle sowie eine
reguläre Saarland-Gemeinde: 108 `new`, keine Ablehnungen. Ein Plan ohne `--region`
meldete das vollständige Inventar mit 10.845 Einträgen und prüfte einen begrenzten
Drei-Gemeinden-Batch erfolgreich. Beide Pläne verwendeten dieselbe leere Testdatenbank;
sie ersetzt keine Klassifikation gegenüber dem vorhandenen Produktionsbestand.
Zusätzlich bestand ein Plan für Aachen, Göttingen, Hannover, Saarbrücken und Eisenach
(Thüringen) mit ihren exakten BKG-AGS. Alle fünf verwenden die reguläre Ebene 8;
es wurden dafür keine Ausnahmen hinzugefügt. Insgesamt sind damit 112 verschiedene
deutsche Gemeinden live geprüft.
Ein vollständiger Provider-Plan aller 10.747 deutschen Gemeinden wurde nicht durchgeführt. Weitere
fehlende/umgeschlüsselte deutsche Gemeinden oder nicht erfasste Sonderfälle sind
damit nicht ausgeschlossen und bleiben im jeweiligen Plan als `rejected` sichtbar.
Vollständigkeit bezeichnet ausschließlich den amtlichen **Eingangskatalog**;
sie garantiert weder Provider-Abdeckung noch eine lückenlose importierte Geografie.

### Grenzen und Resume

CSV: maximal 20.000 deutsche Einträge und 2 MiB. Workbook: maximal 20.000 Zeilen
pro Sheet, 16 MiB komprimiert und 128 MiB entpackt. Diese bestehenden Grenzen
reichen für den geprüften bundesweiten Katalog. `scope` verarbeitet höchstens
20.098 Einträge (`20.000 + 98`), `--offset` 0–20.098 und `--limit` 1–20.098.
Die Einzelimport-Batchgrenze von 100, Geometrie-/HTTP-Limits und sequentielle
Provider-Abfragen bleiben erhalten; `scope` verwendet eine Gemeinde je Transaktion.

```sh
# Gleicher Katalog und gleiche Regionsauswahl wie beim ursprünglichen Lauf:
uv run python -m app.research.scope plan --german-catalog /tmp/uranus-research-gemeinden-2026.csv --offset 500 --limit 100
# Nach Prüfung dieses Batches:
uv run python -m app.research.scope apply --german-catalog /tmp/uranus-research-gemeinden-2026.csv --offset 500 --limit 100
```

Offsets aus alten Versionen mit eingeschränktem Scope nicht weiterverwenden:
Die neue Regionsauswahl ändert die Sortierung. Nach dem Versionswechsel bei 0
beginnen; bestehende Relationsidentitäten behalten ihre UUIDs.

### Operator-Environment auf dem Webserver

`areas`, `scope` und `population` erzeugen `Settings(_env_file=None)`. Sie lesen
nur exportierte Environment-Variablen; normale Web-App-/Worker-Settings unterstützen
weiterhin `.env`. Der root-geschützte Inhalt von `/etc/uranus-admin/operator.env`
wird vor dem Benutzerwechsel geladen. Keine Rechteänderung an `backend/.env`,
kein Kopieren von Secrets und kein zusätzliches Wrapper-Skript sind nötig.

Nach Deployment von Migration `0017` und dem passenden Release, in einer root-Shell
(ohne Shell-Tracing), mit bestehender Operator-Konfiguration einschließlich
`NOMINATIM_BASE_URL` und `ADMIN_AUTH_MANAGEMENT_DATABASE_URL`:

```sh
set -a
. /etc/uranus-admin/operator.env
set +a
cd /var/lib/uranus-admin/current/backend

runuser -u oklab -- uv run --no-cache --no-sync --offline --no-python-downloads --no-env-file python -m app.research.scope plan --german-catalog /tmp/uranus-research-gemeinden-2026.csv
# Erst nach Prüfung des Plans ausdrücklich ausführen:
runuser -u oklab -- uv run --no-cache --no-sync --offline --no-python-downloads --no-env-file python -m app.research.scope apply --german-catalog /tmp/uranus-research-gemeinden-2026.csv
# Beispiel einer Fortsetzung, denselben letzten gemeldeten Offset wiederholen:
runuser -u oklab -- uv run --no-cache --no-sync --offline --no-python-downloads --no-env-file python -m app.research.scope apply --german-catalog /tmp/uranus-research-gemeinden-2026.csv --offset 500 --limit 100
```

`runuser` ohne Login-Shell reicht die exportierten Operatorvariablen weiter.
Bei anderem aktiven Release-Pfad dessen `backend/` verwenden; der BKG-CSV muss
für `oklab` lesbar sein. Die Operator-DSN gehört weiterhin nicht in Runtime-Units.

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
diese Matrix. Auch der Upgrade-Ausgangspunkt `0016` wurde in einer wegwerfbaren
PostGIS-Datenbank migriert und katalogbasiert gefingerprintet. Die bestehenden
Upgrade-Ausgangspunkte bleiben erhalten. Erst Migration und Grants, dann passende
Backend-/Frontend-Versionen starten. Migration `0016` bleibt unverändert.
Die lineare Folgemigration `0017` ersetzt ausschließlich `research_area_region`
durch den Constraint für 16 deutsche und fünf dänische Regionen. Tabelle, UUIDs,
Geometrien und Grants bleiben erhalten; Metadaten und Deployment-Upgrade-Vertrag
sind auf denselben Head abgestimmt. Es sind keine zusätzlichen Grants nötig.
Die `ALTER TABLE`-Operation benötigt kurzzeitig eine exklusive Tabellensperre;
Importjobs dafür koordinieren. Runtime/Worker erwarten anschließend den neuen Head.

Downgrade `0017 → 0016` sperrt die Tabelle vor der Prüfung und bricht ausdrücklich
ab, sobald Gebiete außerhalb des alten Scopes vorhanden sind. Er löscht keine Daten.
Ohne solche Gebiete wird nur der vorherige Constraint wiederhergestellt.
Ein weiterer Downgrade unter `0016` entfernt gemäß der unveränderten Migration
den importierten Gebietsbestand; vorher sichern. Es gibt keine Uranus-DDL/DML.

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

## Shared admin usage

`admin.research_area` ist die kanonische persistierte Gebietsquelle für Research
und Operations-Gemeindefilter. Beide Workspaces suchen mit derselben
`AdministrativeAreaSelect`-Combobox über `GET /api/v1/research/areas`: mindestens
zwei Zeichen, 300 ms Debounce, maximal zehn Ergebnisse, AbortController und
Generationsschutz für Suche und Auswahl-Hydration. Länder-/Regionslabels stammen
aus denselben zentralen Definitionen. Tastaturbedienung, Lade-/Leer-/Fehlerzustand
und Combobox-ARIA sind gemeinsam; Research verwendet Blau, Operations den bisherigen
Admin-Akzent. Auth-Revisionswechsel und Unmount verwerfen laufende Antworten.

`GET /api/v1/research/areas/{id}/metadata` lädt eine Auswahl direkt per UUID.
Dieser zusätzliche kleine Read-Endpunkt benötigt weder Source-Verbindung noch
Polygon, Event-/Venue-/Organisationslisten oder Statistikabfragen des Dossiers.
Die Projektion entspricht dem Area-Listenobjekt. Er verwendet dieselbe
Systemadmin-oder-Journalist-Autorisierung; Operations-Routen bleiben ausschließlich
Systemadmins vorbehalten. POST/PATCH/Import sind hier nicht möglich.

### URL-Kompatibilität und alte Gebiete

**Entscheidung A:** Operations behält `geo_scope_id` als kompatiblen Parameter.
Der Wert ist bei einer neuen Gemeindeauswahl exakt `research_area.id`, identisch
mit dem `area_id` im Research-Workspace. Damit bleiben alle Operations-API-,
Cursor-, Diagnose-/SQL-Provenance- und Link-Verträge erhalten. Ein zweiter
Operations-Parameter mit konkurrierender Priorität wird nicht eingeführt.

Der gemeinsame Resolver lädt in einer begrenzten Admin-Abfrage zunächst die
Research-Area. Eine alte `geo_area`-UUID wird über deren OSM-Relationsidentität auf
eine vorhandene Research-Area aufgelöst. Dabei wird **deren aktuelle Geometrie**
verwendet, niemals die alte Polygonkopie. Die kompatible Geo-Metadatenantwort
kennzeichnet dies durch `area_id` und liefert die kanonische `id`. Das Frontend
lädt die Research-Metadaten und ersetzt einen solchen alten URL-Wert einmal durch
die stabile UUID; übrige Filter und Hash bleiben erhalten. Direkte API-Aufrufe
mit der alten UUID funktionieren weiterhin. Unbekannte IDs führen weiterhin zu
einem sichtbaren Fehler, niemals unbemerkt zu einem systemweiten Resultat.

`admin.geo_area` bleibt für andere bereits gespeicherte administrative Grenzen
bestehen. Ohne passendes Research-Objekt funktionieren alte Links unverändert.
Die expliziten alten Discovery-/Import-Endpunkte bleiben systemadmin-geschützt;
selbst ein expliziter Import verwendet bei bereits bekannter OSM-Relation die
Research-Area ohne Provider-Aufruf und ohne neue Geo-Zeile. Die normale
Operations-Auswahl verwendet diese Endpunkte überhaupt nicht mehr.

Keine Migration, keine zusätzlichen Grants und keine Datenbereinigung sind nötig.
Vorhandene alte Polygonkopien werden nicht automatisch gelöscht oder umgeschrieben.
Die In-Memory-Preferences speichern validierte Metadaten, keine Grenzpolygone,
und werden weiterhin bei Sessionverlust gelöscht. URL > Store > Default bleibt
maßgeblich.

### Geprüfte Operations-Ansichten

| Ansicht                        | Räumlicher Filter        | Zuordnung / Verhalten                                                         |
| ------------------------------ | ------------------------ | ----------------------------------------------------------------------------- |
| `/` Dashboard                  | ja                       | gemeinsame räumliche Teilmengen; systemweite Zahlen bleiben gekennzeichnet    |
| `/activity`                    | ja                       | Organization, Venue, Space, Event, Event-Date; andere Typen ausgeschlossen    |
| `/graph`                       | Startsuche               | dieselben räumlichen Typen; direkte Roots und Beziehungen bleiben vollständig |
| `/statistics`                  | ja                       | räumliche Serien vor Aggregation gefiltert; andere Serien systemweit          |
| `/statistics`, Event-Inhalte   | ja                       | Event-Menge vor Kategorien, Rankings und Nennern gefiltert                    |
| `/events`                      | ja                       | realer Termin mit effektivem Venue; bestehende zeitliche Semantik             |
| `/venues`                      | ja                       | autoritativer `venue.point`                                                   |
| `/spaces`                      | ja                       | Point des zugehörigen Venue                                                   |
| `/organizations`               | ja                       | autoritativer `organization.point`                                            |
| `/findings`                    | ja                       | räumlich zuordenbare Source-Entity; fehlende Punkte bleiben unzugeordnet      |
| Entity-Autocomplete            | ja, vier räumliche Typen | identische Entity-Prädikate                                                   |
| `/quality`, `/inbox`, Queues   | nein                     | vorhandene systemweite Semantik und Kennzeichnung bleiben erhalten            |
| `/geocoding`, `/geocoding/:id` | nein                     | systemweite Standortvorschläge; keine neue Gebietsauswahl                     |
| Users, Images, Entity-Details  | nein                     | bestehende systemweite bzw. direkte Detailsemantik                            |

Die Abfragen verwenden die bereits vorhandenen `ST_Covers`-Prädikate mit
Bounding-Box-Vorprüfung und gebundener EWKB über die getrennte Source-Verbindung.
Grenzpunkte bleiben enthalten; Venue-/Space-Vererbung kommt aus `location.py`.
Operations ordnet Organisationen über ihren autoritativen Standort zu; Research
fragt ihre Event-Aktivität ab. Die gemeinsame Gebietsidentität ändert diese
unterschiedlichen fachlichen Fragen nicht.

Die Namenssuche verwendet weiterhin parametriertes, literal escaptes `ILIKE`,
Land-/Area-Type-Filter, deterministische Sortierung und begrenzte Pagination.
Der bundesweite Eingangskatalog umfasst hier 10.845 Einträge. Teilstrings verwenden
weiterhin einen begrenzten Scan; Produktionslatenzen sind nach dem Import zu messen.
Ein B-Tree wird nicht als Teilstringindex ausgegeben. ID-Hydration verwendet den
UUID-Primary-Key. Listen/Metadaten senden keine Polygone; die räumliche Auflösung
lädt eine Grenze je Request, nicht je Source-Ergebnis. Kein N+1 und kein neuer Cache.

Nominatim bleibt Provider für Area-Import-CLI, Adress-Geocoding und explizite
Discovery-Workflows. Normale Gemeindeauswahl und räumliche Operations-Abfragen
benötigen ausschließlich gespeicherte PostGIS-Daten. Ein Nominatim-Ausfall
beeinträchtigt diese Pfade nicht. `geocode_address()` bleibt unverändert.
