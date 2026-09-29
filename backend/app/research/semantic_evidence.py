"""Allowlisted evidence, deterministic entity ranking and explicit hard area filters."""

import math
from typing import Any, Literal
from uuid import UUID

from pydantic import TypeAdapter

from app.research.area_selection import normalize_area_ids
from app.research.evidence_context import EvidenceContext
from app.research.semantic_contracts import (
    COLLECTIONS,
    OWNER,
    EntityType,
    EvidenceChunk,
    SemanticHit,
)
from app.research.semantic_documents import is_public_text
from app.research.vector_documents import content_hash
from app.research.vector_models import Model
from app.schemas.genre import GenreKey


def area_filter(
    entity: EntityType,
    area_id: UUID | None = None,
    *,
    area_ids: list[UUID] | None = None,
    organization_mode: Literal["home", "activity"] | None = None,
) -> dict[str, Any]:
    selected = normalize_area_ids(area_id, area_ids)
    if selected is None:
        raise ValueError("area_id_required")
    if entity == "organization":
        if organization_mode not in {"home", "activity"}:
            raise ValueError("organization_area_mode_required")
        key = organization_mode + "_area_ids"
    else:
        if organization_mode is not None:
            raise ValueError("unexpected_organization_area_mode")
        key = "area_ids"
    return {"must": [{"key": key, "match": {"any": [str(identifier) for identifier in selected]}}]}


def genre_filter(entity: EntityType | None, genre_keys: list[str]) -> dict[str, Any]:
    if entity != "event":
        raise ValueError("event_collection_required_for_genre_filter")
    if not 1 <= len(genre_keys) <= 50:
        raise ValueError("invalid_genre_filter_limit")
    keys = TypeAdapter(list[GenreKey]).validate_python(genre_keys)
    return {"key": "genre_keys", "match": {"any": sorted(set(keys))}}


def semantic_hits(
    hits: list[dict[str, Any]],
    allowed: set[UUID],
    model: Model,
    *,
    entity: EntityType,
    limit: int = 10,
    supporting: int = 2,
    area_id: UUID | None = None,
    area_ids: list[UUID] | None = None,
    organization_mode: Literal["home", "activity"] | None = None,
) -> list[SemanticHit]:
    if not 1 <= limit <= 50 or not 0 <= supporting <= 3 or len(hits) > 10000:
        raise ValueError("invalid_evidence_limits")
    selected = normalize_area_ids(area_id, area_ids)
    if selected is None and organization_mode is not None:
        raise ValueError("area_id_required")
    gate = (
        area_filter(entity, area_ids=selected, organization_mode=organization_mode)
        if selected is not None
        else None
    )
    grouped: dict[UUID, list[tuple[EvidenceChunk, str, str]]] = {}
    for hit in hits:
        score = hit.get("score")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
        ):
            raise ValueError("invalid_retrieval_score")
        payload = hit.get("payload") or {}
        if (
            payload.get("entity_type") != entity
            or payload.get("index_owner") != OWNER
            or payload.get("embedding_version") != model.version
            or payload.get("document_schema_version") != COLLECTIONS[entity].document_version
        ):
            continue
        identity = UUID(payload["entity_id"])
        if identity not in allowed:
            continue
        if gate:
            condition = gate["must"][0]
            memberships = payload.get(condition["key"], [])
            if not isinstance(memberships, list) or not any(
                identifier in memberships for identifier in condition["match"]["any"]
            ):
                continue
        text, name = payload["chunk_text"], payload["display_name"]
        if (
            not is_public_text(text)
            or not is_public_text(name)
            or content_hash(text) != payload.get("content_hash")
        ):
            raise ValueError("unsafe_or_stale_evidence")
        contexts = []
        if entity == "event":
            contexts = TypeAdapter(list[EvidenceContext]).validate_python(
                payload["evidence_contexts"]
            )
            if not contexts or (
                payload["chunk_kind"] in {"accessibility", "location_context"}
                and any(c.scope == "event" for c in contexts)
            ):
                raise ValueError("invalid_evidence_context")
        evidence = EvidenceChunk(
            chunk_kind=payload["chunk_kind"], chunk_text=text, score=score, contexts=contexts
        )
        grouped.setdefault(identity, []).append((evidence, name, payload["content_hash"]))
    result = []
    for identity, chunks in grouped.items():
        chunks.sort(key=lambda x: (-x[0].score, x[0].chunk_kind, x[2], x[1]))
        winning, name, digest = chunks[0]
        kinds, hashes = {winning.chunk_kind}, {digest}
        supports: list[EvidenceChunk] = []
        for candidate, _, digest in chunks[1:]:
            if len(supports) == supporting:
                break
            if candidate.chunk_kind not in kinds and digest not in hashes:
                supports.append(candidate)
                kinds.add(candidate.chunk_kind)
                hashes.add(digest)
        result.append(
            SemanticHit(
                entity_type=entity,
                entity_id=identity,
                score=winning.score,
                display_name=name,
                winning_chunk=winning,
                candidate_chunks=[c for c, _, _ in chunks],
                supporting_chunks=supports,
            )
        )
    return sorted(result, key=lambda h: (-h.score, str(h.entity_id)))[:limit]


def contextualize_event_hit(
    hit: SemanticHit,
    *,
    venue_id: UUID | None,
    space_id: UUID | None,
    occurrence_id: UUID | None,
    supporting: int = 2,
) -> SemanticHit | None:
    """Choose only after PostgreSQL eligibility/occurrence selection, before paging."""
    if hit.entity_type != "event" or not 0 <= supporting <= 3:
        raise ValueError("invalid_event_evidence_selection")
    chunks = [
        c
        for c in hit.candidate_chunks
        if any(context.matches(venue_id, space_id, occurrence_id) for context in c.contexts)
    ]
    chunks.sort(key=lambda c: (-c.score, c.chunk_kind, content_hash(c.chunk_text)))
    if not chunks:
        return None
    winning = chunks[0]
    kinds, hashes = {winning.chunk_kind}, {content_hash(winning.chunk_text)}
    supports: list[EvidenceChunk] = []
    for chunk in chunks[1:]:
        if len(supports) == supporting:
            break
        digest = content_hash(chunk.chunk_text)
        if chunk.chunk_kind not in kinds and digest not in hashes:
            supports.append(chunk)
            kinds.add(chunk.chunk_kind)
            hashes.add(digest)
    return hit.model_copy(
        update={
            "score": winning.score,
            "winning_chunk": winning,
            "supporting_chunks": supports,
            "candidate_chunks": chunks,
        }
    )
