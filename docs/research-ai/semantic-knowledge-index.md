# Semantischer Knowledge-Index: vorbereiteter Vertrag

Dieser Stand implementiert Extraktion, Dokumente, Evidence und Operator-Planung für
Event, Venue und Organization. Er erstellt keine Collections und führt keinen
Produktions-Reindex durch. Keine API-, UI-, Deployment-, DB-Schema- oder Grant-Änderung.

## Zuständigkeiten und Collection Registry

PostgreSQL/PostGIS bleibt die fachliche Wahrheit. `admin.research_area` ist der
kanonische Gebietskatalog. Nominatim dient Discovery/Import und expliziter Ortsauflösung,
nicht normaler Suche oder Indexierung. Jina liefert semantische Ähnlichkeit; Qdrant
liefert Kandidaten. Evidence sind reale öffentliche Textbelege.

Die serverseitige Registry in
[`semantic_contracts.py`](../../backend/app/research/semantic_contracts.py) enthält:

| Entity       | Collection                             | Dokumentversion          |
| ------------ | -------------------------------------- | ------------------------ |
| Event        | `kulturbytes_events_jina_v3_v1`        | `event-public-v2`        |
| Venue        | `kulturbytes_venues_jina_v3_v1`        | `venue-public-v1`        |
| Organization | `kulturbytes_organizations_jina_v3_v1` | `organization-public-v1` |

Owner aller drei Collections: `kulturbytes-semantic-search-v1`. Unterschiedliche
Entity-Semantik, Filter und vollständige Snapshots verlangen getrennte Reconciliation
und Collection-Lebenszyklen. Spätere parallele Suche kann ihre Ergebnisse zusammenführen.
Browser und Requestparameter dürfen keine Collection-Namen auswählen.

`SemanticDocument` enthält `entity_type`, UUID `entity_id`, `display_name`, bis zu fünf
Sections und eine diskriminierte, geschlossene Payload. Pydantic verbietet unbekannte
Felder und nicht endliche Zahlen. IDs sind strukturierte Metadaten, keine Prosa.
`extract_events()` bleibt ohne Zusatzargument beim bisherigen Event-v1-Vertrag;
`semantic=True` wählt v2. `extract_venues()` und `extract_organizations()` sind eigene,
explizite SQL-Projektionen und verwenden dieselben Public-/Location-/Area-Bausteine.

## Quelle, Sichtbarkeit und Feldlisten

Zusätzliche Felder wurden gegen den lokalen Uranus-Checkout
`106ab24af97854e988f3c1b6c72b8ae2e9c1680f` geprüft: `ddl/venue.ddl`,
`ddl/organization.ddl`, `sql/get-venue.sql`, `sql/get-venues.sql`.
Das ist kein Nachweis für eine produktiv deployte DDL. Vor dem ersten echten Lauf
ist der bestehende read-only Source-Katalogcheck gegen das konkrete Ziel erforderlich.
Synthetische Testfixtures sind keine Live-Schema-Evidenz.

Die Sichtbarkeit folgt der vorhandenen Research-Projektion:

- Events: `released`, `cancelled`, `deferred`, `rescheduled`; bei vorhandenen Terminen
  mindestens ein öffentlicher Termin. `inherited` übernimmt den Eventstatus.
  Ein öffentlicher Termin kann einen Draft-Parent nicht veröffentlichen.
- Venues: effektiver Ort eines öffentlichen Termins oder eigener Punkt innerhalb
  einer gespeicherten Research Municipality. Letzteres entspricht der bestehenden
  Gebietssuche ohne Eventfilter, die auch Orte ohne Aktivität zeigt.
- Organizations: mindestens ein öffentlich eligible Event, auch ohne Termine.
  Bloßer Venue-Besitz veröffentlicht keine zusätzliche Organization.
- `venue.scope` ist Nutzung (`organization`/`shared`), **kein Release-Status**.
  Unerwartete Werte scheitern an der Payload-Validierung; es wird nichts umgedeutet.

Event-v2 verwendet die öffentliche Feldliste von Event-v1:

