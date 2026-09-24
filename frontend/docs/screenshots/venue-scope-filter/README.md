# Venue-Scope-Filter

Synthetische Playwright-Fixtures, keine Live-Daten. Produktionsbuild mit dem
CI-gepinnten Browser-Container. Erzeugt durch
`tests/e2e/venue-scope-filter.spec.ts`; Ansichten mit aktivem `scope=organization`.

- [Tablet, 1024px](venues-1024.png)
- [Mobil, 360px](venues-360.png)

Der Test prüft außerdem 1440px und 390px, URL/History/Reload, Pagination,
Reset bei leeren Ergebnissen, kompakte Header-Aktionen und die Navigation zu Räumen.
Die Desktop-Spalte für den Ortstyp erhält mindestens 19rem für das vollständige Label.
