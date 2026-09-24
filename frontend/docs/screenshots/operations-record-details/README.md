# Operations Record Detail v2.1

Basis: `main` bei `148340ce2fe4bdfe46a18b56d33d069b3e28928e` (PR #114).
Die Aufnahmen verwenden ausschließlich synthetische, bestehende Entity-Contracts
und lokal abgefangene Bilder. Sie belegen keinen Produktions-/Deploymentstand.

| Ansicht             | Desktop 1440×1000                   | Mobile 390×844             |
| ------------------- | ----------------------------------- | -------------------------- |
| Ort                 | [Desktop](venue-desktop.png)        | [Mobile](venue-mobile.png) |
| Organisation        | [Desktop](organization-desktop.png) |                            |
| Raum                | [Desktop](space-desktop.png)        |                            |
| Benutzer            | [Desktop](user-desktop.png)         |                            |
| Bild                | [Desktop](image-desktop.png)        |                            |
| Veranstaltung       | [Desktop](event-desktop.png)        |                            |
| Relationsausschnitt | [Desktop](relations-desktop.png)    |                            |

Visueller Abgleich mit der [Orte-Collection](../operations-collections/venues-desktop.png):
dieselbe Sidebar und Shell, weiße Flächen mit Slate-Grenzen und 12px-Radius,
Fuchsia für die öffentliche Hauptaktion und kleine umrandete interne Aktionen.
Der kompakte Hero ordnet Identität/Kontext und Aktionen; Counts und Adresse stehen
nebeneinander, Relations haben klare Divider. Arbeitsstand und technische Informationen
sind abgegrenzt; die Timeline bleibt als kompakte Evidenzliste lesbar.
Die Bildvorschau bleibt unbeschnitten und über das bestehende Modal vergrößerbar.

`tests/e2e/operations-record-details.spec.ts` erzeugt alle sechs Typen zusätzlich auf
1024×768 und 360×800. Die komplette Matrix liegt im Playwright-Artefakt `test-results`.
Die kleinen Review-Beispiele sind vollständig; bestehende Detailtests prüfen zusätzlich
mehr als 25 Relations, Seitenwechsel, unbekannte Werte, Bildfehler, lange Texte,
Markdown-Sicherheit, Authverlust und verspätete Antworten.

Reproduktion aus `frontend/` nach `pnpm build`:

```sh
TEST_PRODUCTION=1 pnpm test:e2e tests/e2e/operations-record-details.spec.ts --project=desktop
```

Für dieselben Fonts und Browser den gepinnten Playwright-Container aus
[CI](../../../../.github/workflows/ci.yml) verwenden. Die PNGs werden aus den Testausgaben
kopiert; es gibt keine neuen Vollseiten-Pixelgoldens.

Prüfstand: `pnpm install --frozen-lockfile`, Lint, Typecheck, 683 Unit-Tests und
Produktionsbuild erfolgreich. Lint hat vier bereits vorhandene Warnungen in unveränderten
Komponenten. Die vollständige Produktions-E2E-Suite einschließlich CSP besteht mit
441 erfolgreichen und 21 planmäßig übersprungenen Tests. 20 Skips vermeiden doppelte
explizite Viewport-Matrizen im Mobile-Projekt; ein weiterer Test prüft ausschließlich
den Desktop-Tabellenheader. Keine dieser Auslassungen überspringt einen CSP-Test.
Die abschließende reine Text-/Accessible-Name-Anpassung des öffentlichen Graph-Links
ist nach erneutem Build zusätzlich mit 14 erfolgreichen Graph-Regressionstests geprüft.

Verbleibende Grenzen: Relations sind weiterhin eine globale Seite, keine vollständigen
fachlichen Gruppen. Bilder besitzen keinen Graph-Root. Öffentliche Hauptaktionen gibt es
nur bei gelieferter URL. Der Raum benötigt keinen duplizierten Faktenkasten; sein belegter
Orts-/Organisationskontext steht im Hero. Fachliche Timeline-/Workflowaktionen behalten ihre
Bedeutung. Graph, SQL, Statistics und Quality erhalten keine visuelle Migration.
200%-Browserzoom, manuelle Screenreader- und umfassende Kontrastprüfung bleiben Teil des
separaten Accessibility-Audits; die automatisierten Prüfungen sichern native Links,
Fokus, mindestens 44px Controls und fehlenden Seitenoverflow. Keine pauschale WCAG-Zusage
oder prozentuale Dichtebehauptung aus unterschiedlichen historischen Screenshots.
