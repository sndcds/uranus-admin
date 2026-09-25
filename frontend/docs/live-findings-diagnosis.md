# Live-Findings: Diagnose vom 25. September 2026

Ausgangspunkt: `main` bei `3f0705a8babee69c97d15a2d1badc6d094aa7d76`.
Untersucht wurde die lokale Instanz unter `http://localhost:3000` mit
`/findings?mode=live&active_only=false&page=1&page_size=50`.

## Nachgewiesene Ursache

Der Browser zeigte `invalid_response`, obwohl der zugehörige HTTP-Aufruf 200 lieferte.
Chromium reproduzierte den Fehler mit dem vorhandenen lokalen Development-Zugang.
Das vom laufenden Nuxt-Dev-Server ausgelieferte Modul `shared/contracts.ts` enthielt
noch den alten `activityImageUrlSchema`-Regulärausdruck ohne `(?:&type=png)?`.
Die Antwort enthielt öffentliche PNG-Vorschaubilder mit `?width=320&type=png`;
Zod meldete 41 Fehler an `items[*].image_url`. Auch ein frischer Browser und ein
Modulabruf ohne Zeitstempel erhielten das alte Schema: kein reiner Browser-Cachefehler.

Die vollständige tatsächliche HTTP-Antwort bestand dagegen die Validierung mit dem
unveränderten Repository-Schema. Die Unterstützung für PNG war bereits mit PR #123
auf `main` vorhanden. Nach dem Neuladen des lokalen Nuxt-Dev-Servers bestand auch
im Browser die vollständige Antwort die Validierung: 50 Tabellenzeilen, 932 Befunde,
19 Seiten und kein Fehler. Hierzu wurde die Konfigurationsdatei berührt, sodass die
Nuxt-CLI neu lädt; es wurde keine Konfiguration oder generierte Datei geändert.
Bei einem erneut veralteten Dev-Modul den Dev-Server neu starten; produktiv den
passenden Frontend-Build mit ausrollen. Ein größeres Timeout behebt diesen
Versionsunterschied nicht.

Das bisher fehlende `metadata` war **nicht** Ursache eines Validierungsfehlers:
`z.object` entfernte unbekannte Felder. Jetzt bleibt es als optionaler
`Record<string, JSON>` erhalten (`z.record(z.string(), z.json())`). Es werden keine
bestimmten Schlüssel vorausgesetzt. Verschachtelte JSON-Werte sind erlaubt,
Funktionen und andere Nicht-JSON-Werte nicht. Die bestehenden Backend-Regeln liefern
bereits bereinigte Evidenz: beispielsweise Fingerprints, Kategorie, Reason-Codes
und Token-Präsenz statt Token-Werten. Die Backend-Projektionen, Berechtigungen und
Anzeige von Quelldaten werden nicht erweitert.

## Messung der tatsächlichen lokalen Daten

Drei authentifizierte HTTP-Aufrufe über den unveränderten lokalen Nitro-Proxy:

| Lauf | HTTP-Status | Gesamtdauer |
| ---- | ----------- | ----------- |
| 1    | 200         | 244 ms      |
| 2    | 200         | 359 ms      |
| 3    | 200         | 217 ms      |

Alle Aufrufe lieferten 50 Items, insgesamt 932 Befunde und 19 Seiten im Modus `live`.
Der alte **12-Sekunden-Timeout wurde dabei nicht ausgelöst**.

Zusätzlich wurde die vorhandene Backend-Routenfunktion dreimal direkt gegen die
lokal konfigurierte Reader-Verbindung ausgeführt. Messung mit `perf_counter` und
temporären Funktions-Wrappern, ohne Änderung am Produktionscode. Keine DDL/DML,
keine Worker, keine externen Bildabrufe; konsistenter READ ONLY / REPEATABLE READ
Source-Snapshot und bestehende Admin-Boundary-Prüfungen bleiben erhalten.
Die folgende Messung enthält Datenbankzugriff und Anreicherung, aber keinen
HTTP-Transport oder HTTP-Response-Serialisierung. Werte sind gerundet.

