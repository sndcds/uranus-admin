# Verifikation am 14.09.2026

## Ausgeführt

| Prüfung                                         | Ergebnis                                                  |
| ----------------------------------------------- | --------------------------------------------------------- |
| Installation mit `--frozen-lockfile --offline`  | Erfolgreich mit vorhandenem pnpm-Cache                    |
| ESLint (`pnpm lint`)                            | Erfolgreich                                               |
| Strikte Nuxt-/Vue-Typechecks (`pnpm typecheck`) | Erfolgreich                                               |
| Vitest (`pnpm test`)                            | 33 Unit-/Komponententests erfolgreich                     |
| Playwright mit Development-Server               | 6 Tests erfolgreich: Desktop und Mobil                    |
| Production-Build (`pnpm build`)                 | Erfolgreich, Nitro Node-Server                            |
| Playwright gegen Production-Build               | Dieselben 6 Tests erfolgreich                             |
| Visueller Vergleich                             | Mockup und Dashboard als Browser-Screenshots verglichen   |
| Live-API über Nitro-Proxy                       | Alle fünf erlaubten GET-Routen mit HTTP 200               |
| Browser mit lokalem Development-Zugang          | Reale Daten validiert/dargestellt; Navigation erfolgreich |

Die Live-Prüfung verwendete die bereits lokal konfigurierte FastAPI auf Port 8000 und
deren ausdrücklich aktivierten Entwicklungszugang. Findings und die spezifische Venue-Abfrage
lieferten jeweils **6 Treffer**. Das ist ein beobachteter Teststand, kein eingebauter UI-Wert.
Es wurden ausschließlich lesende Requests an FastAPI ausgeführt. Kein Token, keine Liste mit
Personen-/Organisationsdaten und keine Live-Response wurden als Fixture gespeichert.

Die Live-Browserprüfung bestätigte: geleertes Token-Eingabefeld, keine Einträge in
localStorage/sessionStorage, Datenentfernung beim Entfernen des Zugangs und keine
Laufzeitfehler/Hydration-Warnungen. Im Production-Test wurde die Entwicklungsvariable bewusst
auf `true` gesetzt: Die manuelle Token-Eingabe blieb trotzdem entfernt.

Automatisierte Browser-Tests verwenden ausschließlich getrennte Testfixtures. Sie prüfen
Zeitraumwahl, Desktop-/Mobilnavigation, Escape/Fokus, Filter und Seitenwechsel, Detaildialog,
401/503-Zustände, Proxy-Routen- und Methodenbegrenzung sowie horizontale Überbreite.
401, 403, 422, Serverfehler, Timeout und Antwortvalidierung sind zusätzlich durch Unit-Tests
abgedeckt. Die Store-Tests prüfen verspätete Antworten nach Zeitraum-/Filterwechsel und
Zugangswechsel sowie das Leeren sensibler Daten bei 401/403.

## Grenzen und unveränderter Bestand

- Keine echte Uranus-Anmeldung getestet: Dafür fehlt die Backend-Integration.
- Keine Schreiboperationen, Produktionsdatenänderungen oder Deployments.
- Keine umfassende externe Accessibility-Prüfung; Tastatur/Fokus und responsive Bedienung
  wurden im Browser geprüft.
- Backend-Tests wurden für diesen Frontend-Auftrag nicht erneut ausgeführt; Backend-Code
  blieb unverändert.
- Ein Hashvergleich der vorgefundenen Dateien zeigt ausschließlich eine Ergänzung der
  bestehenden Root-README. Alle neuen Implementierungsdateien liegen in `frontend/`.
- Das Original-Mockup blieb unverändert. SHA256:
  `9b11b51789c5a433c1310942e185de39d3c0dfcee92147f47c908c8b03b0f55d`.
- Git-Status war mangels eines gültigen lokalen Git-Repositorys nicht verfügbar. Es wurde
  kein Repository initialisiert und kein Commit/Push/PR erstellt.

Für den Live-Browsertest wurde kurz Port 3001 verwendet, weil Port 3000 bereits belegt war.
Der zusätzliche Testserver wurde anschließend beendet; bestehende Dienste blieben erhalten.
