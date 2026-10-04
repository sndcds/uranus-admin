# Conversational Research v13

Admin baseline: `58fc54f46bd74118b515c2413f4bf62e5d4d2412`.
Select `RESEARCH_PLANNER_CONTRACT=v13` to call Planner `/v13/plan`, schema
`research-query-plan-v13`, prompt `research-planner-v19`. The shared wire and fixture
schemas are checked against the Planner snapshot in unit tests.

```text
Natural language
  → Planner semantic interpretation
  → Research / correction / clarification response OR conversation act
  → existing Research executor OR direct conversational response
  → safe AnswerFacts / closed conversation act
  → grounded natural answer_text
  → frontend transcript and structured results
```

The LLM interprets DE/DA/EN language. PostgreSQL/PostGIS and Qdrant remain the factual
execution and retrieval paths. No second LLM, new executor, database schema, Redis,
source-data write or deployment is introduced.

## Routing

The closed interaction kinds are `research`, `acknowledgement`, `greeting`, `social`,
`help`, `correction`, `clarification_response`, `clarification`.
Research has `research_mode=new|follow_up`. Executable corrections and clarification
responses carry a complete v12 plan and the matching mode. They normalize through
`normalize_v12` and use `ResearchPlanExecutor`.

Acknowledgement, greeting, social and help payloads cannot contain executable plans.
The service returns before normalization, name resolution, SQL, PostGIS or Qdrant.
Authentication may still access the existing Admin session database. Social requests
never enter suggestion learning; the initial v13 path conservatively excludes all
v13 turns from learned suggestions. Legacy learning behavior is preserved.

Examples include “danke”, “hallo”, “wie geht es dir?”, “was kannst du?”, “und morgen?”,
“und sonntags?”, “nein, morgen”, “nicht Kiel, sondern Flensburg”, and equivalent
Danish/English phrasing. Mixed social/research language prioritizes the substantive
request. The model selects the language; ambiguous short utterances keep the previous
language. There is no frontend or backend phrase-list classifier.

## Backend state

The browser sends `query`, optional `conversation_id` and the existing separate runtime
`location_context`. v13 rejects browser-supplied semantic `conversation_context`.
Responses contain a random 256-bit URL-safe ID, never signed readable JSON or an
encoded summary. No semantic conversation state is returned for v13; legacy response
summaries remain available only for rollback clients.

A process-local store is appropriate for the current `app.__main__` entrypoint, which
already runs **one worker**. State expires after 30 minutes of inactivity, with at most
256 conversations and eight per authenticated session. Concurrent turns on one ID are
rejected rather than racing semantic updates. Idle entries are evicted at capacity.
IDs are bound to a hash of the authenticated session credential; another session cannot
read or resume them. Authentication and CSRF checks still run on every request. Logout,
page exit or “Neue Recherche” clears the browser handle; server state expires and is
inaccessible from a new authenticated session. Nothing is persisted as personal history.

State contains at most four bounded typed Research summaries, one pending clarification,
current language and a bounded safe fact projection. Social turns update language but
preserve Research summaries. Successful corrections store the corrected semantics.
Current user wording wins. Unsupported/unrepresentable research must not make later
follow-ups silently use a stale selection; such state is cleared. Location-sensitive
research is not remembered. No raw query transcript, rows, SQL, scores, geometry,
coordinates or private IDs enter planner context or the state projection.

After restart, expiry, eviction or a mismatched ID, v13 asks for context in the language
identified from the current utterance; it does not execute a guessed continuation.
Multiple workers/replicas require sticky routing or a reviewed shared state store;
without that, a different worker asks for context. Redis is not added for this feature.

The new frontend can also use opaque IDs with v11/v12. Admin translates its own bounded
state into their existing context contracts. Their old semantic request contracts are
still accepted by the backend for rollback clients. Older legacy/v9/v10 paths continue
as independent requests. Switching contracts never automatically retries another version.

## Answers and frontend

`project_answer_facts` explicitly selects counts, totals, displayed group labels/values,
ordering and clarification labels. It never serializes source records. Deterministic
DE/DA/EN templates generate `answer_text` and small wording variants, preserve names,
mark semantic results as incomplete and qualify rankings as displayed data. Ties are
not described as a unique winner. No qualitative or causal conclusions are invented.

“nochmal” re-renders the last safe facts. “kannst du das einfacher erklären?” uses the
same concise fact wording. “warum?” describes the result and explicitly avoids inferring
causes. Without stored facts, these acts ask what the user means. Help uses a closed
capability description. Ambiguity verbalizes actual returned candidate labels while the
structured clarification remains authoritative. Optional follow-up suggestions are not
introduced in this first implementation.

The frontend renders conversation responses as ordinary assistant text, without an
unsupported card or “Frage präzisieren” block. Research results keep their structured
views. Browser code no longer assembles summaries, merges filters or rewrites questions
around selected clarification labels: it submits the selected label as current text and
lets the Planner use backend-owned pending semantics. No text classifier or answer
renderer is added to the frontend. IDs stay in component memory, never URLs or storage.

## Capability and acceptance limits

All v12 execution paths remain. Planner-supported constraints that Admin still cannot
execute, such as price filtering, return a natural unsupported clarification rather than
silently broadening the selection. “und kostenlos?” is interpreted with its price
constraint, but does not pretend that filtering ran. Visible-result identities/subsets
still require context; the system does not invent IDs. There is no next-page cursor:
“more” can increase a smaller result limit to 20, otherwise it must clarify.

Structural/provider failures retain safe 502/503 boundaries and no fallback. Semantic
uncertainty is represented as a valid conversation or clarification. Diagnostics include
only `interaction_kind`, `validation_stage` and existing safe operational fields, never
query text, model output, state, SQL, coordinates or credentials.

Unit tests cover routing before execution, state survival, corrected plan execution,
language, privacy, ID ownership/expiry/capacity, safe facts, schema parity and frontend
rendering. They use mocked provider/SQL results and do not prove live NLP or PostGIS
behavior. Live acceptance is opt-in in the Planner repository:

```sh
RESEARCH_PLANNER_LIVE_TEST=1 uv run pytest -q tests/test_research_v13_live.py
```

Rollout order: deploy Planner → deploy Admin → run live acceptance → explicitly set
`RESEARCH_PLANNER_CONTRACT=v13`. Keep `legacy`, `v9`, `v10`, `v11`, `v12` for rollback.
No Docker, deployment or merge is part of this change.
