# Entity-Relationship Graph

`/graph` is a read-only, exploratory view of cultural records, following the supplied
Kulturbytes mockup: compact filters, white graph surface, pastel icon nodes, understated
arrows, a right-hand detail panel and a text legend. Small screens place details below
the graph. No example records are shipped to the application; fixtures exist only in tests.

## Source contract

Six node types are supported: organization, venue, space, event, event_date, user.
Event series, images and predecessor links shown in the reference image are deliberately
absent until their relationship contract is supported. No verification badge, website,
description or count is fabricated to match the image.

The source basis is the verified Uranus dev contract at
`733c54133362460353400eb96c60a0cdb9f8450a`, recorded in
[backend source verification](../../backend/docs/source-verification.md) and the existing
Activity/quality implementation. This change does not claim a new production schema inspection.

| Edge type | Source → target | Exact Uranus source |
| --- | --- | --- |
| `organization_has_venue` | Organisation → Ort; Betreibt | `venue.org_uuid → organization.uuid` |
| `venue_has_space` | Ort → Raum; Hat Raum | `space.venue_uuid → venue.uuid` |
| `organization_has_event` | Organisation → Veranstaltung; Organisiert | `event.org_uuid → organization.uuid` |
| `event_has_date` | Veranstaltung → Termin; Hat Termin | `event_date.event_uuid → event.uuid` |
| `event_uses_venue` | Veranstaltung → Standardort | `event.venue_uuid → venue.uuid` |
| `event_uses_space` | Veranstaltung → Standardraum | `event.space_uuid → space.uuid` |
| `event_date_uses_venue` | Termin → effektiver Ort | `COALESCE(event_date.venue_uuid, event.venue_uuid)` |
| `event_date_uses_space` | Termin → effektiver Raum | Date venue override: `event_date.space_uuid`; otherwise `COALESCE(event_date.space_uuid,event.space_uuid)` |
| `user_member_of_organization` | Benutzer → Organisation; Mitglied von | `organization_member_link.user_uuid/org_uuid`, `has_joined=true` |
| `user_invited_to_organization` | Benutzer → Organisation; Eingeladen zu | Same membership table, `has_joined=false` |
| `organization_partner_request` | Organisation A → B; Partneranfrage | `organization_partner_request.from_org_uuid/to_org_uuid`, `status=pending` |
| `organization_partner_of` | Organisation A ↔ B; Partner von | Accepted request A→B **and** matching `organization_access_grants.src_org_uuid=B,dst_org_uuid=A`; permissions may be zero |

Only existing endpoints become nodes; dangling source references do not invent entities.
Unknown partner statuses and accepted requests without the corroborating reverse grant are
not represented as partnerships. Grants alone do not establish a partnership. Memberships
are never inferred from authorization tables. Dashed edges mark invitations and requests.

Effective location SQL is shared with Activity previews in `repositories/location.py`.
It follows the established `get-event-dates.sql` path and is integration-tested against
`services.quality.core.effective_location`, including reverse traversal from spaces.
The separately documented public projection's COALESCE-only space behavior is not used.

## API and limits

All endpoints are under the existing system-admin authentication boundary:

- `GET /api/v1/graph/search?q=...&entity_type=...&organization_id=...&limit=20`
- `GET /api/v1/graph?root_type=organization&root_key=<uuid>&depth=2&relation_type=...`

Search is case-insensitive, literal substring matching on safe names and UUIDs. Query length
after trimming is 2–120; limit is 1–20. Type and organization are optional search restrictions.
The organization dropdown offers organizations from the loaded graph, not a complete database
inventory. Changing the entity filter also restricts subsequent searches.

Graph depth is 1–3, default 2. Breadth-first traversal follows both ends of each edge while
preserving the source direction in the response. At most 100 nodes and 200 edges are returned.
Every expansion has a bounded, deterministic SQL candidate set (201 edges); cycles and repeats
are deduplicated. If any cap is hit, `truncated=true` and the UI displays an explicit notice.
The requested depth boundary itself is not truncation. Nodes at the last depth are not further
expanded, so the graph is not a complete inventory of every edge among its boundary nodes.

Response:

```ts
{
  root: { type, key },
  nodes: [{ id: 'type:uuid', type, key, label, subtitle, status, admin_url, public_url }],
  edges: [{ id, source, target, type, label, direction: 'directed' | 'undirected' }],
  truncated: boolean,
  max_nodes: 100,
  max_edges: 200
}
```

