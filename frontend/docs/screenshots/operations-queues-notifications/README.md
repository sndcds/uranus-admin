# Operations Queues / Notifications / Checks v2.1

Basis: main nach PR #112 (`44bd5c1`). Nur synthetische Fixtures aus
`tests/fixtures/operations-queues.ts`, keine Produktionsdaten.
`tests/e2e/operations-queues-notifications.spec.ts` erzeugt die Aufnahmen remote in
GitHub CI bei 1440×1000, 1024×768, 390×844 und 360×800.

Die Tests prüfen Tabellen-/Grid-/Stack-Darstellung, 44px Controls, keine horizontale
Seiten-Scrollbar, TechnicalInfoBar, Preview und geladene Zuständigkeit vor der Aufnahme.
Die Notification-Vorschau verwendet die vorhandene synthetische E-Mail: Desktop zeigt HTML
im Sandbox-iframe, schmale Aufnahmen den realen Text-Tab. HTML wird in allen Größen
zuvor geprüft; damit bleiben Chromium-Ganzseitenaufnahmen mit offscreen iframe nicht leer.

Aufnahmen und Anwendungsvalidierung: `b20b4084f9f5854773a8f41e2c4c4badffc4e9b3`,
[GitHub CI 35962385279](https://github.com/sndcds/uranus-admin/actions/runs/35962385279).
Frozen install, Lint, Typecheck, 664 Unit-Tests (51 Dateien), Build und vollständige
Production-E2E einschließlich CSP sind erfolgreich: 429 bestanden, 13 planmäßige Skips.
Die Skips sind doppelte Viewport-Matrizen bzw. der Desktop-Sticky-Test im Mobile-Projekt;
CSP läuft in beiden Projekten. Backend-Jobs sind wegen des Frontend-only-Scope übersprungen.
Dependency Review und JavaScript/TypeScript-CodeQL sind erfolgreich.
`git diff --check` und lokale Pfad-/Linkkontrolle ergänzen die Remote-Prüfung.
Auf ausdrücklichen Wunsch wurden keine lokalen Tests oder Builds gestartet.

## Review-Matrix

| Ansicht                 | 1440×1000                                  | 1024×768                                 | 390×844                                  | 360×800                                        |
| ----------------------- | ------------------------------------------ | ---------------------------------------- | ---------------------------------------- | ---------------------------------------------- |
| Partneranfragen         | [Desktop](partner-requests-desktop.png)    | [Tablet](partner-requests-tablet.png)    | [Mobile](partner-requests-mobile.png)    | [360 px](partner-requests-small-mobile.png)    |
| Teameinladungen         | [Desktop](team-invitations-desktop.png)    | [Tablet](team-invitations-tablet.png)    | [Mobile](team-invitations-mobile.png)    | [360 px](team-invitations-small-mobile.png)    |
| Benutzeraktivierung     | [Desktop](user-activation-desktop.png)     | [Tablet](user-activation-tablet.png)     | [Mobile](user-activation-mobile.png)     | [360 px](user-activation-small-mobile.png)     |
| Benachrichtigungen      | [Desktop](notifications-desktop.png)       | [Tablet](notifications-tablet.png)       | [Mobile](notifications-mobile.png)       | [360 px](notifications-small-mobile.png)       |
| Benachrichtigungsdetail | [Desktop](notification-detail-desktop.png) | [Tablet](notification-detail-tablet.png) | [Mobile](notification-detail-mobile.png) | [360 px](notification-detail-small-mobile.png) |
| Versände                | [Desktop](deliveries-desktop.png)          | [Tablet](deliveries-tablet.png)          | [Mobile](deliveries-mobile.png)          | [360 px](deliveries-small-mobile.png)          |
| Versanddetail           | [Desktop](delivery-detail-desktop.png)     | [Tablet](delivery-detail-tablet.png)     | [Mobile](delivery-detail-mobile.png)     | [360 px](delivery-detail-small-mobile.png)     |
| Prüfläufe               | [Desktop](checks-desktop.png)              | [Tablet](checks-tablet.png)              | [Mobile](checks-mobile.png)              | [360 px](checks-small-mobile.png)              |

## Visueller Review

- Desktop: gerichtete Queue-Identitäten, fachliche Zustände und Versandfehler bleiben getrennt;
  Tabellen sind dicht, Aktionen direkt sichtbar, Technik nachrangig.
- Tablet: Tabellen wechseln in ein zweispaltiges Raster. Header-Aktionen stehen unter dem
  Titel, damit insbesondere „Prüfläufe“ nicht durch die Toolbar zusammengedrückt wird.
- Mobile: eine Spalte, umbrechende Namen/UUIDs, unveränderte 44px-Bedienflächen.
- Detail: Vorschau und Payload sind getrennt; Retry, Zuständigkeit und Versandkette
  haben eigene Abschnitte. Die Vorschau ist weiterhin ein lokal scrollbares Sandbox-iframe.

## Bewusste Vertragsgrenzen

Keine Backend-Erweiterung ist für diese Migration nötig. Mögliche spätere Wünsche:

- Ein echter `observed_at` für Notifications/Deliveries/Checks, falls dort ein Datenstand
  gebraucht wird; aktuell wird keiner behauptet.
- Ein eigener Organisationsname im Versanddetail; aktuell wird nur die belegte UUID gezeigt.
- Ein separater tatsächlicher Worker-Start, falls reine Ausführungsdauer gebraucht wird;
  `started_at` enthält heute bereits den Zeitpunkt des Einreihens.

Die Fixtures und Browserprüfungen belegen den Frontend-Vertrag, keine Live-Datenintegration.
