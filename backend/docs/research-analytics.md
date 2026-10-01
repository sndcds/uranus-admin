# Analytical Research v5 / Planner v8

The browser still submits only `{ "query": "…" }` to `/api/v1/research/query`.
The LLM interprets names and operations; Admin resolves names and runs fixed,
parameterized, read-only PostgreSQL/PostGIS selections. It never asks a model for facts.

| Question class                                    | Source                                                        | Exact?               | Result        |
| ------------------------------------------------- | ------------------------------------------------------------- | -------------------- | ------------- |
| Used genres, event types, categories              | PostgreSQL taxonomy and eligible events                       | Yes                  | taxonomy      |
| Most frequent genres/types/categories             | PostgreSQL grouped distinct events                            | Yes                  | aggregate     |
| Jazz concerts in August 2026                      | Type + composite genre + inclusive local date filters         | Yes                  | count         |
| Western/eastern/northern/southern event or venue  | Effective occurrence venue point, PostGIS                     | Yes                  | spatial       |
| Events outside an area                            | `NOT ST_Covers` on cached authoritative area geometry         | Yes                  | records/count |
| Morning/afternoon/evening/night                   | Local `event_date.start_time`, excluding all-day              | Yes                  | records/count |
| Instrument discovery from descriptions            | No structured instrument taxonomy verified                    | Unsupported          | 422           |
| Wheelchair accessibility count                    | Event-level authoritative interpretation not established      | Unsupported          | 422           |
| Subjective/accessibility/instrument record search | Existing Jina/Qdrant relevance plus authoritative rehydration | No complete count    | records       |
| Busy places                                       | PostgreSQL matching occurrences by effective venue            | Yes                  | aggregate     |
| Active organizers                                 | PostgreSQL distinct events by organization                    | Yes                  | aggregate     |
| Explicit comparisons                              | Existing PostgreSQL target intersections                      | Yes, structured only | comparison    |

## Compatibility and activation

Merge/install the Planner PR first: it adds authenticated `POST /v5/plan` with
`research-query-plan-v5` / `research-planner-v8`, preserving `/plan` v3/v7 and
`/v4/plan` unified-domain planning. Then install this Admin PR and enable
`RESEARCH_ANALYTICS_ENABLED=true`. Default false permits independent rollout;
there is **no retry/fallback to v3** if v5 is enabled but unavailable. The legacy
Admin `/research/plan` endpoint keeps its exact v3 response. Existing v4 project
knowledge/metric endpoints remain unchanged. This PR performs no deployment.
The UI validates both versioned envelopes. Required nullable fields, closed enums,
`extra=forbid`, query-only browser requests and service authentication remain intact.

The versioned JSON Schema is checked against a Planner-exported fixture in
Admin’s `backend/tests/fixtures/research_analytics_schema.json`; the complete reviewed question corpus
is mirrored in both repositories. No migrations or new runtime grants are needed.

## Population, ordering and bounds

All operations reuse `eligible_event_ctes`, effective date/space/venue inheritance,
public status gates, canonical label queries and server-side name resolution.
Taxonomies report **used** values within all hard filters, not every unused dictionary
entry. `genre` uses `(type_id, genre_id)` identities and never category IDs. The
explicit label alias `Konzert` → `Konzerte` is resolved against exact source labels;
unknown/ambiguous labels still clarify. Event counts deduplicate events; occurrence
counts deduplicate date IDs. Rankings expose at most 20 groups, counts are over the
complete eligible population. Taxonomy returns at most 20 alphabetically ordered
items and an exact `total`, so truncation is visible. No complete list is claimed
when the total exceeds returned items. Ascending/descending ranks have stable label
and key ties; spatial ties use date and entity keys.

“Wo finden viele Veranstaltungen statt?” defaults to **occurrence_count by venue**:
repeated dates represent activity at a physical place. “Wer veranstaltet …?” uses
organization and distinct event_count. Explicit “Veranstaltungen” count requests
count distinct events; explicit “Termine” count date IDs. An event with multiple
venues can contribute to each venue group. There is no overlapping-area aggregate:
`group_by=area` stays unsupported until an explicit nonoverlapping level is defined.

Spatial event ranking chooses the extreme matching occurrence, then distinct events.
It does not rank an arbitrary representative date or event-level venue. Missing,
empty and out-of-range coordinates cannot establish a rank. Outside predicates
exclude NULL/empty/invalid geometries; boundary points are inside (`ST_Covers`).
They never classify missing locations as outside or use city/state text heuristics.

v5 time windows in the configured event timezone:

- morning: 06:00 ≤ start < 12:00
- afternoon: 12:00 ≤ start < 18:00
- evening: 18:00 ≤ start < 22:00
- night: 22:00 ≤ start < 24:00 or 00:00 ≤ start < 06:00

All-day and unknown start times are excluded. Dates are inclusive local calendar
dates; a night window does not move a date to the previous day. v3 keeps its existing
18:00–24:00 evening behavior and required period for compatibility.

## Unsupported boundaries and evidence

Local Uranus source inspection found `venue.accessibility_flags`,
`space.accessibility_flags`, summary text and `event_date.accessibility_info`.
These are not evidence for an authoritative event-level “wheelchair accessible”
count: flag semantics, location inheritance and unknown values need a reviewed
contract and live source verification. No structured instrument table was found in
the inspected DDL. This is a repository inspection, not a claim about live schema.
Instrument discovery remains unsupported; description mentions can be retrieved
semantically. Exact semantic counts, aggregates, comparisons and taxonomies remain
forbidden. No Qdrant top-K count is presented as a population statistic.

A shared deterministic multilingual veto rejects recognized analytical questions
that contradict a proposed generic list, taxonomy dimension or ranking dimension.
It runs at the v3 and v5 Planner response boundaries and again before Admin resolution,
including v3 executions. Recognized outside/morning qualifiers cannot silently disappear;
accessibility counts are vetoed even if the model drops the semantic condition. It only rejects; it never rewrites a plan or generates SQL.
It is a conservative regression guard, not exhaustive natural-language understanding.
The versioned prompt and opt-in live-model corpus are still required language checks.

UI output distinguishes “Exakte strukturierte Auswertung” from semantic relevance.
Taxonomies and aggregates use compact text/tables; spatial results lead with the
extreme coordinate; count answers expose resolved taxonomy and date filters.

## Validation and follow-ups

Ordinary tests use mocked model responses and full golden plans. PostgreSQL tests
use disposable synthetic fixtures in GitHub CI; no local Docker is required or run.
Live model acceptance is opt-in (`RESEARCH_PLANNER_LIVE_TEST=1`) and must be evaluated
against the configured provider before operational activation; mocked outputs do
not establish model language accuracy. Follow-ups: evidence-backed instrument
extraction, verified event accessibility semantics, taxonomy pagination if needed,
and a defined nonoverlapping area grouping level.
