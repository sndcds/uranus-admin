# Global administrative work scope and location suggestions — phases 1–3

Base: uranus-admin main `2579e04b24819f16acf6b7ec096d31e0275d6135` (fetched 2026-09-18).
Uranus remote main DDL verified at `15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e`:
organization and venue own nullable geometry(Point,4326); spaces inherit their venue;
events/event dates have venue/space references, no independent points. EMPTY points
are possible (no excluding source constraint, and already present in the synthetic fixture).
This is repository evidence, not an assertion about the deployed database schema.

## Delivery status

Phase 1 was merged in **PR #55**. Phase 2 builds on verified main
`f7b27cf90325776ca8c540086ced8cbf2eaaf7a8` and implements Activity, Findings,
Dashboard, entity statistics, event-content statistics and Graph root discovery.
**Phase 2 needs no migration, grant change, provider configuration or new worker.**
The Alembic head remains `0010`. Deploy compatible API and frontend builds together.

Phase 3 implements internal missing-location rules, immutable candidate generations,
address fingerprints, deterministic matching, a standalone bounded worker and a
systemwide suggestion UI. Migration **0011** follows verified head **0010**.
Based on main `4badefa58b8081a93911667e57be18620cb62cbb` (PR #56); PR #55 remains
Phase 1. Candidate acceptance is still a separate follow-up.

## Three independent concepts

- **Scope:** selected cached administrative working geometry (OSM, not an official certificate).
- **Membership:** authoritative Uranus points covered by that geometry.
- **Suggestions:** possible coordinates from address geocoding, never membership.

No list request calls Nominatim or substitutes a centroid/address/ZIP suggestion.
No code in this feature writes Uranus or creates source indexes. Direct entity details
remain accessible outside the current scope. Selecting a work scope is not authorization.

## API and provider

All endpoints require independent systemadmin authentication:

- `GET /api/v1/geo/areas/search?q=...&limit=10`: trimmed 2–120 characters, no control
  characters, limit 1–10. Returns safe typed metadata, OSM identity, kind, country,
  level, hierarchy, bbox [west,south,east,north], eligibility; no full geometry.
- `POST /api/v1/geo/areas`: exact Origin plus `X-Admin-CSRF: 1` required (also for
  development bearer credentials). Strict body `{source:"osm",source_type:"relation",
  source_id:"27020"}`; unknown properties/geometry/URLs rejected. Body capped at 8 KiB.
- `GET /api/v1/geo/areas/{uuid}`: cached metadata without geometry or provider request.

V1 discovery includes only OSM administrative boundary relations. Search eligibility
means suitable identity/classification; polygon eligibility is finally checked during
server lookup. Nodes/ways/POIs are excluded. The schema identity is provider-neutral;
future BKG/municipal adapters can populate the same model without a Germany-specific API.

The [Nominatim search](https://nominatim.org/release-docs/latest/api/Search/) and
[lookup](https://nominatim.org/release-docs/latest/api/Lookup/) contracts use `format=jsonv2`,
`addressdetails=1`, `namedetails=1`, `extratags=1`; lookup additionally uses
`osm_ids=R<id>` and `polygon_geojson=1`, without simplification. Both `class` and newer
`category` responses are understood. On 2026-09-18 a manual, read-only compatibility
probe of the configured internal service returned Flensburg relation 27020, category
boundary/type administrative, Polygon, admin_level 6. Live responses are not test fixtures.

No productive default: `NOMINATIM_BASE_URL` must be explicitly set, normally to
`https://nominatim.oklabflensburg.de`. Exact HTTP(S) origin only; no credentials, path,
query, fragments, wildcard, controls or user-controlled host. Production/staging require
HTTPS. No fallback to nominatim.openstreetmap.org. Redirects are disabled; environment
proxy variables are ignored; User-Agent is `uranus-admin/0.1.0 geo-service`.

Architecture supports administrative regions across Europe and elsewhere. Actual
coverage depends on the deployed Nominatim dataset; no coverage is inferred from a
successful Flensburg query. OSM attribution is visible in the selector.

## Storage and geometry

Migration **0010**, actual predecessor **0009**, creates only `admin.geo_area`:

| Columns | Type / purpose |
| --- | --- |
| id | UUID primary key, stable across reuse |
| source, source_type, source_id | text, unique composite provider identity |
| name, display_name | bounded provider text, normalized whitespace |
| country_code, admin_level, kind | country and original level; normalized kind |
| provider_class, provider_type, provider_addresstype | original classification |
| geometry | nonempty, valid MultiPolygon, SRID 4326 |
| bbox | Polygon, 4326; envelope derived from stored geometry |
| hierarchy | JSONB default {}; only 13 allowlisted address hierarchy keys, 240 chars each |
| fetched_at, created_at, updated_at | timestamptz |

GIST on geometry; BTree on country_code, kind, fetched_at; unique provider identity.
No source DDL. Runtime `admin_user`: SELECT, INSERT, UPDATE only, no DELETE.
The readiness grant registry checks the table and all three privileges; migration
head is derived from Alembic. Provider availability is never checked by `/ready`.
PostGIS must already be installed by the database operator; this migration installs no extension.

Geometry is fetched by the server using identity alone. Only GeoJSON Polygon and
MultiPolygon are accepted; input GeometryCollections, empty/unclosed rings, invalid
coordinate dimensions/ranges and excessive complexity are rejected. PostGIS applies
ST_SetSRID(4326), ST_MakeValid, ST_CollectionExtract(...,3), ST_Multi; empty repair
results are rejected. A database check also enforces validity and nonemptiness.

Default limits: **8 seconds total provider time**, **16 MiB response**,
**250,000 input positions**, **10 result objects**. HTTP streaming aborts at the byte
limit; compressed responses are refused to prevent decompression amplification.
The database statement timeout independently bounds PostGIS work. No simplification
changes membership precision. Oversized country boundaries can fail safely; measure
representative deployed polygons before increasing limits (configured hard ceilings:
30 seconds, 32 MiB, 500,000 positions).

An existing identity reuses its UUID without a provider request, even during outage.
Concurrent first imports converge through the unique constraint/upsert. No automatic
TTL refresh or delete exists in V1. A later explicit refresh should preserve id and
update geometry/name/hierarchy/fetched_at/updated_at. Boundary-version history is deferred.

Kind mapping prefers explicit provider address types. Unknown categories fall back
to country-specific tables (DE: 2/4/6/8, DK: 2/4/7), never a universal level=8 mapping.
Unknown country/level without recognizable addresstype yields `other`. Thus Flensburg
can be `city` despite level 6, Schleswig-Holstein `region`, and a Danish kommune
`municipality`. Raw country/level/classification remain stored for interpretation.

## Membership and temporal combination

`resolve_geo_scope(admin_connection, uuid)` loads typed metadata and EWKB from admin.
The API passes **bound bytes** to the read-only Source connection. The source role
needs no admin schema privilege. No query ever joins `admin.geo_area` from Source.
Unknown valid ID => 404 `geo_scope_not_found`; malformed UUID => 422; never unfiltered fallback.

Fixed SQL uses `point IS NOT NULL AND point && ST_GeomFromEWKB(:geo_scope_wkb)
AND ST_Covers(ST_GeomFromEWKB(:geo_scope_wkb), point)`. Covers includes boundary edges;
NULL and EMPTY points have no membership. Venue buildings are not used.

| Surface | geo_scope_id | Membership |
| --- | --- | --- |
| Organizations | yes | organization.point |
| Venues | yes | venue.point |
| Spaces | yes | parent venue.point |
| Events | yes | EXISTS real event_date with effective venue.point |
| Entity search | yes, four spatial types | identical predicates and temporal combination |
| Users, images | no | globally listed; proxy rejects geo query |
| Event dates | shared predicate, no standalone list | COALESCE(date venue,event venue), same existing location module |
| Activity | yes | spatial types only; nonspatial types excluded |
| Findings | yes | derive via affected source entity, missing-point findings unlocated |
| Dashboard | yes | spatial metrics filtered, global metrics explicitly distinguished |
| Entity statistics | yes | spatial series scoped before buckets; nonspatial series explicitly global |
| Event content | yes | event population scoped before counts, rankings, coverage and denominator |
| Graph | search only | root search only; relationships/direct roots remain complete |

Events without dates stay unlocated, even if event.venue_uuid exists. No artificial
fallback to event-level location. A date venue override wins; `EFFECTIVE_VENUE_SQL`
and `EFFECTIVE_SPACE_SQL` stay unchanged. A space is not another fallback venue.

For `temporal=upcoming|past`, the *same date* must satisfy both time and geometry.
The shared effective end expression uses configured event timezone, all-day/end-time
semantics, upcoming >= request now, past < now. Example: past date inside Flensburg,
future date in Kiel => Flensburg+past yes, Flensburg+upcoming no, Kiel+upcoming yes;
without temporal filter, both scopes include the event. Release status filtering
remains the existing separate entity filter; geo does not invent publication rules.

Filter before COUNT and LIMIT/OFFSET, preserve sorting. One EXISTS predicate per
query, no per-record queries. Existing batch previews remain unchanged.

## Frontend state and URL

Pinia `sharedGeoScope: GeoArea | null` parallels sharedPeriod. Neither overwrites
the other. No localStorage, sessionStorage, IndexedDB, profile field or custom cookie.
Existing auth clear/logout/new-login resets all preferences, including scope.
Late resolution/import responses cannot restore a previous login's scope.

Priority on supported pages: **URL geo_scope_id > session store > none**.
Authenticated middleware resolves metadata before list setup, and serializes an
inherited scope into the URL. Direct login return URLs retain an explicit scope.
Reload uses the cached-area endpoint, not Nominatim. Unsupported pages keep global
state in memory but do not serialize/send an unsupported filter. Their header explains
that the view is global. Returning to a supported list serializes the scope again.

Local “Filter zurücksetzen” preserves geo; global “Gebiet zurücksetzen” clears geo
and removes only that query key, resetting list page to 1 while preserving other filters.
Choosing a different area also resets page to 1. Shared period behavior is unchanged.
Invalid/unknown scopes are removed with a visible warning; storage failure keeps the
URL filter and presents errors instead of displaying unfiltered results silently.

Selector: 300ms debounce, minimum two characters, AbortController plus generation
checks, loading/empty/safe-error states, modal focus handling, combobox/listbox,
arrow/Enter/Escape support, mobile wrapping and ellipsis. Provider strings are escaped
text, never v-html. Zod validates all Geo API responses; proxy allowlists routes and
query keys individually and validates strict import bodies.

## Deployment, failure and privacy

1. Back up admin metadata using the existing deployment process.
2. With `ADMIN_MIGRATION_DATABASE_URL` (migrator only), run `uv run alembic upgrade head`.
3. Provision `GRANT SELECT, INSERT, UPDATE ON admin.geo_area TO admin_user;`.
4. Configure optional NOMINATIM_* variables from `.env.example`, deploy API/frontend,
   check readiness and exercise area search/import with a systemadmin session.
5. For Phase 3, also apply the migration/grants and worker deployment below.

Provider unconfigured/unavailable, redirects, malformed JSON, oversized responses:
503 `geo_provider_unavailable`; cached filtering unaffected. Ineligible identities:
422 `geo_area_not_eligible`; bad geometry: 422 `geo_area_geometry_invalid`.
Imports are idempotent, so an interrupted response can safely be retried. Source/admin
storage failures retain existing safe API behavior. No raw provider errors reach the UI.

Structured log events: geo_area_search, geo_area_cache_hit, geo_area_imported,
geo_area_import_failed. No query/address or response body labels. HTTPX/httpcore and
SQL logs are warning-level; request logging uses route templates, not querystrings.
Only the bounded hierarchy/metadata and geometry are cached, never full provider rows.

## Performance and validation

Synthetic tests use real PostGIS, a fake HTTP transport and a disposable database.
They cover polygons/multipolygons/repair/empty rejection, edge/inside/outside/NULL/EMPTY,
space inheritance, dateless events, date overrides, combined temporal semantics,
cache reuse/outage, strict identity/SSRF limits, scope resolution and isolated role
privileges. EXPLAIN ANALYZE/BUFFERS JSON is produced on the small event fixture; no
production performance result is claimed. Browser tests use a controlled local provider
contract, with existing SSR/auth/CSP/protected-content tests retained.

Existing upstream indexes: venue.point GIST, event_date.event_uuid and venue_uuid,
event.venue_uuid. Organization point has **no GIST index in the audited DDL**.
Recommend an upstream Uranus performance issue for an organization.point GIST index,
based on representative EXPLAIN measurements. Never create it from uranus-admin.
Large country geometries and source dataset size require production-like measurement.

Candidate acceptance is a separate future domain-write feature. It requires a verified,
authorized Uranus API contract for organization.point/venue.point. No direct SQL or
service-token shortcut is part of this or the planned suggestion worker.


## Phase 2 API and read boundaries

All six new query surfaces accept the same optional UUID `geo_scope_id`:

| Endpoint | Behavior with scope |
| --- | --- |
| `/dashboard/activity` | organization, venue, space, event and event_date only |
| `/findings` | affected spatial entities with UUID keys; persisted and live modes |
| `/dashboard/summary` | spatial creations and quality scoped; other metrics labelled global |
| `/statistics/entities` | spatial series scoped; user/partner_request/team_invitation global |
| `/statistics/events/content` | scoped event population before every aggregate |
| `/graph/search` | spatial root discovery only; explicit user + geo returns 422 |

Nuxt explicitly allowlists these parameters. `/graph` traversal does **not** accept
geo_scope_id. Its page URL carries scope only as discovery context. Direct roots
outside scope and relationships to outside/nonspatial nodes remain available.
Activity rejects explicit nonspatial type + geo with 422, and its UI offers only
spatial types. Unknown timestamp counts use the same scope. In the audited Source
DDL all five spatial types have NOT NULL created_at; unknown image timestamps thus
contribute zero to scoped Activity. No timestamp fallback is invented.

All endpoint scope resolution reads `admin.geo_area` once on the Admin connection;
only bound EWKB enters Source SQL. Phase 2 performs **no Nominatim request**, including
when the provider is unconfigured or offline. Unknown scopes return 404, malformed
UUIDs 422. Cached geometry does not change the source reader's permissions.

`spatial_predicate` accepts a code-owned key expression, with distinct inner aliases
so it can be reused inside aggregates without capturing the caller's alias. No SQL
identifier comes from a request. `mixed_spatial_predicate` composes those same
predicates, excludes other types and guards casts using CASE (technical Activity
keys are composite strings). It does not duplicate event/effective-location logic.
Creation time windows are independent of event-date spatial membership. All current
and previous comparison windows use the same geometry.

## Findings: exact totals with bounded memory

Persisted findings remain exclusively on the Admin connection. A read-only,
REPEATABLE READ server cursor selects matching rows in priority-score descending,
C-collated ID order, applying ordinary filters first. It yields **500 rows per batch**.
The Source connection has its own read-only REPEATABLE READ snapshot. A shared
membership helper groups UUID-valid identities by the five fixed spatial types and
checks each group with a bound UUID array, reusing `spatial_predicate`.
Non-UUID technical keys and nonspatial findings are excluded without a database cast.

Only the requested page (plus one item for cursor has_more) is retained; every eligible
row is counted to preserve **exact totals**. There is no full-result ID list, no
per-finding query, no temporary table and no Admin/Source join. The 1,201-finding
fixture requires three Source membership queries for one type; it produces an exact
600-item result even for the last page. Dashboard quality counts use the same stream
and membership helper, excluding resolved history as before. Live mode retains its
existing explicit global diagnostic scan, then filters results in 500-item batches
before pagination/counting; live Dashboard reuses the same filter.

Exact counting costs O(filtered candidate count) per request, regardless of requested
page. Memory is O(batch + page), but runtime is not independent of dataset size. This
is a deliberate no-migration tradeoff, not a production-volume claim. Existing command
and proxy timeouts remain in force; a timeout is an error, never an approximate total
or silently global response. Measure representative production-like finding volumes
before considering a dedicated derived-membership cache with explicit invalidation.

Each connection is internally snapshot-consistent. Admin findings and current Uranus
locations are **not a distributed snapshot**: a small interconnection race is possible.
This is an observational work view, not evidence for a write or authorization decision.
Activity and Finding cursor fingerprints include geo_scope_id; global/scoped and
cross-area cursor reuse is rejected. Changing/clearing scope removes an old cursor.

## Dashboard and statistics presentation

The additive Dashboard contract retains `new_records` (including its mixed total)
for compatibility, and supplies `geo_scope_id`, `new_record_scopes`,
`scoped_new_records_total`, `global_new_records_total`. Without a scope the new totals
are null. With one, the UI shows separate totals and labels every creation metric
**Gebiet** or **Systemweit**; it never presents the mixed sum as the area's total.
Users, images, partner requests and memberships remain global. Their links go to
appropriate global entity/queue views. Quality totals, severity, urgent counts and
rule_counts are spatial; latest/last-successful check runs and workflow queues remain
explicitly systemwide and independent of the creation period.

Entity series carry `scope: geo | global`; metric cards, chart legends and table
headers show the distinction under an active scope. Mixed-series distribution is
explicitly described as combining geographic and systemwide series. Recent entities
exclude nonspatial records when scoped. Event-content counts, coverage and ranking
shares all use the scoped event denominator, including period=all and comparison.

Supported page URLs are `/`, `/activity`, `/findings`, `/statistics`, `/graph` and the
four Phase 1 entity lists. Login, settings, notifications, users/images and direct
entity details are not newly scoped. Local reset preserves the scope, changing the
period preserves it, and global clear removes only geo (plus resetting pagination on
paginated lists). Existing logout/session-loss preference reset applies unchanged.

## Phase 2 performance review

Tests save EXPLAIN ANALYZE/BUFFERS JSON for Activity count/page/unknown count, entity
aggregation/recent, event-content and graph discovery. Small synthetic fixtures use
venue.point GIST, primary-key indexes and event_date.event_uuid where chosen by the
planner; tiny tables also produce sequential scans. Some fixed membership EXISTS
subplans are correlated; these are PostgreSQL plan operations, not N+1 network calls.
The bound geometry appears as a constant in custom plans rather than a per-row
provider/deserialization request. No materialized scope CTE or simplified geometry
was introduced without evidence of benefit. The explicit spatial-type restriction prunes nonspatial UNION branches. The final
small-fixture Graph plan did not trigger JIT; tiny-fixture timing is not a production benchmark.

Organization.point still lacks a GIST index in the previously audited upstream DDL.
Any index belongs in a Uranus-owned change after representative measurements. Phase 2
contains no Source DML/DDL, migration, new grant or external provider dependency.

## Missing location suggestions (Phase 3)

### Source of truth and source verification

On 2026-09-19, remote Uranus main was rechecked at
[`15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e`](https://github.com/sndcds/uranus/tree/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e).
`ddl/organization.ddl` confirms uuid/name/street/house_number/address_addition/
postal_code/city/country/state and nullable geometry(Point,4326).
`ddl/venue.ddl` confirms uuid/org_uuid/name/street/house_number/postal_code/city/
country/state/point/osm_id. EMPTY is permitted by the exported constraints.
Organization country is varchar(100); venue country is char(3), with only a length
constraint. The numeric bigint `osm_id` has no verified node/way/relation type, so
it is fingerprinted but never used for an inferred OSM lookup. This audit proves
repository compatibility, not a live deployment's schema; use the existing read-only
catalog verifier when deployment evidence is needed.

Rules `organization_missing_location` and `venue_missing_location` report warning,
field `point`, for NULL or EMPTY authoritative points. The existing specialized
`venue_missing_geolocation` rule remains available with its event relevance semantics.
The two new rules are internal only; the closed external notification policy excludes
them. Successful covering quality scans resolve findings after a source point appears.
No quality scan or ordinary GET performs address geocoding. Missing-point findings
remain excluded by an active Geo Scope; suggestions never confer spatial membership.

### Persistence, history and privilege boundary

Migration `0011` creates only `admin.geocode_request` and `admin.geocode_candidate`.
No migration discovers source entities or issues provider requests. Requests have a
unique `(entity_type, entity_key)` identity (organization/venue UUID), SHA-256 source
and query fingerprints, generation, query/scoring versions, status, attempt count,
checked/due/created/updated times, safe error category and worker lease identity.
Status: pending, checking, candidate, ambiguous, not_found, insufficient_input, failed,
stale. There is deliberately no accepted state.

Candidates are immutable rows, unique by `(request_id, generation, rank)` with FK to
the request. Each candidate retains its source/query fingerprints and algorithm versions,
so historical matches remain interpretable even after a changed address. Every completed
refresh uses a new generation. Address changes also advance generation, reset attempts,
clear the lease and enqueue a new evaluation. Old candidates remain stored; API exposes
only the current generation. V1 has no retention/deletion job.

Database and Pydantic reject invalid latitude/longitude, NaN and Infinity. Score is
0..1; rank is 1..5. Provider importance is separately stored and finite. Constraints
also validate status, entity type, positive versions/generation, nonnegative attempts,
fingerprint syntax, lease/state consistency, safe error, OSM identity and JSON shapes.
Indexes: unique entity identity, status/due/id BTree, partial checking lease index,
unique request/generation/rank BTree (also serving bounded candidate retrieval).

Owner remains the migrator. Runtime grants:

```sql
GRANT SELECT, INSERT, UPDATE ON admin.geocode_request TO admin_user;
GRANT SELECT, INSERT ON admin.geocode_candidate TO admin_user;
```

No runtime DELETE, TRUNCATE, DDL, candidate UPDATE, ownership or source write access.
Runtime boundary checks reject excessive geocode rights and candidate ownership.
Readiness requires the current Alembic head, tables and grants; Nominatim is not a
readiness dependency. Downgrade removes only the two new tables (and their suggestion
history); existing geo areas/findings/notifications are preserved.

### Fingerprints and deterministic matching v1

Source fingerprint canonicalization: Unicode NFC, trim and collapse internal whitespace,
null/empty both represented by empty string, preserve case and semantic Unicode. SHA-256
over sorted compact UTF-8 JSON of name/street/house_number/postal_code/city/country/state,
plus organization address_addition or venue osm_id. It does not include contact data.

Query strategy version 1 requires street plus city or postal code. No automatic name-only
search: a name cannot be proven sufficiently unique from this contract. Address addition
and abbreviated source state do not enter the query. One provider call maximum per attempt,
structured street (house number then street), city, postalcode, countrycodes when known,
otherwise country text. No free-form fallback, q, polygons, scope bias or spatial distance.
The [Nominatim structured search contract](https://nominatim.org/release-docs/latest/api/Search/)
uses `format=jsonv2`, `addressdetails=1`, `namedetails=1`, limit <=5. Existing configured
origin, total timeout/byte cap, no redirects, no environment proxies, identity encoding
and safe User-Agent protections are shared with boundary search/lookup.

ISO2/ISO3 correspondence is a frozen ISO 3166-1 code-pair table from the installed
iso-codes `iso_3166-1.json`. Valid codes are supported internationally. Name aliases are
limited to the verified Germany/Denmark DE/DA/EN entries in upstream
`tools/country_codes_en_de_da.csv`; other names give `country_unknown` for scoring.
Query fingerprint hashes strategy version and the actual normalized structured inputs.
Changing an algorithm version alone does not mass-requeue entities on deployment.

Scoring v1 (independent of Nominatim importance and name):

| Exact address signal | Weight |
| --- | --- |
| Normalized country code | 0.20 |
| Postal code | 0.25 |
| City/town/village/municipality | 0.20 |
| Road/street | 0.20 |
| House number | 0.15 |

Compare canonical Unicode casefolded strings. Postal internal spaces are preserved.
House-number spaces may be removed (`12 A` = `12a`, but `12` != `12a`). No fuzzy matching,
transliteration or street abbreviation guessing. Missing/unknown/mismatched fields score
zero; weights are never renormalized, so incomplete addresses remain lower scoring.
Reason codes are fixed `<field>_exact`, `<field>_mismatch`, `<field>_missing`, and
`country_unknown`. Provider prose is never a reason. Name/importance cannot outweigh an
incorrect address. Score is an address agreement measure, not a probability or confirmation.

Results are sorted score descending, provider rank as deterministic tie-breaker; duplicate
OSM identities are collapsed. Best score >=0.75 and lead over second >=0.15 yields candidate;
a single result still needs >=0.75. Other nonempty results are ambiguous (including a lone
weak result), empty result is not_found. Even a 1.0 match remains only a suggestion.
Store at most five candidates, display_name <=1024 and whitelisted address values <=240:
road, house_number, postcode, city, town, village, municipality, county, state, country,
country_code. No complete provider dump, response HTML rendering or internal provider host
appears in the API/UI. OSM links are constructed from validated node/way/relation plus
positive ID, otherwise from validated numeric coordinates; normal HTTPS links need no CSP
change. Selector and candidate cards share OpenStreetMap attribution.

### Worker and retries

`uv run python -m app.geocode_worker --once` is the complete production entry point;
without `--once` it polls every 60 seconds. Discovery and reconciliation use keyset batches
of 500 with explicit source projections and read-only REPEATABLE READ transactions.
Missing source owners/new authoritative points mark existing requests stale. New or changed
addresses are upserted transactionally, never per finding. Memory is bounded by a source
batch; synchronization visits the dataset and is O(source + stored requests), not constant
time. Initial discovery may create many pending requests but issues at most the configured
processing batch of provider attempts (default 50) per run.

Claims use FOR UPDATE SKIP LOCKED with owner/generation/expiry fencing. Expired leases are
reclaimable; completion cannot commit after lease loss or generation change. Requests are
claimed individually so queued jobs do not consume their lease while waiting for earlier
network work. A session advisory lock additionally limits the whole worker to one active
consumer across processes; connection loss releases it. It is not a write transaction.
Provider HTTP and pacing hold no admin write transaction. Provider concurrency is one,
with default 250ms sleep between calls. Lease defaults to 300 seconds (minimum 120), above
the shared provider timeout's maximum 30 seconds. A crash leaves recoverable checking state.

Before/after provider work, fresh source reads check existence, point and fingerprint.
API reads also suppress current candidates immediately on observed point/address changes,
without writing or calling the provider. Source/admin observations are not an atomic
cross-database snapshot; candidate acceptance cannot rely on these observations alone.

Candidate/ambiguous: no automatic refresh. Insufficient input: no provider call or scheduled
retry; source change is required for useful evaluation. Not found: retry after 30 days.
Provider errors: failed, only `provider_unavailable`, retry after 60 minutes. Invalid provider
results fail safely, never masquerade as empty success. No raw provider exceptions/queries/
addresses in logs. Structured geocode_run counts and request-id/candidate-count events support
operations. Queue age/worker progress are separate from readiness. A provider outage leaves
cached Geo Scope, findings and stored suggestions available.

### API and systemwide workflow

All routes inherit independent systemadmin auth:

- GET `/api/v1/geocode/requests`: entity_type/status/page/page_size, maximum 100 rows;
  server counts describe all stored states, not just the page. Filters/counts describe the
  last worker state; a row may be displayed stale after fresh source revalidation.
- GET `/api/v1/geocode/requests/{uuid}`: current generation, at most five candidates.
- POST `/api/v1/geocode/requests/{uuid}/retry`: HTTP 202 pending, no body or query;
  exact Origin and `X-Admin-CSRF: 1`, also for development bearer auth. Locks the request,
  re-reads source existence/point/fingerprint and queues a new generation. No provider HTTP,
  subprocess or background task. Already pending/checking => geocode_retry_not_allowed;
  removed/positioned source => geocode_no_longer_needed (409); unknown request => 404.

Source display names/addresses are loaded batchwise, not copied wholesale into admin.
Findings (persisted and live with configured admin storage) receive an optional request UUID
through one bounded admin lookup. No per-row HTTP requests. `/geocoding` and `/geocoding/{uuid}`
show source address, safe status, score/reasons, OSM links and a protected recheck control.
The queue is systemwide, does not support/send geo_scope_id, and keeps session Geo Scope
for returning to supported pages. No acceptance button exists. Provider/source text is escaped.

### Deployment and hourly systemd timer

Use paths/account names appropriate to the actual installation; these are examples, not
claims about existing services. Runtime environment must exclude migrator/operator DSNs.

1. Stage compatible code; keep the new timer stopped and coordinate API downtime.
2. Select the admin migration target explicitly; run `uv run alembic heads`,
   `uv run alembic upgrade head`, `uv run alembic current`, `uv run alembic check` with
   `ADMIN_MIGRATION_DATABASE_URL` as migrator. Then remove it from runtime environment.
3. Apply the two explicit grants above. Configure shared NOMINATIM_BASE_URL and GEOCODE_*
   settings from `.env.example`; no new provider origin setting or public fallback exists.
4. Restart API and the existing check worker with the new backend code, deploy frontend,
   and verify `/ready` against new head/grants. A long-running old check worker must be
   restarted to load the two new rules.
5. Run a quality check, then the geocode worker once manually; inspect counts, last stored
   states and candidate cards. No point changes or email should result.
6. Only then enable the hourly timer. Fifty evaluations per hourly run deliberately drains
   large initial queues gradually; tune batch/frequency against internal provider capacity.

Example `/etc/systemd/system/uranus-admin-geocode-worker.service`:

```ini
[Unit]
Description=Uranus Admin Geocode Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=oklab
Group=oklab
WorkingDirectory=/home/oklab/build/uranus-admin/backend
EnvironmentFile=/home/oklab/build/uranus-admin/backend/.env
ExecStart=/home/oklab/build/uranus-admin/backend/.venv/bin/python -m app.geocode_worker --once
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadOnlyPaths=/home/oklab/build/uranus-admin/backend
UMask=0027
StandardOutput=journal
StandardError=journal
```

Example `uranus-admin-geocode-worker.timer`:

```ini
[Unit]
Description=Hourly location suggestions

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=120
Unit=uranus-admin-geocode-worker.service

[Install]
WantedBy=timers.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl start uranus-admin-geocode-worker.service
journalctl -u uranus-admin-geocode-worker.service
# After first-run review:
sudo systemctl enable --now uranus-admin-geocode-worker.timer
```

Hourly is sufficient for nonurgent address suggestions. Manual retry queues immediately
but waits for the next timer (or explicit manual start); the browser does not start a worker.
Tests use fake HTTP transport and disposable PostgreSQL/PostGIS, never live geocoding.
A manual compatibility probe may use a known public venue address against the configured
internal provider; it is optional, outside CI and should not log addresses or response bodies.

### Follow-up: controlled candidate acceptance

Still required: a separately verified and authorized Uranus API contract for each point
write; systemadmin-to-domain authorization semantics; explicit confirmation UI; source,
fingerprint/generation and exact lat/lon revalidation immediately before submission;
immutable actor/request/result audit and safe handling of conflicts/network ambiguity.
No direct SQL, shared signing secret, impersonation or service-token shortcut. No acceptance
is implemented by this phase, including perfect matches. Retention and explicit algorithm
reprocessing are separate future operations, not automatic deployment behavior.
