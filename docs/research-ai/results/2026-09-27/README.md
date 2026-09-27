# Measured event retrieval pilot — 2026-09-27

All final runs use 576 Research-public events from the same normalized document
snapshot. The source inventory contained 619 events; the public gate excludes the
other 43. Counts and timings below are observations, not a future source contract.

Normalized document SHA-256:
`ad1906cf45628018934f911f627a835d48fd36c8ff39960563520968f22e67da`.

## Final retrieval measurements

| Model    | Final chunks | Queries / exported rows | Mean query latency | P95 query latency | Maximum encoder RSS |
| -------- | -----------: | ----------------------: | -----------------: | ----------------: | ------------------: |
| e5-small |        1,128 |                30 / 300 |            44.5 ms |           49.4 ms |            1.21 GiB |
| e5-base  |        1,128 |                30 / 300 |           117.8 ms |          134.0 ms |            1.72 GiB |
| jina-v3  |        1,124 |                30 / 300 |           460.6 ms |          528.8 ms |            3.85 GiB |

Latency includes query encoding, authenticated TLS transport and Qdrant retrieval.
These are 30 warm queries per model on a shared CPU server, not a production load
test. RSS is the encoder process peak across the recorded stages; model startup
and tokenizer preparation are excluded from embedding duration. Small collections
use exact search (`indexed_vectors_count=0`), with on-disk vectors and payload.

## Indexing stages

| Model    | Stage      | Newly embedded chunks / events | Wall seconds | Encoder CPU seconds | Chunks/second | Events/second |
| -------- | ---------- | -----------------------------: | -----------: | ------------------: | ------------: | ------------: |
| e5-small | sync-10    |                        22 / 10 |         5.79 |               11.08 |         3.800 |         1.727 |
| e5-small | sync-100   |                       164 / 90 |        45.16 |               85.88 |         3.632 |         1.993 |
| e5-small | sync-full  |                      940 / 476 |       235.80 |              444.75 |         3.986 |         2.019 |
| e5-small | price-sync |                        82 / 80 |        13.25 |               24.29 |         6.187 |         6.036 |
| e5-base  | sync-10    |                        22 / 10 |        20.88 |               34.03 |         1.053 |         0.479 |
| e5-base  | sync-100   |                       164 / 90 |       137.97 |              265.79 |         1.189 |         0.652 |
| e5-base  | sync-full  |                      940 / 476 |       666.06 |             1290.18 |         1.411 |         0.715 |
| e5-base  | price-sync |                        82 / 80 |        41.94 |               80.00 |         1.955 |         1.908 |
| jina-v3  | sync-10    |                        22 / 10 |        60.66 |              114.95 |         0.363 |         0.165 |
| jina-v3  | sync-100   |                       164 / 90 |       504.67 |              962.81 |         0.325 |         0.178 |
| jina-v3  | sync-full  |                      938 / 476 |      2648.55 |             5060.02 |         0.354 |         0.180 |

Stages are incremental: `sync-100` adds work after the first 10 events, and
`sync-full` adds the remainder after 100. E5 stages initially indexed 1,126 chunks.
The explicit public presale-fee flag was then included in normalized ticket prose:
`price-sync` embedded 82 replacement/new chunks for 80 events and removed 80 old
chunks, producing the final 1,128 points. Final E5 exports come from that updated
corpus; stage reports preserve the earlier measurements rather than rewriting them.
Jina starts with the final document builder. Its tokenizer yields a different chunk
count from the same normalized prose. Do not compare summed E5 work, which includes
this update, as though it were an identical fresh Jina indexing run.

Repeated complete reconciliation performs zero embeddings, payload updates or
deletions. This verifies idempotency on the live snapshot. Synthetic integration
cases separately cover changed/private/deleted events and missing/stale points.

## Exports and relevance

- **e5-small**: [report](e5-small/report.json), [stage measurements](e5-small/stages.json), [Top10 JSON](e5-small/results.json), [Top10 CSV](e5-small/results.csv).
- **e5-base**: [report](e5-base/report.json), [stage measurements](e5-base/stages.json), [Top10 JSON](e5-base/results.json), [Top10 CSV](e5-base/results.csv).
- **jina-v3**: [report](jina-v3/report.json), [stage measurements](jina-v3/stages.json), [Top10 JSON](jina-v3/results.json), [Top10 CSV](jina-v3/results.csv).

Each export contains 30 queries and ten distinct event IDs per query. The first six
queries cover families/free entry, cultural education, accessibility, registration,
language courses and sustainability. Titles, scores and event identities were
inspected; no relevance grades were inferred from titles alone. `manual_relevance`
remains empty and `quality_metrics` is null. No quality winner or production model
is selected. See the [evaluation protocol](../../benchmark.md) for real manual
judgments and pooled Precision@5/10, MRR@10 and nDCG@10.

Cross-language hits by declared source language (unknown labels remain unknown):

| Model    | DE queries → DA events | DA queries → DE events | EN queries → DE/DA events |
| -------- | ---------------------: | ---------------------: | ------------------------: |
| e5-small |                      3 |                      7 |                        35 |
| e5-base  |                      2 |                     11 |                        28 |
| jina-v3  |                     11 |                     27 |                        29 |