| Section       | Öffentliche Inhalte                                                                                                                                                                     |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| content       | title, subtitle, summary, description; übersetzte category/type/genre names; tags; content language und languages; Organization-Name, effektive Venue-/Space-Namen, Research-Area-Namen |
| participation | participation_info, meeting_point, min/max_age, geprüfter online_link                                                                                                                   |
| accessibility | accessibility_summary der effektiven Venue/Space sowie öffentliche date.accessibility_info                                                                                              |
| tickets       | price_type, min/max_price, currency, bekannte Ticket-/Registrierungsflags, ticket_link, registration_link, registration_deadline                                                        |
| additional    | source_link                                                                                                                                                                             |

Event-Payload: gemeinsamer Kern plus `title`, `organization_id`, `category_ids`,
öffentlicher `status`, `language`, `venue_ids`, `space_ids`, `first_date`, `next_date`,
`last_date` und effektive Ortsdaten. `source_updated_at` ist weiterhin der interpretierte
Event-`modified_at`; Änderungen verknüpfter Quellen werden über den vollständigen
Snapshot und Payload-/Texthashes erkannt, nicht über diesen einen Zeitstempel.

Venue-v1:

| Section          | Öffentliche Inhalte                                                   |
| ---------------- | --------------------------------------------------------------------- |
| content          | name, summary, description, type, Organization-Name                   |
| accessibility    | accessibility_summary                                                 |
| facilities       | opening_hours                                                         |
| location_context | street, house_number, postal_code, city, country, Research-Area-Namen |
| additional       | web_link, ticket_link, ticket_info                                    |

Venue-Payload: Kern plus `name`, `scope`, `organization_id`, `latitude`, `longitude`.
Keine Interpretation ungeklärter Accessibility-Bitmasken; keine erfundenen Kategorien,
Ausstattungsmerkmale oder Facility-Tabellen. Der vorhandene öffentliche Typcode wird
verwendet, kein unbestätigter Übersetzungsjoin.

Organization-v1: `name` und `description` in `content`, Namen der nachgewiesenen
Aktivitätsgebiete in `activities`, geprüfter `web_link` in `additional`.
Keine Eventtitel/-beschreibungen kopieren; keine wachsende Eventliste. Eigenständige
Zweck-/Aktivitäts-/Kategorienfelder sind nicht belegt und werden nicht erfunden.
Payload: Kern plus `name`, tatsächliche Home-Koordinate sowie getrennte Home-/Activity-Felder.

## Geografie: verbindliche Filtersemantik

Die Zuordnung liest gecachte Municipality-Geometrien in `admin.research_area` mit
Bounding-Box-Vorfilter und `ST_Covers(area.geometry, point)`. Nur gültige WGS84-Punkte
werden zugeordnet. Fehlende, leere, nicht endliche oder außerhalb WGS84 liegende
Koordinaten ergeben keine Area. Es gibt keine Geocoding-Anfrage und keinen Rückschluss
aus Name, Stadttext, Adresse oder Embedding.

- **Event + area_id:** Mindestens ein öffentlicher Termin hat seinen effektiven Ort
  im Gebiet. `EFFECTIVE_VENUE_SQL` und `EFFECTIVE_SPACE_SQL` bleiben maßgeblich;
  ein Venue-Override beendet die automatische Vererbung des Event-Spaces.
  Alle öffentlichen effektiven Orte stehen in `effective_locations` als zusammengehörige
  Objekte mit `effective_venue_id/name`, `effective_space_id/name` und
  `effective_latitude/longitude`. Die gleichnamigen singulären Payload-Felder werden
  nur bei genau einem eindeutigen Objekt befüllt. Bei mehreren Orten bleiben sie null.
  Ohne Termine bleibt das Event wie im bisherigen Research-Pfad geografisch unbekannt;
  ein Default-Venue wird nicht als existierender Veranstaltungstermin interpretiert.
- **Venue + area_id:** Eigener Venue-Punkt liegt im Gebiet. Der Sitz der Organization
  beeinflusst diese Zuordnung nicht.
