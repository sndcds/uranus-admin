# Learning Research suggestions

Research learns from successful supported `/api/v1/research/query` executions,
including successful empty results. Failed, invalid, unsupported, plan-only and
clarification responses do not learn. There is no seed catalogue, backfill,
per-keystroke learning, language model call while typing, encoder, Jina or Qdrant
suggestion retrieval. Queries start qualifying after three successful executions.

## Privacy and storage

Migration `0018` adds only admin-owned tables:

- `research_query_history`: successful execution observations; eligible human query
  text, normalized text, known intent/entity/metric, source, optional conversion
  correlation and timestamp. Rejected text is NULL, with `is_eligible=false`.
- `research_query_suggestion`: unique normalized query, latest successful human
  display form, language, indexed token prefixes, four counters, eligibility/block
  flags and first/last use/selection timestamps.
- `research_query_suggestion_event`: append-only impression/selection events,
  opaque request UUID, suggestion UUID, position and timestamp. Only impressions
  retain a privacy-checked normalized prefix.

No user/account IDs, browser fingerprints, session IDs or behavioral profiles are
stored. Planner free-text slots, domain and area are deliberately not retained.
The current planner provides no language value; `und` means unknown, not a language
guess. Retrieval accepts an optional known language and includes unknown-language
rows. A future verified language signal can populate this column.

The deterministic gate rejects email/account identifiers, phone-like numbers,
UUIDs/long opaque IDs, keys/tokens/password markers, URLs/infrastructure addresses,
SSH material, obvious injection/probing and code/SQL syntax, invisible control
characters and input longer than 300 characters. This conservative heuristic can
reject harmless questions and cannot guarantee detection of all personal data.
Rejected input is never copied into learning text columns or logs. Only a redacted
successful observation with enum diagnostics remains. Raw queries and provider
errors are not logged. Explicitly blocked suggestions remain blocked on reuse.

Normalization trims and collapses whitespace, Unicode-casefolds and removes final
sentence punctuation. It does not stem, translate or rewrite grammar. Display text
preserves case and punctuation from the latest successful human wording.

## API and interaction semantics

All endpoints require the existing Research grant (journalist or system admin).
Cookie writes retain exact Origin and `X-Admin-CSRF: 1` checks.

- `GET /api/v1/research/suggestions?q=welche%20org&limit=8`: normalized prefix at
  least two characters, raw prefix at most 120, limit 1–8. Returns `request_id` and
  `{id, query, position}` items. Only eligible, non-blocked rows with at least three
  successes qualify. Request IDs are random UUIDs, unrelated to identity.
- `POST /api/v1/research/suggestions/impression`: `{request_id, prefix,
suggestions: [{id, position}]}`. One to eight distinct IDs/positions, positions
  1–8. Counts each matching eligible request/suggestion pair once.
- `POST /api/v1/research/suggestions/select`: `{request_id, suggestion_id,
position}`. Requires an eligible suggestion and a matching impression less than
  ten minutes old. Counts a selection once and returns its opaque `receipt`.

The normal execution body remains strictly `{"query":"..."}`. The optional
`X-Research-Selection` UUID header carries the receipt only on `/research/query`;
Nitro validates and explicitly forwards it only there. It is not a credential,
is not put in URLs/storage, and cannot authorize query plans or source writes.
Conversion requires successful execution of the same normalized query, a selection
within ten minutes and an unused request/suggestion conversion pair. Replays can
represent new successful executions, but cannot duplicate conversion credit.

Counters and history are updated in one admin transaction. Unique event/conversion
constraints plus consistent suggestion locks prevent duplicate increments under
concurrency. Telemetry failure rolls back its own transaction, logs only a fixed
category and leaves the Research answer usable. Learning has a one-second budget;
under contention/unavailability an observation may be lost. No detached work is used.

## Retrieval and ranking

One PostgreSQL lookup uses an eligible/non-blocked partial GIN index on bounded
word prefixes and literal, escaped text matching. Full-query starts outrank
ordinary token-boundary matches; arbitrary substring fallback is omitted. There
are no source indexes or new extensions. Results sort by score descending, then
normalized text in C collation and UUID for deterministic ties.

Readable server constants define this score (natural logarithms):

```text
100 * starts_with_prefix
+ 3 * ln(success_count + 1)
+ 1 * ln(suggestion_selections + 1)
+ 5 * ln(successful_selections + 1)
+ 4 / (1 + age_in_days / 30)
+ 2 * min(1, (suggestion_selections + 2) / (suggestion_impressions + 10))
```

Age is time since the last successful use, clamped to zero. Conversion carries
more weight than a click; smoothed CTR is bounded to two points. No numeric score
is exposed to the browser. Frequencies count executions, not distinct people.

## UI

The question textarea requests at most eight suggestions after 200 ms of focused
input, with cancellation and generation checks. It reports an impression once
only after the current results render. Escape, blur, navigation, auth changes and
unmount clear pending work/results. Arrow keys change the active option; Enter
selects it. Pointer/touch selection keeps input focus. The list overlays the form
and uses combobox/listbox ARIA semantics.

Selection waits for the bounded impression/selection calls (two seconds each) and submits through
the existing Research flow. Telemetry failure still allows execution. The receipt
is used once in component memory. The neutral explanatory text makes no claim of
personalization. Existing explicitly shareable question links remain unchanged.

## Operations and follow-ups

Before deploying compatible API/frontend builds, migrate using the explicitly
selected migrator and provision current `RUNTIME_GRANTS`: SELECT/INSERT on history
and events; SELECT/INSERT/UPDATE on suggestions. No runtime DELETE or schema/source
write grants. Readiness enforces the new head/grants; runtime never self-provisions.
The Ansible release manifest derives runtime grants from this same mapping.
Upgrade contracts target `0018` and exclude the three new tables at earlier
supported origins; the `0017` inventory fingerprint is verified from committed
source (its constraint-only change retained the `0016` inventory).
Downgrade drops these three learning tables and their data; existing Research data
is untouched. No backfill, deployment or worker changes are needed by this PR.

A compact system-admin-only diagnostics view (eligible totals, top suggestions and
four counters/last use), moderation UI, operator retention policy and learned
language metadata are follow-ups. Until then, authorized database operators can
inspect/block rows; Research users have no block or arbitrary-update endpoint.
Semantic suggestion retrieval is explicitly outside this implementation.

PostgreSQL migration, counter, deduplication and receipt tests run in GitHub CI
against the existing disposable database. Local checks use only non-Docker units.
