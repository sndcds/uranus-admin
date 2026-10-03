"""Vectors propose vocabulary identities; the current public SQL snapshot authorizes them."""

import asyncio
import logging
from contextlib import AsyncExitStack

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.research_taxonomy import load_taxonomy
from app.research.taxonomy import Kind, corpus_hash, documents, index_payload
from app.research.taxonomy_policy import confident, load_policy
from app.research.taxonomy_transport import TaxonomyQdrant, validated_proposals
from app.research.vector_transport import Encoder
from app.schemas.research_execution import ResolutionCandidate


def outcome(name: str) -> None:
    # Fixed outcome names only: no concepts, labels, scores, vectors or IDs.
    logging.getLogger("admin.research").info("research_taxonomy_" + name)


async def resolve_taxonomy_semantic(
    connection: AsyncConnection,
    settings: Settings,
    query: str,
    *,
    expected_kind: Kind | None = None,
    type_ids: set[str] | None = None,
) -> list[ResolutionCandidate]:
    if settings.research_taxonomy_policy_path is None:
        return []
    if not query.strip() or len(query) > 500:
        return []
    try:
        if not settings.semantic_search_noncommercial_jina:
            raise ValueError("jina_acknowledgment_required")
        policy = await asyncio.to_thread(load_policy, settings.research_taxonomy_policy_path)
        async with asyncio.timeout(8), AsyncExitStack() as stack:
            qdrant = TaxonomyQdrant(settings)
            stack.push_async_callback(qdrant.http.close)
            if await qdrant.info() is None:
                outcome("semantic_unresolved")
                return []
            encoder = Encoder(settings, "jina-v3")
            stack.push_async_callback(encoder.http.close)
            vector = (await encoder.embed([query.strip()], query=True))[0]
            raw = await qdrant.query_taxonomy(
                vector, expected_kind=expected_kind, type_ids=type_ids
            )
            hits = validated_proposals(
                raw, policy.corpus_hash, expected_kind=expected_kind, type_ids=type_ids
            )
            # One bounded bulk SQL load, not N+1. Revalidate every proposed point,
            # including runners-up, before confidence can authorize any filter.
            current = documents(await load_taxonomy(connection))
            if corpus_hash(current) != policy.corpus_hash:
                outcome("stale_candidate_rejected")
                return []
            # Small closed vocabulary: audit the entire point inventory, so an
            # interrupted rebuild cannot hide a runner-up and inflate confidence.
            expected_points = {
                d.point_id: index_payload(d, policy.corpus_hash).model_dump(mode="json")
                for d in current
            }
            if await qdrant.points() != expected_points:
                outcome("stale_candidate_rejected")
                return []
            canonical = {d.key: d for d in current}
            for payload, _ in hits:
                doc = canonical.get(payload.key)
                if doc is None or any(
                    payload.model_dump()[k] != v for k, v in doc.model_dump().items()
                ):
                    outcome("stale_candidate_rejected")
                    return []
            selected = confident(hits, policy)
            outcome(
                "semantic_accepted"
                if len(selected) == 1
                else "semantic_ambiguous"
                if selected
                else "semantic_unresolved"
            )
            return [
                ResolutionCandidate(
                    entity_type=p.kind,
                    id=canonical[p.key].identity,
                    label=canonical[p.key].canonical_label,
                )
                for p, _ in selected
            ]
    except (
        APIError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
        OSError,
        TimeoutError,
    ):
        outcome("semantic_unresolved")
        return []
