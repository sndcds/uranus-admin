"""Explicit operator pilot: public source snapshot -> bounded internal retrieval services."""

import argparse
import asyncio
import fcntl
import json
import logging
import os
from collections.abc import Sequence
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.admin_database import assert_admin_boundary, create_admin_engine
from app.config import Settings
from app.database import create_engine
from app.logging import configure_logging
from app.repositories.vector_entities import extract_organizations, extract_venues
from app.repositories.vector_events import extract_events
from app.research.semantic_contracts import COLLECTIONS, SemanticDocument
from app.research.vector_benchmark import benchmark, quality_metrics, questions, save_json
from app.research.vector_documents import DOCUMENT_VERSION, EventDocument, content_hash
from app.research.vector_models import MODELS
from app.research.vector_sync import apply_changes, plan_changes
from app.research.vector_transport import Encoder, Qdrant

# Check effective privileges, including column-level grants and inherited ownership.
SOURCE_BOUNDARY = """SELECT EXISTS(SELECT 1 FROM pg_roles
WHERE rolname=current_user AND (rolsuper OR rolcreaterole)) OR
has_schema_privilege(current_user,'uranus','CREATE') OR EXISTS(
SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='uranus' AND c.relkind IN ('r','p','v','m','f') AND (
 has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') OR
 has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE') OR
 pg_has_role(current_user,c.relowner,'USAGE')))"""


async def run(args: argparse.Namespace, settings: Settings) -> dict[str, object]:
    entity = getattr(args, "entity", None)
    if entity is not None and (entity not in COLLECTIONS or args.model != "jina-v3"):
        raise ValueError("semantic_collection_model_required")
    if entity is not None and args.command == "benchmark":
        raise ValueError("benchmark_requires_legacy_event_collection")
    documents: Sequence[EventDocument | SemanticDocument]
    source = create_engine(settings)
    admin = create_admin_engine(settings)
    now = datetime.now(UTC)
    try:
        async with AsyncExitStack() as stack:
            connection = await stack.enter_async_context(source.connect())
            await stack.enter_async_context(connection.begin())
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            if (await connection.execute(text(SOURCE_BOUNDARY))).scalar_one():
                raise ValueError("unsafe_source_role")
            metadata = None
            if admin is not None:
                metadata = await stack.enter_async_context(admin.connect())
                await stack.enter_async_context(metadata.begin())
                await metadata.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                await assert_admin_boundary(metadata)
            if entity is not None and args.command in {"sync", "reconcile"}:
                if (
                    metadata is None
                    or not (
                        await metadata.execute(
                            text("SELECT to_regclass('admin.research_area') IS NOT NULL")
                        )
                    ).scalar_one()
                ):
                    raise ValueError("research_areas_required_for_sync")
            if entity == "event":
                documents, total = await extract_events(
                    connection, metadata, settings, now, args.limit, semantic=True
                )
            elif entity == "venue":
                documents, total = await extract_venues(
                    connection, metadata, settings, now, args.limit
                )
            elif entity == "organization":
                documents, total = await extract_organizations(
                    connection, metadata, settings, now, args.limit
                )
            else:
                documents, total = await extract_events(
                    connection, metadata, settings, now, args.limit
                )
            table = {"event": "event", "venue": "venue", "organization": "organization"}[
                entity or "event"
            ]
            source_total = (
                await connection.execute(text(f"SELECT count(*) FROM uranus.{table}"))
            ).scalar_one()
    finally:
        await source.dispose()
        if admin is not None:
            await admin.dispose()
    # All DB connections/transactions are closed before any model or Qdrant work.
    model = MODELS[args.model]
    qdrant = Qdrant(settings, args.model, entity=entity)
    encoder = Encoder(settings, args.model)
    try:
        chunks = await encoder.prepare(documents)
        info = await qdrant.info()
        existing = await qdrant.points() if info else {}
        plan = plan_changes(
            documents, chunks, existing, model, complete=args.limit is None, entity=entity
        )
        manifest: dict[str, object] = {
            "snapshot_at": now.isoformat(),
            **(
                {"events_total": total, "events_selected": len(documents)} if entity is None else {}
            ),
            "entity_type": entity or "event",
            "source_entity_count": source_total,
            "public_entity_count": total,
            "selected_public_count": len(documents),
            "document_count": len(documents),
            **snapshot_metrics(documents),
            "approximate_payload_bytes": sum(
                len(json.dumps(p, ensure_ascii=False).encode("utf-8"))
                for _, p in plan.desired.values()
            ),
            "complete_snapshot": args.limit is None,
            "model": model.name,
            "embedding_version": model.version,
            "document_schema_version": COLLECTIONS[entity].document_version
            if entity
            else DOCUMENT_VERSION,
            "collection_name": qdrant.collection,
            "license": model.license,
            "area_assignment_available": all(
                payload_dict(d)["area_assignment_available"] for d in documents
            ),
            "normalized_document_hash": content_hash(
                json.dumps(
                    [
                        {
                            "entity_id": str(d.entity_id),
                            "sections": [s.model_dump() for s in d.sections],
                        }
                        for d in documents
                    ],
                    sort_keys=True,
                    ensure_ascii=False,
                )
            ),
            "corpus_hash": content_hash(
                json.dumps(sorted((i, c.content_hash) for i, (c, _) in plan.desired.items()))
            ),
            **plan.counts(),
        }
        print(json.dumps({"event": "vector_plan", **manifest}), flush=True)
        if args.command in {"sync", "reconcile"}:
            manifest["metrics"] = await apply_changes(qdrant, encoder, plan)
            manifest["collection"] = await qdrant.info()
        elif args.command == "benchmark":
            if plan.embed or plan.delete or plan.metadata:
                raise ValueError("reconcile_required_before_benchmark")
            if args.output is None or args.questions is None:
                raise ValueError("benchmark_output_and_questions_required")
            return await benchmark(
                qdrant,
                encoder,
                [d for d in documents if isinstance(d, EventDocument)],
                chunks,
                questions(args.questions),
                args.output,
                manifest,
            )
        if args.output is not None:
            await asyncio.to_thread(args.output.mkdir, parents=True, exist_ok=True, mode=0o700)
            save_json(args.output / "run.json", manifest)
        return manifest
    finally:
        await qdrant.http.close()
        await encoder.http.close()


