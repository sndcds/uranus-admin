# Experimental semantic event search

The Research landing page retains its existing search form and single `q` input.
Classic search is the default. A labelled radio group offers **Semantisch ·
Experimentell** as an explicit opt-in. The existing header search on the results
page supports the same choice; no separate search page/form was introduced.
On the landing page the redundant header input is hidden.

`/research/search?q=...&search_mode=semantic` preserves the selected mode on reload,
history navigation and copied search links. Semantic text is sent only on submit,
Enter or an explicitly applied structured filter, never on each keystroke. The
existing classic header debounce and classic endpoint remain unchanged.

## Retrieval and source authority

`GET /api/v1/research/semantic-search` follows the existing Research GET convention.
The router requires `get_current_research_user`: an authenticated independent account
with journalist **or** system administrator permission. Anonymous requests receive
401; accounts with neither grant receive 403. The admin Research API is not public.

1. Validate a required 2–120 character query containing at least two non-whitespace
   characters. Unknown parameters, model/provider selection and non-event types are
   rejected. The server fixes the model to `jina-v3` and embedding kind to `query`.
2. Use the existing authenticated, fixed-origin Encoder transport on Server B.
3. Query up to **50 chunks** from the fixed event knowledge collection
   `kulturbytes_events_jina_v3_v1` (`event-public-v3`, owner
   `kulturbytes-semantic-search-v1`). Both unstructured and structured event searches
   now use `Qdrant(..., entity="event")`; the former `uranus_bench_events_jina_v3`
   pilot collection is no longer queried by this endpoint. `semantic_hits()` validates
   owner, entity type, embedding/document versions, public text, content hash and
   bounded IDs, then ranks events deterministically with UUID tie-breaks.
4. Preserve `SemanticHit` objects, extract their UUIDs, and only then acquire a
   PostgreSQL READ ONLY / REPEATABLE READ snapshot. Reuse the existing public
   projections, date visibility, effective location inheritance and bound SQL filters.
5. For **only** the records returned by PostgreSQL, attach validated evidence by
   `entity_key`. Return a separate `SemanticResearchPage` of `SemanticResearchRecord`
   objects, each with required `semantic`. Keep the original `ResearchPage` and
   `ResearchRecord` unchanged for classic search, details and CSV export. At most
   **20 current events** are returned; `page_size` may reduce that bound. Only page 1
   exists, and counts describe this bounded selection.

Qdrant supplies retrieval candidates and indexed public evidence. PostgreSQL remains
solely authoritative for current public eligibility, structured filters, deletion,
public/draft state and displayed record fields. Discarded candidates contribute
neither records nor evidence. Indexed evidence may lag source edits: the hash proves
consistency with the indexed chunk, not freshness against the current source text.
Names, descriptions, categories, organizations, locations, dates and images in the
record itself continue to come from PostgreSQL.

### “Warum passt das?”: evidence, not model reasoning

**„Warum passt das?“ ist Evidence, keine Modellbegründung und keine Chain-of-Thought.**
The explanation consists of the deterministic label/reason for the winning chunk
kind, that actually indexed public winning chunk, and optional validated supporting
chunks. No LLM generates or paraphrases a reason, no query text is interpolated, and
no quality judgment is produced. The central mapping is
[`semantic_explanations.py`](../../backend/app/research/semantic_explanations.py).

`semantic.score` preserves the entity similarity score without API rounding.
`matched_aspect`, `matched_aspect_label` and `reason` describe the winning kind;
`evidence` and `supporting_evidence` expose only `kind`, `label`, `text`. No arbitrary
payload, contact fields, internal notes or supporting scores are returned. The
existing `semantic_hits()` default stays at two supporting chunks (internal and
response contract maximum: three), with distinct kinds and text hashes.
Owner/version mismatches are discarded; unsafe text or a mismatching hash fails
closed with a safe unavailable response. Existing privacy checks are reused.

`area_id`, `from_date`, `to_date`, `city`, `category`, `status`, `organization_id`
and `venue_id` retain existing Research semantics. Filters restrict the candidate
selection; they do not change the embedding or infer criteria from the text.
A phrase mentioning Flensburg or “next week” remains semantic text. No municipality,
period, price or other constraint is automatically extracted.

### Multiple Research Areas

The event-only endpoint also accepts repeated `area_ids` UUID query parameters.
Areas are **ORed**: an event qualifies when a current public occurrence matches
any selected area (and the other structured filters). For example, substitute the
persisted Research Area UUIDs for Flensburg, Aabenraa and Sønderborg:

```text
/api/v1/research/semantic-search?q=Kultur&area_ids=<flensburg>&area_ids=<aabenraa>&area_ids=<sonderborg>
```

The query text parameter remains `q`. Existing `area_id=<uuid>` callers keep their
single-area behavior. Supply either `area_id` or `area_ids`, never both. A list must
contain 1–50 UUID entries; duplicates are removed. An empty or invalid UUID value,
an oversized list or mixed parameter forms return 422. Every requested area must
exist; an unknown ID returns 404 even if retrieval has no candidates. Known areas
with no matching events return an empty successful result.

