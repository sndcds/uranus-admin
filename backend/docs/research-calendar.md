# Recurring calendar Research

The audited v9/v15 wire has a weekday grouping and one scalar weekday filter,
but cannot encode Saturday OR Sunday or July–September across years. Required
closed set fields therefore live in additive v10/v16, preserving deployed v9.
The Planner audit and contract are in its `docs/recurring-calendar.md`.
The coordinated Planner commit is `18eea0faa6d6447cdbc763a5c1d045257c8bf1dd`.
`tests/fixtures/research_v10_contract.json` pins its schema digest. Schema comparison
normalizes only enum ordering (Python Literal interning can change that order);
all members, bounds, required fields and closed-object constraints remain exact.

`RESEARCH_PLANNER_CONTRACT=v10` selects exactly one `/v10/plan` call on the
normal `/api/v1/research/query` route. Default remains `legacy`; v9 and the
existing v8 administrative path remain available. No fallback/retry exists.
Deploy the matching Planner and Admin, pass model acceptance, then opt in through
the protected runtime configuration. Ansible's existing setting discovery validates
this setting; no new service or manual proxy route is needed. Rollback selects
`legacy` or `v9`. No database migration, grants or deployment is included.

V10 `temporal.recurring_weekdays` is a unique bounded integer set (ISO Monday=1
through Sunday=7); `recurring_months` is a unique bounded integer set (1–12).
Empty means unrestricted. Within a set values combine with OR; different sets
and ordinary temporal bounds combine with AND. `normalize_v10` extracts these
predicates, reuses existing v9 adapters for the remaining semantics, then restores
them as sorted immutable `TemporalSelection.weekdays/months`. No condition is
dropped to make a plan executable. Scalar v9 weekday maps to the same internal set.

The shared authoritative occurrence population applies numeric
`extract(isodow FROM d.start_date)` and `extract(month FROM d.start_date)` with bound
integer arrays. These are event-local calendar dates, without locale-dependent
names or timezone conversion. No year is inferred. Missing dates fail a recurring
filter; undated-event and no-activity venue fallbacks cannot bypass it. Shared
date/visibility/effective-venue/taxonomy rules remain in one SQL implementation.
Eligibility and semantic rehydration both retain the same predicates.

`weekday` uses the existing ordered cell aggregator for single and multiple axes,
including event_type × weekday and genre × weekday. Raw weekday key/name is
`"1"`–`"7"`; German names are display-only. Month remains `"01"`–`"12"` across
eligible years. Global limits, DISTINCT occurrence/event identities, tie-breakers
and municipality inventory guards are unchanged. SQL provenance captures the actual
statement and safe weekday/month bindings through the existing collector; location
and geometry redaction remain unchanged.

Concrete audience records use existing search/event/semantic execution:
complete SQL eligibility → embedding/Qdrant ranking → authoritative rehydration.
No audience index or exact semantic count is introduced. Quantitative audience
requests remain explicitly unsupported for missing structured population data.
Undefined evaluative criteria remain blocked; Admin still cannot represent
`needs_definition` as an executable clarification and returns its existing safe
unsupported error. Holiday calendars, overlap, arbitrary clocks, trends and other
previously unsupported operations remain unsupported.

Shared witness fixtures test Planner wire/native HTTP boundaries and Admin's normal
endpoint through actual repository SQL construction. Mocked model responses do not
establish language accuracy. PostgreSQL tests cover recurring values across years,
intersection with date bounds, DISTINCT identity and missing occurrences; they skip
locally without an explicitly configured disposable `TEST_DATABASE_URL`. No Docker
or live service is started by these tests.
