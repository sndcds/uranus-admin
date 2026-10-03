# In-session Research conversations

## Audit and boundary

Baseline Admin `a007a05` and Planner `3d6d005` used a single answer in
`ResearchQuestion.vue`. Replacing `data` cleared the previous answer. Planner v10
could express recurring calendar semantics but its closed `PlanRequest` accepted
only query, timezone and language. Neither rendered answers nor concatenated query
strings are a safe conversational contract.

The additive Planner `/v11/plan` contract (`research-query-plan-v11`, prompt
`research-planner-v17`) adds optional typed advisory `conversation_context` to the
request. V3/V5/V6/V7/V8/V9/V10 are unchanged. V11 uses the existing v10 execution
semantics. It adds no executor, SQL capability, database storage or second model
request. `needs_context` is a clarification and never executes source SQL.

```text
Composer → in-memory turns → normal /api/v1/research/query
  → plan_active (v11 when explicitly configured)
  → typed Planner interpretation → normalize → InternalResearchPlan
  → existing resolver/executor → authoritative response + safe semantic summary
  → historical ResearchQueryAnswer + deterministic German summary
```

## Ephemeral state and bounds

- At most **20 turns**, oldest evicted; stable monotonically increasing IDs.
- Each turn owns its question, response/error and advisory context used for retry.
- At most **4 contiguous successful previous plan summaries**, oldest first.
- Each summary is at most **2048 UTF-8 JSON bytes**, context at most **8192 bytes**.
- Names/concepts: 160 characters; taxonomy filter lists: 8 values; dimensions: 3;
  recurring weekdays: 7; months: 12; one named administrative predicate.
- Only fully represented plans are remembered. A failure, clarification or missing
  summary breaks the context chain. Comparison, geometry inventory/coverage,
  level-qualified administrative plans, explicit clock offsets and private location
  plans currently have no summary. No difficult constraint is silently dropped.
- No localStorage, sessionStorage, database history, profile memory or transcript URL.
  Unmount/reload loses history. Reload executes only the latest URL question.
- “Neue Recherche” aborts work, clears turns, context, location and draft, and opens
  `/research`. Authentication and global learned suggestions remain untouched.

The draft stays in the composer after submit (consistent retention policy). It is
never overwritten by a completion. Retry repeats the exact failed turn, even if the
user has since edited the draft. Back/forward reveals a matching existing turn
without executing it again; a new URL question starts an independent turn.

## Planner context and privacy

Admin explicitly projects normalized intent, metric, groupings, ordering/limit,
calendar semantics, taxonomy/name filters, a public named area and semantic concept.
Context contains **no original questions**, result rows, full descriptions, SQL,
parameters, source IDs, coordinates, geometry, vector scores, authentication or prose.
The browser returns these closed advisory summaries; they never authorize execution.
Planner treats context as untrusted data and still emits a fully validated current
plan. Current wording overrides context; standalone questions are independent.

Browser location stays in the separate existing location context. Any request with
location context, or a location-sensitive plan, returns no conversation summary.
Contextual requests are excluded from suggestion learning, as are existing sensitive
location requests. No new logging/persistence is introduced.

Result-identity follow-ups (“the first”, “which of those”) have **no result-reference
contract yet** and require `needs_context` rather than guessing a subset. Semantic
follow-ups (“only Sundays”, “only in Flensburg”, “in August”) use plan summaries.
Prompt/native boundary tests use mocked model outputs: they establish transport and
execution contracts, not live-model interpretation quality. Live acceptance is a
rollout gate.

## UI and deterministic answers

One persistent composer and all turns share `.research-conversation-width` (64rem
maximum, available main-column width on small screens). A common scrollport means
the scrollbar cannot make answers narrower than the composer. The sticky footer is
inside Research main, with safe-area padding; no sidebar or viewport-wide positioning.
There are no uploads or attachments. Textarea keyboard focus remains accessible.

The welcome hero/examples exist only before the first turn. The redundant discovery
section is removed; all destination pages remain in navigation. User questions are
compact right-aligned bubbles; structured answers retain their existing components.
Historical SQL Editors use each turn's own provenance and remain read-only.

The pure backend `build_research_answer` in `app/research/answer.py` produces
German sentences from the normalized plan, executed result and provenance. The
required nullable `answer_text` response field is bounded to 1000 characters.
The frontend displays this field verbatim; historical turns retain their own text.
No answer prose is included in `conversation_context` or sent to Planner.
Aggregate extrema use plan ordering; grouped extrema use result ordering. Null
ordering gives neutral text, comparisons give a factual value range. Explicit
nominative/dative labels distinguish “7 Termine” from “mit 7 Terminen”.
Displayed maximums/ties are explicitly scoped to displayed groups. Semantic results
are not exact populations. Clarifications receive no invented successful summary.

## Rollout / rollback

Deploy the coordinated Planner v11 implementation before opting Admin into
`RESEARCH_PLANNER_CONTRACT=v11`. The default remains **legacy**. There is no automatic
fallback or browser contract selection. Sending context to an older configured
transport fails explicitly; ordinary no-context calls remain compatible.

No migration, new credentials, grants, workers or infrastructure are required.
Disabling v11 returns to existing single-question interpretation while retaining the
local transcript UI. Reload clears any context obtained before a rollback.
No deployment or merge is part of this change.

The checked-in `conversation_v11.json` witnesses share the same expected plans with
Planner tests: seasonal → Sunday → Flensburg → August; a new organization question
with no inherited filters; and an unresolved result-identity reference. The pinned
`conversation_v11_schema.json` checks the mirrored context/envelope schema without
fetching a moving upstream contract during tests.

Coordinated Planner source: `6c85cebe00284e8dac9aa608ef0384b8126ff61a`. Snapshot digest and exact versions
are recorded in `backend/tests/fixtures/conversation_v11_contract.json`.

V12 additionally retains lexical administrative level expectations and up to four
AND areas in safe summaries. See [the combined v12 contract](modern-v12.md).
