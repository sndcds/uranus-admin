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
Other v9 language capabilities remain explicitly unsupported by this adapter.

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
