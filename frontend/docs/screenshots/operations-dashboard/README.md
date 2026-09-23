# Operations Dashboard — synthetischer Review

Dashboard-only Migration auf Basis von `main` `76016593bfde39d5aada821f2e0afd9f14eba63a`.
Visuelle Referenz: oberes linkes Dashboard im Operations-Center-Entwurf.
Die Aufnahmen enthalten ausschließlich `tests/fixtures/operations-dashboard.ts`,
eine lokale Testsitzung und die feste Client-Abrufzeit 23.09.2026, 12:05 Europe/Berlin.
Die serverseitig gerenderte Shell-Uhr zeigt den Zeitpunkt des jeweiligen Testlaufs.
Keine Produktionsdaten; Fixture-Counts sind keine Aussage über den Live-Bestand.

| Aufnahme                         | Viewport    |
| -------------------------------- | ----------- |
| [Desktop](desktop.png)           | 1440 × 1000 |
| [Tablet](tablet.png)             | 1024 × 768  |
| [Mobile](mobile.png)             | 390 × 844   |
| [Small Mobile](small-mobile.png) | 360 × 800   |

Vollseitenaufnahmen erhalten auch die unterhalb des Viewports liegenden Filter/Metadaten.
Reproduktion nach `pnpm build`, im gleichen gepinnten Playwright-Container wie CI:

```sh
TEST_PRODUCTION=1 UPDATE_DASHBOARD_SCREENSHOTS=1 pnpm test:e2e operations-dashboard --project=desktop
```

Der normale Testlauf schreibt ausschließlich nach `test-results`, nicht in diese Dokumentation.
Im CI-Container wird derselbe Test mit `node node_modules/@playwright/test/cli.js test`
statt pnpm gestartet.

Entscheidungen gegenüber dem Bild: alle neun vorhandenen Typen bleiben sichtbar;
kein fingierter Queue-Gesamtbestand oder System-/Datenbankstatus. Technische Zeitangaben
unterscheiden Client-Abruf, Prüflauf und Zeitfenster. Die Tabelle bewahrt vollständige
Evidenztexte, Typ/Status und Quellenangaben; SQL/Markierungen sind nachrangige Zeilenaktionen.
Die Seiten Benutzer, Veranstaltung und Geocoding aus dem Entwurf gehören nicht zu diesem PR.

Review-Feinabstimmung: Verhältnis Arbeitsliste/Seitenpanel, Anzahl Tile-Spalten und
sichtbare Zeilenaktionen anhand realer Textlängen bewerten. Funktionale Tests ergänzen die Aufnahmen um Tastaturbedienung, 44px Controls
und fehlenden horizontalen Seitenüberlauf.
