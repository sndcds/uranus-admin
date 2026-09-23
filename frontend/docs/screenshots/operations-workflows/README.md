# Operations Workflows v2.1 — synthetischer Review

## Findings Workspace / Finding Detail

Der Findings-Follow-up zu PR #112 verwendet `tests/e2e/findings-workspace.spec.ts`
mit synthetischen `operations-workflows`-Fixtures und abgefangenen Bildantworten.
Die Matrix erfasst 1440 × 1000, 1024 × 768, 390 × 844 und 360 × 800. Fixturezeit und Client-
Abrufzeit sind für diese Aufnahmen auf den 23.09.2026, 14:00 Europe/Berlin fixiert.
Die globale Kopfzeile zeigt die Laufzeit des CI-Servers. Weder Namen noch Bilder oder Datenstände stammen aus Produktion.

| Ansicht        | Desktop                                   | Mobile                                 |
| -------------- | ----------------------------------------- | -------------------------------------- |
| Befunde        | [1440 × 1000](findings-desktop.png)       | [390 × 844](findings-mobile.png)       |
| Finding Detail | [1440 × 1000](finding-detail-desktop.png) | [390 × 844](finding-detail-mobile.png) |

Die Liste zeigt Priorität zuerst, getrennte Datensatz-/Befundzellen, Reviewstatus,
44px-Bearbeitung und verfügbare SQL-Aktionen. Der Tabellenkopf haftet nur innerhalb
des lokalen Desktop-Scrollbereichs. Tablet nutzt ein Grid, Mobile gestapelte Zeilen.
Das breite Detail trennt Evidenz, Priorisierung, Review, operative Zuständigkeit,
Werkzeuge und Technik. Live hat keine Review-/Assignment-Aktion.

Die CI stellt `frontend-test-results` auch bei erfolgreichen Läufen bereit. Die
Review-Screenshots werden nach Sichtung gezielt aus diesem Artefakt übernommen;
Visual-Goldens werden nicht automatisch überschrieben. Der abschließende CI-Lauf
und die Sichtung werden nach Fertigstellung hier dokumentiert.

Reproduktion aus `frontend/` nach Installation und Build:

```sh
TEST_PRODUCTION=1 pnpm test:e2e tests/e2e/findings-workspace.spec.ts
```

Browserprüfungen kontrollieren Priorität/Labels, 44px-Aktionen, Sticky-Geometrie,
Seiten- und Dialogüberlauf, lange Namen, Fokusfalle/Rückgabe, Review-Speichern,
bedingte Felder, fehlenden Erstfund, behobene Befunde, getrennte Wiedervorlagen,
Live-SQL und das Fehlen ungültiger Live-Assignments. Die bestehende Production-CSP
bleibt aktiv. Ergänzende Suites prüfen SQL-Hashlinks, Auth, Geo, Filter, Pagination,
Stale-Daten und Bild-URLs. Lokale Tests bleiben auf Wunsch wegen Rechnerlast aus;
die vollständigen Gates laufen auf GitHub.

## Vorhandene Inbox-/Marks-Aufnahmen

Diese Dateien bleiben im gezielten Findings-Follow-up unverändert. Sie stammen
vom früheren synthetischen Reviewlauf vom 23.09.2026, 21:33–21:34 Europe/Berlin und
sind als Zwischenstand zu lesen. `marks-scoped-desktop.png` zeigt den Datensatzkontext
während des Ladevorgangs; eine spätere Aufnahme mit geladener Liste bleibt separat offen.

| Ansicht                          | Desktop                             | Mobile                           |
| -------------------------------- | ----------------------------------- | -------------------------------- |
| Inbox                            | [Desktop](inbox-desktop.png)        | [Mobile](inbox-mobile.png)       |
| Markierungen                     | [Desktop](marks-desktop.png)        | –                                |
| Markierungen im Datensatzkontext | [Desktop](marks-scoped-desktop.png) | –                                |
| Markierungsdetail                | [Desktop](mark-detail-desktop.png)  | [Mobile](mark-detail-mobile.png) |

Die bestehenden Regressionen in `operations-workflows.spec.ts` prüfen weiterhin
Inbox-Shortcuts, URL-/History-/Pagination-Semantik, Mark-Konflikte mit erhaltenem
Entwurf, lange Notizen und technische Metadaten. In diesem Follow-up werden diese
Seiten nicht verändert oder erneut migriert.
