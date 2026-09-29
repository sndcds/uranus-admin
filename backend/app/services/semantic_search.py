"""Fixed-model retrieval with validated evidence and authoritative source rehydration."""

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.database import get_connection
from app.errors import APIError
from app.repositories.research import rehydrate_semantic_events
from app.repositories.research_areas import request_area, request_areas
from app.research.semantic_evidence import semantic_hits
from app.research.semantic_explanations import explain
from app.research.vector_models import MODELS
from app.research.vector_transport import Encoder, Qdrant
from app.schemas.research import (
    SemanticResearchFilters,
    SemanticResearchPage,
    SemanticResearchRecord,
)

MODEL = "jina-v3"
REQUEST_TIMEOUT_SECONDS = 8


async def semantic_search(
    request: Request, settings: Settings, filters: SemanticResearchFilters
) -> SemanticResearchPage:
    started = perf_counter()
    metrics: dict[str, float | int | str | None] = {
        "embedding_ms": 0.0,
        "qdrant_ms": 0.0,
        "retrieval_ms": 0.0,
        "postgres_rehydrate_ms": 0.0,
        "candidate_count": 0,
        "returned_count": 0,
        "error_type": "none",
    }
    stage = "embedding_ms"
    before = started
    deadline = asyncio.timeout(REQUEST_TIMEOUT_SECONDS)
    try:
        if not settings.semantic_search_noncommercial_jina:
            raise ValueError("noncommercial_acknowledgment_required")
        async with deadline, AsyncExitStack() as stack:
            # The candidate-only gateway cannot satisfy the evidence response contract.
            encoder = Encoder(settings, MODEL)
            stack.push_async_callback(encoder.http.close)
            qdrant = Qdrant(settings, MODEL, entity="event")
            stack.push_async_callback(qdrant.http.close)
            vector = (await encoder.embed([filters.q.strip()], query=True))[0]
            metrics[stage] = round((perf_counter() - before) * 1000, 2)
            stage, before = "qdrant_ms", perf_counter()
            hits = await qdrant.search(
                vector,
                50,
                area_id=filters.area_id,
                area_ids=filters.area_ids or None,
                genre_keys=filters.genre_keys or None,
            )
            if len(hits) > 50:
                raise ValueError("invalid_candidate_count")
            # This bounds retrieval identities; it does not establish public eligibility.
            allowed_ids = {UUID(hit["payload"]["entity_id"]) for hit in hits}
            semantic_results = semantic_hits(
                hits,
                allowed_ids,
                MODELS[MODEL],
                entity="event",
                limit=50,
                area_id=filters.area_id,
                area_ids=filters.area_ids,
            )
            candidates = [hit.entity_id for hit in semantic_results]
            evidence_by_id = {hit.entity_id: hit for hit in semantic_results}
            metrics["candidate_count"] = len(candidates)
            metrics[stage] = round((perf_counter() - before) * 1000, 2)
            metrics["retrieval_ms"] = round((perf_counter() - started) * 1000, 2)
            stage, before = "postgres_rehydrate_ms", perf_counter()
            # Acquire the reader only after retrieval. No old snapshot, pool slot or
            # DB transaction is held while calling the encoder or Qdrant.
            area = (
                await request_areas(request, filters.area_ids)
                if filters.area_ids is not None
                else await request_area(request, filters.area_id)
            )
            async with asynccontextmanager(get_connection)(request) as connection:
                page = await rehydrate_semantic_events(
                    connection,
                    settings,
                    filters,
                    candidates,
                    datetime.now(UTC),
                    area,
                )
            metrics["returned_count"] = len(page.items)
            return SemanticResearchPage(
                items=[
                    SemanticResearchRecord(
                        **item.model_dump(), semantic=explain(evidence_by_id[item.entity_key])
                    )
                    for item in page.items
                ],
                pagination=page.pagination,
                observed_at=page.observed_at,
                timezone=page.timezone,
            )
    except (
        APIError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
        SQLAlchemyError,
    ) as exc:
        # Only retrieval failures belong to the semantic-unavailable contract.
        # Area/source errors retain their existing API or central error handling.
        provider_failure = stage != "postgres_rehydrate_ms" and not isinstance(
            exc, (APIError, SQLAlchemyError)
        )
        if isinstance(exc, APIError):
            provider_failure = (
                stage != "postgres_rehydrate_ms"
                and exc.status == 503
                and exc.code == "vector_service_unavailable"
            )
        if not provider_failure and not (isinstance(exc, TimeoutError) and deadline.expired()):
            metrics["error_type"] = "request_error"
            raise
        metrics["error_type"] = "semantic_unavailable"
        raise APIError(
            503,
            "research_semantic_unavailable",
            "Semantic search is temporarily unavailable. Please retry or use classic search.",
        ) from None
    finally:
        metrics[stage] = round((perf_counter() - before) * 1000, 2)
        metrics["total_ms"] = round((perf_counter() - started) * 1000, 2)
        logging.getLogger("admin.research").info("research_semantic_search", extra=metrics)
