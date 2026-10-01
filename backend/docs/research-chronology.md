# Chronological Research records — v2 / v5

The wire contract is **research-query-plan-v2**, with prompt **research-planner-v5**.
Both services and the frontend require the new fields; no v1 or mixed-version
compatibility mode exists. All plan fields remain required, including nullable fields.

| Field      | Values                       | Validation                             |
| ---------- | ---------------------------- | -------------------------------------- |
| `ordering` | `none`, `earliest`, `latest` | Chronological event occurrences only   |
| `limit`    | integer 1–20 or `null`       | `null` exactly when ordering is `none` |

Chronological ordering requires `entity_type=event`, `intent=list` or `search`,
`answer_mode=records` and a non-null limit. It is forbidden for counts, aggregates,
comparisons and recommendations. Recommendations retain their semantic behavior.
Invalid combinations, unknown enums, omitted fields, coercible types and out-of-range
limits fail validation; nothing is repaired or silently clamped.

## Meaning and execution

“First event in the system” means the earliest matching public event occurrence in
Research, never the event row's `created_at`. Creation-time/database-age questions
are unsupported (`unsupported_reason=unsupported_constraint`, neutral ordering/limit).
Best, most interesting and highest quality are not chronological ordering concepts.

Admin reuses its authoritative occurrence projection and all existing public event/date
status, area, effective venue/space, organization, category, genre, date-range and
start-time eligibility. It does not change `research_page()` or browser sort values.
Undated events and occurrences with unknown start dates cannot rank chronologically.

For each event, select its first matching occurrence under the following SQL order;
then sort these distinct events under the same order and apply the bound limit:

```sql
-- earliest
start_date ASC, start_time ASC NULLS LAST, date_key ASC, entity_key ASC
-- latest
start_date DESC, start_time DESC NULLS LAST, date_key DESC, entity_key DESC
```

`date_key` is the occurrence UUID; `entity_key` is the event UUID. Window ranking
(`row_number() OVER (PARTITION BY entity_key ORDER BY ...)`) returns every event at
most once. Event A at Jan 1 and Jan 3 and Event B at Jan 2 yields A (Jan 1), B (Jan 2)
for earliest limit 2. All returned date/time, effective venue/space, city, address,
coordinates and occurrence status fields come from the selected occurrence.
An event with Jan and December occurrences can therefore rank first and last using
different occurrence contexts. The result contains up to `limit` events (zero if no
eligible occurrence exists). `total=null` means no full population count was requested;
it does not imply semantic search. Count/aggregate/compare paths remain exact and unbounded
by these new fields.

## Temporal and semantic interaction

Ordering and temporal filters are independent. First/earliest does not imply past;
latest does not imply future. “wann war das erste event im system?” uses `temporal=none`,
`ordering=earliest`, `limit=1`, `intent=list`, `semantic_query=null`.
Historical “welches war das letzte event?” uses `past/latest/1`.
“was ist die nächste veranstaltung?” uses `future/earliest/1`.
Explicit numeric or spelled-out cardinalities set the limit within 1–20.

Existing calendar semantics remain: past ends before `reference_date`; future includes
the reference date. Thus “next” is the nearest occurrence on/after the reference local
calendar date, not a new clock-time filter. Explicit periods and evening filters apply
before occurrence ranking, with the configured event timezone.

Pure chronological questions do not invoke semantic retrieval. Hybrid semantic plus
chronological requests currently use `unsupported_reason=unsupported_constraint`:
the planner retains the semantic condition and chronology in an unsupported `search`
plan, and its API returns 422 `planner_unsupported_plan` (Admin maps this to
`research_plan_unsupported`). A purported supported hybrid plan fails validation.
No top-K semantic sample is treated as a complete chronological population.

## Compatibility and deployment

This is a synchronized breaking deployment, with no database migration, new grants,
worker restart requirement or Uranus writes. Prepare and validate both release artifacts
and the matching Admin frontend first. Coordinate a maintenance window: stop/withdraw
Research request traffic, deploy planner v2/v5, deploy compatible Admin backend and
frontend, verify version tags and a known earliest/next query, then restore traffic.
Do not expose either incompatible intermediate combination. Roll back both together.
The changes and PR creation do not deploy anything automatically.

The previous v1/v4 operator model-acceptance evidence remains historical; it is not
v2/v5 live inference evidence. Offline fixtures and mocked provider HTTP prove wire
validation and execution behavior. Optional live model acceptance must be reported
separately. Native PostgreSQL/PostGIS tests exercise real SQL with synthetic source
fixtures and do not establish a deployed source schema or production data result.
