# Public event documents and synchronization

## Source projection

`backend/app/repositories/vector_events.py` selects explicit public event fields,
organization names, canonical category labels, deterministic localized type/genre
labels and effective public occurrence locations. An event parent must have a public
Research status (`released`, `cancelled`, `deferred`, `rescheduled`). An event with
dates needs at least one effective-public date; an event without dates remains eligible.
Draft/review parents and private dates are excluded.

Allowed prose includes title/subtitle/summary/description, taxonomy/tags, organizer,
effective venue/space names, imported municipality names, languages, participation,
meeting point, age bounds, public accessibility summaries, price information,
ticket/registration flags and safe public links. HTML becomes plain text; script/style
content, email addresses, UUIDs and credential/query-bearing URLs are removed.
No arbitrary dictionary/JSON serialization is used as embedding input.

Registration email/phone, admin notes/findings, user/session/auth data, private metadata,
custom JSON, external IDs and technical debug fields are not projected. Free-text
source fields are still editorial source content: this is not a general PII classifier.

Event-date venue override stops inherited event-space assignment, exactly as in
`repositories/location.py`. Only public occurrence contexts contribute names and
`venue_ids`, `space_ids`, `area_ids`. Multiple locations are preserved. No definitive
organization headquarters municipality is inferred. Areas use local PostGIS
`ST_Covers`, including boundary points; no Nominatim request occurs during indexing
or retrieval. When area storage is absent, the manifest explicitly reports it.

Dates remain structured context (`first_date`, `next_date`, `last_date`); they are
not separate semantic entities. `next_date` uses existing event-timezone start
semantics. Dates are not used as an implicit upcoming-only retrieval restriction.
Events without occurrences have no occurrence-derived venue/space context.

## Chunks and identity

Short documents produce one chunk. Long documents are divided by content,
participation, accessibility, tickets and additional sections, preferring paragraph
or sentence boundaries. A native model tokenizer counts prefixes and special tokens.
Maximum 480 tokens, overlap up to 64 tokens; no silent tokenizer truncation. This
slightly lowers the requested approximate range to respect E5's 512-token limit.
Section remainders may be shorter. Very long unbroken text uses bounded splits.

E5 passage text includes the literal `passage: ` prefix; queries include `query: `.
Jina uses task-specific retrieval passage/query adapters. SHA-256 is calculated over
exactly the UTF-8 passage text embedded, including the E5 prefix. UUIDv5 point identity
uses event ID + chunk kind + content hash; repeated identical sections deduplicate.
An insertion before an unchanged chunk does not require re-embedding that chunk.

Payload includes index ownership, event identity, chunk index/kind/hash, model/version,
document schema version, source modified timestamp if known, organization ID,
venue/space/area/category IDs, status/language, date context and area availability.
It excludes the full text and title. Current titles are fetched from the public source
snapshot for benchmark exports. Raw UUIDs never enter semantic text.

## Incremental work and reconciliation

The pilot scans a bounded public snapshot (maximum 10,000 events, 100,000 contexts,
64 MiB normalized corpus, 100,000 points). It does **not** trust `modified_at` as a
complete watermark: nullable timestamps and changes to linked venues/taxonomy would
otherwise be missed. Embedding work is incremental by content hash/version.

- New or version-incompatible chunks: embed and upsert.
- Unchanged text but changed metadata: overwrite payload only.
- Identical chunks and metadata: no write and no embedding.
- Removed/private events or stale chunks: delete after successful replacement upserts.

`sync` and `reconcile` deliberately share the same complete comparison in this pilot.
Reconciliation detects missing points, missing/replaced chunks, hashes, model/schema
versions and stale points. An interrupted run is repaired idempotently. There is no
claim of atomic whole-collection publication; a future online endpoint needs a
publication protocol and eligibility recheck.

`--limit 10` / `--limit 100` never deletes other events. Only a successful unlimited
source snapshot authorizes collection-wide stale deletion. Provider/source failures
stop the run. Foreign/unowned points and incompatible collection dimensions fail closed.
A local flock serializes jobs on the designated indexer host; multi-host concurrent
indexers are unsupported. No extra admin state table/migration is needed: stored
payload hashes are the comparison state. Source data is never synchronization state.

Retrieval takes chunk scores, keeps the maximum score per event, and returns the
best ten distinct public events. It expands candidates up to a bounded 10,000 chunks
if duplicates occupy the initial window. Benchmark requires a reconciled snapshot;
it is not a user-facing search API and makes no claim of result completeness beyond
this bound.
