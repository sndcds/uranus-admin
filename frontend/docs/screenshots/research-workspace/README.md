# Kulturbytes Recherche: visual review

Captured with the existing Playwright production workflow on 2026-09-26, using the
pinned Chromium container from CI. Records, images and map tiles are synthetic test
fixtures; these screenshots do not demonstrate live source-data availability.

- [Desktop landing](desktop-landing.png)
- [Desktop search / split view](desktop-search.png)
- [Event dossier](desktop-event-dossier.png)
- [Venue dossier](desktop-venue-dossier.png)
- [Organization dossier](desktop-organization-dossier.png)
- [Mobile search](mobile-search.png)
- [Mobile event dossier](mobile-event-dossier.png)

The supplied mockup informs the separate navigation, large search, horizontal
filters, chips, compact results, map split view, selected-result preview and sharing
controls. Existing slate/navy/fuchsia tokens, shared controls, Leaflet and responsive
table behavior take precedence over the mockup's blue palette. Mobile navigation
and filters use the existing modal; results and map use separate views.

Reviewed desktop search and all three dossiers, mobile navigation, filters, search
and event dossier. No operations controls are included. Missing images remain
missing, and the timeline states that historical field values are unavailable.