def payload_dict(document: EventDocument | SemanticDocument) -> dict[str, Any]:
    return (
        document.payload.model_dump(mode="json")
        if isinstance(document, SemanticDocument)
        else document.payload
    )


def snapshot_metrics(documents: Sequence[EventDocument | SemanticDocument]) -> dict[str, object]:
    values = [payload_dict(d) for d in documents]
    assigned = sum(
        bool(p.get("area_ids") or p.get("home_area_ids") or p.get("activity_area_ids"))
        for p in values
    )
    return {
        "documents_with_area": assigned,
        "area_assignment_coverage": assigned / len(values) if values else 0,
        "documents_without_semantic_content": sum(not d.sections for d in documents),
        "documents_without_location": sum(
            not any(
                v.get("effective_latitude") is not None for v in p.get("effective_locations", [])
            )
            if p.get("entity_type") == "event"
            else p.get("latitude") is None
            for p in values
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "sync", "reconcile", "benchmark", "evaluate"))
    parser.add_argument("--model", choices=tuple(MODELS))
    parser.add_argument(
        "--entity",
        choices=tuple(COLLECTIONS),
        help="New Jina knowledge collection. Omit only for the legacy event pilot/benchmark.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--noncommercial-jina", action="store_true")
    parser.add_argument(
        "--lock-file", type=Path, default=Path("/tmp/uranus-event-vector-index.lock")
    )
    args = parser.parse_args()
    configure_logging("INFO")
    try:
        if args.command == "evaluate":
            if args.judgments is None or args.judgments.stat().st_size > 8_000_000:
                raise ValueError("bounded_judgments_required")
            print(json.dumps(quality_metrics(json.loads(args.judgments.read_text()))))
            return
        if args.model is None:
            parser.error("--model is required; no production default is selected")
        if args.entity is not None and (args.model != "jina-v3" or args.command == "benchmark"):
            parser.error(
                "--entity requires jina-v3 and plan/sync/reconcile; benchmark remains legacy"
            )
        if args.model == "jina-v3" and not args.noncommercial_jina:
            parser.error("Jina requires explicit --noncommercial-jina acknowledgment")
        if args.limit is not None and not 1 <= args.limit <= 10000:
            parser.error("--limit must be 1..10000")
        os.umask(0o077)
        # One operator host per deployment. O_NOFOLLOW prevents shared-/tmp symlink attacks.
        with os.fdopen(
            os.open(args.lock_file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "w"
        ) as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = asyncio.run(run(args, Settings()))
            print(json.dumps({"event": "vector_complete", **result}, allow_nan=False))
    except Exception as exc:
        logging.getLogger("admin.vector").error(
            "vector_job_failed", extra={"error_type": type(exc).__name__}
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
