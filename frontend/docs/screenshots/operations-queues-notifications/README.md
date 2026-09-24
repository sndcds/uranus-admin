# Operations Queues / Notifications / Checks v2.1

Basis: main nach PR #112 (`44bd5c1`). Nur synthetische Fixtures aus
`tests/fixtures/operations-queues.ts`, keine Produktionsdaten.
`tests/e2e/operations-queues-notifications.spec.ts` erzeugt die Aufnahmen remote in
GitHub CI bei 1440×1000, 1024×768, 390×844 und 360×800.

Die Tests prüfen Tabellen-/Grid-/Stack-Darstellung, 44px Controls, keine horizontale
Seiten-Scrollbar, TechnicalInfoBar, Preview und geladene Zuständigkeit vor der Aufnahme.
Notifications-Vorschau verwendet die vorhandene synthetische E-Mail im Sandbox-iframe.

Validierung und visuelle Sichtung stehen bis zum vollständigen CI-Lauf noch aus.
Es werden auf ausdrücklichen Wunsch keine lokalen Tests oder Builds gestartet.
