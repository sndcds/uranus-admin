# Operations / Analytics Workspaces v2.1

Basis: frisch geholtes main nach PR #116,
`3b2d337c6f4651e5226750dde312d5d60a42c701`.
Alle Aufnahmen stammen aus synthetischen Playwright-Fixtures. Sie belegen keinen
Produktionsdaten- oder Deployment-Stand.

| Ansicht                          | Aufnahme                                                         |
| -------------------------------- | ---------------------------------------------------------------- |
| Erstellung, 1440 × 1000          | [statistics-desktop.png](statistics-desktop.png)                 |
| Erstellung, 1024 × 768           | [statistics-tablet.png](statistics-tablet.png)                   |
| Erstellung, 390 × 844            | [statistics-mobile.png](statistics-mobile.png)                   |
| Gleichlange Vorperiode           | [statistics-compare-desktop.png](statistics-compare-desktop.png) |
| Custom-Subpanel vor dem Anwenden | [statistics-custom-desktop.png](statistics-custom-desktop.png)   |
| Event-Inhalte, 1440 × 1000       | [event-content-desktop.png](event-content-desktop.png)           |
| Event-Inhalte, 390 × 844         | [event-content-mobile.png](event-content-mobile.png)             |
| Quality, 1440 × 1000             | [quality-desktop.png](quality-desktop.png)                       |
| Quality, 390 × 844               | [quality-mobile.png](quality-mobile.png)                         |

Full-page-Aufnahmen können höher als der Viewport sein. Die automatisierte Matrix
deckt zusätzlich 360 × 800 ab; pro Ansicht läuft sie einmal im Desktop-Projekt.
Zwölf identische Wiederholungen im Mobile-Projekt werden bewusst übersprungen.
Weitere Interaktions-/Regressionstests laufen in beiden Projekten.

Erstellung: KPI-Summary vor der dominanten Timeline, kompakte Controls, sekundäre
Verteilung, explizite „Öffnen“-Aktionen und Datentabellen-Disclosure. Event-Inhalte:
dieselben Toolbar-/KPI-Rollen, lesbare Coverage und Rankings. Quality: gelieferter
Status sofort sichtbar, bestehende Regelgruppen und Counts, integrierter Standort-
Drilldown. Fehlende Counts bleiben „Nicht verfügbar“. Technik ist sekundär.
Alle neun Aufnahmen wurden visuell geprüft; weder Controls noch Inhalte werden
am Seitenrand abgeschnitten. Qualitätsgruppen fließen ab 1280px vollständig in
zwei Spalten, darunter in einer Spalte mit derselben DOM-/Fokusreihenfolge.

## Reproduktion

Nach Installation und Produktionsbuild `tests/e2e/operations-analytics.spec.ts`
im [gepinnten Playwright-Container](../../sql-editor.md#reproduzierbare-visuelle-tests)
mit `TEST_PRODUCTION=1` und `--workers=2` ausführen. Die neun benannten PNGs aus
den Testausgaben hierher kopieren. Keine geänderten Pixel-Toleranzen.

## Prüfstand

- `pnpm install --frozen-lockfile`, Lint, Typecheck und Produktionsbuild erfolgreich.
  Lint: vier bestehende Warnungen in unveränderten Shared-Komponenten, keine Fehler.
- Vollständiger Unit-Lauf: 718 Tests in 57 Dateien bestanden; nach der letzten
  Quality-Verdichtung zusätzlich 26 betroffene Unit-Tests bestanden.
- Gezielte Produktions-E2E inklusive CSP: 50 bestanden, 12 doppelte Matrixfälle
  übersprungen. Die finale Größenmatrix und alle neun Aufnahmen wurden zusätzlich
  im anschließend gestarteten Produktionsgesamtlauf erfolgreich erzeugt.
- Der lokale Produktionsgesamtlauf wurde auf Nutzerwunsch vor Abschluss beendet.
  Die vollständige Validierung übernimmt GitHub CI; kein vollständiges lokales
  Gesamtergebnis wird behauptet.
- Geänderte Vue-/TS-/CSS-Dateien und dieser Index sind mit Prettier geprüft;
  `git diff --check` und neue Dokumentationspfade sind geprüft.

## Grenzen

Die Fixture-Tests prüfen UI-Verträge, Tastaturbedienung, lokale Scrollbereiche,
Seitenoverflow, Zustände und Produktions-CSP. Sie ersetzen keine Live-Daten-/Backend-
Integration und keinen vollständigen Screenreader-, Kontrast- oder Browser-Zoom-Audit.
Der FINAL UI CONSISTENCY + ACCESSIBILITY AUDIT bleibt eine separate Aufgabe.
Es folgen in diesem PR keine weiteren Feature-Redesigns.
