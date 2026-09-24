# Operations Collections v2.1

Synthetische Review-Matrix aus `tests/e2e/operations-collections.spec.ts`:
Activity und alle sechs Bestandslisten bei 1440×1000, 1024×768, 390×844 und 360×800.
Die Fixtures verwenden ausschließlich vorhandene Contracts, lange Namen/Adressen/E-Mails,
lokal abgefangene Bilder und keine Produktionsdaten. Die vollständigen 28 Aufnahmen liegen
im CI-Artefakt `frontend-test-results`; diese Auswahl ist dauerhaft eingecheckt.

| Ansicht         | Desktop 1440×1000                    | Mobile 390×844                |
| --------------- | ------------------------------------ | ----------------------------- |
| Activity        | [Desktop](activity-desktop.png)      | [Mobile](activity-mobile.png) |
| Veranstaltungen | [Desktop](events-desktop.png)        | [Mobile](events-mobile.png)   |
| Organisationen  | [Desktop](organizations-desktop.png) |                               |
| Orte            | [Desktop](venues-desktop.png)        |                               |
| Räume           | [Desktop](spaces-desktop.png)        |                               |
| Benutzer        | [Desktop](users-desktop.png)         |                               |
| Bilder          | [Desktop](images-desktop.png)        |                               |

Zusätzlich: [Tablet 1024×768](entity-tablet.png) und
[kleines Mobile 360×800](entity-small-mobile.png), jeweils Veranstaltungen.

Basis: main nach PR #113 (`162fe8f8de28a32c359a7586e7730920afbe0a63`).
Frontend-only; keine Backend-/API-Änderungen. Die Bestandslisten teilen eine Präsentation,
Activity behält Tagesgruppen und ausdrücklich seitenbezogene Typzahlen.

Prüfstand: App-Commit `8a6ec035964cc9e3635e7e3afb7e6b0fba22c057`,
[erfolgreicher vollständiger CI-Lauf](https://github.com/sndcds/uranus-admin/actions/runs/35968041267).
Frozen install, Lint, Typecheck, 676 Unit-Tests, Build und 437 Production-E2E-Tests einschließlich
CSP erfolgreich. 17 explizite E2E-Skips betreffen doppelte Viewport-Matrizen im Mobile-Projekt
und einen Desktop-spezifischen Sticky-Header-Test. Backend-Jobs wurden gemäß Pfadfilter
übersprungen. `git diff --check` erfolgreich. Lokal wurden auf Wunsch keine Tests oder
Builds ausgeführt. Die Bilder wurden visuell auf klare Zeilentrennung, kompakte Filter,
lesbare lange Inhalte, erreichbare Aktionen und sekundäre technische Daten geprüft.
Die automatisierte Matrix prüft alle sieben Routen in vier Größen auf Seitenoverflow.
Diese Aufnahmen sind Review-Evidenz, keine Pixelgoldens oder Behauptung vollständiger
WCAG-Konformität.
