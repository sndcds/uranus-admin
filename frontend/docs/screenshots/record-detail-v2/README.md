# Record Detail v2 — Review

Synthetischer Event-Pilot, keine Produktionsdaten. Aufnahmen aus dem
Produktionsbuild mit kontrollierten API-/Bild-Fixtures und erzwungener Test-CSP.
Sie dienen dem Review, nicht als pixelgenaue Vollseiten-Goldens.

- [Desktop, 1440 × 1000](desktop.png)
- [Mobile, 390 × 844](mobile.png)

`tests/e2e/event-detail-v2.spec.ts` prüft zusätzlich 1024 × 768 und 360 × 800.
`tests/e2e/layout-consistency.spec.ts` erzeugt für alle 34 Hauptrouten/Ansichten
Review-Aufnahmen auf Desktop, Tablet und Mobile. Die vollständige Matrix liegt
im Playwright-Ausgabeverzeichnis und im CI-Artefakt `frontend-test-results`.

Reproduktion nach `pnpm build`:

```sh
TEST_PRODUCTION=1 pnpm test:e2e tests/e2e/event-detail-v2.spec.ts tests/e2e/layout-consistency.spec.ts
```

Weitere Befunde und der Migrationsplan stehen im
[Frontend-Audit](../../ui-ux-audit.md), die verbindlichen Muster im
[Design Guide v2](../../design-system.md).
