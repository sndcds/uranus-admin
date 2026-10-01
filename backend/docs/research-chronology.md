# Event record ordering and independent limits — v3 / v6

The required wire contract is **research-query-plan-v3**, with prompt
**research-planner-v6**. Both fields remain required JSON keys, including when null:

| Field      | Type                          | Meaning                                                                        |
| ---------- | ----------------------------- | ------------------------------------------------------------------------------ |
| `ordering` | `"asc"`, `"desc"`, or `null`  | Requested event occurrence direction; null means unspecified                   |
| `limit`    | Strict integer 1–20 or `null` | Requested maximum number of returned records; null uses the normal bound of 20 |

Ordering and limit are independent: null/null, null/2, asc/null, asc/2, desc/null
and desc/2 are all valid. Old `none`, `earliest`, `latest`, unknown enums,
omitted fields, boolean/string/float limits and out-of-range integers are rejected.

Non-null ordering requires `entity_type=event`, `intent=list` or `search` and
`answer_mode=records`. No venue/organization event-date ordering is invented.
Limits are valid for list/search/recommend record results, including venue and
organization lists; recommendations keep their existing relevance ranking.
Count/aggregate/compare require **both fields null**. A request for an exact count
combined with an output-list limit is explicitly unsupported, with neutral ordering
and limit; the presentation restriction is never used to count only N rows.

## Effective execution

For **structured planner-driven event records** only:

```text
effective_ordering = plan.ordering or "asc"
effective_limit = plan.limit or 20
```

Null does not mean unsorted or unbounded. The planner does not invent an explicit
ASC request when none was made; Admin owns the default. All such event selections
use the occurrence-aware SQL path, not incidental `research_page()` ordering.
Classic browser Research search/list behavior remains unchanged.

Admin reuses the authoritative occurrence projection: public event/date status,
area, effective venue/space, organization, category, genre, date range and local
start-time eligibility all apply **before** ranking and the SQL limit. Undated
events and occurrences without a known start date cannot establish chronology
and remain outside this occurrence selection; classic search still exposes its
existing undated records. No eligibility is inferred from a semantic top-K sample.

```sql
-- asc (including the structured default)
start_date ASC, start_time ASC NULLS LAST, date_key ASC, entity_key ASC
-- desc (only explicitly requested)
start_date DESC, start_time DESC NULLS LAST, date_key DESC, entity_key DESC
```

`date_key` is the occurrence UUID; `entity_key` is the event UUID. Window ranking
(`row_number() OVER (PARTITION BY entity_key ORDER BY ...)`) selects each event's
earliest eligible occurrence for ASC or latest eligible occurrence for DESC.
Then these distinct event records are globally sorted in the same direction and
bounded by `LIMIT`. Event A at Jan 1 and Jan 3, plus Event B at Jan 2, yields
A (Jan 1), B (Jan 2) for ASC limit 2; the limit never counts duplicate occurrences.
Every returned date/time, effective venue/space, city, address, coordinate and
occurrence-status field comes from the selected occurrence.

These event-record selections return `total=null`: no full population count was
requested/calculated. `items.length` is only the displayed selection size.
Non-event structured lists retain their exact repository totals and apply the
limit via their SQL page size. Count/aggregate/compare SQL remains unchanged.

## Language and temporal interpretation

| Query                                                                                      | ordering | limit | temporal |
| ------------------------------------------------------------------------------------------ | -------- | ----- | -------- |
| welche veranstaltungen sind in flensburg?                                                  | null     | null  | none     |
| welche veranstaltungen sind in flensburg? sortiere die nach datum.                         | asc      | null  | none     |
| welche veranstaltungen sind in flensburg? sortiere die nach datum. zeige nur 2 ergebnisse. | asc      | 2     | none     |
| zeige nur 2 veranstaltungen in flensburg                                                   | null     | 2     | none     |
| zeige die letzten 2 veranstaltungen in flensburg                                           | desc     | 2     | none     |
| wann war das erste event im system?                                                        | asc      | 1     | none     |
| welches war das letzte event?                                                              | desc     | 1     | past     |
| was ist die nächste veranstaltung?                                                         | asc      | 1     | future   |

German, English and Danish fixtures cover implicit ordering, explicit ASC/DESC,
independent numeric/spelled-out limits and first/last/next. Bare sort/limit commands
refer to event records without inventing a prior place or topic; the service has
no conversation memory. Ordering does not itself imply past or future.
Existing calendar semantics remain: past ends before `reference_date`, future
includes that local date. “Next” therefore uses the nearest eligible occurrence
on/after the reference date, not a newly introduced current-clock-time constraint.
Explicit periods and evening filters apply before ranking.

Event chronology is not event-row `created_at`. “wann wurde das erste event im
system angelegt?” and database-age questions remain
`unsupported_reason=unsupported_constraint`, with ordering/limit null.
Best/most interesting/highest quality are not chronological ordering values.

## Semantic exception and display

Semantic search and recommendations retain **relevance ranking**, including when
ordering is null. An independent limit uses the existing server-side semantic
page-size contract without changing eligibility, retrieval or ranking. No
semantic knowledge retrieval code is changed by this extension.

Explicit semantic relevance plus date ordering remains unsupported: preserve
both conditions in a search plan with `unsupported_reason=unsupported_constraint`.
The planner maps that to HTTP 422 `planner_unsupported_plan`; Admin maps it to
`research_plan_unsupported`. A purported supported hybrid fails validation.

The answer UI labels structured event results “Sortierung: Datum aufsteigend”
(null or asc) or “Sortierung: Datum absteigend” (desc). An explicit limit displays
“Maximal N Ergebnisse”. This states effective execution, not an invented user
request. Semantic results have no date-sort claim. All planner answer event cards
show the full date including year; null totals are never displayed as population
counts or automatically described as semantic search.

## Breaking compatibility and deployment

Planner PR #10's v2/v5 contract has been merged; this replaces it with v3/v6.
The still-open Admin PR #159 must use this matching mirror, executor and frontend
before merging/releasing. No v1/v2 dual-read or malformed mixed-version envelope
is accepted. Old version acceptance evidence remains historical, not live v6
model accuracy evidence.

Prepare both release artifacts first. In a coordinated maintenance window,
withdraw Research request traffic, deploy planner v3/v6, deploy the matching Admin
backend and frontend, verify versions plus the limited Flensburg/first/next
queries, then restore traffic. Roll back both services and the frontend together.
There are no migrations, new grants, worker changes or Uranus writes. No merge
or production deployment is performed automatically.

Offline golden fixtures and mocked provider HTTP establish contract/dispatch
behavior, not live model accuracy. Native PostgreSQL/PostGIS regressions use
synthetic source data. Local tests use no Docker; the existing GitHub CI may use
its containers, and its outcome is not awaited for this follow-up.
