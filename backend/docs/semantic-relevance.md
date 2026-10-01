# Online semantic relevance policy

Public eligibility alone does not establish semantic relevance. A long tail of weak
similarity matches can make an otherwise valid event selection misleading. The shared
online semantic pipeline therefore applies a conservative relevance gate, centrally
owned by `app/research/semantic_limits.py`. It is not browser configurable.

For the highest **final context-valid event score** B:

```text
threshold = max(0.10, B * 0.40)
keep candidate iff candidate.semantic.score >= threshold
```

`SEMANTIC_ABSOLUTE_MIN_SCORE = 0.10` removes very weak sets even if their best result
is weak. `SEMANTIC_RELATIVE_MIN_RATIO = 0.40` additionally removes the low tail relative
to the strongest valid result. These are initial empirical policy candidates selected
from the reported score series and made reviewable in synthetic offline cases; they
are not universally optimal or independently calibrated across real queries. Similarity
scores are not probabilities or percentages. The gate cannot guarantee relevance,
accessibility, free admission, or any other factual property by score alone.

For the reported production-like series `[0.275, 0.231, 0.174, 0.103, 0.058]`, the
threshold is approximately `0.11`, leaving `[0.275, 0.231, 0.174]`. If the best score
is `0.07`, the threshold is `0.10` and the selection is empty. No result is forced.
Empty input has no threshold; non-finite scores fail closed. Comparisons and returned
scores are never rounded (normal floating-point arithmetic applies).

## Ordering and scope

1. Retrieve at most 50 Qdrant chunks and validate them in `semantic_hits()`.
2. Rehydrate using authoritative PostgreSQL eligibility and occurrence selection.
3. Run `contextualize_event_hit()` for every rehydrated event. Its actually valid
   winning chunk supplies the event score. A raw 0.40 chunk for the wrong occurrence
   cannot rescue a valid 0.08 fallback or raise the relative threshold for other events.
4. Compute the threshold from all remaining final scores and filter.
5. Sort score DESC with the existing UUID tie-breaker, then apply `page_size`.

This applies to the shared semantic GET and planner-driven semantic record paths.
Structured lists and exact counts, aggregates and comparisons are unchanged. Public
response schemas, public/date/area eligibility, and semantic evidence checks are unchanged.
`SemanticResearchPage.pagination.total` counts the returned bounded selection after
paging, not the source population or all potentially relevant matches. Planner records
continue to report `total=null` for semantic retrieval.

Answer mode displays “Keine ausreichend passenden Veranstaltungen gefunden.” for an
empty semantic selection. Classic semantic search retains its existing suitable empty
state. The frontend renders the server selection without filtering or threshold controls.

## Review and observability

The offline [corpus](../tests/fixtures/semantic_relevance_cases.json) contains 24 realistic
German questions with synthetic event descriptions, final scores and explicit relevance
labels (`clearly_relevant`, `borderline`, `irrelevant`) and review rationales. Expected
survivors are checked in tests. Borderline examples deliberately span both sides of the
gate: these labels are qualitative judgments, not score bands. The corpus contains no
production IDs or private data. It is a review artifact, **not** a measured model-quality
benchmark or independent human evaluation. Real-query calibration and any future reranker
remain separate work; no perfect-relevance claim is made.

`research_semantic_search` retains existing timings/counts and adds:

- `pre_threshold_count`: events with context-valid evidence.
- `post_threshold_count`: events surviving the gate, before `page_size`.
- `best_score`: highest final score, or null when there are none.
- `effective_min_score`: applied threshold, or null when there are no final scores.

Only log scores are rounded to six decimals. No query, event title, evidence text,
individual score list or vector is logged. `returned_count` remains the count after
paging. Existing requests with known empty SQL eligibility still short-circuit retrieval.

**No reindex required.** This changes online filtering only. Embedding model/version,
chunking, document versions, Qdrant collection and candidate bound remain unchanged.
No migrations, grants or worker changes are needed. Deployments remain an explicit
operator action; this PR does not deploy anything.
