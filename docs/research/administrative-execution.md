# Internal Research plan and administrative geography

## Responsibilities and request path

```mermaid
flowchart TD
    U[User Question] --> P[Research Planner: semantic geographic intent]
    P --> G[Research Geocoder: geographic/admin resolution]
    G --> A[Uranus Admin: internal typed plan]
    A --> E[PostGIS Executor]
```

The responsibility diagram is implemented as:

```mermaid
sequenceDiagram
    participant User
    participant Admin
    participant Planner
    participant Resolver
    participant Geocoder
    participant Executor
    User->>Admin: POST /api/v1/research/v8/query, question only
    Admin->>Planner: one /v8/plan request
    Planner-->>Admin: strict v8 / v14 wire
    Admin->>Admin: Normalizer → InternalResearchPlan
    Admin->>Resolver: names, expected roles, AND constraints
    Resolver->>Geocoder: search candidates, explicit boundary lookup
    Geocoder-->>Resolver: observed roles, codes, OSM identity, polygon
    Resolver-->>Admin: AdministrativeAreaRef + resolved boundary
    Admin->>Executor: ResolvedResearchPlan (no raw geographic queries)
    Executor-->>User: exact records/counts/groups + unknown-location count
```

`research/wire/` mirrors the versioned Planner contract and its closed validation.
It contains no name-to-area tables and is checked against the Planner's v8 schema
snapshot. `normalizer.py` is the only wire-to-internal adapter. The Executor receives
`ResolvedResearchPlan`, never wire-v7/v8 objects or raw area/category queries. There
is no `V7ResearchExecutor`. Existing versioned/legacy endpoints remain available;
the new endpoint does not change the default browser Research query route.

The new authenticated backend endpoint accepts only a question; browser-submitted
plans are rejected. Existing journalist/system-admin authorization, body limits,
Origin/CSRF checks and safe error envelopes remain. No frontend proxy wildcard or
browser access to private service keys was introduced.

## Core model, identities and hierarchy

`AdministrativeAreaRef` carries name, level, country_code, optional official code
and its tag namespace, OSM type/ID, `area_id`, and `boundary_reference`.
Levels are municipality, district, state, country, region. No German domain class
names or hardcoded state/county name tables exist in the new core.

`area_id = osm:<N|W|R>:<id>:<level>` is an Admin reference constructed only from
validated Geocoder identity and role. It is not an official identifier. Including
the role allows a dual municipality/district object to participate in both
inventories. The original official code is copied unchanged when available; it is
never synthesized, padded or used as an unnamespaced primary key.
`boundary_reference` is the SHA-256 of the validated polygon JSON. Geometry is
resolved separately and stays out of result records and normal search payloads.

Parent/child intent preserves the subject and grouping level independently of
spatial constraints. For municipalities in Nordfriesland, the subject/group is
municipality and the parent predicate is inside a resolved district. The same
model handles districts inside a state. A catalog may be explicitly scoped by its
resolved `parent_area_id`; hierarchy filtering additionally checks full boundary
coverage in PostGIS. A parent name is never inferred from a code prefix.

## Resolution and ambiguity

The private client validates every administrative field and polygon shape, retains
its bounded loopback-only transport, and never reflects provider error text.
Ordinary legacy Place projections strip the private metadata after validation so
existing browser contracts remain unchanged. Search replies remain bounded to five
candidates/256 KiB; explicit boundary lookup to 8 MiB. No request bodies are logged.

Resolver selection first checks observed roles and optional country context, then
canonical exact names among eligible candidates. Multiple distinct eligible
identities require clarification; candidate order is irrelevant. The lookup must
confirm the requested OSM type/ID, country and role. Missing geometry, unknown
levels and district/state mismatches fail explicitly. A bounding box or centroid
never stands in for an administrative boundary. Numeric OSM mapping is exclusively
the Geocoder's responsibility. The Planner's expected role cannot overwrite it.

## Membership and event location

The source projection is `repositories/research.py::research_sql(occurrences=True)`.
It retains the existing public event/date status gates, category interpretation,
organization joins and event-date venue overrides. The effective venue is
`COALESCE(event_date.venue_uuid, event.venue_uuid)`; a date venue override stops
inheritance of the event's space, as defined in `repositories/location.py`.
The authoritative point is that effective venue's `venue.point`. No space point,
browser location, suggested geocode or direct event geometry is invented.
An undated event retains the existing projection's unknown location semantics.

For each eligible occurrence point:

