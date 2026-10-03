"""Operator-only taxonomy snapshot indexing; separate lifecycle from event documents."""

import argparse
import asyncio
import fcntl
import json
import logging
import os
from contextlib import AsyncExitStack
from pathlib import Path

from sqlalchemy import text

from app.config import Settings
from app.database import create_engine
from app.logging import configure_logging
from app.repositories.research_taxonomy import load_taxonomy
from app.research.taxonomy import TaxonomyVectorDocument, corpus_hash, documents, index_payload
from app.research.taxonomy_transport import TaxonomyQdrant
from app.research.vector_index import SOURCE_BOUNDARY
from app.research.vector_transport import Encoder


async def sync_taxonomy(
    qdrant: TaxonomyQdrant,
    encoder: Encoder,
    docs: list[TaxonomyVectorDocument],
    *,
    rebuild: bool = False,
    apply: bool = True,
) -> dict[str, int]:
    if len(docs) > 4096 or len({d.key for d in docs}) != len(docs):
        raise ValueError("invalid_taxonomy_snapshot")
    digest = corpus_hash(docs)
    exists = await qdrant.info()
    existing = await qdrant.points() if exists is not None else {}
    desired = {d.point_id: index_payload(d, digest).model_dump(mode="json") for d in docs}
    changed = sorted(i for i in desired if rebuild or existing.get(i) != desired[i])
    stale = sorted(existing.keys() - desired.keys())
    counts = {
        "documents": len(docs),
        "upserted": len(changed),
        "deleted": len(stale),
        "unchanged": len(desired) - len(changed),
    }
    if not apply:
        return counts
    if exists is None:
        await qdrant.create()
    # Deterministic stable IDs; interrupted runs are repaired by rerun. Delete
    # only after every replacement succeeded. Runtime requires one corpus digest.
    for offset in range(0, len(changed), 2):
        identifiers = changed[offset : offset + 2]
        vectors = await encoder.embed([desired[i]["embedding_text"] for i in identifiers])
        await qdrant.upsert(
            [
                {"id": i, "payload": desired[i], "vector": vector}
                for i, vector in zip(identifiers, vectors, strict=True)
            ]
        )
    await qdrant.delete(stale)
    return counts


async def run(args: argparse.Namespace) -> dict[str, object]:
    settings = Settings()
    if not settings.semantic_search_noncommercial_jina:
        raise ValueError("jina_acknowledgment_required")
    source = create_engine(settings)
    try:
        async with source.connect() as connection, connection.begin():
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            await connection.execute(text("SET LOCAL statement_timeout = '15000ms'"))
            if (await connection.execute(text(SOURCE_BOUNDARY))).scalar_one():
                raise ValueError("unsafe_source_role")
            docs = documents(await load_taxonomy(connection))
    finally:
        await source.dispose()
    async with AsyncExitStack() as stack:
        qdrant = TaxonomyQdrant(settings)
        stack.push_async_callback(qdrant.http.close)
        encoder = Encoder(settings, "jina-v3")
        stack.push_async_callback(encoder.http.close)
        if args.command == "benchmark":
            from app.research.taxonomy_benchmark import measure

            if args.benchmark is None or args.output is None:
                raise ValueError("benchmark_and_output_required")
            await measure(qdrant, encoder, docs, args.benchmark, args.output)
            return {"measured": True}
        return dict(
            await sync_taxonomy(
                qdrant,
                encoder,
                docs,
                rebuild=args.command == "rebuild",
                apply=args.command != "plan",
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "sync", "rebuild", "benchmark", "calibrate"))
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reviewed-benchmark", action="store_true")
    args = parser.parse_args()
    configure_logging("INFO")
    os.umask(0o077)
    try:
        with os.fdopen(
            os.open(
                "/tmp/uranus-taxonomy-index.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            ),
            "w",
        ) as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.command == "calibrate":
                from app.research.taxonomy_benchmark import calibrate_file

                if not args.reviewed_benchmark or not args.measurements or not args.output:
                    raise ValueError("reviewed_benchmark_measurements_and_output_required")
                calibrate_file(args.measurements, args.output)
                counts: dict[str, object] = {"calibrated": True}
            else:
                counts = asyncio.run(run(args))
            print(json.dumps(counts))
    except Exception as exc:
        logging.getLogger("admin.research").error(
            "taxonomy_job_failed", extra={"error_type": type(exc).__name__}
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