- **Organization + area_id:** Ein expliziter Modus ist erforderlich. `home_area_ids/names`
  stammen ausschließlich vom Organization-Punkt. `activity_area_ids/names` stammen
  aus öffentlichen effektiven Eventorten und eigenen Research-eligible Venues.
  Die generischen Organization-`area_ids/names` bleiben leer, damit keine stille
  Vermischung entsteht. Ohne belastbaren Home-Punkt keine Home-Area.

Shared Boundary-Punkte gehören nach `ST_Covers` zu beiden benachbarten Gebieten.
Positive Flächenüberlappungen führen dagegen zum Abbruch, analog zum bestehenden
Importvertrag. Die Importregeln für deutsche kreisfreie Städte/Stadtstaaten und
Dänemarks Municipality-Level 7 werden unverändert wiederverwendet; keine pauschale
Level-8-Annahme in der Indexierung.

`semantic_evidence.area_filter()` liefert den harten Qdrant-Payloadfilter.
Der interne `Qdrant.search(..., area_id=..., organization_mode=...)`-Transport
sendet ihn vor der Vektorrangfolge an Qdrant, damit ein Ortsfilter nicht erst
nach einem begrenzten Kandidatenabruf greift.
`semantic_hits()` kann denselben Filter defensiv nachprüfen. Die neue Search-API ist
noch nicht angeschlossen: Eine zukünftige Ortsauflösung muss „Husum“ auf einen
existierenden Research-Area-Identifier auflösen und diesen Filter anwenden.
Ein Organisationsname „Flensburger Veranstaltungsgesellschaft mbH“ darf weder
Husumer Events ausschließen noch Flensburger Events durch den Husum-Filter lassen.
Zeit-/Statuskombinationen brauchen weiterhin die autoritative SQL-Nachprüfung:
Eventweite Arrays beweisen keine Kombination von Datum und Ort desselben Termins.

## Evidence, Hashes und Datenschutz

Chunking bleibt `sections-480-overlap64-v2`: nativer Tokenizer, maximal 480 Tokens
inklusive Modellpräfix und Spezialtokens, Überlappung 64, keine Trunkierung.
Kurze Dokumente werden wie bisher zu einem `content`-Chunk kombiniert. Bei langen
Dokumenten bleiben die tatsächlichen Section-Kinds erhalten. Neue erlaubte Kinds:
`facilities`, `location_context`, `activities`, `categories`; leere Sections entfallen.

Jeder Punkt trägt den geschlossenen Entity-Payload plus `chunk_index`, `chunk_kind`,
`chunk_text`, `content_hash`, `embedding_model`, `embedding_version`.
`chunk_text` ist exakt die an `/embed` übergebene normalisierte Passage, kein gesamtes
Dokument. Maximal 480 Tokens und zusätzlich die bestehende 200.000-Zeichen-Schranke.
Der Plan prüft Hash, Kontaktfreiheit und Zugehörigkeit zum materialisierten Dokument.
Ein Schemawechsel bei identischem Text benötigt nur ein Payload-Update.

SHA-256 umfasst ausschließlich den tatsächlichen UTF-8-Chunktext. UUID5-Punkt-IDs
verwenden `entity_type:entity_id:chunk_kind:content_hash`. Unterschiedliche Entities
kollidieren daher auch bei identischer fachlicher UUID nicht.

Area-IDs, Koordinaten oder Zeitstempel können ohne Re-Embedding aktualisiert werden.
Wenn sich Area-Namen oder Titel **im semantischen Text** ändern, ändert sich der
Texthash und es wird korrekt neu eingebettet. Ein Metadatenfeld allein ist kein Grund
für Re-Embedding; ein veränderter `embedding_version` dagegen schon.

`SemanticHit`: Entity-Typ/UUID, endlicher Score, öffentlicher `display_name`,
`winning_chunk` und standardmäßig maximal zwei, absolut maximal drei `supporting_chunks`.
Jeder Beleg enthält Kind, Text und Score. Höchster Chunk-Score ist Entity-Score;
Gleichstände werden deterministisch nach Kind/Hash/Name und danach Entity-UUID sortiert.
Support-Kinds und Inhalte sind eindeutig. Es werden nur explizite Ergebnisfelder
zurückgegeben, keine beliebigen Qdrant-Payloads.

