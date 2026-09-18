# Global administrative work scope — phase 1

Base: uranus-admin main `2579e04b24819f16acf6b7ec096d31e0275d6135` (fetched 2026-09-18).
Uranus remote main DDL verified at `15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e`:
organization and venue own nullable geometry(Point,4326); spaces inherit their venue;
events/event dates have venue/space references, no independent points. EMPTY points
are possible (no excluding source constraint, and already present in the synthetic fixture).
This is repository evidence, not an assertion about the deployed database schema.

## Delivery split

This PR delivers the complete first phase proposed in the feature request. Separate
reviewable follow-ups are required before calling the *whole* feature complete:

1. **This PR:** geo_area, Nominatim area discovery/import/cache, four spatial entity
   lists and autocomplete, global selector, URL/session behavior, tests and deployment.
2. **PR 2 — feat(geo): scope activity, findings and analytics:** spatial-only Activity;
   entity-derived Findings across the separate database connections; pre-aggregation
   filtering for Statistics/event content; explicit global Dashboard KPIs; Graph root
   discovery with full relationships retained. Reuse `spatial_predicate`, including
   its event_date branch; never join admin tables with Source reader queries.
3. **PR 3 — feat(geo): suggest missing organization and venue locations:** internal-only
   missing-location rules, bounded geocode candidate storage and standalone worker,
   source/query fingerprints, own address match score, ambiguity, suggestion UI,
   retry/rate limits and hardened systemd service/timer. No candidate table, worker,
   mail policy changes or dormant suggestion endpoints are shipped in this first PR.

The header explicitly says which views are still global. It never claims Statistics,
Activity, Findings, Graph, Dashboard, users or images are spatially restricted in phase 1.

## Three independent concepts

- **Scope:** selected cached administrative working geometry (OSM, not an official certificate).
- **Membership:** authoritative Uranus points covered by that geometry.
- **Suggestions (follow-up):** possible coordinates from address geocoding, never membership.

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

| Surface | geo_scope_id in phase 1 | Membership |
| --- | --- | --- |
| Organizations | yes | organization.point |
| Venues | yes | venue.point |
| Spaces | yes | parent venue.point |
| Events | yes | EXISTS real event_date with effective venue.point |
| Entity search | yes, four spatial types | identical predicates and temporal combination |
| Users, images | no | globally listed; proxy rejects geo query |
| Event dates | shared predicate, no standalone list | COALESCE(date venue,event venue), same existing location module |
| Activity | PR 2 | spatial types only; nonspatial types excluded |
| Findings | PR 2 | derive via affected source entity, missing-point findings unlocated |
| Dashboard | PR 2 | spatial metrics filtered, global metrics explicitly distinguished |
| Statistics/content | PR 2 | filter event population before aggregation/denominator |
| Graph | PR 2 | root search only; relationships/direct roots remain complete |

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

Priority on supported list pages: **URL geo_scope_id > session store > none**.
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
5. No geocode service/timer is deployed in this phase. PR 3 will define its exact CLI,
   environment/rate limits and hardened systemd units together with the worker tests.

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