Search returns `{ items: GraphNode[] }`. An absent root returns 404; invalid enums, UUIDs,
depths or search parameters return 422; authentication failures return 401/403.
Pydantic response models and Zod contracts validate both endpoints; Zod also validates graph
identities, unique IDs, edge endpoints and link targets.

## Interaction and rendering

The graph route loads modular `d3-force`, `d3-selection`, `d3-zoom` and `d3-drag`, without a CDN.
Vue owns the SVG markup and accessible labels; D3 owns simulation coordinates, dragging and
zoom transforms. `graphDataToSimulation` copies records so D3 never mutates the API response.
The initial layout runs 180 bounded ticks before display. It cools after dragging and is stopped
on replacement/unmount; D3 listeners are detached on unmount. No position persistence is used.

- Click or Enter/Space selects a node; selected nodes have a purple ring.
- Direct neighbors remain clear; other nodes are dimmed.
- Drag pins a node for the current graph session. Zoom, pan, fit and reset use actual buttons.
- Details show safe metadata, UUID copy, direct relationships, event/place subsets and links.
- Relationships are buttons, allowing exploration without interacting with the SVG.
- “Als Ausgangspunkt verwenden” updates root/depth in the URL; Back/Forward restores them.
- Entity filtering creates a derived view and keeps the root visible. Relationship filtering
  is server-side and applies during traversal. Counts always describe the loaded/visible graph.
- Edge labels may be disabled; dense graphs label only edges touching the selected node.

| Type | Color | Existing AppIcon |
| --- | --- | --- |
| Organisation | Violet | organization / Building2 |
| Ort | Green | pin / MapPin |
| Raum | Cyan | space / DoorOpen |
| Veranstaltung | Rose | calendar / CalendarDays |
| Termin | Purple | calendar / CalendarDays |
| Benutzer | Blue | user / User |

No minimap is included. Node size identifies the root, not a statistical weight.

## Security, links and performance

Queries use bound parameters and fixed SQL identifiers. The existing read-only, repeatable-read
connection and statement timeout are preserved. One adjacency query and one node batch per depth,
plus root lookup and a single batch for existing Activity public links: at most eight data queries
for depth 3, not one request per node. No full graph is fetched on page entry. SQL name searches and
reverse location lookups can still scan relevant tables; production query plans and missing source
indexes remain an operational performance limitation, not a claim of production benchmarking.

User nodes expose the canonical label (display_name → username → email → UUID, skipping
empty strings), UUID and activation status. Email can appear in protected labels; credentials
remain excluded from the graph contract. Public links reuse Activity's existing
configured-instance/slug/release checks;
unsupported public URLs remain null. Admin links use the existing Action model: organizations,
venues, spaces, events and users link to their canonical detail pages; event dates retain
the Activity target. Graph search and graph responses reuse the shared Action validation,
which checks the exact entity type/key and also accepts legacy Activity links. Arbitrary
internal paths and external admin targets remain rejected.
Graph links are also available from Activity, finding details and mark details for supported UUID
entities only. The Nuxt proxy allows only the two exact routes and their named query parameters.

Search is debounced 300ms. Request generations ignore stale responses after query changes,
root changes, access loss or unmount; requests also retain the existing API timeout.
Keyboard focus, SVG labels, real buttons, text legend and the external relationship list provide
non-color and non-pointer access. Production CSP is unchanged; tests exercise `/graph` under an
enforced policy without `unsafe-eval`. No production configuration, DB or deployment is changed.

## Verification

Backend tests cover all six roots/search types, joined/invited membership, accepted/pending partner
semantics, overridden/inherited locations in both directions, depth, cycles, deterministic output,
limits, safe fields and API authorization/validation. Frontend tests cover contracts, immutable
transforms, filters, details, SVG keyboard selection and proxy restrictions. Playwright uses a
small synthetic graph on desktop/mobile for search, selection, filters, deep links, errors,
truncation and screenshots; the production CSP test renders and interacts with the graph.

### PR verification (2026-09-16)

Verified in an isolated checkout based on `main`, containing only the relationship graph feature.

- Backend: `uv sync --locked`, Ruff lint/format, strict mypy and all 280 tests passed
  against disposable PostgreSQL/PostGIS.
- Frontend: frozen lockfile install, ESLint, strict typecheck, all 114 unit tests and the
  production build passed.