Privacy-Review:

- Explizite SQL-/Text-/Payload-Feldlisten; keine Kontakte, User, Auth-/Sessiondaten,
  Findings, internen Notizen, Importtokens, Owner-/Editor-User-IDs oder JSON-Dumps.
- HTML wird zu Text; Script/Style/Iframe/Object-Inhalte entfallen. E-Mail-Adressen
  und UUIDs werden aus Prosa entfernt. Der neue Sanitizer entfernt zusätzlich
  markierte Telefonnummern, internationale Präfixe und erkennbare deutsche Nummern.
  Tests bewahren Altersangaben, Preise, Datum, Uhrzeit, Hausnummer und Postleitzahl.
- Nur syntaktisch geprüfte HTTP(S)-Links ohne Credentials, Query und Fragment;
  Mailto/Tel sowie E-Mail-/UUID-haltige Links entfallen. Keine Links werden abgerufen.
- Regex-Bereinigung ist kein allgemeiner PII-Klassifikator: verschleierte Kontakte
  oder unmarkierte mehrdeutige Nummern können nicht zuverlässig erkannt werden.
  Vor einer Veröffentlichung ist eine Stichprobe der tatsächlichen öffentlichen
  Freitexte nötig; es wird keine perfekte Anonymisierung behauptet.
- Keine Modellbegründung, keine Chain-of-Thought, keine LLM-Erklärung. Eine spätere
  „Warum dieser Treffer?“-Ansicht zeigt diese **Evidence**, nicht erfundenes Reasoning.

## Snapshot, Sync und Plan

Source- und Admin-Snapshot laufen READ ONLY / REPEATABLE READ mit UTC.
`SOURCE_BOUNDARY` prüft effektive Source-Privilegien; Admin verwendet die vorhandene
Boundary-Prüfung. Beide Engines werden vollständig geschlossen/disposed, bevor
Encoder- oder Qdrant-Zugriffe beginnen. Keine Source-DML, Trigger, Outbox oder Migration.

Bounds: höchstens 10.000 Dokumente/Entity, 100.000 Termin-/Kontextzeilen und Punkte,
64 MiB materialisierter Corpus, Area-Zuordnung in Batches von 500 Punkten. Venue-
Sichtbarkeit benötigt die vollständige begrenzte Punktmenge; auch ein Venue-Teillauf
bricht oberhalb 10.000 Source-Venues ab statt eine falsche Gesamtzahl zu melden.

Ein vollständiger Snapshot entfernt veraltete Punkte, auch nach Löschung oder Verlust
der Public Eligibility. `--limit` ist explizit unvollständig: niemals unbekannte Entities
löschen, nur überholte Chunks tatsächlich ausgewählter Entities ersetzen. Grenzen und
Extraktionsfehler brechen den Lauf ab. Für neue Collections erfordert `sync/reconcile`
eine verfügbare Research-Area-Tabelle; ein fehlender Katalog darf keine Venue-Löschungen
auslösen. Plan darf fehlende Area-Zuordnung als unavailable berichten.

Collection-Owner, Entity-Typ, Modell/Dimension und Plan-Ziel werden geprüft. Fremde
Punkte führen zum Abbruch. Dokumentversionen werden gegen den aktuellen Vertrag
aktualisiert, Embedding-Versionwechsel erzeugen neue Vektoren. Neue Punkte werden vor
Entfernung alter Punkte geschrieben. Abgebrochene Läufe sind durch stabile IDs reparierbar;
kein Erfolg bei Teilausfall. Ein Operator-Lock serialisiert Jobs auf einem Host.

Aus `backend/`, nur für eine autorisierte Operatorumgebung:

```sh
uv run python -m app.research.vector_index plan --entity event --model jina-v3 --noncommercial-jina
uv run python -m app.research.vector_index plan --entity venue --model jina-v3 --noncommercial-jina
uv run python -m app.research.vector_index plan --entity organization --model jina-v3 --noncommercial-jina
```

