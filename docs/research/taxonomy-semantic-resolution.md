# Semantic taxonomy resolution

A lexical taxonomy term follows the existing Research execution pipeline:

```text
Planner taxonomy term (no lookups or IDs)
  -> exact label / typography / conservative German inflection
  -> other hierarchy level exact match (when semantic taxonomy is opted in)
  -> Jina query embedding + dedicated taxonomy Qdrant collection
  -> authoritative PostgreSQL revalidation + measured confidence policy
  -> resolved event_type or composite genre identity
  -> existing InternalResearchPlan / shared SQL executor
```

An exact unique match always wins and never calls an encoder. An exact ambiguity
stays ambiguous; vectors cannot overrule authoritative lexical ambiguity. Category,
venue, organization and area matching are unchanged. A Planner event-type term may
resolve to a genre (and conversely), because that wire field does not establish a
canonical identity. The resolved field records the **actual** level. Explicit type
context still restricts genre search; contradictory parents retain `taxonomy_conflict`.

Taxonomy semantic search maps language to controlled vocabulary. Event semantic
search retrieves relevant content. These are different operations and collections.
A taxonomy match can constrain exact counts, but event top-K never establishes an
exact population. Unresolved taxonomy constraints remain clarifications, including
for list/search: this implementation does not silently replace a Planner hard filter
with free event retrieval. Existing explicit semantic event plans continue unchanged.

## Source and documents

`repositories/research_taxonomy.py` owns the shared `EVENT_TYPES_SQL` / `GENRES_SQL`
projections previously located in the resolver. Their public-event eligibility and
German-first canonical label selection are unchanged. A single bounded source query
reads both levels and their existing localized names from `uranus.event_type`,
`uranus.genre_type`, and `uranus.event_type_link`. Unused/private-only values are not
indexed or authorized. No Uranus writes, migrations or additional HTTP taxonomy source.

The audit found no alias/synonym source in these projections/schema contracts. This
change introduces no curated query alias mapping. Authoritative translated names
supply multilingual lexical context; it does not fabricate English/Danish translations.
A reviewed benchmark target label is a judgment, never an index/document source.

`TaxonomyVectorDocument` contains a stable key (`event_type:<type_id>` or
`genre:<type_id>:<genre_id>`), level, separate source IDs, canonical label/language,
localized labels, parent label and deterministic embedding text. Types include their
public child genre labels; genres include their parent and their translations.
Maximum 4,096 identities, 64 translations per identity, 500 characters per label and
8,000 characters per embedding text; overflow fails closed. The reused encoder
also enforces its existing 480-token passage limit without truncation; an oversized
taxonomy document blocks sync and requires a reviewed document-schema update, not
silent loss of child labels. Stable UUIDv5 point IDs
are transport identities, not Uranus IDs. No events, descriptions, users or locations
are stored in this collection.

The collection is **`kulturbytes_event_taxonomy_jina_v3_v1`**, following the fixed
`kulturbytes_*_jina_v3_v1` semantic collection naming convention. It is separate from
all event/venue/organization collections and the configurable legacy benchmark
prefix. It uses the existing pinned Jina-v3 model, normalized query/passage adapters,
1,024 dimensions and cosine distance. Existing bounded authenticated internal HTTP
transport is reused. Payloads carry owner, document version, embedding model/version
and the complete deterministic corpus digest.

## Confidence is a deployment gate

There are deliberately **no guessed production thresholds**. By default
`RESEARCH_TAXONOMY_POLICY_PATH` is unset, preserving existing exact resolution.
Operators enable the optional semantic step only after reviewing measured benchmark
results and provisioning the resulting local policy JSON. No API or browser can set
this path, thresholds, collection, credentials or model.

The benchmark fixture is `backend/tests/fixtures/taxonomy_benchmark.json` (23 cases).
It proposes type targets for Theater, Schauspiel, Bühne, Theateraufführung and
Bühnenkunst; genre targets for Circus/Zirkus/Zirkustheater and named musical/dramatic
genres. Broad concepts include ambiguous and unresolved judgments. Konzertmusik and
Livemusik are conservative ambiguity cases until reviewed against actual source data.
**These are reviewable expectations, not a claim of live model accuracy.** The
canonical labels and judgments must be confirmed by an operator against the current
source corpus. Missing or duplicate canonical targets block measurement; no IDs are
invented. A term such as Kunst may have an exact canonical match in a real corpus:
that exact match still wins at runtime regardless of the _semantic-only_ benchmark.

