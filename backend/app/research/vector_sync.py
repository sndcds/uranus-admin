"""Incremental embedding reuse and explicit reconciliation against a complete snapshot."""

import math
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.research.vector_documents import DOCUMENT_VERSION, Chunk, EventDocument, point_id
from app.research.vector_models import Model
from app.research.vector_transport import MAX_POINTS, Encoder, Qdrant


@dataclass
class Plan:
    desired: dict[str, tuple[Chunk, dict[str, Any]]]
    embed: list[str] = field(default_factory=list)
    metadata: list[str] = field(default_factory=list)
    delete: list[str] = field(default_factory=list)
    new: int = 0
    unchanged: int = 0

    def counts(self) -> dict[str, int]:
        return {
            "chunks": len(self.desired),
            "new": self.new,
            "updated": len(self.embed) - self.new,
            "metadata_updated": len(self.metadata),
            "unchanged": self.unchanged,
            "deleted": len(self.delete),
        }


def plan_changes(
    documents: list[EventDocument],
    chunks: dict[str, list[Chunk]],
    existing: dict[str, dict[str, Any]],
    model: Model,
    *,
    complete: bool,
) -> Plan:
    desired: dict[str, tuple[Chunk, dict[str, Any]]] = {}
    for document in documents:
        for chunk in chunks[str(document.entity_id)]:
            identifier = point_id(document.entity_id, chunk)
            if identifier in desired:
                raise ValueError("duplicate_document_chunk")
            desired[identifier] = (
                chunk,
                {
                    **document.payload,
                    "chunk_index": chunk.chunk_index,
                    "chunk_kind": chunk.chunk_kind,
                    "content_hash": chunk.content_hash,
                    "embedding_model": model.name,
                    "embedding_version": model.version,
                },
            )
    if len(desired) > MAX_POINTS:
        raise ValueError("collection_point_limit")
    plan = Plan(desired)
    selected = {str(d.entity_id) for d in documents}
    for identifier, (_chunk, payload) in desired.items():
        old = existing.get(identifier)
        if old is None:
            plan.new += 1
            plan.embed.append(identifier)
        elif any(
            old.get(key) != payload.get(key)
            for key in (
                "content_hash",
                "embedding_model",
                "embedding_version",
                "document_schema_version",
            )
        ):
            plan.embed.append(identifier)
        elif old != payload:
            plan.metadata.append(identifier)
        else:
            plan.unchanged += 1
    plan.delete = sorted(
        identifier
        for identifier, old in existing.items()
        if identifier not in desired and (complete or old.get("entity_id") in selected)
    )
    return plan


async def apply_changes(qdrant: Qdrant, encoder: Encoder, plan: Plan) -> dict[str, Any]:
    started = perf_counter()
    embedding_seconds = 0.0
    if await qdrant.info() is None:
        await qdrant.create()
    # New valid vectors are committed before old chunks are removed. An interrupted
    # run is repaired by the same stable IDs/hashes; never report partial success.
    for offset in range(0, len(plan.embed), 2):
        identifiers = plan.embed[offset : offset + 2]
        before = perf_counter()
        vectors = await encoder.embed([plan.desired[i][0].text for i in identifiers])
        embedding_seconds += perf_counter() - before
        await qdrant.upsert(
            [
                {"id": identifier, "vector": vector, "payload": plan.desired[identifier][1]}
                for identifier, vector in zip(identifiers, vectors, strict=True)
            ]
        )
    for identifier in plan.metadata:
        await qdrant.payload(identifier, plan.desired[identifier][1])
    await qdrant.delete(plan.delete)
    wall = perf_counter() - started
    embedded_events = len({plan.desired[i][1]["entity_id"] for i in plan.embed})
    return {
        "wall_seconds": wall,
        "embedding_seconds": embedding_seconds,
        "embedded_chunks": len(plan.embed),
        "embedded_events": embedded_events,
        "chunks_per_second": len(plan.embed) / wall if wall else 0,
        "events_per_second": embedded_events / wall if wall else 0,
        "encoder_cpu_seconds": sum(float(m.get("cpu_seconds", 0)) for m in encoder.metrics),
        "encoder_peak_rss_bytes": max(
            (int(m.get("peak_rss_bytes", 0)) for m in encoder.metrics), default=0
        ),
    }


def deduplicate(
    hits: list[dict[str, Any]], allowed: set[str], model: Model
) -> list[dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for hit in hits:
        if not isinstance(hit.get("score"), (int, float)) or not math.isfinite(hit["score"]):
            raise ValueError("invalid_retrieval_score")
        payload = hit.get("payload") or {}
        key = payload.get("entity_id")
        if (
            key not in allowed
            or payload.get("embedding_version") != model.version
            or (payload.get("document_schema_version") != DOCUMENT_VERSION)
        ):
            continue
        if key not in events or hit["score"] > events[key]["score"]:
            events[key] = hit
    return sorted(events.values(), key=lambda h: (-h["score"], h["payload"]["entity_id"]))[:10]