Requests with `area_ids` use the typed event collection and apply the OR filter
before the candidate limit, as described in [structured filters](#structured-genre-and-area-filters).
Selected boundaries are resolved together and unioned, then checked against current
authoritative points during public rehydration. The existing single `area_id` path
remains compatible. Embedding, ranking and event-only response handling stay unchanged.
The internal semantic collection transport and evidence checks also support OR
filters for venues (`area_ids`) and organizations (`home_area_ids` or
`activity_area_ids`, selected by an explicit `organization_mode`).

No UI multi-select, location-name resolution or natural-language parsing is added.
No index rebuild, database migration, grant change or worker change is required.

## UI behavior and limitations

Existing `ResearchFilters`, `ResearchResult`, map/table/list views, dossier links,
selection previews and permalinks are reused. The event-only scope and experimental
status are explicit. Semantic results show a compact fixed reason and an accessible
“Beleg anzeigen” details disclosure for the winning and supporting evidence. Text
wraps and is rendered as plain text, without HTML or Markdown execution. List,
table and selected preview expose the same explanation only in semantic mode.
The small technical “Ähnlichkeit: 0.446” line rounds only for display. Similarity
scores are **not probabilities or relevance percentages**.
The semantic mode hides date/name sorting, pagination and the classic full-result CSV
export, since those controls would misrepresent a bounded semantic selection.

`RequestState` displays “Semantische Suche läuft …”; the existing header submit
button is disabled during retrieval. There is no polling or artificial delay.
Empty results say “Keine passenden Veranstaltungen gefunden.” Configuration, license,
provider, timeout and source failures return a fixed safe error and allow retry or
switching back to classic search. A new semantic request clears previous results;
failed retrieval does not silently fall back to classic search or an empty success.

Candidate retrieval is bounded and may miss otherwise eligible events beyond its
50 chunks, especially with many chunks per event or restrictive filters. Index text
can lag source edits, affecting rank; rehydration guarantees current record fields
and eligibility at the source snapshot, not current semantic relevance or a complete
index publication. There is no relevance threshold or quality/SLA promise.

## Configuration, license and operations

### Candidate-only gateway compatibility

`SEMANTIC_SEARCH_URL` and the tested adapter in `search_gateway.py` are retained,
but the evidence endpoint no longer uses them, even for unstructured queries.
The gateway returns only candidate UUIDs/scores and cannot supply validated chunk
evidence. No pseudo-evidence or gateway-authored reason is accepted. A deployment
configured only with `SEMANTIC_SEARCH_URL` must provide direct Encoder/Qdrant
configuration before this endpoint can work; otherwise it returns the safe 503.

**Follow-up TODO:** if gateway retrieval is needed again, agree a bounded,
versioned evidence contract and pass its chunks through the same
`semantic_evidence.py` owner/version/public-text/hash checks before reuse. Do not
accept free-form `reason` fields. Gateway redirect rejection, fixed HTTPS endpoint,
credential isolation and its existing candidate contract remain unchanged.

### Direct Encoder/Qdrant transport

Reuse server-only `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_TIMEOUT_SECONDS`,
`EMBEDDING_URL`,
`EMBEDDING_API_KEY`, `EMBEDDING_TIMEOUT_SECONDS`. Additionally, the API runtime
requires an explicit operator acknowledgment. The event collection name comes from
the registry; `QDRANT_COLLECTION_PREFIX` applies to legacy benchmarks, not this endpoint:

```dotenv
SEMANTIC_SEARCH_NONCOMMERCIAL_JINA=true
```

This defaults **false** and must only be set for the approved noncommercial pilot.
Jina v3 is **CC-BY-NC-4.0**; this pilot does not establish permission for future
commercial/production use. Existing CLI `--noncommercial-jina` and encoder/prefetch
license gates remain required and unchanged. No model selector or license controls
are exposed to journalists. See [pilot operations](operations.md) for existing
internal transport, credential and model provenance requirements.

The online request adds an eight-second overall deadline, within the existing
ten-second Nitro proxy timeout, while preserving shorter configured provider timeouts.
This is a resource bound, not an SLA. Production origins continue to require HTTPS;
redirects, environment proxies and client-selected endpoints are forbidden.

No migrations, grants, new ports, Server B changes, index synchronization or automatic
deployment are required by this change. A later approved release must supply vector
settings and the acknowledgment to the API process separately; the existing protected
CLI client file is not automatically loaded by the API. Classic search works without
any vector configuration. Missing area storage still fails closed when an area filter
is requested; no runtime schema repair is attempted.

No LLM, Pydantic AI, agent, tool calling, chat, intent interpretation or SQL generation
is involved. There are no Uranus writes or browser secrets. Fixed SQL uses the existing
reader boundary; vector queries never upsert/delete points. Search text necessarily
travels to the configured encoder and appears in the user's explicit search
URL/permalink, as classic Research queries do. Application/proxy logging must continue
to omit raw URLs/query strings. No query text, reasons, chunk text, scores, vectors, event descriptions, provider
response text or credentials enter normal structured logs. No persistent query cache
or browser storage is added.

## Measurements and validation

Structured `research_semantic_search` events contain `embedding_ms`, `qdrant_ms`,
`retrieval_ms`, `postgres_rehydrate_ms`, `total_ms`, `candidate_count`, `returned_count` and a fixed
failure category. Durations include application transport/connection setup; the
PostgreSQL stage includes reader acquisition, area resolution if requested, projection
and images. Failure events retain elapsed time for the failing stage. Unstarted
stages remain zero. No sensitive diagnostics are included in API responses.
For the combined service, embedding and Qdrant durations are **null**, because the
upstream API supplies neither measurement; `retrieval_ms` measures their combined
request. Do not interpret missing stage measurements as zero or compare them with
the individually measured direct-path durations below.

On **2026-09-27**, an isolated temporary copy of the new service ran on Server A,
using the existing Server B pilot and verified least-privilege source reader. One
warm-up was excluded, then ten varied German semantic queries ran sequentially.
No deployed service/configuration, index, source data or Server B infrastructure
was changed. All ten returned 20 current public events.

| Stage                  |    Median | p95 (nearest rank, 10 samples) |
| ---------------------- | --------: | -----------------------------: |
| Embedding              | 658.50 ms |                      760.07 ms |
| Qdrant                 | 267.82 ms |                      271.73 ms |
| PostgreSQL rehydration |  15.75 ms |                       36.40 ms |
| Total service          | 945.07 ms |                    1,040.77 ms |

This supports roughly subsecond warm CPU search as an expectation for the observed
pilot, with this sample's p95 slightly over one second. It excludes browser, Nitro and
HTTP authentication overhead; it is not an endpoint SLA or a commercial-readiness
claim. Live area filtering was not measured. Automated tests use fake internal HTTP
and isolated PostgreSQL/PostGIS; normal frontend CI needs neither Jina nor Qdrant.

The historical candidate-only combined service (no longer used by this endpoint)
was also measured on **2026-09-27** from the local backend,
using its configured source reader after verifying effective read-only privileges.
One warm-up was excluded. Ten varied German queries completed sequentially with
seven seconds between requests after the earlier rapid sequence encountered HTTP 429. Those idle gaps are excluded from timings. PostgreSQL returned 8–10 eligible
events per query from the ten supplied candidates.

| Stage                   |    Median | p95 (nearest rank, 10 samples) |
| ----------------------- | --------: | -----------------------------: |
| Combined search service | 784.67 ms |                    1,311.56 ms |
| PostgreSQL rehydration  |  13.12 ms |                       21.25 ms |
| Total service           | 796.19 ms |                    1,329.67 ms |

Separate embedding/Qdrant durations were unavailable for that historical gateway API. These measurements
again exclude browser/Nitro/auth overhead and establish neither upstream quota nor
an SLA. No source writes, index changes or production deployment were performed.

## Structured genre and area filters

The semantic endpoint additionally accepts repeated `genre_keys` (maximum 50 raw
entries) and repeated `area_ids` (1–50 raw entries). Both lists are validated
and deduplicated. Empty genre lists impose no restriction; explicit empty area lists
are rejected. Genre keys are canonical
`type_id:genre_id` identifiers, not localized names. Genre 0 is excluded.
`area_id` remains the single-area parameter; combining it with `area_ids`
is rejected. Category filtering remains the existing independent `category` filter.

```text
/api/v1/research/semantic-search?q=Live-Musik&area_ids=<flensburg>&genre_keys=<jazz-key>
/api/v1/research/semantic-search?q=Live-Musik&area_ids=<flensburg>&area_ids=<husum>&genre_keys=<jazz-key>&genre_keys=<rock-key>
```

Replace placeholders with persisted area UUIDs and actual composite genre keys.
Locations are **ORed within the area dimension**; genres are **ORed within the genre
dimension**; area and genre dimensions are **ANDed**. Thus `(Flensburg OR Husum)
AND Jazz` excludes Jazz in Kiel and Rock-only events in Husum. Adding Rock to the
genre list admits the Husum event. Mentioning a genre in `q` alone is semantic text,
not an exact filter.

All semantic event requests use `kulturbytes_events_jina_v3_v1` with
`event-public-v3` payloads. Explicit `area_id` / `area_ids` and `genre_keys` become
Qdrant payload filters **before** the 50-chunk candidate limit. The direct
Encoder/Qdrant configuration and license acknowledgment are required regardless of
`SEMANTIC_SEARCH_URL`. There is no legacy collection fallback or request-controlled
collection selection.

After retrieval, PostgreSQL rechecks current genre links, public eligibility,
category and all existing filters. Multiple cached area boundaries are read in one
bounded admin query and unioned for the same source spatial predicate. Qdrant names,
status and genre metadata never establish authorization or public eligibility.
Stale assignments can therefore be removed from results; newly matching records
still require an index refresh to enter the bounded candidate set.

The API client, Zod validation, Nitro repeated-parameter allowlist and generated
OpenAPI support these parameters. No genre-picker UI is introduced. Payload
version/backfill and embedding reuse are described in the
[semantic index contract](semantic-knowledge-index.md#structured-event-genres-event-public-v3).
