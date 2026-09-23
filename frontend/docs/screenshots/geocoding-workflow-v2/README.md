# Standortprüfung — Workflow v2

Deterministische Review-Artefakte aus `tests/e2e/geocoding.spec.ts`:

- `desktop.png`: 1440 × 1000
- `tablet.png`: 1024 × 768
- `mobile.png`: 390 × 844

Aufgenommen mit dem Produktionsbuild im Playwright-Container. Datensatz, Vorschlag,
Admin-Auswahl und Kartenkacheln sind synthetische Fixtures. Die laufabhängige Uhrzeit der
SSR-Shell wird ausschließlich bei der Aufnahme ausgeblendet. Keine Produktionsdaten, keine realen Tile-Requests.
Die zusätzliche Größe 360 × 800 und der Mehrfachvergleich werden als Testartefakte
abgelegt. Diese Bilder dienen dem Review, nicht einer pixelgenauen Golden-Prüfung.