- inside = `ST_CoveredBy(point, boundary)`;
- outside = `NOT ST_CoveredBy(point, boundary)`, only for a known valid point;
- every ANDed condition applies to the **same occurrence** before distinct event
  counting. One occurrence outside SH and a different one inside Germany do not
  jointly satisfy outside SH AND inside Germany.

A boundary point is inside and not outside. All input polygons undergo PostGIS
validity/nonempty checks before membership evaluation. Unknown locations are
excluded from spatial matches and reported separately as
`unknown_location_count`: eligible events with no known eligible occurrence point.
An event with both an inside and an outside occurrence can appear in each separate
query; inside/outside are complements per point, not per multi-location event.

Administrative grouping counts distinct event IDs in each boundary. Shared boundary
points can count in both adjacent groups because coverage includes their edges;
totals across groups are therefore not necessarily additive. Parent inside means
full child-boundary coverage; outside is its complement. The point constraints
also apply to counted occurrences. Source access remains read-only; there are no
Uranus DML, source migrations, schema changes or new source-location assumptions.

## Complete grouping inventories

Search is not an exhaustive inventory. Ranking and especially `event_count = 0`
require an explicit complete catalog for the grouping level and scope. The new
path does not reinterpret the old municipal cache's generic region entries as
states. It uses an operator-built file configured by
`RESEARCH_ADMINISTRATIVE_CATALOG_PATH`; missing/incomplete/ambiguous catalogs fail
with `research_inventory_unavailable` instead of empty or misleading success.

The strict `Catalogs` document contains catalogs with level, optional resolved
parent_area_id, country_codes, complete, inventory_source and Geocoder-derived
items including boundaries. Complete means an operator has verified an exhaustive
inventory for the stated scope; it is never inferred from Nominatim search. Results
expose `inventory_countries`, making the indexed coverage explicit. Unscoped rankings
cover the configured inventory, not an invented worldwide area census.

Build one catalog using the private Geocoder and an authoritative operator-supplied
identity manifest:

```sh
cd backend
uv run python -m app.research.administrative_import manifest.json catalog.json
```

The manifest has `level`, `parent_area_id`, `country_codes`, `complete`,
`inventory_source` and `identities` (`osm_type`, `osm_id`). Every identity is looked
up through Research Geocoder and level-validated; search result counts cannot mark
it complete. The output is exclusively created and existing files are preserved.
Multiple reviewed catalogs can be combined under the `catalogs` array. File reads
and total geometry are bounded to 32 MiB and 12,000 areas per catalog; larger
inventories fail explicitly and need a separately designed indexed catalog store.
No catalog, official list or production geography was fetched/applied for this PR.
Operator inventory refresh remains explicit and should record the inventory source
version/date; the runtime does not silently refresh or accept partial imports.

## Supported execution and boundaries

Offline examples cover outside Schleswig-Holstein, inside Schleswig-Flensburg,
Flensburg/country/generic-region wire intent, district rankings, state rankings
with category Kultur, zero-event municipalities inside Nordfriesland and the
outside-state AND inside-country conjunction. Germany metadata resolution is owned
by Geocoder; Denmark-ready core types accept other country codes, but a Danish
mapping adapter and verified complete inventories still need provisioning.

The new path executes event lists/counts, administrative event-count ranks and
aggregates, one exact category filter, and zero-event child discovery. It rejects
other v8 constraints (temporal, semantic, prices, border distance, additional
metrics/filter combinations) as a whole. Existing endpoints retain their existing
capabilities; there is no runtime fallback between contracts. The new backend
endpoint is not yet wired into the legacy browser Research form.

Fixtures are synthetic and offline. They establish contract/SQL behavior, not live
OSM coverage or model language accuracy. Tests include actual PostGIS geometry,
boundary points, unknown locations, effective venue overrides, same-occurrence AND,
category filtering, empty children, level mismatch, ambiguity, closed wire snapshots,
private transport validation and endpoint authentication. Normal CI requires no
live Planner or Nominatim. Existing backend/frontend commands and OpenAPI snapshot
validation continue to apply.

## Rollout

Merge the existing Planner v13 predecessor PR #20, then Geocoder metadata, Planner
v8/v14 and Admin integration. No production deployment was performed. Deployment
requires all offline gates: first install the Admin-compatible client/new endpoint
while retaining legacy consumers, then enable the Geocoder metadata release and
Planner v8 endpoint, provision reviewed catalogs, and finally direct consumers to
the Admin v8 endpoint. This compatibility-first order avoids breaking strict old
Geocoder clients. No database migration/grant change is required for this path.
