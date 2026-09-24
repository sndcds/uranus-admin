# Operations Workspaces v2.1 — Review

Ausgangspunkt: frisch geholtes `main` nach PR #115,
`db43a15a457a02bb5615f92e43bb7711509e2b53`.
Die Aufnahmen zeigen ausschließlich synthetische Playwright-Fixtures, keine
Produktionsdaten und keinen nachgewiesenen Deployment-Stand.

## Graph

| Zustand                                      | Aufnahme                                           |
| -------------------------------------------- | -------------------------------------------------- |
| Ohne Root, 1440 × 1000                       | [graph-empty-desktop.png](graph-empty-desktop.png) |
| Canvas und Inspector, 1440 × 1000            | [graph-desktop.png](graph-desktop.png)             |
| Inspector unter der Canvas, 1024 × 768       | [graph-tablet.png](graph-tablet.png)               |
| Gestapelte Controls und Inspector, 390 × 844 | [graph-mobile.png](graph-mobile.png)               |

Die Canvas trägt die Hauptarbeit. Toolbar, Inspector und technische Schlussleiste
bilden getrennte Bereiche ohne zusätzliche verschachtelte Karten. Mobil bleibt der
vollständige Graph über Zoom und Vollbild erkundbar; die Textliste direkter Beziehungen
im Inspector bleibt zugänglich. Node-/Edge-Zahlen unterscheiden sichtbar und geladen.
Geo Scope gilt weiterhin nur für die Root-Suche.

## SQL

| Zustand                                       | Aufnahme                                           |
| --------------------------------------------- | -------------------------------------------------- |
| Bereit, Verbindung noch getrennt, 1440 × 1000 | [sql-desktop.png](sql-desktop.png)                 |
| Laufende Abfrage mit Abbrechen                | [sql-running-desktop.png](sql-running-desktop.png) |
| Ergebnis mit dichter Tabelle                  | [sql-result-desktop.png](sql-result-desktop.png)   |
| Sicherer Fehler mit gelieferter SQL-Position  | [sql-error-desktop.png](sql-error-desktop.png)     |
| Kontext vor Editor, 390 × 844                 | [sql-mobile.png](sql-mobile.png)                   |

Der Editor ist die Hauptfläche. READ ONLY ist neutral hervorgehoben, Connection ein
Textbadge. Die Kontextspalte bleibt schmal, Ergebnisse scrollen lokal. Fehler markieren
nur den Ergebnisbereich. Die bestehende SQL-Token-, Gutter- und Umbruchdarstellung sowie
Diagnose-/Provenance-Dialoge bleiben erhalten. Full-page-Aufnahmen können höher als
der angegebene Viewport sein.

## Reproduktion und Grenzen

`tests/e2e/operations-workspaces.spec.ts` erzeugt die Bilder als Playwright-Artefakte
und prüft beide Seiten bei 1440/1024/390/360px. Die explizite Viergrößenmatrix läuft nur
im Desktop-Projekt; acht identische Wiederholungen im Mobile-Projekt sind absichtlich
übersprungen. Die weiteren Interaktionstests laufen in beiden Projekten.

Nach Installation und Build die Tests im gepinnten Playwright-Container aus
[SQL-Editor-Dokumentation](../../sql-editor.md#reproduzierbare-visuelle-tests) ausführen.
Für einen gezielten Lauf `tests/e2e/operations-workspaces.spec.ts --workers=2` ergänzen.
Die neun oben benannten PNGs aus den jeweiligen Testausgaben hierher kopieren.
Die vier geänderten SQL-Console-Pixelreferenzen wurden in derselben Umgebung aktualisiert;
Dialog-/Tokenreferenzen und Vergleichstoleranzen bleiben unverändert.

Prüfstand dieser Migration:

- `pnpm install --frozen-lockfile`, Lint, Typecheck und Produktionsbuild erfolgreich.
- 704 Unit-Tests in 56 Dateien bestanden (Vitest mit zwei Workern).
- Vollständige Production-Chromium-E2E im gepinnten Container: 455 bestanden,
  29 übersprungen, keine Fehler; einschließlich CSP, Graph-Fullscreen, SQL-Diagnosen
  und unveränderter Dialog-/Token-Pixelreferenzen.
- Die 29 Skips sind 21 bestehende Desktop-/Screenshot-Prüfungen im Mobile-Projekt
  und acht Wiederholungen der oben beschriebenen neuen Viergrößenmatrix.
- Lint meldet vier bestehende Warnungen in unveränderten Shared-Komponenten,
  keine Fehler. Geänderte Code-/Testdateien und diese Übersicht bestehen Prettier.
- Dokumentationslinks geprüft; `git diff --check` erfolgreich.

Automatisierte Prüfungen umfassen Tastatur-/Root-Fokus, Fullscreen/Fokus-Rückgabe,
Controls, lokale Scrollflächen, Seitenoverflow, Status-/Fehlerrollen und Production-CSP.
Die Bilder wurden visuell gesichtet. Dies ist kein vollständiger Screenreader-,
Kontrast- oder Browser-Zoom-Audit. Backend-/PostGIS-Integration und Live-Daten wurden
für diese ausschließlich frontendseitige Migration nicht ausgeführt. Statistics,
Quality und der abschließende Accessibility-Audit bleiben separate Aufgaben.