- All 52 production Playwright cases passed on desktop/mobile, including the enforced CSP test.
  Screenshots: [desktop](screenshots/entity-graph-desktop.png) and
  [mobile](screenshots/entity-graph-mobile.png).
- Modular D3 is part of the dynamically loaded graph route; the page does not require a CDN
  or a relaxed script CSP. No production data, service or deployment was changed.

### Additional local verification before PR integration (2026-09-16)

These earlier observations were recorded in the combined local Graph/check-worker checkout.
They describe that snapshot, not a fresh verification of the merged branch. The PR verification
above describes the isolated Graph checkout. PR #32 subsequently updated the check-job browser
test to wait for initial loading and reset its polling counter when starting a job.

- Backend: 306 tests passed against disposable PostgreSQL/PostGIS; after the UUID lookup
  optimization, all 58 affected Graph/Activity tests passed again. Ruff and strict mypy passed.
- Frontend: frozen lockfile install, ESLint, strict typecheck, 120 unit tests and production
  build passed. All 54 production Playwright cases passed on desktop/mobile, including CSP.
- The production graph route is a dynamic entry. Its JavaScript chunk (UI and modular D3)
  measured 84,512 bytes, 29,171 bytes gzip; the shared graph presentation helper measured
  1,949 / 954 bytes. These are chunk sizes, not a measured total baseline bundle increase.
- Browser verification used isolated localhost ports 3101/31903 because another test run
  occupied the standard ports. Temporary runner/fixture copies are not part of the feature.
- Development Playwright: all six graph cases passed. The full run had 45 passes, four
  production-only skips and five failures. A serial retry passed three failures; the two
  `check-jobs.spec.ts` cases still failed waiting for “Wartet auf Worker”. Their traces
  contain no start POST after the click, consistent with a pre-hydration interaction.
  Those separate, already-in-progress check-job changes were not modified for this feature.

## Native browser fullscreen

The **Vollbild** button uses `requestFullscreen()` directly from the user's click on the existing
`GraphWorkspace` element. Only this workspace enters fullscreen: toolbar, graph, details, status,
loading/errors and legend. The application navigation, page header and search filters remain
outside it. No modal, second SVG, second active simulation, dependency or API change is involved.

`useFullscreen` detects both `document.fullscreenEnabled` and the element API after mounting.
Unsupported browsers hide the control. The state always compares `document.fullscreenElement`
with this exact workspace and follows `fullscreenchange`, including browser Escape. Rejected
requests show a short generic message. Controls remain keyboard accessible, focus returns to the
entry button on exit, and removing the workspace (including route leave) exits only its own
fullscreen and removes the listener. There is no focus trap or application Escape handler.
Browser APIs are never accessed during SSR. Browser/embedding policy can still deny fullscreen;
there is deliberately no fake fullscreen fallback or query parameter.

The existing SVG ResizeObserver updates dimensions and the zoom extent. Simulation coordinates
remain centered at `(0, 0)`; the viewport is positioned through the zoom transform, so resizing
needs no new center force or simulation. On entry and exit, fitting runs once after Vue layout
and two animation frames. Ordinary resize (including hiding details) preserves manual zoom/pan.
The explicit reset control retains its existing simulation-reset behavior.

Desktop fullscreen details use a 360px side panel; below 1024px they are an optional overlay,
initially closed on entry. Selecting a node opens details. The compact legend stays in a footer;
counts/depth and truncation remain visible. Query-only root/history navigation keeps the workspace
mounted even while its data reloads. Root selection uses the existing Nuxt router and API contract.
SVG `<title>` tooltips and details live inside the workspace; no body teleport is needed.

Unit tests mock browser state, rejection, Escape, unsupported APIs, cleanup, focus, SSR and resize.
Playwright exercises the **real Chromium Fullscreen API**, on desktop and mobile-sized Chromium,
including root/back navigation, detail toggles and screenshots. Mobile emulation does not prove
support on every mobile browser: actual support is determined exclusively by feature detection.
CSP is unchanged; the existing production test without `unsafe-eval` remains required.

Fullscreen verification: frozen install, lint, typecheck, **131 unit tests**, production build,
**52 development E2E tests** (four existing production-only cases) and **56 production E2E tests**
passed. Production includes the existing enforced CSP tests without `unsafe-eval`.
Screenshots with synthetic test data: [normal](screenshots/graph-fullscreen-normal.png),
[desktop fullscreen](screenshots/graph-fullscreen-desktop.png),
[mobile fullscreen/details](screenshots/graph-fullscreen-mobile.png).
