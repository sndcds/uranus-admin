"""Experimental fixed-model retrieval; vector payloads never become Research records."""

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
from app.repositories.research_areas import request_area, request_area_union
from app.research.search_gateway import retrieve_candidates
from app.research.semantic_evidence import semantic_hits
from app.research.vector_models import MODELS
from app.research.vector_sync import deduplicate
from app.research.vector_transport import Encoder, Qdrant
from app.schemas.research import ResearchPage, SemanticResearchFilters

MODEL = "jina-v3"
REQUEST_TIMEOUT_SECONDS = 8


async def semantic_search(
    request: Request, settings: Settings, filters: SemanticResearchFilters
) -> ResearchPage:
    started = perf_counter()
    structured = bool(filters.genre_keys or filters.area_ids)
    gateway = settings.semantic_search_url if not structured else None
    metrics: dict[str, float | int | str | None] = {
        "embedding_ms": None if gateway else 0.0,
        "qdrant_ms": None if gateway else 0.0,
        "retrieval_ms": 0.0,
        "postgres_rehydrate_ms": 0.0,
        "candidate_count": 0,
        "returned_count": 0,
        "error_type": "none",
    }
    stage = "retrieval_ms" if gateway else "embedding_ms"
    before = started
    deadline = asyncio.timeout(REQUEST_TIMEOUT_SECONDS)
    try:
        if not settings.semantic_search_noncommercial_jina:
            raise ValueError("noncommercial_acknowledgment_required")
        async with deadline, AsyncExitStack() as stack:
            if gateway:
                candidates = await retrieve_candidates(gateway, filters.q.strip())
            else:
                encoder = Encoder(settings, MODEL)
                stack.push_async_callback(encoder.http.close)
                qdrant = (
                    Qdrant(settings, MODEL, entity="event")
                    if structured
                    else Qdrant(settings, MODEL)
                )
                stack.push_async_callback(qdrant.http.close)
                vector = (await encoder.embed([filters.q.strip()], query=True))[0]
                metrics[stage] = round((perf_counter() - before) * 1000, 2)
                stage, before = "qdrant_ms", perf_counter()
                if structured:
                    hits = await qdrant.search(
                        vector,
                        50,
                        area_id=filters.area_id,
                        area_ids=filters.area_ids or None,
                        genre_keys=filters.genre_keys or None,
                    )
                else:
                    hits = await qdrant.search(vector, 50)
                if len(hits) > 50:
                    raise ValueError("invalid_candidate_count")
                # Only source rehydration decides public eligibility in either collection.
                if structured:
                    allowed_ids = {UUID(hit["payload"]["entity_id"]) for hit in hits}
                    candidates = [
                        hit.entity_id
                        for hit in semantic_hits(
                            hits, allowed_ids, MODELS[MODEL], entity="event", limit=50
                        )
                    ]
                else:
                    # Eligibility is deliberately NOT inferred from these payloads.
                    hits = [
                        hit
                        for hit in hits
                        if hit["payload"].get("entity_type") == "event"
                        and hit["payload"].get("index_owner") == "uranus-admin-event-pilot-v1"
                    ]
                    allowed = {str(UUID(hit["payload"]["entity_id"])) for hit in hits}
                    ranked = deduplicate(hits, allowed, MODELS[MODEL], limit=50)
                    candidates = [UUID(hit["payload"]["entity_id"]) for hit in ranked]
            metrics["candidate_count"] = len(candidates)
            metrics[stage] = round((perf_counter() - before) * 1000, 2)
            metrics["retrieval_ms"] = round((perf_counter() - started) * 1000, 2)
            stage, before = "postgres_rehydrate_ms", perf_counter()
            # Acquire the reader only after retrieval. No old snapshot, pool slot or
            # DB transaction is held while calling the encoder or Qdrant.
            area = await request_area(request, filters.area_id)
            area_union = (
                await request_area_union(request, filters.area_ids) if filters.area_ids else None
            )
            async with asynccontextmanager(get_connection)(request) as connection:
                page = await rehydrate_semantic_events(
                    connection,
                    settings,
                    filters,
                    candidates,
                    datetime.now(UTC),
                    area,
                    **({"area_union": area_union} if filters.area_ids else {}),
                )
            metrics["returned_count"] = len(page.items)
            return page
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
