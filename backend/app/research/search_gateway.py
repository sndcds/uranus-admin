"""Bounded candidate-only access to the operator-confirmed Jina-v3 event gateway."""

import json
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from app.errors import APIError

# The supplied gateway accepts ten, but rejects twenty/fifty. Do not silently retry
# with larger limits, forward admin credentials, or trust its cached status field.
CANDIDATE_LIMIT = 10
MAX_RESPONSE_BYTES = 64 * 1024


class Candidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entity_id: UUID
    score: FiniteFloat = Field(strict=True)


class Candidates(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[Candidate] = Field(max_length=CANDIDATE_LIMIT)
    count: int = Field(strict=True, ge=0, le=CANDIDATE_LIMIT)


async def retrieve_candidates(
    url: str, query: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> list[UUID]:
    try:
        async with httpx.AsyncClient(
            timeout=6, follow_redirects=False, trust_env=False, transport=transport
        ) as client:
            async with client.stream(
                "POST", url, json={"query": query, "limit": CANDIDATE_LIMIT}
            ) as response:
                if (
                    response.status_code != 200
                    or response.headers.get("content-type", "").split(";")[0] != "application/json"
                ):
                    raise ValueError("invalid_gateway_response")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError("gateway_response_too_large")
                candidates = Candidates.model_validate(json.loads(body))
        if candidates.count != len(candidates.results):
            raise ValueError("invalid_gateway_count")
        # Defensive best-score deduplication; metadata/prose never leave this adapter.
        ranked = sorted(candidates.results, key=lambda hit: (-hit.score, str(hit.entity_id)))
        return list(dict.fromkeys(hit.entity_id for hit in ranked))
    except (httpx.HTTPError, ValueError, TypeError):
        raise APIError(
            503, "vector_service_unavailable", "Internal vector service unavailable."
        ) from None
