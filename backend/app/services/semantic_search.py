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
from app.repositories.research_areas import request_area
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
    metrics: dict[str, float | int | str] = {
        "embedding_ms": 0.0,
        "qdrant_ms": 0.0,
        "postgres_rehydrate_ms": 0.0,
        "candidate_count": 0,
        "returned_count": 0,
        "error_type": "none",
    }
    stage = "embedding_ms"
    before = started
    try:
        if not settings.semantic_search_noncommercial_jina:
            raise ValueError("noncommercial_acknowledgment_required")
        async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS), AsyncExitStack() as stack:
            encoder = Encoder(settings, MODEL)
            stack.push_async_callback(encoder.http.close)
            qdrant = Qdrant(settings, MODEL)
            stack.push_async_callback(qdrant.http.close)
            vector = (await encoder.embed([filters.q.strip()], query=True))[0]
            metrics[stage] = round((perf_counter() - before) * 1000, 2)
            stage, before = "qdrant_ms", perf_counter()
            hits = await qdrant.search(vector, 50)
            if len(hits) > 50:
                raise ValueError("invalid_candidate_count")
            # Validate IDs and provenance, then reuse best-chunk ranking. Eligibility
            # is deliberately NOT inferred from these payloads.
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
            stage, before = "postgres_rehydrate_ms", perf_counter()
            # Acquire the reader only after retrieval. No old snapshot, pool slot or
            # DB transaction is held while calling the encoder or Qdrant.
            area = await request_area(request, filters.area_id)
            async with asynccontextmanager(get_connection)(request) as connection:
                page = await rehydrate_semantic_events(
                    connection, settings, filters, candidates, datetime.now(UTC), area
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
    ):
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
