# Kulturbytes Recherche

Research is a separate read-only workspace within `uranus-admin`. It uses an
independent Nuxt layout and navigation under `/research`, with the claim
“Kultur verstehen. Zusammenhänge entdecken.” System administrators can switch
between Operations and Research; journalists only receive Research navigation.
The backend enforces the same distinction for direct API access.

## Routes and data

- `/research`: landing page and global search.
- `/research/search`, `/research/map`: search and map exploration.
- `/research/events`, `/research/venues`, `/research/organizations`: typed collections.
- `/research/events/:id`, `/research/venues/:id`, `/research/organizations/:id`: dossiers.

The HTTP client remains `app/utils/admin-api.ts`; Zod research contracts are
re-exported by `shared/contracts.ts`. Nitro explicitly allowlists Research GET
routes and query fields. Research requests never enter the SQL inspection history.
No Research component calls an Operations endpoint.

`/api/v1/research/search` and the three collection endpoints return explicit public
projections. `/options` supplies category labels. Dossiers include public dates,
filtered events, monthly distinct event counts and bounded usage rankings.
`/export` returns validated export columns/rows from one source snapshot for browser
CSV encoding. There is no write endpoint, account management API or generic source proxy.

## Filter semantics

The URL is authoritative; no browser persistence or saved-query backend exists.
Supported parameters: `q`, `entity_type`, `from_date`, `to_date`, `city`, `category`,
`status`, `organization_id`, `venue_id`, `sort`, `page`, `page_size`. `view` is a
frontend-only presentation choice. Invalid filters produce an error, not a broader
unfiltered search. Search input is debounced and stale response generations discarded.

Example: `/research/search?city=Flensburg&from_date=2026-01-01&to_date=2026-06-30&category=2`.
Category IDs come from the source taxonomy; this example does not assert that ID 2
has a particular meaning in production.

Dates mean the local event start date, inclusive at both ends, in `EVENT_TIMEZONE`.
They do not mean creation date or an inferred end date. City and venue filters use
the effective date venue. An explicit date venue stops inheritance of the event's
space, following `repositories/location.py` and Roald's correction in `0d98bf7`.

Only public event and effective date statuses (`released`, `cancelled`, `deferred`,
`rescheduled`) qualify. Search returns one event with its earliest matching public
date; undated public events appear only without occurrence restrictions. Date ties
use the source date UUID. Organizations/venues have distinct event counts in the
same occurrence filter. Event text search uses the canonical safe subset of
`SEARCH_DEFINITIONS`; private contacts and external IDs are excluded even from matching.

Map markers represent the visible result page. Every marker uses a provided,
validated WGS84 point; no geocoding or coordinate writes occur. Event dossiers show
venues from the visible date page. Missing coordinates stay visible as a coverage
limitation. Fullscreen, attribution, tile failures and keyboard markers share the
existing Leaflet implementation extracted into `PointMap`; `CandidateMap` preserves
its original API. There is no new map or clustering dependency.

CSV exports the entire current filter, independently of pagination, from a fresh
consistent source snapshot. Above 10,000 records the API returns a bounded error;
no partial download is described as complete. The export uses the existing CSV
quoting and spreadsheet-formula neutralization helper. Source data may change
between the displayed page and an export; the filter is reproducible, not an archived snapshot.

## Dossiers and evidence

Dossiers reuse `RecordSection`, `CompactFacts`, `DenseTable`, `StatusBadge`, the
safe event `MarkdownContent`, pagination, map and D3 `EntityGraph`. Graph nodes
never carry an administrative URL. The graph/list describes the current dossier
page, not an exhaustive source graph. Usage rankings aggregate the whole filtered
cohort and label their top-ten bound separately.

Timeline shows source creation and last modification timestamps, with unknowns
preserved. It explicitly does not claim which field changed. No admin event stream,
actor, finding, comment, membership or user identity is included. Sources show
retrieval time, actual update time and a safe original link where available.
Credential-bearing URLs and URLs with query/fragment values are omitted.

## Design and provenance

