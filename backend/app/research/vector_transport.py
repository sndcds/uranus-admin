"""Fixed-origin, authenticated and bounded internal HTTP; never return provider errors."""

import asyncio
import json
import math
from collections.abc import Sequence
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

import httpx

from app.config import Settings
from app.errors import APIError
from app.research.semantic_contracts import COLLECTIONS, OWNER, EntityType, SemanticDocument
from app.research.semantic_evidence import area_filter
from app.research.vector_documents import Chunk, EventDocument, content_hash
from app.research.vector_models import MODELS, Model

MAX_POINTS = 100_000


class InternalHTTP:
    def __init__(
        self,
        origin: str,
        key: str,
        timeout: int,
        header: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=origin,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            headers={header: key},
            transport=transport,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(
        self, method: str, path: str, data: Any = None, *, missing: bool = False
    ) -> dict[str, Any] | None:
        try:
            body = json.dumps(data, allow_nan=False).encode() if data is not None else None
            if body is not None and len(body) > 2 * 1024 * 1024:
                raise ValueError
            async with (
                asyncio.timeout(self.timeout),
                self.client.stream(
                    method, path, content=body, headers={"Content-Type": "application/json"}
                ) as response,
            ):
                if missing and response.status_code == 404:
                    return None
                if (
                    response.status_code != 200
                    or response.headers.get("content-type", "").split(";")[0] != "application/json"
                ):
                    raise ValueError
                content = bytearray()
                async for part in response.aiter_bytes():
                    content.extend(part)
                    if len(content) > 8 * 1024 * 1024:
                        raise ValueError
                result = json.loads(content)
                if not isinstance(result, dict):
                    raise ValueError
                return result
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError):
            raise APIError(
                503, "vector_service_unavailable", "Internal vector service unavailable."
            ) from None


class Qdrant:
    def __init__(
        self,
        settings: Settings,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        entity: EntityType | None = None,
    ):
        if settings.qdrant_url is None or settings.qdrant_api_key is None:
            raise ValueError("qdrant_configuration_required")
        if entity is not None and model != "jina-v3":
            raise ValueError("semantic_model_mismatch")
        self.entity = entity
        self.owner = OWNER if entity is not None else "uranus-admin-event-pilot-v1"
        self.collection = (
            COLLECTIONS[entity].name
            if entity is not None
            else settings.qdrant_collection_prefix + "_events_" + model.replace("-", "_")
        )
        self.model = MODELS[model]
        self.path = "/collections/" + quote(self.collection, safe="")
        self.http = InternalHTTP(
            settings.qdrant_url,
            settings.qdrant_api_key.get_secret_value(),
            settings.qdrant_timeout_seconds,
            "api-key",
            transport,
        )

    async def info(self) -> dict[str, Any] | None:
        value = await self.http.request("GET", self.path, missing=True)
        if value is None:
            return None
        result: dict[str, Any] = value["result"]
        vector = result["config"]["params"]["vectors"]
        if vector.get("size") != self.model.dimensions or vector.get("distance") != "Cosine":
            raise ValueError("incompatible_vector_collection")
        return result

    async def create(self) -> None:
        await self.http.request(
            "PUT",
            self.path,
            {
                "vectors": {"size": self.model.dimensions, "distance": "Cosine", "on_disk": True},
                "on_disk_payload": True,
                "shard_number": 1,
                "replication_factor": 1,
                "optimizers_config": {"max_optimization_threads": 1},
                "hnsw_config": {"max_indexing_threads": 1},
            },
        )

    async def points(self) -> dict[str, dict[str, Any]]:
        points: dict[str, dict[str, Any]] = {}
        offset: str | int | None = None
        seen: set[str] = set()
        while True:
            result = await self.http.request(
                "POST",
                self.path + "/points/scroll",
                {
                    "limit": 128,
                    "with_payload": True,
                    "with_vector": False,
                    "offset": offset,
                },
            )
            assert result is not None
            for point in result["result"]["points"]:
                payload = point.get("payload") or {}
                if payload.get("index_owner") != self.owner or payload.get("entity_type") != (
                    self.entity or "event"
                ):
                    raise ValueError("foreign_collection_points")
                identity = str(point["id"])
                if identity in points:
                    raise ValueError("duplicate_collection_point")
                points[identity] = payload
                if len(points) > MAX_POINTS:
                    raise ValueError("collection_point_limit")
            offset = result["result"].get("next_page_offset")
            if offset is None:
                return points
            if str(offset) in seen:
                raise ValueError("invalid_scroll_cursor")
            seen.add(str(offset))

    async def upsert(self, points: list[dict[str, Any]]) -> None:
        await self.http.request("PUT", self.path + "/points?wait=true", {"points": points})

    async def payload(self, identifier: str, payload: dict[str, Any]) -> None:
        await self.http.request(
            "PUT",
            self.path + "/points/payload?wait=true",
            {
                "points": [identifier],
                "payload": payload,
            },
        )

    async def delete(self, identifiers: list[str]) -> None:
        for offset in range(0, len(identifiers), 128):
            await self.http.request(
                "POST",
                self.path + "/points/delete?wait=true",
                {
                    "points": identifiers[offset : offset + 128],
                },
            )

    async def search(
        self,
        vector: list[float],
        limit: int,
        *,
        area_id: UUID | None = None,
        organization_mode: Literal["home", "activity"] | None = None,
    ) -> list[dict[str, Any]]:
        validate_vectors([vector], self.model, 1)
        if not 1 <= limit <= 10000:
            raise ValueError("invalid_search_limit")
        filters: dict[str, Any] = {}
        if area_id is not None:
            if self.entity is None:
                raise ValueError("semantic_collection_required_for_area_filter")
            filters["filter"] = area_filter(
                self.entity, area_id, organization_mode=organization_mode
            )
        elif organization_mode is not None:
            raise ValueError("area_id_required")
        value = await self.http.request(
            "POST",
            self.path + "/points/query",
            {
                **filters,
                "query": vector,
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
            },
        )
        assert value is not None
        result: list[dict[str, Any]] = value["result"]["points"]
        return result