`plan` schreibt weder DB noch Qdrant und ruft `/embed` nicht auf. Wie der bestehende
Pilot benötigt er `/chunks` zum exakten Zählen mit dem nativen Tokenizer und lesenden
Qdrant-Zugriff; er ist kein offline Token-Schätzer. Der bisherige Encoder lädt dabei
seine gecachten Modellartefakte, erzeugt aber keine Embeddings. Ein separater
ONNX-Service kann Tokenisierung ohne Modellinitialisierung implementieren.

Der Report enthält Source-Gesamtzahl, public/ausgewählte Anzahl, Dokument-/Chunkzahl,
Area-Verfügbarkeit/-Coverage, Dokumente ohne Text/Location, ungefähre UTF-8-Payloadbytes,
Versionen, Collection, Snapshot-/Corpus-Hashes und geplante Änderungen. Bei Organizations
bezeichnet „ohne Location“ den fehlenden Home-Punkt; Activity kann trotzdem bekannt sein.
Optionaler lokaler Output enthält nur das Manifest, keinen Corpus.

`sync` und `reconcile` sind für spätere explizite Operatorläufe vorbereitet. **Für diesen
Task werden beide nicht gegen AWS oder sonstige reale Collections ausgeführt.**
`--entity all` wird bewusst nicht angeboten; Operatoren planen die drei bounded Läufe
nacheinander. Ohne `--entity` bleibt der alte Event-Pilotpfad erhalten. `benchmark` und
`evaluate` behalten ihre bisherigen Artefakte/Metriken; `benchmark --entity ...` wird
explizit abgewiesen. `uranus_bench_events_jina_v3` und historische Ergebnisse bleiben
unverändert. Neue Entities brauchen später eigene bewertete Querysets.

## Jina v3 / ONNX-Transportvertrag

Zielruntime ist Jina v3 unter ONNX. Der interne HTTP-Vertrag bleibt unverändert:
`POST /embed` mit `model: "jina-v3"`, `kind: "passage"` und maximal zwei `texts`;
später Query-Encoding mit `kind: "query"`. Antwort: 1024-dimensionale endliche,
nicht-null Vektoren und exakt erwartete `embedding_version`. Die bestehende
Normalisierung ist Bestandteil der Modellversion, Qdrant verwendet Cosine.
`/chunks` liefert Text, Index, Kind, Hash und native Tokenzahl. Authentisierung,
Timeouts, Bodylimits, keine Redirects und keine Environment-Proxies bleiben bestehen.

Es wird kein ONNX-Artefakt, Modellgewicht oder Service ausgerollt. Die bestehende
Encoder-Version bezeichnet ausdrücklich die aktuelle native Implementierung.
Vor ONNX-Einsatz muss eine geprüfte Artefakt-/Embedding-Version festgelegt und
Query-/Passage-Parität, Tokenisierung und Normalisierung validiert werden. Eine andere
Runtime darf nicht ungeprüft die alte Version behaupten; inkompatible Versionen werden
abgewiesen. Runtime-Details bleiben intern, es entsteht kein öffentlicher API-Vertrag.
Jinas bestehende explizite Noncommercial-Bestätigung bleibt erforderlich.

## Validierung und verbleibende Freigaben

Neue Unit-Tests decken alle drei Dokumente, Datenschutz, Hashes, Evidence, deterministische
Deduplizierung, Registry und Sync ab. PostGIS-Tests prüfen Husum/Flensburg A–D,
fehlende Punkte, Public-Verlust und überlappende Gebiete. Bestehende Tests prüfen
Boundary-Punkte, effektive Venue-/Space-Vererbung, Stadt-Ausnahmen und Dänemark.
Kein Unit-Test ruft Nominatim oder einen echten Encoder auf.

Vor einem späteren Produktionsindex bleiben: Live-Source-Katalogcheck, öffentlicher
Freitext-Stichprobenreview, ONNX-Artefakt-/Versionsfreigabe, Lizenz-/Betriebsentscheidung,
entityspezifische Retrieval-Benchmarks und gesonderte Reindex-/Deployment-Autorisierung.
