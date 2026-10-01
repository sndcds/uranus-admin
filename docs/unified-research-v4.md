# Unified Research v4: exact metrics and project evidence

`POST /api/v1/research/v4/query` accepts only `{"query":"…"}`. It is disabled by
`RESEARCH_DOMAIN_ENABLED=false` by default. When enabled, Admin calls the planner's
`/v4/plan`, validates its closed domain contract and dispatches on the server.
The planner is a model-backed natural-language interpreter: it returns plans only,
never facts. Admin is the exact executor/router; the knowledge service supplies
project evidence. Admin accepts only `schema_version=research-query-plan-v4` and
`interpreter_version=research-domain-planner-v2`, mirrored from merged Planner PR #12 at
`48831449947520ce3a42c465d0e0357c4316c823`. Mixed interpreter versions fail closed;
there is no legacy dual-read or response repair. Provider-internal `DomainProposal`
and `ProviderDataDecision` are not Admin contracts. The final Planner change preserves
constraints internally; its generated public JSON Schema is identical to the previous
pin and remains `PlanEnvelopeV4` → `DataPlan | KnowledgePlan`. Neither
`has_temporal_constraint` nor `has_other_constraint` is an Admin wire field.
The browser cannot submit a plan, executor, collection, model or repository selector.
Existing `/research/query`, Research UI and planner v3 behavior remain unchanged.

- `data`: Admin's existing read-only PostgreSQL connection and complete public
  Research population, including occurrence location inheritance and area resolution.
- `project_knowledge`: authenticated `uranus-research-knowledge /evidence-answer`.
  No source DB connection is opened for this path. Evidence payloads, hashes,
  source links, supported facts and commit lists are validated before returning them.

Configuration uses the existing planner URL/key, plus optional
`RESEARCH_KNOWLEDGE_URL=http://127.0.0.1:6336` and
`RESEARCH_KNOWLEDGE_API_KEY` (32–512 printable characters). Both knowledge fields must
be set together. Loopback services can use a separately provisioned encrypted tunnel.
No encoder change, new database role, migration or deployment is included.
Knowledge receives no production database credentials or browser session credentials.

## Executable public metric contract

Only these six entity/metric pairs are accepted in `DataPlan`:

| Entity       | Metric                 |
| ------------ | ---------------------- |
| event        | description_characters |
| event        | occurrence_count       |
| organization | event_count            |
| organization | venue_count            |
| venue        | occurrence_count       |
| category     | event_count            |

The entity enum contains only event, venue, organization and category. The metric
enum contains only description_characters, occurrence_count, event_count and
venue_count; the pair validator rejects every other combination. Future metrics
and area entities are outside the accepted wire schema. Ordering is asc/desc;
limit is 1–20, default 1. Only **organization/event_count** accepts non-null
`area_query`, for example “Wer veranstaltet in Flensburg am meisten?”. Every other
pair with an area fails validation before execution; no constraint is dropped.
The supported case retains indexed area resolution and exact PostgreSQL/PostGIS
filtering. Jina/Qdrant do not participate in exact metric execution.

Counts are DISTINCT source identifiers, not Qdrant candidate counts.
Category frequency counts distinct public events per category. Venue usage counts
all distinct effective occurrence venues. Ties use source key order (C collation).
Entities with no eligible event activity are absent from these initial rankings.

Longest Veranstaltungstext means event / rank / description_characters / desc / 1.
Use `semantic_documents.public_clean(event.description)` then Python `len`: HTML
hidden content removed, entities decoded, NFC normalized, private contact/unsafe URLs
redacted and whitespace normalized. Unicode code points are counted, including one
for an emoji; this is neither UTF-8 bytes nor grapheme count. Markdown remains literal
text under the existing public projection, not a rendered-Markdown measurement.
NULL becomes empty text. Projection version is `research-public-clean-v1`.

The complete description population is selected in PostgreSQL. Admin computes the
same deterministic public projection before ranking. Before transferring prose, SQL
probes size: >10,000 events or >2,000,000 raw description code points returns an
explicit too-broad error, never a winner from a truncated sample. SQL reads occur in
a read-only repeatable-read snapshot. The conservative raw-text preflight runs
before Python `public_clean()` and can reject a population whose cleaned text
would fit. It cannot return an incorrect ranking from a partial population.
No production schema mutation is needed.

## Answers and acceptance

Data answers return records, the entity/metric/order plan, resolved filters,
observed_at, projection version and `authoritative_source=postgresql`.
Project answers return supported, typed facts, evidence, indexed_commits, a reason
and `authoritative_source=project_sources`. Similarity itself is not factual proof.
Unknown founding date must stay unsupported; the eventual UI can render:
“Ein explizites Gründungsdatum konnte in den indexierten Quellen nicht belegt werden.”

## Knowledge plans and service failures

A successful KnowledgePlan has exactly one supported fact key:
`uranus_overview`, `admin_overview`, `semantic_search_repository`,
`embedding_component`, `embedding_model`, `qdrant_usage`, `encoder_communication`,
`planner_component`, `geocoding`, `architecture`, `founding_date`.
`unknown` is not accepted from the planner; unsupported questions return 422.

`knowledge_query` is nonblank and 1–2000 characters. It must equal the original
user question exactly, including whitespace and case. The planner client and
orchestrator both reject rewritten retrieval text before contacting knowledge.
Admin sends this exact question to authenticated `POST /evidence-answer`.
Fact-key matching, evidence schemas, content hashes, provenance, indexed commits
and `authoritative_source` are validated before returning an answer.
An unsupported founding-date answer stays unsupported; Admin invents no date.

