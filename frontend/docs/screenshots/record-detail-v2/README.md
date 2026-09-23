# Record Detail v2 — Review

Synthetische Veranstaltungen, Organisationen, Orte, Räume, Benutzer und Bilder, keine Produktionsdaten. Aufnahmen aus dem
Produktionsbuild mit kontrollierten API-/Bild-Fixtures und erzwungener Test-CSP.
Sie dienen dem Review, nicht als pixelgenaue Vollseiten-Goldens.

Review-Stand PR #103: allgemeine Liste „Verknüpfte Datensätze“ statt Fachgruppen
aus einer globalen Relationsseite. Veranstalter sowie Standardort/-raum stehen
unabhängig davon im Hero beziehungsweise in den primären Fakten. Der separate
30-Termine-Test prüft die Pagination mit zwei Seiten.

- [Desktop, 1440 × 1000](desktop.png)
- [Mobile, 390 × 844](mobile.png)

Organisation/Ort/Raum verwenden eigene Kontext-/Faktenhierarchien; Beziehungen bleiben
überall global paginiert. Die Organisationsaufnahme zeigt bewusst Seite 1 mit 25 von
28 Verknüpfungen, keine vollständigen Fachgruppen. Zugehöriger Ort und Organisation
erscheinen beim Raum einmal im Hero. Die Ortsaufnahme enthält keine erfundenen Koordinaten.

| Detailtyp    | Desktop 1440 × 1000                 | Mobile 390 × 844                  |
| ------------ | ----------------------------------- | --------------------------------- |
| Organisation | [Desktop](organization-desktop.png) | [Mobile](organization-mobile.png) |
| Ort          | [Desktop](venue-desktop.png)        | [Mobile](venue-mobile.png)        |
| Raum         | [Desktop](space-desktop.png)        | [Mobile](space-mobile.png)        |
| Benutzer     | [Desktop](user-desktop.png)         | [Mobile](user-mobile.png)         |
| Bild         | [Desktop](image-desktop.png)        | [Mobile](image-mobile.png)        |

Benutzer/Bild verwenden kompakte synthetische Review-Beispiele mit zwei beziehungsweise
drei belegten Verknüpfungen. Der Benutzerzähler benennt Einladungen ausdrücklich;
das Bild bleibt im Originalverhältnis sichtbar. `user-image-detail-v2.spec.ts` prüft
zusätzlich große Fixtures mit 26/27 global paginierten Relationen, lange E-Mail/Alttexte,
Bildfehler, Hoch-/Querformat und Modal-Fokus auf allen vier Größen.

`tests/e2e/event-detail-v2.spec.ts` und `tests/e2e/place-detail-v2.spec.ts` prüfen zusätzlich
1024 × 768 und 360 × 800, einschließlich benannter Regionen, Aktionen, Touch-Zielen und Overflow.
`tests/e2e/layout-consistency.spec.ts` erzeugt für alle 34 Hauptrouten/Ansichten
Review-Aufnahmen auf Desktop, Tablet und Mobile. Die vollständige Matrix liegt
im Playwright-Ausgabeverzeichnis und im CI-Artefakt `frontend-test-results`.

Reproduktion nach `pnpm build`:

```sh
TEST_PRODUCTION=1 pnpm test:e2e tests/e2e/event-detail-v2.spec.ts tests/e2e/place-detail-v2.spec.ts tests/e2e/user-image-detail-v2.spec.ts tests/e2e/layout-consistency.spec.ts
```

Weitere Befunde und der Migrationsplan stehen im
[Frontend-Audit](../../ui-ux-audit.md), die verbindlichen Muster im
[Design Guide v2](../../design-system.md).
