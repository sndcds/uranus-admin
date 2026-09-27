# Operating the event retrieval pilot

The [experimental Research UI search](semantic-search-pilot.md) is disabled until
its noncommercial acknowledgment and vector settings are configured in the API
runtime. There is no chat endpoint. Indexing commands remain explicit operator jobs. Never run source fixtures, migrations or reconciliation against an arbitrary
collection. Do not install model weights on Server A or send its DB credentials to B.

## Server B installation

Prerequisites: reviewed existing Docker/Compose, nginx, nftables, valid existing
`nominatim.oklabflensburg.de` certificate, AMD64 CPU, sufficient RAM/disk. Inspect
existing services, listeners and firewall first. The checked-in installer is specific
to the approved A/B topology, not a generic bootstrap for unknown servers.

From a reviewed checkout on B:

```sh
sudo deploy/research-ai/install.sh
sudo docker compose -f deploy/research-ai/compose.yml build encoder
# Run one prefetch at a time. No HF token is required for these public pinned models.
sudo docker run --rm --cpus=1 --memory=1g --memory-swap=1g \
  -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 -v /srv/models:/models \
  uranus-research-encoder:pilot python prefetch.py e5-small
# Repeat with e5-base; Jina additionally requires --noncommercial-jina.
sudo docker compose -f deploy/research-ai/compose.yml up -d --no-build
```

`install.sh` refuses existing dedicated configuration rather than replacing it. It
creates `/srv/qdrant/storage`, `/srv/qdrant/snapshots`, `/srv/models`, protected keys
under `/etc/uranus-research-ai`, its own firewall service and a separate nginx snippet.
It validates nginx before reload. Existing firewall tables, Nominatim configuration,
PostgreSQL, OneUptime and Server A's active release are not modified.

The encoder image is built from digest-pinned Python/uv bases and `backend/uv.lock`.
The optional `embedding` dependency group is **not** installed by normal backend
`uv sync`; it uses CPU Torch, no CUDA packages. Qdrant is digest-pinned v1.19.1.
Use `docker compose config --quiet`; do not print secret configuration or docker
inspect environment values. Keys live in mounted protected files, not compose text.

The nftables service is enabled at boot. If manually changing/reapplying its rules,
replace only the `inet uranus_research_ai` table in one atomic nft transaction;
never flush the host/Docker ruleset. The nginx IP allowlist and API authentication
remain independent defenses. Check the guard after firewall maintenance/reboot.

For a code update, rebuild and recreate only `encoder`. Do not restart a model
service while an indexing job is running. There is no automatic production deployment.
Rollback stops this compose project and removes only its nginx snippet/firewall
service after review; retain storage, snapshots and protected credentials for recovery.

## Server A configuration and commands

The normal CLI runs from `backend/` with existing `DATABASE_URL` (verified reader),
optional restricted `ADMIN_DATABASE_URL`, source/event timezone settings and:

```dotenv
QDRANT_URL=https://nominatim.oklabflensburg.de:7443
QDRANT_API_KEY=<protected-service-key>
QDRANT_TIMEOUT_SECONDS=30
QDRANT_COLLECTION_PREFIX=uranus_bench
EMBEDDING_URL=https://nominatim.oklabflensburg.de:7444
EMBEDDING_API_KEY=<different-protected-service-key>
EMBEDDING_TIMEOUT_SECONDS=600
```

Keys must have at least 32 characters. Origins forbid paths, credentials, query and
fragment; production requires HTTPS. There is no browser config and no public fallback.

`deploy/research-ai/run-indexer.py` is the deployment-specific operator wrapper. It
loads only the required source/admin reader settings from the existing protected
runtime file and vector settings from `/etc/uranus-research-ai/client.env`. Transfer
that client file B→A through authenticated SSH directly into a mode-0600 file. Never
paste keys, use them as command-line arguments, log them or copy private SSH keys.
The wrapper is run with suitable local permission to read these files; the database
role remains read-only regardless of OS user. Do not expose this wrapper over HTTP.

```sh
cd backend
uv sync --locked
uv run python -m app.research.vector_index plan --model e5-small --limit 10
uv run python -m app.research.vector_index sync --model e5-small --limit 10
# Inspect query smoke, then repeat plan/sync with --limit 100, then without --limit.
uv run python -m app.research.vector_index reconcile --model e5-small
uv run python -m app.research.vector_index benchmark --model e5-small \
  --questions ../docs/research-ai/event-retrieval-benchmark.json \
  --output /private/results/e5-small
uv run python -m app.research.vector_index evaluate --judgments /private/pooled-results.json
```

For other models replace the explicit model argument with `e5-base` or
`jina-v3 --noncommercial-jina`. Use a fresh output directory per run (files are
exclusive-create, mode 0600; directories 0700). No secrets or full geometry/text
dumps are logged. `plan` performs source reads, tokenization and index reads only;
it never creates a collection, writes points or computes passage embeddings.

The deployment helper `staged-benchmark.py MODEL --output /private/new-run` runs
plan/sync/query-smoke for 10, 100 and all events, then verifies an unchanged full
reconciliation. It aborts on any failed stage, unexpected counts or non-distinct
Top10 results. It is intended for this corpus of at least ten eligible events.
Use one indexer host and one job at a time; local flock is not a distributed lease.

## Manual pooled relevance review

Run the standard-library-only review tool from the repository root against a fresh
benchmark directory containing one `*/results.json` per model:

```sh
python deploy/research-ai/review-benchmark.py \
  --results-dir /private/results/2026-09-27-review-v2 \
  --output /private/pooled-results.json
```

The checked-in `docs/research-ai/results/2026-09-27/` exports lack `review_excerpt`
and are explicitly rejected. Leave them unchanged; rerun benchmarks with the new
exporter into a new directory, preferably outside Git. Excerpts come only from the
exact winning normalized, allowlisted chunk, truncated to 1200 characters.

