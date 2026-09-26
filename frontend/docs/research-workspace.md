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

The pasted mockup guided hierarchy, search/filter chips, list/map split, compact
rows, status text, selected detail preview, quick links, CSV and permalink actions.
The existing Slate surfaces, Navy/Fuchsia accents, typography, spacing, focus and
44px control conventions take priority over copying the mockup's blue palette.
Mobile uses a navigation dialog, filter dialog and separate list/map selection.
There are no dead saved-research, help or feedback placeholders.

Reviewed project patterns include auth/service/dependencies/manage, explicit source
projections, source location/temporal helpers, canonical entity search, errors,
frozen Alembic migrations, runtime/operator grant checks, Nuxt auth middleware,
request-generation guards, Pinia, API/Zod/Nitro, existing map/D3 and Playwright fixtures.
Roald's directly attributable non-merge reference is `0d98bf7` in quality/core.py;
the wider style is the repository's convention, not claimed personal authorship.
PR #129 references include `d15e3c1`, `a1ec2bb`, `30c5437`.

## Verification

`tests/unit/research.test.ts` covers strict public contracts, URL parsing, redirects,
relations, CSV, client privacy and proxy allowlists. `tests/e2e/research.spec.ts`
covers authenticated journalist navigation, Operations denial, filters/reload,
map/table/list, dossiers, graph/list, timeline limits, export, clipboard, errors,
mobile dialogs and screenshots. The existing auth and geocoding regressions remain.
Review screenshots use synthetic records and intercepted local test tiles only.

Source gaps and future features: [research-backend-gaps.md](../../docs/research-backend-gaps.md).
Deployment/account setup: [authentication.md](../../backend/docs/authentication.md#research-authorization).
