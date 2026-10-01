# Unified Research v4: exact metrics and project evidence

`POST /api/v1/research/v4/query` accepts only `{"query":"…"}`. It is disabled by
`RESEARCH_DOMAIN_ENABLED=false` by default. When enabled, Admin calls the planner's
new `/v4/plan`, validates its closed domain contract and dispatches on the server.
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

## Closed metric catalogue

| Entity | Catalogue | Executable now |
| --- | --- | --- |
| event | description_characters, description_words, public_text_characters, occurrence_count, duration_minutes | description_characters, occurrence_count |
| venue | event_count, occurrence_count, organization_count, category_count | occurrence_count |
| organization | event_count, occurrence_count, venue_count, area_count, category_count | event_count, venue_count |
| area | event_count, venue_count, organization_count, events_per_capita | none |
| category | event_count | event_count |

Unimplemented catalogue entries fail closed. Future duration/public-text/word metrics
need explicit projections; per-capita metrics additionally need dated population
source evidence. Counts are DISTINCT source identifiers, not Qdrant candidate counts.
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
a read-only repeatable-read snapshot. No production schema mutation is needed.

## Answers and acceptance

Data answers return records, the entity/metric/order plan, resolved filters,
observed_at, projection version and `authoritative_source=postgresql`.
Project answers return supported, typed facts, evidence, indexed_commits, a reason
and `authoritative_source=project_sources`. Similarity itself is not factual proof.
Unknown founding date must stay unsupported; the eventual UI can render:
“Ein explizites Gründungsdatum konnte in den indexierten Quellen nicht belegt werden.”

Required paths tested: longest event text; organization with most events; repository
implementing semantic search; embedding producer; unsupported founding date.
Additional data plans cover venue/event occurrence counts, organization distinct
venues and category frequency. Planner catalogue examples exist in DE/EN/DA.

The new endpoint is API-only in this PR. A separately reviewed browser migration must
add the Nitro allowlist, Zod union and evidence presentation together; do not silently
send v4 results to the existing v3 renderer. Rollout after separate deployment approval:
merge contracts, provision knowledge sources/index and local encoder, verify evidence
revision links, opt server clients into v4, then migrate UI. Disable the flag to roll
back while v3 remains operational. Nothing is deployed by this change.
