# Multilingual event retrieval benchmark

The versioned [question set](event-retrieval-benchmark.json) contains 30 DE/DA/EN
retrieval probes, including the six requested acceptance queries. These are questions,
not invented ground truth. Cross-language effectiveness depends on actual source
inventory; a Danish question retrieving German content does not establish that
Danish events are present.

## Models and licenses (checked 2026-09-27)

| Requested model                | Dimensions | License      | Pinned weights                                                                      |
| ------------------------------ | ---------: | ------------ | ----------------------------------------------------------------------------------- |
| intfloat/multilingual-e5-small |        384 | MIT          | `614241f622f53c4eeff9890bdc4f31cfecc418b3`                                          |
| intfloat/multilingual-e5-base  |        768 | MIT          | `d128750597153bb5987e10b1c3493a34e5a4502a`                                          |
| jinaai/jina-embeddings-v3      |       1024 | CC-BY-NC-4.0 | native `jinaai/jina-embeddings-v3-hf` at `d18862d9a48706220815554fac3ebb4dfa46fc28` |

Sources: [E5-small card](https://huggingface.co/intfloat/multilingual-e5-small),
[E5-base card](https://huggingface.co/intfloat/multilingual-e5-base),
[Jina original card](https://huggingface.co/jinaai/jina-embeddings-v3),
[Jina native card](https://huggingface.co/jinaai/jina-embeddings-v3-hf).

The original Jina repository was also reviewed at
`ab036b023d30b4d1138c4c3bfa9f0c445ab455d6`. We explicitly use Jina's official native
Transformers conversion, not its original remote-code implementation. Retrieval
query/passage LoRA adapters are pinned from that same native revision. Results are
identified as this implementation, not claimed bit-identical to the remote-code version.

The operator confirmed this benchmark is noncommercial. Jina requires explicit
`--noncommercial-jina` acknowledgment and a corresponding service setting. This is
not permission for commercial production use. No production model winner/default
is selected. Reassess license and deployment requirements before production use.

Runtime: locked CPU PyTorch 2.14.0, Transformers 5.17.0, PEFT; float32 mean pooling,
L2 normalization, cosine similarity, one model at a time, batch 2, two CPU threads.
Model weights are cached on B, never committed. Each model has its own collection:
`uranus_bench_events_e5_small`, `uranus_bench_events_e5_base`,
`uranus_bench_events_jina_v3`.

The live public inventory has language labels: 348 German, 34 Danish, 3 English,
and 191 unknown. Unknown stays unknown; this is not inferred language detection.
Scores from different models are not directly calibrated against one another.

## Protocol and measurements

Start with plan → sync for 10 public events; inspect retrieval and distinct event IDs;
then plan → sync for 100; then plan → sync for the complete eligible snapshot.
Finally repeat plan/reconcile to verify unchanged chunks and run all 30 queries.
Only one model runs at a time. Restarting the encoder between models resets the
process peak-RSS measurement. Prefetch/download time is excluded from embedding time.

Reports contain source snapshot time, document/model versions, model-independent normalized-document fingerprint, model-specific chunk corpus/query hashes,
event/chunk counts, wall/embedding time, events/s, chunks/s, encoder CPU time and
process peak RSS. Query latency includes encoding, TLS transport and Qdrant retrieval.
The normalized-document fingerprint hashes event IDs and normalized sections before
model prefixes/tokenization; it excludes time-dependent date metadata.
Sync timing excludes extraction/chunk preparation; stage timings report only newly
embedded chunks. Peak RSS is the encoder process lifetime maximum, not total host
RAM. Qdrant disk/RAM measurements and actual run results are recorded with the live
benchmark artifacts. Small collections may use exact scans rather than build HNSW.

Export columns: query ID/text/language, source event language (unknown stays null), model, rank, event ID, current public title,
score, winning chunk kind, latency, `manual_relevance`. CSV cells guard formula
prefixes. No document prose, vectors, credentials or internal admin data are exported.

`manual_relevance` is initially empty. Human reviewers can assign 2 (clearly relevant),
1 (partially relevant), 0 (irrelevant), consistently across pooled results. The
`evaluate --judgments pooled-results.json` command refuses to turn unjudged rows into
zeroes. With fully judged input it computes Precision@5, Precision@10, MRR@10 and
nDCG@10. Precision treats grades 1/2 as relevant; nDCG uses graded gain and the
supplied pooled judged events as the ideal ranking. This is a pooled evaluation,
not exhaustive corpus relevance or recall. No winner without real judgments.

See [operations](operations.md) for exact reproducible commands and artifact paths.

## Recorded pilot results

The [2026-09-27 measurements](results/2026-09-27/README.md) contain the model
comparison, stage timings, resource usage, verification results and all Top10
CSV/JSON exports. They distinguish retrieval measurements from still-unjudged
relevance and record the exact document/model provenance.

## Interpreting the pilot

A semantic match for “kostenlos”, “barrierefrei” or “mit Anmeldung” is **not** a
verified structured constraint. Inspect current source fields before making such
claims; a later research planner should combine retrieval with explicit filters.
The first six queries were executed and their Top10 titles/scores/unique identities
inspected, but no title-only relevance grades were invented. Same-title rows can be
different source events; deduplication is by stable event ID, never by title.

Long-event ticket/accessibility chunks do not automatically repeat the event title.
Shared boilerplate can therefore produce identical vectors and tied scores across
different events. Max-score aggregation preserves these hits; the exported winning
chunk kind makes them reviewable. Parent-context repetition or alternative chunk
aggregation would need a separately versioned, measured follow-up, not an assumed
quality improvement applied after this benchmark.