### Public Evidence and excerpt redistribution

Admin mirrors Knowledge PR #1 at
`adcb6b917850b2656fd6145181ad47c3c4d3becd`, using its generated
`contracts/AnswerResponse.json`. The pinned schema fixture is
`backend/tests/fixtures/project_knowledge_answer_schema.json`; the entire generated
Admin schema must match it. This response uses public `Evidence`, never internal
`Chunk`, `Assertion` or `GraphAssertion` payloads. The eleven FactKeys listed above
are also the complete answer vocabulary; `unknown` is rejected.

Evidence preserves `id`, repository/path, pinned commit/source URL, content hash,
line range, license and license-source URL, availability, redistribution permission,
excerpt status and `graph_edge_ids`. Knowledge may withhold source text for licensing
or policy reasons. `chunk_text` is nullable and may be omitted upstream; Admin
serializes missing text as null, never an invented excerpt or empty string.

`excerpt_included=true` requires non-null text and
`evidence_redistribution_allowed=true`. `excerpt_included=false` requires absent/null
text. `supported=true` does **not** require excerpt redistribution: reviewed facts
remain supported by metadata-only evidence. Admin checks every `Fact.evidence_ids`
reference against public `Evidence.id`, rejecting missing or duplicate identities.
It does not require assertion quotes or rederive facts from text.

Admin retains its consumer-side support/reason, indexed-commit and provenance
checks: reviewed repository names, relative paths, pinned GitHub source URLs, line
ordering and SHA formats. Included excerpts must match their SHA-256 content hash;
withheld excerpts retain the digest as metadata without attempting to reconstruct
the source text. Invalid responses fail closed without repair or exposed upstream
error bodies. No public `/query` or graph endpoint is added to Admin, and future
browser rendering must handle withheld excerpts.

Planner requests use the fixed configured URL and service authentication, without
browser credentials or retries. Status mapping:

| Planner outcome               | Admin status / safe error                                               |
| ----------------------------- | ----------------------------------------------------------------------- |
| 200                           | Strict public PlanEnvelopeV4 validation; invalid payloads fail with 502 |
| 422                           | 422 / research_plan_unsupported                                         |
| 502                           | 502 / research_domain_invalid                                           |
| 503, timeout, transport error | 503 / research_domain_unavailable                                       |

Planner response bodies are never exposed as errors.

## Synthetic cross-repository acceptance

`backend/tests/fixtures/research_domain_planner_schema.json` is the public
`PlanEnvelopeV4.model_json_schema()` snapshot generated from the pinned planner
source and its shared Query type. The contract test compares the entire Admin
schema; behavioral tests cover validators that JSON Schema cannot express.
`backend/tests/fixtures/research_domain_acceptance.json` selects upstream golden
questions plus the requested Flensburg variant of the upstream Husum question.
These fixtures are synthetic contract evidence, not live model-quality evidence.

The nine acceptance questions cover both longest-description phrasings,
organization event counts including Flensburg, both semantic-search repository
phrasings, both embedding-producer phrasings and unsupported founding date. Tests
use the real Admin endpoint/client with mocked planner and evidence HTTP responses;
SQL execution and area resolution are mocked in this no-service routing test.
Existing disposable PostgreSQL tests separately verify exact metric execution,
Unicode projection and complete-population bounds; they skip without
`TEST_DATABASE_URL`. No live planner, knowledge, encoder or Qdrant calls are needed.

The separate eight-case companion harness is Knowledge's `integration/` at the
reviewed commit. Run it from Admin `backend/` with read-only Knowledge and merged
Planner source snapshots on `PYTHONPATH`, their dependencies available, and an empty
disposable PostgreSQL/PostGIS database ending in `_test`:

```sh
TEST_DATABASE_URL=postgresql+asyncpg://TEST_USER:TEST_PASSWORD@127.0.0.1:TEST_PORT/knowledge_test \
PYTHONPATH=/snapshot/knowledge/src:/snapshot/planner/src:/checkout/admin/backend \
python -m pytest -q /snapshot/knowledge/integration --override-ini asyncio_mode=auto
```

These eight checks exercise actual ASGI boundaries and exact PostgreSQL longest-text
and organization-count queries; supported semantic-search/embedding facts;
unsupported founding date; metadata-only evidence; eleven-FactKey parity; and
Planner/Admin public-schema parity. Encoder/Qdrant/model responses are synthetic.
Admin's focused suite additionally checks Knowledge public-schema parity and the
excerpt/reference regressions. The harness needs no Docker when a disposable local
PostgreSQL/PostGIS instance is available, and never needs production services.
Verified against the pinned Knowledge and merged Planner revisions above: **8 passed,
0 failed, 0 skipped**, using a disposable local PostgreSQL 17/PostGIS instance.

The new endpoint is API-only in this PR. A separately reviewed browser migration must
add the Nitro allowlist, Zod union and evidence presentation together; do not silently
send v4 results to the existing v3 renderer. Rollout after separate deployment approval:
merge contracts, provision knowledge sources/index and local encoder, verify evidence
revision links, opt server clients into v4, then migrate UI. Disable the flag to roll
back while v3 remains operational. Nothing is deployed by this change.
