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
- [Map collection](desktop-map.png)
- [Event collection](desktop-events.png)
- [Venue collection](desktop-venues.png)
- [Organization collection](desktop-organizations.png)
- [Desktop table](desktop-table.png)
- [Mobile table](mobile-table.png)
- [All category colors and neutral fallback](desktop-category-colors.png)

The second visual refinement pass uses the supplied mockups as its primary visual
reference: one header search on collection pages, compact primary filters, a grouped
date chip, flatter navigation, blue selection, denser rows, stronger map presence
and a selected-result preview with actions and quick links. The landing follows
the illustrated hero composition. Dossiers pair overview/context, dates/map and
timeline/sources. Existing components, typography, tokens and data semantics remain.
Mobile navigation and filters use the existing modal; results and map use separate
views. The review fixtures contain no record photos, so these captures intentionally
show the compact fallback. Production uses safe image URLs when present.

Reviewed desktop search and all three dossiers, mobile navigation, filters, search
and event dossier. No operations controls are included. Missing images remain
missing, and the timeline states that historical field values are unavailable.

Category dots use the exact Kulturbytes palette, shared by results, preview,
filter chips and dossier category lists. Search fixtures cover all six categories;
the dedicated category capture also includes an unknown category in neutral slate.
Fixture category IDs follow the public client's stable mapping; names/counts and
assignments in these captures remain synthetic.
