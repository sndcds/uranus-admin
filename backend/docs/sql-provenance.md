# SQL / Datenherkunft (Phase 2)

## Purpose and distinction

Finding SQL Diagnostics answers “why did this individual finding exist?”. Its Phase-1
API and eight pilot rules remain unchanged. View SQL Provenance answers “which sources
and application processing contribute to this view?”. One view usually has several queries.
Neither feature accepts browser SQL. There is no editor, WebSocket, write mode or console.

Audit baseline: `776d7f92cf857e9b31d37abd44afdf06b63ee59c`. The audit covered API routes,
repositories/services, pages/components and `admin-api.ts` before query extraction.
The machine-readable inventory is
[`coverage.json`](../app/sql_diagnostics/provenance/coverage.json). Tests require every
SQL-enabled inventory entry to have a registry definition and a matching frontend parameter allowlist.
Coverage describes this implementation, **not production deployment**.

## Architecture and registered parameters

- `repositories/query.py`: immutable `ReadQuery` containing the existing SQLAlchemy
  statement and bound values. Runtime repositories and provenance call the same builders.
- `sql_diagnostics/provenance/models.py`: concrete per-view Pydantic models reuse runtime
  filters and reject additional properties. UUID IDs, page bounds, enums and cursor validation
  remain authoritative on the server.
- `registry.py`: fixed view/source identifiers and query groups. No browser table/column identifiers.
- `render.py`: PostgreSQL SQLAlchemy compilation, separate bind parameters and literal copy
  rendering. Expanding binds and Core expressions are compiled from the runtime statement.
- `service.py`: definitions, bounded execution, safe serialization and structured audit.
- `api/sql_provenance.py`: explicitly registered typed routes, global system-admin auth and
  existing Origin/CSRF enforcement. Nitro has matching route/method/query/body allowlists.

Endpoints:

```text
GET  /api/v1/sql-provenance/{registered_view}?<typed view parameters>
POST /api/v1/sql-provenance/{registered_view}/{registered_source}/execute
```

POST receives only the typed view parameter object. `sql`, `table`, `column`, arbitrary
source combinations, extra query parameters and duplicate GET parameters are rejected.
Definitions perform **no source/admin SQL** beyond normal authentication. Execution rebuilds
the registered query; the returned SQL cannot be edited and submitted for execution.

`SqlProvenanceDefinition` contains view/endpoint, sources, postprocessing, notes, parameters
and `observed_at`. Each source has a stable ID, datasource, bound SQL, safe copy SQL, columns,
implementation reference, `readonly=true`, executable status and dependency descriptions.

## Runtime equality and dependency limits

List/count/order/page/cursor conditions come from the same runtime builder. The safe inspection
projection removes opaque JSON, snapshots, mail bodies and error payloads; this narrowing is
explicitly labelled. It preserves the runtime predicates, ordering, limits and offsets.

Some later query parameters depend on earlier result rows: entity enrichment, membership
batches, geocode generations, activity previews, graph frontiers and optional notification
configuration. Phase 2 shows these registered **templates**, describes the dependency and
**disables copying/execution** while the necessary values are unknown. Empty planning lists
are not claimed to be real result IDs; SQLAlchemy expanding-bind markers denote unresolved
batches. The graph frontier template contains all supported entity branches; runtime includes
only branches present in that frontier. This is a declared template, not a captured execution.

A geo-filtered view shows the cached boundary lookup and spatial runtime query templates.
Persisted findings show the actual ordered admin scan and the per-type membership queries,
then explain Python membership/counting/pagination. It never substitutes an unscoped total.
Live findings expose source snapshots, queue projections and Python rule evaluation instead
of inventing a single SQL query producing findings.

Notification configuration JSON is shown as a non-executable dependency, because capability
and nested-value safety cannot be established by a pure definition request. Historical mail
preview rendering is application processing of the notification detail payload, not new SQL.
External Nominatim and image/browser HTTP loading are external sources, not database queries.

## Shared execution and security boundaries

Phase 1 and Phase 2 use **one** primitive in `sql_diagnostics/readonly.py`:

```text
registered ReadQuery → selected engine → REPEATABLE READ / READ ONLY
→ statement timeout 5s / lock timeout 1s / idle transaction timeout 10s
→ async streaming cursor → bounded rows → ROLLBACK (also on errors/cancellation)
```

The outer operation timeout is eight seconds. Default execution returns at most 50 rows;
the internal hard cap is 100. An outer LIMIT preserves the original inner page semantics.
Reaching 50 is labelled “possibly more rows”; the UI does not pretend truncation is a complete
view response. Aggregates can also exceed the inspection cap and retain that warning.

**Uranus:** the existing source engine (`DATABASE_URL`) uses the deployment-verified reader
boundary. No admin connection is used for Uranus query groups. Source data is read only.