| Abschnitt                                                      | Lauf 1   | Lauf 2   | Lauf 3   |
| -------------------------------------------------------------- | -------- | -------- | -------- |
| Gesamte Routenfunktion                                         | 355,7 ms | 256,8 ms | 212,5 ms |
| Gesamter Scan                                                  | 323,6 ms | 243,6 ms | 200,2 ms |
| Source-Snapshots laden                                         | 105,9 ms | 39,9 ms  | 45,4 ms  |
| 38 Core-Regelauswertungen                                      | 179,1 ms | 181,8 ms | 133,9 ms |
| Queue-Findings                                                 | 20,3 ms  | 13,6 ms  | 12,5 ms  |
| Priorisierung, 926 Core-Aufrufe (in Regelauswertung enthalten) | 3,6 ms   | 3,8 ms   | 3,3 ms   |
| Filtern, Sortieren, Pagination und SQL-Verfügbarkeit zusammen  | 1,10 ms  | 0,92 ms  | 0,92 ms  |
| SQL-Diagnostik-Verfügbarkeit für 50 Items (darin enthalten)    | 0,11 ms  | 0,09 ms  | 0,14 ms  |
| Bildvorschau-Anreicherung                                      | 9,91 ms  | 6,92 ms  | 6,52 ms  |
| Standortvorschlag-Anreicherung                                 | 0,008 ms | 0,008 ms | 0,004 ms |

Verschachtelte Zeiten sind nicht additiv. Der Scan umfasst außerdem Venue-SQL und
Kontextaufbau. Auf dieser Seite gab es keine passenden Standort-Findings, daher
kehrte die Standortanreicherung vor einem Admin-Query zurück. Die Messung sagt nichts
über Seiten mit solchen Findings aus. SQL-Verfügbarkeit ist eine lokale Prüfung der
registrierten Diagnose und führt keine Diagnostik-SQL-Abfragen aus.

Die Regelauswertung dominiert diesen lokalen Bestand. Ein separates Performance-
Follow-up ist bei wachsendem Bestand sinnvoll (Snapshot-Größe, Regellaufzeiten,
Queue-SQL messen), aktuell aber keine Voraussetzung für die Fehlerbehebung. Es
wurden weder Seitengröße noch Live-Semantik geändert.

## Zeitgrenzen und Fehlervertrag

Die unabhängige Timeout-Schwäche wurde vor Änderungen mit einem synthetischen
13-Sekunden-Request nachgewiesen: Client-Abbruch nach 12 Sekunden als generischer
502, Proxy-Abbruch bereits nach 10 Sekunden als 504. Fake-Timer reproduzieren das
Verhalten ohne echte Wartezeiten. Nur das Browser-Limit zu erhöhen wäre wirkungslos.

| Anfrage                                                       | Browser | Nitro → Backend |
| ------------------------------------------------------------- | ------- | --------------- |
| Exakt GET `/api/v1/findings?mode=live`                        | 60 s    | 58 s            |
| Persisted Findings, fehlender Modus und alle anderen Requests | 12 s    | 10 s            |

Die zwei Sekunden Differenz lassen Zeit für Transport und Fehlerdarstellung.
Alle Proxy-Allowlisten, Auth-/CSRF-Prüfungen, Redirect-Sperren und Query-Validierungen
bleiben erhalten. Kein Requestparameter kann einen frei wählbaren Timeout setzen.
Die bestehenden Datenbank-Statement-Timeouts bleiben unverändert.

Client-Timeout und externes AbortSignal werden weiterhin durch `AbortSignal.any`
verbunden. Der zuerst wirksame Caller-Abbruch bleibt ein Caller-Abbruch. Das
Timeout gilt auch beim Lesen des Response-Bodys. Fehler werden ohne technische
Details, Response-Inhalte oder Zod-Evidenz an die UI übergeben:

- `live_findings_timeout` / `request_timeout`: 504, eigene Timeout-Meldung und
  Überschrift „Abruf dauert zu lange“.
- `network_error`: 502, API nicht erreichbar.
- `invalid_response`: 502, erfolgreiche Antwort mit ungültigem JSON oder Schema.
- HTTP-Status und bestehende 401-/403-Meldungen bleiben erhalten.

Pydantic und OpenAPI enthalten `metadata` bereits. Es gibt keine Backend-API-,
Migrations-, Grant- oder Worker-Änderung. Frontend und Nitro werden gemeinsam gebaut.

## Regressionstests

`tests/fixtures/live-findings.ts` ist eine synthetische 50er-Seite mit den gemeldeten
Formen: Event-Date, Priorität 1 / Score 6700, PNG-URL, freie JSON-Metadaten,
`cursor_pagination: null` und Image-Link mit nullable UUID/Aktion/Bild. Es werden
keine tatsächlichen Quelldatensätze oder Zugangsdaten eingecheckt.

