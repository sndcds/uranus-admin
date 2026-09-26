# Admin Operations Workspace

## Observed uranus-admin conventions

Baseline: `dev`, created with approval from `main` at
`d1a14804c135037b43a3b945b84171ce634d87fe`. The remote had no `dev` branch.
Only `sndcds/uranus-admin` was inspected. Backend files were read to establish
existing capabilities, not changed; no live source schema was queried.

- Routing: Nuxt file routes, collections and `[id]` detail pages; navigation in
  `app/utils/navigation.ts`. Existing auth/geo middleware remains authoritative.
- Page structure: overview, collection, record detail, workflow and workspace
  patterns in [design-system.md](design-system.md).
- Components: `PageHeader`, `RecordSection`, `EntityHero`, `RecordRelations`,
  `RecordWorkflowSummary`, `EntityTimeline`, `ActivityRow`, `FindingsList`.
- API: `app/utils/admin-api.ts`, existing Zod contracts and Nitro allowlists.
  No new endpoints, proxy capabilities or response fields.
- State: Pinia for shared state; `useOperationsRequest` for independent local
  requests. Generation guards discard obsolete results. Protected layout unmounts
  on auth revision; no browser persistence.
- Tables: `DenseTable` and existing domain lists, stacked labeled cells on mobile.
- Modals: native dialog through `AppModal`, focus restoration, existing findings review.
- Errors/loading: `RequestState`, same-selection stale data warnings, retry;
  `EmptyState` distinguishes no records from a failed request.
- Mobile: wrapping actions, bounded grids, 44px controls, no new component library.
- Tests: Vitest/Vue Test Utils, Playwright desktop/mobile projects, synthetic
  fixtures, production CSP and visual review artifacts.
- Naming/styling: German labels from existing presenters; navy/fuchsia Operations
  v2.1 tokens, existing spacing and typography classes. No new design system.

## Dashboard

The existing summary, prioritized findings, quality overview and check-run state
remain. `DashboardOperations` independently loads three bounded requests in parallel:

| Area            | Existing API                                 | Semantics                                                           |
| --------------- | -------------------------------------------- | ------------------------------------------------------------------- |
| Inbox           | `GET /api/v1/inbox?page_size=1`              | Systemwide visible work and server-provided critical/overdue counts |
| Geocoding       | `GET /api/v1/geocode/requests?page_size=1`   | Global stored status counts, not live worker health                 |
| Recent activity | `GET /api/v1/dashboard/activity?page_size=4` | Creation records in the selected period/area, not an audit stream   |

Changing the period/area only reloads activity in this component. Refresh reloads
all dashboard sections; each section has its own retry and error state. No polling,
per-row fetches or sequential dashboard request chain. Social Publishing explicitly
reports unavailable data instead of showing zero counters.

## Inspector and navigation

`/inspect/:entity_type/:id` uses the existing entity keys, including encoded
composite keys. Type and key are validated before any page API requests.

- Users, organizations, venues, spaces, events and images: reuse the existing
  entity detail response, identity hero, workflow counts, paginated relationships,
  five active findings and cursor-paginated timeline. Full domain content stays in
  the existing detail page, linked from the inspector.
- Event dates: exact-key activity lookup and existing graph navigation; no invented
  event-date detail/timeline API.
- Team memberships and partner requests: exact-key activity plus bounded existing
  queue lookup. Participant names/links come from returned queue fields.
  Invitation time is never described as join time.
- Findings are independently loaded. Failure does not blank the primary record,
  relations or timeline. Unsupported data is explicitly unavailable.

Global search retains all nine existing types, authoritative user labels, keyboard
navigation, cancellation and in-memory privacy semantics. Selecting an entity opens
its inspector. Existing server action schemas are unchanged; the original action
remains available inside the inspector. `EntityInspectorLink` is reused in records,
activity, findings tools, inbox, queues, graph and geocoding.

`GraphLink` remains the only graph navigation presenter. It supports the six graph
root types and resolves memberships using the existing validated user root. Images
and partner requests do not acquire fabricated graph roots; returned participant
organizations have their own graph links in the inspector.

## Activity, geocoding and social data

Timeline rows expose existing affected-field, rule, HTTP result, generation and
match-score evidence. Source updates explicitly state that historical field values
are unavailable. No actor identity is guessed from an admin subject.

Geocoding retains the existing candidate map, status messages and bounded retry.
It gains consistent inspector/graph actions, status drilldowns, refresh, a neutral
missing-map state and the source entity's independent timeline. Suggestions remain
non-authoritative and never update source points.

`/social-publishing` explains availability for Posts, Targets, Publications and
Scheduling. It issues no domain requests or social-provider calls. It is not a
working publication history: see [backend-gaps.md](backend-gaps.md).

## Verification and review

`tests/e2e/admin-operations-workspace.spec.ts` covers inspectors, independent errors,
empty states, non-fabricated source diffs, unavailable social states and review
screenshots at desktop/tablet/mobile widths. Existing search tests assert the new
inspector destinations while preserving action validation and privacy tests.

Use the repository's pnpm scripts: frozen install, lint, typecheck, test, build,
and production Playwright. On a production-loaded host, leave the production build
and full production browser suite to the existing CI frontend job. No migrations,
grants, worker restarts or backend deployment are required by this frontend change.
