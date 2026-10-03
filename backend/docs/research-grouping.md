# Ordered multidimensional Research grouping

The normal `/api/v1/research/query` route selects its Planner contract at the
server transport boundary. Set `RESEARCH_PLANNER_CONTRACT=v9` in the protected
runtime environment to call `/v9/plan` once (schema `research-query-plan-v9`,
prompt `research-planner-v15`). The default `legacy` preserves the existing
v3/v5/v6 selection and location-context behavior. Rollback is `legacy`.
No automatic negotiation, language heuristics, second call or version fallback
is introduced. Deploy a compatible Planner before opting in; this PR does not deploy.
The existing Ansible runtime setting discovery includes the new setting; the browser
cannot choose it. V8 administrative transport and capabilities remain unchanged.

Both transports normalize into InternalResearchPlan and use the shared resolver
and ResearchPlanExecutor. The normal ResearchExecutionResponse preserves the
validated wire plan, resolution, execution provenance, observed_at, timezone and
measured planner/total diagnostics. ResearchQuestion still calls researchQuery;
grouped results reach ResearchQueryAnswer through that same validated envelope.
The unused `/v9/query`, proxy entry and researchGroupedQuery helper are removed.
The frontend strictly mirrors the executable v9 plan subset; unsupported v9
capabilities fail closed before a success envelope is returned.
No migration, grant or deployment is included.

InternalResearchPlan.groupings is an ordered tuple. Legacy scalar entry points
normalize to a singleton; none normalizes to empty. A multidimensional plan never
exposes a representative scalar axis. Duplicate/unknown dimensions are rejected.
The generic grouping primitive supports event, venue, organization, category,
event_type, genre, month and municipality, with event_count/occurrence_count.
The v9 adapter also maps the existing legacy families described below; unsupported
wire constructs still fail before source execution.

The repository reuses research_sql(occurrences=True) for the authoritative public
population and administrative_execution.execution_sql for polygon membership.
No status/date/venue/organization/taxonomy eligibility SQL is copied. Municipal
inventory resolution and geometry/product-bound checks are shared with existing
administrative execution. Unknown locations do not establish municipal membership.
No source data is written and no municipality is inferred from postal/city text.

Each complete cell counts distinct date UUIDs for occurrence_count. DISTINCT
removes duplicate link/category joins, not distinct logical events. An occurrence
may contribute to several taxonomy cells. Event type and genre axes retain their
link-parent relationship. A month is local occurrence start-date month 01..12,
across years unless constrained by the shared date filters. Missing dimensions
are excluded. No zero-count Cartesian inventory or inferred seasonality is emitted.

The grouped result carries dimensions in order and coordinates (dimension/key/name)
for EVERY cell. Sorting is global metric asc/desc, then each axis's lower(name)
COLLATE C and stable key, in tuple order. Null ordering means tuple order. A global
limit of at most 20 applies after aggregation; null limit uses20. It is not top20
per month/type, nor a claim of complete matrix coverage. Existing scalar result
contracts remain available. Frontend Zod rejects lost/reordered dimensions and
renders both coordinates and their count.

Offline tests cover normalization, strict bounds, result coordinates and SQL
construction. Disposable PostgreSQL tests verify occurrence-vs-event counts and
join duplicates in CI. No local Docker/PostgreSQL execution is required.

## SQL provenance integration

Grouped repository execution uses the shared `execute_research_sql` collector
introduced in #176, with label `Mehrdimensionale Auswertung` and kind `execution`.
The normal response carries `sql_provenance` alongside the grouped result. The
existing read-only SQL Editor displays that captured statement; grouping has no
separate UI or SQL executor. The exact executed TextClause and effective bindings
are captured, with the shared redaction rules unchanged (including inventory,
boundary geometry and private location parameters).

The combined API regression checks the captured SQL and redacted parameters against
the recording connection. Its response fixture is also validated and rendered by
the frontend tests, so a grouped result cannot inherit unrelated count-query SQL.
This fixture uses synthetic rows; PostgreSQL/PostGIS population tests remain
separate and require the disposable test database.


## v9 legacy capability parity

`research/normalize_v9.py` is the sole v9 wire adapter. It consumes the existing
strict v9 mirror; no Planner schema, internal model, resolver, repository SQL or
executor capability is added. `normalize_grouping.py` retains only the frozen v7
scalar compatibility adapter. The normal route and transport selection are unchanged.