The tool pools by `(query_id, entity_id)` across models. Each pair is reviewed once;
different event IDs and different queries remain separate. Query, public event title,
chunk types and distinct winning excerpts are shown, without model names, ranks or
scores. Review order is deterministic and independent of model rankings. Identical
excerpts are collapsed and the E5 `passage: ` prefix is hidden in the display.
Terminal control characters are filtered. No AI or score-based grading occurs.

- `2`: clearly relevant; `1`: partially relevant; `0`: irrelevant.
- `s`: skip this pair for this session; it remains unjudged and returns on resume.
- `q`: save and quit. EOF or Ctrl+C also preserves completed judgments.

Every grade is applied to all model rows for that query/event pair and saved
atomically with mode `0600`, file and directory fsync. The output keeps the original
model/rank/score columns for evaluation, but never shows them during review. Input
files are not changed. Use a separate output file and one reviewer at a time in
operator-owned directories; concurrent reviewers are not coordinated. Symlink
inputs, output files and parent directories are rejected. Temporary files use unique
names and are cleaned up after a failed replacement, preserving the previous output.

Restart the same command to resume. Already judged pairs are skipped; grades must
agree across all model rows and any existing output. Conflicting query texts, event
titles, judgments or invalid rankings abort before prompting. Existing output must
match the complete input rows apart from grades and row order; new or changed runs
require a separate output file so stale judgments are not silently reused.

Limits: 20 result files, 1000 directory entries, 20,000 total rows and 8 MB aggregate
input/output JSON, with bounded individual text fields. Invalid JSON, duplicate JSON
keys, nonfinite numbers, malformed grades and missing excerpts are rejected. An
unjudged pair stays empty; neither skipping nor quitting assigns an automatic zero.

After completing all judgments:

```sh
cd backend
uv run python -m app.research.vector_index evaluate \
  --judgments /private/pooled-results.json
```

The existing evaluator accepts the output directly. It returns `null` for incomplete
judgments and computes pooled relevance metrics only when every row is judged.

## Health, measurements and snapshots

```sh
sudo docker compose -f deploy/research-ai/compose.yml ps
sudo docker stats --no-stream uranus-research-ai-qdrant-1 uranus-research-ai-encoder-1
sudo du -sh /srv/qdrant/storage/collections/* /srv/models
sudo systemctl status uranus-research-ai-guard.service
```

On Server B, a quick local check is:

```sh
curl -fsS http://127.0.0.1:6335/health
curl -fsS http://127.0.0.1:6333/healthz
```

The encoder intentionally has no Swagger UI or root landing page. `GET /docs` may
return 405 and `GET /` returns 404; neither is a readiness test. Authenticated
`POST /embed` accepts `{"model":"e5-base","kind":"query","texts":["Sprachkurse"]}`
and returns one 768-dimensional vector. It does not itself search events. Read the
Bearer key from its protected file inside an operator script, never print it or
place it in a curl command line. HTTP 429 means the single-request encoder is busy;
retry after the active benchmark request completes.

For a complete local curl smoke test on B, read the protected key into curl's
standard-input header stream. The key is neither printed nor passed in curl's
process arguments. Do not enable shell tracing or curl verbose/trace output:

```sh
sudo bash <<'SH'
set +x
set -euo pipefail
printf 'Authorization: Bearer %s\n' \
  "$(cat /etc/uranus-research-ai/embedding.key)" |
curl --silent --show-error --fail-with-body --max-time 600 \
  --request POST --header @- --header 'Content-Type: application/json' \
  --data '{"model":"e5-base","kind":"query","texts":["kostenlose Veranstaltungen für Familien"]}' \
  http://127.0.0.1:6335/embed
printf '\n'
SH
```

Run this after an active benchmark finishes: switching the loaded model introduces
extra load and would contaminate timing measurements. The response is an embedding,
not an event search result.

Docker checks local `/healthz` (Qdrant) and `/health` (encoder). Encoder reports a
bounded failure counter; container restart resets it. A health check proves process
liveness, not that a given model is cached/loaded. Indexer dry-run and smoke establish
end-to-end readiness separately. Qdrant API requires a key; embedding writes require
Bearer auth. Confirm HTTP 401 without keys from A, blocked 7443/7444 from elsewhere,
and no public raw 6333/6334/6335. Nginx access logging is off for these listeners;
Docker logs rotate at 3 × 10 MiB. No query/prose logging is enabled.

OneUptime can later monitor these checks from A or local B; no anonymous internet
health endpoint or new external monitor is created by this pilot.

Qdrant snapshots use the authenticated `POST /collections/{collection}/snapshots`
API (server-side `/srv/qdrant/snapshots`). Use the existing configured client in an
operator Python session; never put the API key in shell history. Only snapshot this
pilot's known collections. Copy snapshot files with protected filesystem permissions
if off-host retention is needed. No schedule/retention deletion is enabled by default.
Qdrant is rebuildable: preserve reviewed code, dependency lock, model revisions,
question set and benchmark artifacts. A full reconciliation can rebuild an empty
pilot collection from Uranus without any source changes.

## Known live limitations

The observed Server A release has migration 0015 and no imported area table. Area
metadata is therefore unavailable in these live payloads; the PostGIS assignment
path exists and is tested, but enabling live municipality context requires a separately
reviewed admin deployment/import. The existing application is intentionally left running.

`modified_at` is not a complete change feed. The pilot scans a bounded full source
snapshot and reuses embeddings by exact content hash, rather than claiming a reliable
watermark. No online publication isolation, distributed sync locking, production SLA,
preferences, watches, notifications or LLM is included.