The calibration command derives minimum-score and top-two margin thresholds from
observations. It emits a policy only when all reviewed positive, ambiguous and negative
cases meet their expected decisions. If no safe thresholds exist, it fails, requiring
broader benchmark/data/model review rather than quietly lowering confidence. Validate
on additional held-out paraphrases before rollout: a small calibration set is not
statistical evidence of general language accuracy. Unit test scores are synthetic and
are never shipped as an active policy.

At runtime at most six proposals are retrieved, at most five clarification choices
returned. A sufficiently high dominant candidate is accepted. Close plausible
candidates remain ambiguous. A weak top score, or insufficient margin with no second
confident candidate, remains unresolved. Optional kind and type context constrain
retrieval and are checked again on returned candidates. Include contextual cases in
operator acceptance testing when enabling the feature.

All proposals, not only the winner, are checked against a bulk PostgreSQL snapshot.
Current labels, composite identity, parent and full document must agree. Model and
corpus digest must match the policy. Because the vocabulary is small, the complete
bounded Qdrant point inventory is also compared with the source-derived expected
payloads: an interrupted rebuild must not hide a competitor and inflate confidence.
Missing/partial/stale/foreign collections or incompatible dimensions/models fail
closed. The entire semantic attempt has an eight-second deadline. No weak/stale
candidate can authorize an unfiltered source query. A source corpus change requires
sync and renewed calibration, intentionally preferring clarification to stale matches.

## Operator workflow (not run automatically)

From `backend/`, with existing protected reader/encoder/Qdrant configuration and the
existing Jina license acknowledgment `SEMANTIC_SEARCH_NONCOMMERCIAL_JINA=true`:

```sh
uv run python -m app.research.taxonomy_index plan
uv run python -m app.research.taxonomy_index sync
# Force re-embedding all documents without destructive collection replacement:
uv run python -m app.research.taxonomy_index rebuild
uv run python -m app.research.taxonomy_index benchmark \
  --benchmark tests/fixtures/taxonomy_benchmark.json --output /tmp/taxonomy-measured.json
# Only after reviewing canonical targets, scores and acceptance cases:
uv run python -m app.research.taxonomy_index calibrate \
  --reviewed-benchmark --measurements /tmp/taxonomy-measured.json \
  --output /tmp/taxonomy-policy.json
```

Provision the reviewed policy in a protected operator-managed path and set
`RESEARCH_TAXONOMY_POLICY_PATH` to it. Existing `EMBEDDING_URL`/key and `QDRANT_URL`/key
are reused. No secrets are generated, copied or stored in policy/index artifacts.
No per-request lazy indexing or automated production activation. Unset the policy
path to roll back to exact-only behavior; no migration or event-index change needed.

The index CLI uses a separate local single-operator lock, verifies the source role
and READ ONLY snapshot, closes source connections before embeddings, upserts all
changed/new documents before deleting stale points, and reports counts only. Stable
IDs and complete snapshots make reruns idempotent. An empty complete source snapshot
removes stale points. A model/dimension mismatch requires an explicit operator-managed
collection migration; `rebuild` never deletes an incompatible/foreign collection.

## Privacy, responses and observations

Only canonical `ResolutionCandidate` fields reach existing response composition;
vector scores, embedding texts, model payloads and Qdrant point IDs do not. Ambiguous
taxonomy choices use local ordinal display keys rather than database IDs **at the
HTTP response edge only**. Internal resolver/executor results retain authoritative
composite IDs, including ambiguous genre candidates. The response projection copies
candidates without mutating domain results; candidate
buttons still resubmit their canonical label, not an execution ID. Successful resolved
fields retain the existing canonical-ID provenance contract needed for execution.
No new public schema, endpoint, frontend flow or Planner behavior.

Fixed log events count exact hits/ambiguity, semantic acceptance/ambiguity/unresolved,
and stale rejection. They contain no question text, labels, scores, vectors, transcript
or provider errors. Runtime resolution adds no persistence. Index/benchmark artifacts
contain only public vocabulary and operator-supplied benchmark concepts.

## Verification and remaining rollout work

Mocked encoder/Qdrant tests prove the normal API/normalizer/resolver/shared executor
flow for “wo findet theater statt”, “wo findet circus statt”, and “wo findet schauspiel
statt”, cross-level genre filters, ambiguity, low-confidence count refusal and retained
parent conflict checks. Index tests cover deterministic text, translations, stable IDs,
idempotence, stale deletion, interrupted writes and compatibility rejection. A real
PostgreSQL projection test is included and skips without the disposable test database.

Live Jina measurements and domain review have **not** been performed by this change.
Theater/Schauspiel -> Theater & Bühne and Circus/Zirkus -> Zirkus-Theater therefore
remain benchmark expectations, executed only when actual calibrated scores and current
canonical source rows authorize them. No Docker, deployment, model call to Planner or
CI polling is required by the implementation/test workflow.