**Admin:** the existing admin engine has runtime DML privileges. **READ ONLY is therefore an
important security boundary for admin provenance**, in addition to the code-owned SELECT
registry. The existing `assert_admin_boundary()` privilege check is preserved inside the guarded
transaction. No reader role is provisioned by this change. A disposable PostgreSQL test confirms
that an attempted UPDATE fails with SQLSTATE `25006` even with the real fixture runtime role.

All registered statements are SELECT-only and single-statement checked; this checker is an
additional code invariant, **not** a parser intended to authorize arbitrary user SQL. Fixed
repository projections, bound values, role boundaries and transactions work together.

## Sensitive data and auditing

The Phase-1 sensitive field policy is reused: password hashes, import/activation/accept/reset
and session tokens, SMTP/DB credentials never appear as result columns. Token checks return
presence booleans only. Opaque JSON/snapshots/mail/error fields are excluded from Core
projections, structured result maps are withheld, and source URL credentials/sensitive query
parameters are redacted by the shared renderer. There is no authentication-table provenance.
Copy SQL contains view parameters, never source result literals or secrets from source rows.

Driver exceptions are replaced with fixed safe errors without exception chaining. Audit fields:
actor subject, registered view/source ID, datasource, duration, row count, success/failure
category. No SQL, parameter dictionaries, result rows, addresses, tokens or DSNs are logged.
Both backend and Zod response validation reject sensitive result columns.

## UI, time and staleness

Every data-driven page header provides `SQL / Datenherkunft`. The button waits for the actual
successful API request and reuses its effective filters, including session-restored values,
local severity, pagination and cursor. Definition loading is on demand; queries run only on
an individual click. Each source owns its result/loading/error state. Existing `SqlCodeBlock`,
`SqlResultTable` and the accessible `AppModal` are reused, including Escape and focus restoration.

View request revisions and auth generation prevent late responses from publishing stale
parameters. Filter/request changes close and discard the drawer. `as_of` preserves an available
view observation time for period/age computation; result `observed_at` reports execution time.
Each execution reads a **new snapshot**, not the historical snapshot that rendered the page.
Where a runtime response has no observation timestamp, the definition time is used and shown.

## Examples and postprocessing

Dashboard (persisted, no Geo Scope) has eight groups:

1. `dashboard.new_records`: Uranus creation counts for the selected period.
2. `dashboard.unknown_images`: Uranus images with unknown creation timestamp.
3. `dashboard.quality_counts`: Admin per-rule active counts; `resolved` excluded.
4. `dashboard.preview_count`: Admin total with `active_only=true` and preview severity.
5. `dashboard.preview_records`: same predicate, priority order, four-row preview.
6. `dashboard.latest_run`: newest admin check run.
7. `dashboard.last_successful_run`: latest successful check.
8. `dashboard.suggestions`: dependent geocode badges for the preview records.

The UI explains `period_window`, source/admin timezones, current-stock vs period semantics,
urgent priority metadata, Python count summation and Geo Scope membership. Check status is
independent of the selected time window.

Venue detail groups: entity, related count, related page, facts, own preview, related previews,
active finding count and active mark count. `related_page` retains 25-row pagination; related
preview IDs remain a declared dependency. Public links and display facts are Python enrichment.

Partner requests: count and records reuse `QUEUE_SQL` and `queue_page_queries`, including
status/organization/minimum-age filters, stable age/key ordering and page offset. `map_queue`
uses `URANUS_TIMESTAMP_TIMEZONE`, existing age thresholds and verified timestamp meanings.

## Coverage matrix

`registered` means the default query groups are executable. `registered_with_dependencies`
also exposes non-executable dependent templates as described above. Geo/live/compare variants
can change the number and executability of groups. Auxiliary registries (search/check detail/
geo area/legacy venue quality) are available through the typed API; the main page button
represents the visible primary data response, not transient autocomplete suggestions.