A second visual refinement pass follows the supplied search, collection, landing
and dossier mockups as the primary visual specification. The Research layout
contains the presentation variants: flat navigation, blue selection/actions, soft
badges, a single header search on collection pages, compact primary filters and
secondary filters in the existing modal. The date range is one removable chip;
underlying inclusive date and URL semantics are unchanged. Header search retains
applied filters and clears pagination. The landing hero uses a decorative local
SVG city illustration, existing icons and its own prominent search.

Desktop search pairs dense result rows with the existing Leaflet map, a compact
entity legend, actual public popup facts, selected-record preview and quick links.
The table view reuses DenseTable's action slot for keyboard-accessible preview
selection and a soft blue selected row. Mobile retains the stacked table layout.
Dossiers pair overview/context, events/map and timeline/sources; monthly bars use
only delivered months and retain an accessible exact-value table. Missing months
are not invented as zero. The original tables, safe Markdown, map, graph, controls,
fonts, tokens and 44px touch targets remain. Operations styles and map defaults
are unchanged. Mobile stacks the dossier and uses the existing navigation/filter
dialogs and separate list/map views.

Mockup-only data is not copied: names, images, counts and links depend on actual
safe response fields. Missing images leave compact text content. The account area
uses the available subject because the session has no display-name field. There
are no dead saved-research, help, feedback, similarity or route-planning controls;
no fictitious clustering or historical field diffs are shown.

Reviewed project patterns include auth/service/dependencies/manage, explicit source
projections, source location/temporal helpers, canonical entity search, errors,
frozen Alembic migrations, runtime/operator grant checks, Nuxt auth middleware,
request-generation guards, Pinia, API/Zod/Nitro, existing map/D3 and Playwright fixtures.
Roald's directly attributable non-merge reference is `0d98bf7` in quality/core.py;
the wider style is the repository's convention, not claimed personal authorship.
PR #129 references include `d15e3c1`, `a1ec2bb`, `30c5437`.

## Category colors

`app/utils/research-categories.ts` owns the exact Kulturbytes colors. Stable source
IDs, verified against [CategorySelector.vue](https://github.com/sndcds/kulturbytes-client/blob/main/app/components/event/ui/CategorySelector.vue),
map to semantic keys independently of translated labels. The canonical values come
from [event.scss](https://github.com/sndcds/kulturbytes-client/blob/main/app/assets/css/event.scss).

| ID  | Key       | Label        | Color     |
| --- | --------- | ------------ | --------- |
| 1   | culture   | Kultur       | `#F20D5E` |
| 2   | education | Bildung      | `#FF7A53` |
| 3   | sports    | Sport        | `#F3B52A` |
| 4   | leisure   | Freizeit     | `#04C18D` |
| 5   | family    | Familie      | `#09BAEC` |
| 6   | society   | Gesellschaft | `#1A71E4` |

`ResearchCategoryBadge` uses the original color as a dot and existing slate text
on a light surface (approximately 14:1 contrast). White text on the six original
colors would yield 4.20, 2.57, 1.83, 2.33, 2.27 and 4.64:1 respectively, so solid
chips with white text are not used. Unknown IDs remain slate, even when their label
matches a known category. Active filter chips use the same mapping. The native
select remains native. Results, selected preview, dossier headers and category
usage lists share the badge. Tables/popups currently have no category field;
monthly activity bars, entity types and status badges retain their own semantics.
No second CSS token palette or category request is introduced.

## Verification

`tests/unit/research.test.ts` covers strict public contracts, URL parsing, redirects,
relations, CSV, client privacy and proxy allowlists. `tests/e2e/research.spec.ts`
covers authenticated journalist navigation, Operations denial, filters/reload,
map/table/list, dossiers, graph/list, timeline limits, export, clipboard, errors,
mobile dialogs and screenshots. The existing auth and geocoding regressions remain.
Review [screenshots](screenshots/research-workspace/README.md) use synthetic records
and intercepted local test tiles only.

Source gaps and future features: [research-backend-gaps.md](../../docs/research-backend-gaps.md).
Deployment/account setup: [authentication.md](../../backend/docs/authentication.md#research-authorization).