| Existing capability | v9 representation | Existing execution |
| --- | --- | --- |
| Event, venue, organization lists | `list`, corresponding entity | chronological records / research page |
| Exact counts | event/occurrence/venue/organization count | count selection |
| Distinct count equivalents | `distinct_count` of those same four identities | same count metric, never semantic top-K |
| Scalar aggregates / count rankings | one supported axis and count metric | aggregate selection |
| Seasonal and other multidimensional groups | ordered dimensions, event/occurrence count | unchanged grouped selection |
| Genre / event type / category taxonomy | `taxonomy` plus taxonomy kind | taxonomy selection |
| Event semantic search / recommendations | `search` with query and optional focus | complete hard eligibility, semantic ranking, authoritative rehydration |
| Venue / organization / area comparisons | count metric, venue/organization/region targets | existing per-target count selection |
| Chronological event ordering | `rank`, `value(start_date)`, optional singleton event axis | chronological records |
| Coordinate ordering | `rank`, `value(longitude/latitude)`, event or venue | spatial records |
| Named area inside/outside | named `area_query` | existing administrative resolution and membership |
| Named place | `at`, named `place_query` | existing v6 address/bbox/bounded-radius resolution |
| Nearby | user_location / nearby, needs_location | existing context, reverse/manual lookup and radius |
| Administrative inventory grouping | region / country / municipality, event count; optional eq-zero metric filter | existing complete catalog / bounded polygon primitive |

All existing periods and explicit date ranges map to TemporalSelection, as do
v5/v6 dayparts. A closed `start_time gte` filter maps exactly to inclusive
`time_from`. Venue/organization/event type/category/genre equality filters retain
name resolution and hard eligibility. The metric identifies the counted population;
a ranked/comparison venue subject is not substituted for that population.

Clarifications `needs_criteria`, `needs_location` and `needs_date` retain their
state. A criterion-free rank remains a clarification with no invented count. Other
clarification states and explicitly unsupported plans fail closed. Browser context
never reaches Planner and sensitive-location questions are not learned. SQL
provenance continues using the existing collector and redaction.

### Deliberate boundaries and lossless-mapping gaps

- No trend, anomaly, relation, explain, knowledge, price, text-length/duration,
  ratio/diversity or arbitrary metric execution. No occurrence record endpoint or
  semantic execution on venues/organizations. Exact semantic counts remain rejected.
- No holiday/calendar, weekday, overlap, multi-day, metadata-time or lookback
  execution. `before_time` and `after_time` are not silently converted to the
  inclusive lower-bound primitive; arbitrary clock predicates are rejected.
- The historical v3 evening (>=18:00) differs from the bounded v5/v6 evening
  daypart (18:00–22:00). Only an explicit gte clock filter reproduces the former.
  The current Planner prompt prefers before/after temporal slots, so that historical
  interpretation is not claimed as automatic language parity.
- Multiple same-field v9 name equality predicates are not a legacy taxonomy OR-list.
  They are rejected instead of weakening AND semantics. V9 has no explicit OR-list
  representation for that legacy combination.
- V9 has one spatial object and no explicit state/district level. It cannot encode
  the full v8 AND-boundary/expected-level contract or simultaneous area+place scope.
  Do not infer missing predicates or levels from language. V8 remains available.
- Level-specific comparison targets (e.g. municipality/country) cannot lose their
  expected level in the existing ComparisonTarget; only generic region -> area,
  venue and organization comparisons map losslessly.
- No explicit radius, nearest/directional-relative/border execution is invented.
  Common comparison filters cannot be overwritten. Unsupported group/entity/metric
  combinations fail before resolution/SQL, with no fallback Planner call.

### Rollout

V9 can replace the **losslessly representable, currently executable legacy subset**
through the normal Research endpoint. It is not an unconditional full replacement
for the wire-expression gaps listed above. A cutover requires compatible Planner
PR #20, its acceptance gates (including these semantic boundaries), and explicit
operator opt-in. `RESEARCH_PLANNER_CONTRACT=legacy` remains the default and rollback.
No production configuration changes or deployment are part of this PR.

The parity matrix compares complete InternalResearchPlan values, excluding wire
metadata. Its validated wire fixtures are shared with frontend Zod tests. Normal
API tests exercise the existing SQL families, comparison provenance, semantic
eligibility/rehydration, and nearby browser/manual roundtrips. Valid but unsupported
wire plans are tested for rejection before resolution/source access.
