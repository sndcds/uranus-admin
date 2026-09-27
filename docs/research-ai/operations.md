# Operating the event retrieval pilot

No production chat/search endpoint is enabled. All commands are explicit operator
jobs. Never run source fixtures, migrations or reconciliation against an arbitrary
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

## Health, measurements and snapshots

```sh
sudo docker compose -f deploy/research-ai/compose.yml ps
sudo docker stats --no-stream uranus-research-ai-qdrant-1 uranus-research-ai-encoder-1
sudo du -sh /srv/qdrant/storage/collections/* /srv/models
sudo systemctl status uranus-research-ai-guard.service
```

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