| View                    | API (prefix `/api/v1`)              | Sources       | Repository/service                                          | SQL | Query groups                               | Postprocessing                                                                                                                            | Phase 2                      |
| ----------------------- | ----------------------------------- | ------------- | ----------------------------------------------------------- | --- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| dashboard               | /dashboard/summary                  | uranus, admin | services.dashboard; repositories.dashboard; services.checks | yes | 8 default; geo/live/compare may add groups | period_window, source timezone, persisted_counts (unresolved), urgent metadata, check status; geo membership batches                      | registered_with_dependencies |
| activity                | /dashboard/activity                 | uranus        | repositories.activity; repositories.activity_previews       | yes | 4 default; geo/live/compare may add groups | period/cursor decoding, unknown timestamps, safe previews                                                                                 | registered_with_dependencies |
| findings                | /findings                           | admin, uranus | services.checks; services.quality.engine; api.findings      | yes | 3 default; geo/live/compare may add groups | stored_finding, priority metadata, active_only, cursor; geo membership before pagination; live Python rules                               | registered_with_dependencies |
| quality                 | /dashboard/summary                  | admin, uranus | services.dashboard; services.checks                         | yes | 5 default; geo/live/compare may add groups | Dashboard summary response; quality counts exclude resolved, zero-filled rule registry; venue explanation is static and links to findings | registered                   |
| checks                  | /check-runs                         | admin         | api.checks                                                  | yes | 2 default; geo/live/compare may add groups | CheckRun validation, pagination                                                                                                           | registered                   |
| checks.detail           | /check-runs/{id}                    | admin         | api.checks                                                  | yes | 1 default; geo/live/compare may add groups | CheckRun validation                                                                                                                       | registered                   |
| organizations           | /organizations                      | uranus, admin | repositories.entities; activity_previews                    | yes | 6 default; geo/live/compare may add groups | search escaping, period/temporal/geo, records/enrich, workflow counts                                                                     | registered_with_dependencies |
| organizations.detail    | /organizations/{id}                 | uranus, admin | repositories.entities; activity_previews                    | yes | 8 default; geo/live/compare may add groups | related_page (25), entity/related enrichment; optional graph and marks loaded separately                                                  | registered_with_dependencies |
| venues                  | /venues                             | uranus, admin | repositories.entities; activity_previews                    | yes | 6 default; geo/live/compare may add groups | search escaping, period/temporal/geo, records/enrich, workflow counts                                                                     | registered_with_dependencies |
| venues.detail           | /venues/{id}                        | uranus, admin | repositories.entities; activity_previews                    | yes | 8 default; geo/live/compare may add groups | related_page (25), entity/related enrichment; optional graph and marks loaded separately                                                  | registered_with_dependencies |
| spaces                  | /spaces                             | uranus, admin | repositories.entities; activity_previews                    | yes | 6 default; geo/live/compare may add groups | search escaping, period/temporal/geo, records/enrich, workflow counts                                                                     | registered_with_dependencies |
| spaces.detail           | /spaces/{id}                        | uranus, admin | repositories.entities; activity_previews                    | yes | 8 default; geo/live/compare may add groups | related_page (25), entity/related enrichment; optional graph and marks loaded separately                                                  | registered_with_dependencies |
| events                  | /events                             | uranus, admin | repositories.entities; activity_previews                    | yes | 6 default; geo/live/compare may add groups | search escaping, period/temporal/geo, records/enrich, workflow counts                                                                     | registered_with_dependencies |
| events.detail           | /events/{id}                        | uranus, admin | repositories.entities; activity_previews                    | yes | 8 default; geo/live/compare may add groups | related_page (25), entity/related enrichment; optional graph and marks loaded separately                                                  | registered_with_dependencies |
| users                   | /users                              | uranus, admin | repositories.entities; activity_previews                    | yes | 6 default; geo/live/compare may add groups | search escaping, period/temporal/geo, records/enrich, workflow counts                                                                     | registered_with_dependencies |
| users.detail            | /users/{id}                         | uranus, admin | repositories.entities; activity_previews                    | yes | 8 default; geo/live/compare may add groups | related_page (25), entity/related enrichment; optional graph and marks loaded separately                                                  | registered_with_dependencies |
| images                  | /images                             | uranus, admin | repositories.entities; activity_previews                    | yes | 6 default; geo/live/compare may add groups | search escaping, period/temporal/geo, records/enrich, workflow counts                                                                     | registered_with_dependencies |
| images.detail           | /images/{id}                        | uranus, admin | repositories.entities; activity_previews                    | yes | 8 default; geo/live/compare may add groups | related_page (25), entity/related enrichment; optional graph and marks loaded separately                                                  | registered_with_dependencies |
| queues.partner_requests | /work-queues/partner_requests       | uranus        | repositories.queues; services.queues                        | yes | 2 default; geo/live/compare may add groups | map_queue, timezone, age/pending thresholds, identity/action links                                                                        | registered                   |
| queues.team_invitations | /work-queues/team_invitations       | uranus        | repositories.queues; services.queues                        | yes | 2 default; geo/live/compare may add groups | map_queue, timezone, age/pending thresholds, identity/action links                                                                        | registered                   |
| queues.user_activation  | /work-queues/user_activation        | uranus        | repositories.queues; services.queues                        | yes | 2 default; geo/live/compare may add groups | map_queue, timezone, age/pending thresholds, identity/action links                                                                        | registered                   |
| geocoding               | /geocode/requests                   | admin, uranus | repositories.geocode; geocode_sources                       | yes | 6 default; geo/live/compare may add groups | fingerprint/stale comparison; Nominatim candidates are cached admin state; no HTTP during read                                            | registered_with_dependencies |
| geocoding.detail        | /geocode/requests/{id}              | admin, uranus | repositories.geocode; geocode_sources                       | yes | 4 default; geo/live/compare may add groups | current source address/fingerprint vs cached candidate state                                                                              | registered_with_dependencies |
| marks                   | /record-marks                       | admin         | services.marks                                              | yes | 2 default; geo/live/compare may add groups | status/urgency/reason filters, ordering                                                                                                   | registered                   |
| marks.detail            | /record-marks/{id}                  | admin         | services.marks                                              | yes | 2 default; geo/live/compare may add groups | immutable event history ordered by version                                                                                                | registered                   |
| graph                   | /graph                              | uranus        | repositories.graph                                          | yes | 4 default; geo/live/compare may add groups | root nodes, adjacency per frontier, candidate nodes, bounded graph + previews; D3 layout in browser                                       | registered_with_dependencies |
| statistics              | /statistics/entities                | uranus        | repositories.statistics; services.statistics                | yes | 2 default; geo/live/compare may add groups | period_window, natural timezone buckets, DST, previous totals, recent action links                                                        | registered                   |
| statistics.content      | /statistics/events/content          | uranus        | repositories.event_content; services.event_content          | yes | 1 default; geo/live/compare may add groups | period/previous window, coverage percentages and ranking deltas                                                                           | registered                   |
| notifications           | /notifications                      | uranus, admin | api.notifications; services.notifications.config            | yes | 9 default; geo/live/compare may add groups | config validation, local_day, delivery_enabled setting; no SMTP                                                                           | registered_with_dependencies |
| notifications.detail    | /notifications/{id}                 | admin         | api.notifications                                           | yes | 2 default; geo/live/compare may add groups | payload validation; optional preview localized/escaped in Python, no send                                                                 | registered                   |
| deliveries              | /notification-deliveries            | admin         | api.notifications                                           | yes | 2 default; geo/live/compare may add groups | organization name from immutable snapshot; delivery_enabled setting                                                                       | registered                   |
| deliveries.detail       | /notification-deliveries/{id}       | admin         | api.notifications                                           | yes | 3 default; geo/live/compare may add groups | immutable mail history, notification association, retries; sandboxed HTML rendering                                                       | registered                   |
| geo.area                | /geo/areas/{id}                     | admin         | services.geo.scopes                                         | yes | 1 default; geo/live/compare may add groups | cached boundary geometry/metadata                                                                                                         | registered                   |
| entity-search           | /entity-search                      | uranus        | repositories.entity_search                                  | yes | 1 default; geo/live/compare may add groups | type-specific search predicates, escaped substring, scope/period                                                                          | registered                   |
| graph.search            | /graph/search                       | uranus        | repositories.graph                                          | yes | 1 default; geo/live/compare may add groups | escaped substring, bounded nodes, geo scope                                                                                               | registered                   |
| quality.venues          | /quality/venues/missing-geolocation | uranus        | repositories.venues; services.quality.venues                | yes | 2 default; geo/live/compare may add groups | upcoming/published priority and generic findings                                                                                          | registered                   |
| login/logout/session    | —                                   | —             | —                                                           | no  | 0                                          | Authentication secrets and session control; outside data-view provenance                                                                  | not_applicable               |
| health/ready            | —                                   | —             | —                                                           | no  | 0                                          | Operational probes and privilege preflight, not view data                                                                                 | not_applicable               |
| commands                | —                                   | —             | —                                                           | no  | 0                                          | Writes/enqueue/retry/import/review are outside read provenance                                                                            | not_applicable               |
| geo.search              | —                                   | —             | —                                                           | no  | 0                                          | External Nominatim HTTP response, no local SQL                                                                                            | not_applicable               |
| static metadata         | —                                   | —             | —                                                           | no  | 0                                          | Code-owned labels, rule definitions, navigation; no SQL                                                                                   | not_applicable               |

## Extending the registry and later phases

Extract or reuse the runtime query builder, add a concrete parameter model and stable source
IDs, declare every dependency/postprocessing step, and review the safe projection. Update
coverage, frontend parameter allowlist, OpenAPI and synthetic regression fixtures together.
Test real PostgreSQL execution, literal rendering, bounds, auth/CSRF and secret exclusions.
Do not mark a dependency executable until its exact parameters can be obtained safely.

The shared async streaming cursor is an internal bounded execution primitive. Phase 3 may
build a separately reviewed interactive read-only interface on it, but this registry does
not authorize arbitrary SQL. No WebSocket or free query execution is included here.

No migrations, schema changes, roles, grants or Uranus writes are part of this implementation.
Synthetic fixture setup remains restricted to disposable `_test` databases.