`tests/unit/live-findings-regression.test.ts` prüft Browser- und Proxy-Zeitgrenzen,
13-Sekunden-Erfolg, Caller-Abbruch, Timeout während Body-Lesen, Transportfehler,
JSON-/Schemafehler und Metadaten. `components.test.ts` sichert die Fehlerüberschriften
und 401/403. Der Findings-Workspace-E2E prüft Pending-Anzeige, bereinigte Timeout-Meldung,
Retry und alle 50 Live-Zeilen auf Desktop und Mobile ohne feste Sleeps.

## Validierung dieses Branches

- Frontend-Lint: erfolgreich, vier vorhandene Warnungen außerhalb der Änderungen.
- Frontend-Typecheck und Produktionsbuild: erfolgreich.
- Vollständige finale Frontend-Unit-Suite: 778 Tests in 40,79 s.
- Neue Desktop-/Mobile-E2E: 2 bestanden in 22,0 s.
- Vollständige Development-E2E: 468 bestanden, 49 planmäßig übersprungen,
  3 fehlgeschlagen in 26,7 min. Graph-Suche auf Desktop bestand bei der isolierten
  Wiederholung (auch Mobile). Der SQL-Workspace-Test zur leeren ersten Abfrage
  scheiterte auf beiden Viewports erneut: Die erste Aktion wurde nicht ausgeführt.
  Derselbe Test scheitert auch auf dem unveränderten Ausgangsstand von `main`
  in einem separaten Checkout mit denselben Abhängigkeiten. Dieser bestehende
  Fehler wird nicht durch Änderungen an Findings oder durch lockere Assertions verdeckt.
- Fokussierte Backend-Suite (`test_quality_v2`, `test_quality_venues`,
  `test_active_findings`, `test_finding_previews`): 96 bestanden, 33 übersprungen
  in 2,02 s. Keine `TEST_DATABASE_URL` gesetzt; PostgreSQL-/PostGIS-Integrationstests
  wurden ausdrücklich nicht auf der vorhandenen lokalen Datenbank ausgeführt.
- Vollständige Produktions-E2E auf dem Host mit acht Workern: 468 bestanden,
  41 planmäßig übersprungen, 11 fehlgeschlagen in 12,4 min. Die Fehler bestanden
  aus Testzeitlimits der großen Matrizen/Geo-Scope-Navigation, zwei visuellen
  SQL-Abweichungen und einem abgebrochenen Testseitenabruf bei Wiedervorlage.
  Alle betroffenen Tests bestanden anschließend im CI-Container (siehe unten).
- Produktionsprüfung im exakt gepinnten CI-Playwright-Container mit zwei Workern:
  47 bestanden, 25 planmäßig übersprungen in 3,3 min. Umfasst Findings, CSP,
  SQL-Screenshots sowie die großen Analytics-/Collections-/Record-Detail-Matrizen.
  Diese Prüfung bestätigt die lokal unter acht Workern in Testzeitlimits gelaufenen
  Matrizen und die außerhalb des CI-Images visuell abweichenden SQL-Screenshots.
- Ergänzende Produktionsprüfung von Geo Scope und Wiedervorlage im selben
  CI-Container mit einem Worker: 12 bestanden in 38,1 s. Damit wurden sämtliche
  11 im Host-Produktionslauf fehlgeschlagenen Fälle erfolgreich nachgeprüft.
- Echte lokale Browserprüfung: 50 Zeilen / 932 Befunde / keine Zod-Fehler.

Für lokale Playwright-Läufe wurden vorübergehend nur Ausgabe-/Vite-Cachepfade unter
`/tmp` und Auth-Testport 31903 statt des bereits belegten 31902 verwendet.
Anwendung, Tests und Assertions blieben gleich; diese Hilfskonfigurationen werden
nicht eingecheckt.

## Geänderte Dateien

- `app/utils/admin-api.ts`: Request-Timeout, Abbruchsignal und Fehlerklassifizierung.
- `server/utils/admin-proxy.ts`: ausschließlich Live-Findings mit längerem Upstream-Limit;
  sichere Fehlercodes auch beim Lesen des Bodys.
- `shared/contracts.ts`: Finding-Metadaten als JSON-Record.
- `shared/errors.ts` und `app/components/RequestState.vue`: getrennte deutsche Fehleranzeigen.
- `tests/fixtures/live-findings.ts`: synthetische vollständige 50er-Antwort.
- `tests/unit/live-findings-regression.test.ts` und `tests/unit/components.test.ts`:
  Timer-, Contract-, Fehler- und Komponentenregressionen.
- `tests/e2e/findings-workspace.spec.ts`: Pending-, Timeout- und Retry-Workflow.
- `README.md`, diese Diagnosedokumentation und `../AGENTS.md`: Befunde und Timeout-Vertrag.
