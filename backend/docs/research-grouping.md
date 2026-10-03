# Ordered multidimensional Research grouping

The additive `/api/v1/research/v9/query` route calls Planner `/v9/plan` once,
normalizes the closed wire plan, then uses the existing ResearchPlanExecutor.
It does not switch existing clients or use a version-specific executor.
Planner v9 / prompt v15 preserves the public v7 contract. V8 remains the
administrative-geography transport. No migration, grant or deployment is included.

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