These counts are query/event rows, not unique events or quality scores. There are
20 DE, five DA and five EN questions. The source has 348 DE, 34 DA, three EN and
191 unknown-language public events. Cross-language retrieval exists in these
exports; relevance still requires review.

## Scope and reproducibility

- Functional indexer/service source: commit `e0b256b1789606b93f23782d9b6cfc5908dff8e9`; subsequent changes only publish reports/operator documentation.
- Versions, source timestamps, collection settings and corpus/query fingerprints are in each report. Model/license pins are in the [benchmark protocol](../../benchmark.md).
- Jina uses the official native `jinaai/jina-embeddings-v3-hf` conversion, CC-BY-NC-4.0, for the explicitly authorized noncommercial benchmark.
- Live Server A remains on its existing admin migration `0015`; `research_area` is absent. Area assignment is therefore explicitly unavailable in these live exports. PostGIS assignment is implemented and covered by isolated integration tests.
- `sync` and `reconcile` compare a full bounded public snapshot and reuse hashes; there is no unreliable event-only timestamp watermark.
- The pilot adds no public search endpoint, LLM, source mutation, source schema change or automatic publishing.
- The authoritative live operator artifacts remain under `/var/lib/uranus-research-ai/results/final-v2` on A. Checked-in CSV line endings are normalized to LF; values are unchanged.

## Infrastructure measurements

| Collection | Allocated storage | Apparent storage (includes sparse WAL) |
| ---------- | ----------------: | -------------------------------------: |
| e5_small   |          6.76 MiB |                             196.10 MiB |
| e5_base    |         10.18 MiB |                             196.10 MiB |
| jina_v3    |         11.92 MiB |                             196.10 MiB |

The shared pinned model cache occupies 2.60 GiB. Collection storage includes payload, indexes and WAL; it is not a pure vector-size measurement.

[Final infrastructure snapshot](infrastructure.json) records image IDs, resource ceilings, health, firewall state and host memory. [During-indexing snapshot](infrastructure-during-indexing.json) records the same measurements while Jina was active; its point storage was still incomplete.

Qdrant remains running with persisted collections. The encoder was restarted after the completed benchmark to unload model weights; it remains healthy and reloads cached weights on the next authenticated request. Existing services were not restarted.

One authenticated snapshot was created for each of the three completed pilot
collections; [names, sizes and checksums](snapshots.json) are recorded. These reside
under `/srv/qdrant/snapshots` on B. Snapshot creation was verified; a destructive
restore test was not performed on the live collections.

## Verification

The functional code at `e0b256b1789606b93f23782d9b6cfc5908dff8e9` passed the
[PR CI run](https://github.com/sndcds/uranus-admin/actions/runs/36310512815).
Subsequent commits publish measured artifacts and documentation only. The 20
functional source/deployment files on both A and B were compared by SHA-256 with
the local checkout: all match the [recorded hashes](source-files.json).

| Command / check                                                                                                                                               | Result                                                           |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `cd backend && uv sync --locked`                                                                                                                              | Passed in CI; embedding weights are not downloaded by unit tests |
| `uv run ruff check .`                                                                                                                                         | Passed                                                           |
| `uv run ruff format --check .`                                                                                                                                | Passed                                                           |
| `uv run mypy`                                                                                                                                                 | Passed, 186 source files                                         |
| `TEST_DATABASE_URL=<disposable PostGIS> TEST_QDRANT_URL=<isolated Qdrant> uv run pytest -q`                                                                   | CI: 2,132 passed, 3 skipped, 110 warnings                        |
| `uv run pytest -q tests/test_database_docs.py::test_generator_creates_all_artifacts_offline tests/test_database_docs.py::test_cli_selection_and_skip_options` | The three Graphviz-dependent CI skips passed locally             |
| `TEST_DATABASE_URL=<disposable PostGIS> TEST_QDRANT_URL=http://127.0.0.1:56333 uv run pytest -q tests/test_vector_index.py`                                   | 39 passed, no skips; real PostGIS and Qdrant                     |
| `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm typecheck`, `pnpm build`                                                                                 | Passed in CI                                                     |
| `pnpm test`                                                                                                                                                   | 64 files, 881 tests passed                                       |
| `TEST_PRODUCTION=1 pnpm test:e2e`                                                                                                                             | 553 passed, 41 skipped viewport-specific variants                |
| Deployment checks                                                                                                                                             | All three isolated PostgreSQL/PostGIS matrices passed            |
| Security                                                                                                                                                      | CodeQL Python/JS and Dependency review passed                    |
| Documentation                                                                                                                                                 | Prettier, local relative links and `git diff --check` passed     |

The three CI backend skips are existing Graphviz rendering tests; no vector,
PostGIS or Qdrant test was skipped. The E2E skips are existing explicit viewport
matrix/desktop-only conditions, not backend integration evidence.

Live checks: both authenticated TLS APIs return 401 without keys from A; raw ports
6333/6334/6335 and restricted TLS ports 7443/7444 are unreachable from an outside
host. Both container healthchecks pass. The independent firewall guard is enabled;
nginx/PostgreSQL and existing OneUptime containers remain running. A still points
to release `8a11d2deedb5f6f3751200fb21877efbc94960bb`.
