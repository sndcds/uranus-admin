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
3. Query up to **50 chunks** from `uranus_bench_events_jina_v3` (or the explicitly
   configured prefix). Validate ownership, stable UUIDs, model/document versions
   and finite scores. Reuse `deduplicate()`, retaining the best chunk per event and
   a deterministic UUID tie-break. Its benchmark default remains ten events; online
   retrieval retains up to 50 distinct candidates for subsequent filtering.
4. Only then acquire a PostgreSQL reader and its READ ONLY / REPEATABLE READ
   snapshot. Reuse `repositories/research.py` public projections, date visibility,
   effective venue/space inheritance and category labels. The UUID candidate array
   is bound in SQL, including inside event/date filtering.
5. Apply structured filters in PostgreSQL, retain semantic order, and return at
   most **20 current events** through the unchanged `ResearchPage` / `ResearchRecord`
   response. `page_size` can reduce the bound; only page 1 exists. Counts describe
   the returned limited selection, not the entire source corpus.

Qdrant supplies identity and ranking only. Deleted, draft/private parents and events
whose remaining dates are not public are removed, even if still indexed. A public
event without dates follows the existing Research eligibility rules. Names,
descriptions, categories, organizations, effective venues/spaces, dates, coordinates
and images are loaded from current PostgreSQL records. No Qdrant prose is rendered.

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

The existing pilot/gateway still retrieves bounded candidates before source
filtering. Selected boundaries are resolved together and unioned, then checked
against current authoritative points during the unchanged public rehydration.
This does not switch the endpoint to the newer semantic collections, add venue or
organization API retrieval, or change embedding, ranking or score behavior.
The internal semantic collection transport and evidence checks support OR filters
for events/venues (`area_ids`) and organizations (`home_area_ids` or
`activity_area_ids`, selected by an explicit `organization_mode`).

No UI multi-select, location-name resolution or natural-language parsing is added.
No index rebuild, database migration, grant change or worker change is required.

## UI behavior and limitations

Existing `ResearchFilters`, `ResearchResult`, map/table/list views, dossier links,
selection previews and permalinks are reused. The event-only scope and experimental
status are explicit. Scores are neither returned nor displayed, including as percentages.
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
can lag source edits, affecting rank; rehydration guarantees current displayed facts
and eligibility at the source snapshot, not current semantic relevance or a complete
index publication. There is no relevance threshold or quality/SLA promise.

## Configuration, license and operations

### Combined search service

The operator confirmed on 2026-09-27 that `https://search.kulturbytes.de/search`
uses fixed **Jina v3 and events**. To use that existing service instead of the direct
Encoder/Qdrant transport, set these server-only values:

```dotenv
SEMANTIC_SEARCH_URL=https://search.kulturbytes.de/search
SEMANTIC_SEARCH_NONCOMMERCIAL_JINA=true
```

For local development, add these values to the ignored `backend/.env` and restart
the backend process: settings are loaded at application startup. An already running
process does not automatically reread `.env`. Missing configuration or the absent
noncommercial acknowledgment produces the safe `research_semantic_unavailable`
(HTTP 503) response. Never commit the local `.env` or print its other values.

The backend sends `POST {"query": "…", "limit": 10}` over verified HTTPS.
The service accepted ten candidates in live verification; limits 20 and 50 returned
HTTP 422. Therefore this path has **at most ten candidates before filtering**, and
may return fewer after PostgreSQL eligibility/structured filters. It cannot provide
the direct path's 50-chunk overfetch. No extra requests attempt to fill the result
set. The gateway does not expose its internal chunk limit or index/version metadata;
those properties depend on its operator-managed implementation, not this adapter.

Responses must contain a bounded `results` array of UUID `entity_id` and finite
numeric `score`, with a matching `count`. Defensive best-score deduplication and a
UUID tie-break preserve deterministic ranking. The returned `status` is ignored:
all candidates go through exactly the same current PostgreSQL eligibility checks,
filters and record projections as the direct path. No provider fields reach the UI.

The configured endpoint must be an exact HTTPS `/search` URL without credentials,
query parameters or fragments. Admin authorization remains mandatory. No admin
credentials, vector keys, cookies or CSRF headers are forwarded to this externally
reachable service, which currently accepts requests without authentication. The
query text leaves the admin backend for that explicitly configured service; operators
must keep query/body logging disabled there as well. Browser traffic still uses the
same-origin Research proxy. Response bodies are limited to 64 KiB, the network
timeout is six seconds, and the existing eight-second overall deadline still applies.
Redirects and environment proxies are disabled. Failures use the same safe error;
there is no automatic fallback or additional direct-vector request.
Live verification also observed HTTP 429 for a series of rapid requests. Upstream
rate limiting uses the same safe unavailable state, without automatic retries or
polling. Since requests originate from the admin backend, limits may be shared by
multiple journalists; no upstream quota or capacity guarantee has been established.

The license acknowledgment remains required. Direct vector credentials are not
needed when this URL is configured; when absent, the original Encoder/Qdrant path
below remains available. No production runtime configuration or deployment is changed by
adding this option.

### Direct Encoder/Qdrant transport

Reuse server-only `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_TIMEOUT_SECONDS`,
`QDRANT_COLLECTION_PREFIX` (default `uranus_bench`), `EMBEDDING_URL`,
`EMBEDDING_API_KEY`, `EMBEDDING_TIMEOUT_SECONDS`. Additionally, the API runtime
requires an explicit operator acknowledgment:

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
travels to the configured encoder or search gateway and appears in the user's explicit search
URL/permalink, as classic Research queries do. Application/proxy logging must continue
to omit raw URLs/query strings. No query text, vectors, event descriptions, provider
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

The combined service was also measured on **2026-09-27** from the local backend,
using its configured source reader after verifying effective read-only privileges.
One warm-up was excluded. Ten varied German queries completed sequentially with
seven seconds between requests after the earlier rapid sequence encountered HTTP 429. Those idle gaps are excluded from timings. PostgreSQL returned 8–10 eligible
events per query from the ten supplied candidates.

| Stage                   |    Median | p95 (nearest rank, 10 samples) |
| ----------------------- | --------: | -----------------------------: |
| Combined search service | 784.67 ms |                    1,311.56 ms |
| PostgreSQL rehydration  |  13.12 ms |                       21.25 ms |
| Total service           | 796.19 ms |                    1,329.67 ms |

Separate embedding/Qdrant durations are unavailable for this API. These measurements
again exclude browser/Nitro/auth overhead and establish neither upstream quota nor
an SLA. No source writes, index changes or production deployment were performed.