def validate_vectors(vectors: Any, model: Model, expected: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != expected:
        raise ValueError("invalid_vector_count")
    for vector in vectors:
        if (
            not isinstance(vector, list)
            or len(vector) != model.dimensions
            or not all(
                isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n)
                for n in vector
            )
            or not any(vector)
        ):
            raise ValueError("invalid_vector")
    return [[float(n) for n in v] for v in vectors]


class Encoder:
    def __init__(
        self, settings: Settings, model: str, transport: httpx.AsyncBaseTransport | None = None
    ):
        if settings.embedding_url is None or settings.embedding_api_key is None:
            raise ValueError("embedding_configuration_required")
        self.key = model
        self.model = MODELS[model]
        self.http = InternalHTTP(
            settings.embedding_url,
            "Bearer " + settings.embedding_api_key.get_secret_value(),
            settings.embedding_timeout_seconds,
            "Authorization",
            transport,
        )
        self.metrics: list[dict[str, Any]] = []

    def checked(self, response: dict[str, Any] | None) -> dict[str, Any]:
        if response is None or response.get("embedding_version") != self.model.version:
            raise ValueError("encoder_version_mismatch")
        return response

    async def prepare(
        self, documents: Sequence[EventDocument | SemanticDocument]
    ) -> dict[str, list[Chunk]]:
        result: dict[str, list[Chunk]] = {str(d.entity_id): [] for d in documents if not d.sections}
        documents = [d for d in documents if d.sections]
        for offset in range(0, len(documents), 4):
            batch = documents[offset : offset + 4]
            response = self.checked(
                await self.http.request(
                    "POST",
                    "/chunks",
                    {
                        "model": self.key,
                        "documents": [
                            {
                                "entity_id": str(d.entity_id),
                                "sections": [s.model_dump() for s in d.sections],
                            }
                            for d in batch
                        ],
                    },
                )
            )
            prepared = response["documents"]
            if len(prepared) != len(batch):
                raise ValueError("invalid_chunk_response")
            for doc, item in zip(batch, prepared, strict=True):
                if item["entity_id"] != str(doc.entity_id):
                    raise ValueError("invalid_chunk_identity")
                chunks = [Chunk.model_validate(c) for c in item["chunks"]]
                if (
                    not chunks
                    or len(chunks) > 1000
                    or any(
                        c.content_hash != content_hash(c.text)
                        or c.chunk_index != i
                        or c.token_count > 480
                        for i, c in enumerate(chunks)
                    )
                ):
                    raise ValueError("invalid_chunk_response")
                result[str(doc.entity_id)] = chunks
        return result

    async def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        response = self.checked(
            await self.http.request(
                "POST",
                "/embed",
                {
                    "model": self.key,
                    "texts": texts,
                    "kind": "query" if query else "passage",
                },
            )
        )
        self.metrics.append(response.get("metrics", {}))
        return validate_vectors(response["vectors"], self.model, len(texts))
