# Operations Center v2.1 — Foundations review

Ausgangspunkt: `main` bei `10f41ca78cad640317fbd06be70ce2f766845b82`.
Referenz: das bereitgestellte Operations-Center-Mockup. Diese Phase setzt dessen
Designsprache in gemeinsamen Komponenten und im App-Rahmen um. Die dort gezeigten
vollständigen Dashboard-/Record-/Geocoding-Umbauten folgen in eigenen PRs.

## Review-Aufnahmen

Alle Werte sind synthetische Fixtures, keine Produktions- oder Source-Evidenz.

- [Komponenten, Desktop](components-1440.png)
- [Komponenten, Tablet](components-820.png)
- [Komponenten, Mobil](components-390.png)
- [Komponenten, schmal mobil](components-360.png)
- [Desktop-Sidebar](sidebar-desktop.png)
- [Mobiler Drawer](sidebar-mobile.png)
- [CompactFacts](compact-facts.png)
- [TechnicalInfoBar](technical-info.png)
- [DenseTable](dense-table.png)

Die Komponentenansicht zeigt CompactFacts, explizite Panel-/Subtle-Surfaces,
DenseTable mit Status/Zeilenaktionen, kompakten EmptyState und TechnicalInfoBar.
Sie läuft ausschließlich als separate Vite-Testfixture auf Loopback-Port 3101;
es gibt keine zusätzliche Nuxt-Route, kein Demo-Featureflag und keine API-Requests.

## Reproduktion

Aus `frontend/`:

```sh
pnpm test:e2e tests/e2e/operations-foundations.spec.ts --workers=2
```

Playwright schreibt neue Aufnahmen in `test-results/`; ausgewählte Review-Aufnahmen
werden bewusst in diesem Ordner versioniert. Automatisch erzeugte Test-/Builddateien
bleiben unversioniert. Der Testserver nutzt `tests/fixtures/operations/vite.config.ts`.
Shell-Tests verwenden die echte Nuxt-App mit kontrolliertem Auth-Backend und API-Fixtures.
Die Komponentenfixture ist kein Nachweis für die Produktions-CSP; dafür läuft die
bestehende CSP-Suite separat gegen den Nuxt-Produktionsbuild.

## Designentscheidungen

- Navy-Sidebar, Fuchsia für aktive Navigation, sichtbarer Tastaturfokus auf dunklem Grund.
- 20px Hauptabstand, 16px Panelpadding, 12px Grids; 8px Controls und 12px Panelradien.
- Alle neuen Controls und Navigationslinks mindestens 44px hoch. Tabellenzeilen wachsen
  bei Aktionen auf 52px, bei mehrzeiligem Inhalt bedarfsgerecht darüber hinaus.
- Echte Datenzuordnung und lesbare Labels bleiben wichtiger als die exakte Pixelhöhe
  des verkleinerten Referenzbilds. Technische Nullwerte erzeugen keine Scheininformation.
- Vorhandene RecordSections bleiben standardmäßig plain; Panelmigration folgt pro Seite.

## Mögliche Anpassungen nach Review

- Navigationsgruppen und gewünschte Desktop-Sidebarbreite.
- Panel-/Subtle-Verteilung und Spaltenverhältnisse bei der jeweiligen Seitenmigration.
- Zeilenhöhe bei umfangreichen Row Actions; mobil gestapelt oder gezielt lokal scrollbar.
- Anordnung der belegten technischen Metadaten pro Domäne.

Screenreader-Handprüfung und 200%-Zoom-Review bleiben Teil des abschließenden
Accessibility-Audits; Screenshots und Browser-Tests behaupten keine vollständige WCAG-Prüfung.

## Validierung

- Frozen-Lockfile-Installation, ESLint, Typecheck und Produktionsbuild erfolgreich.
- Unit-Tests: 43 Dateien, 602 Tests erfolgreich.
- Vollständige Entwicklungs-E2E: 338 erfolgreich, 8 ausschließlich für Produktion
  vorgesehene CSP-Prüfungen erwartungsgemäß übersprungen.
- Vollständige Produktions-E2E nach den abschließenden Anpassungen: 346 erfolgreich,
  einschließlich CSP und unveränderter SQL-Theme-Referenz.
- Abschließende Entwicklungsprüfungen für Komponenten, Shell und Geo Scope: 16 erfolgreich.
- Sechs SQL-Layout-Aufnahmen für die gemeinsamen Abstands-/Control-Änderungen visuell
  geprüft und aktualisiert. Keine Änderung an SQL-Verhalten oder Editorfarben.
- Relative Review-Links und `git diff --check` geprüft. Keine Backend-Tests ausgeführt,
  da keine Backend-, API- oder Datenbankänderungen enthalten sind.
