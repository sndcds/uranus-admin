"""Dedicated taxonomy collection using the existing authenticated bounded HTTP transport."""

import json
import math
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.research.taxonomy import COLLECTION, MODEL, OWNER, Kind, TaxonomyPayload
from app.research.vector_transport import Qdrant, validate_vectors


class TaxonomyQdrant(Qdrant):
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(settings, "jina-v3", transport)
        self.collection = COLLECTION
        self.path = "/collections/" + quote(COLLECTION, safe="")
        self.owner = OWNER

    async def points(self) -> dict[str, dict[str, Any]]:
        points: dict[str, dict[str, Any]] = {}
        offset: str | int | None = None
        seen: set[str] = set()
        for _page in range(65):
            response = await self.http.request(
                "POST",
                self.path + "/points/scroll",
                {
                    "limit": 64,
                    "offset": offset,
                    "with_payload": True,
                    "with_vector": False,
                },
            )
            assert response is not None
            page = response["result"]["points"]
            if len(page) > 64:
                raise ValueError("taxonomy_scroll_limit")
            for point in page:
                payload = TaxonomyPayload.model_validate_json(
                    json.dumps(point["payload"], allow_nan=False)
                )
                identifier = str(point["id"])
                if identifier != payload.point_id or identifier in points:
                    raise ValueError("taxonomy_point_identity")
                points[identifier] = payload.model_dump(mode="json")
                if len(points) > 4096:
                    raise ValueError("taxonomy_point_limit")
            offset = response["result"].get("next_page_offset")
            if offset is None:
                return points
            if str(offset) in seen:
                raise ValueError("taxonomy_scroll_cursor")
            seen.add(str(offset))
        raise ValueError("taxonomy_scroll_page_limit")

    async def query_taxonomy(
        self,
        vector: list[float],
        *,
        expected_kind: Kind | None = None,
        type_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        validate_vectors([vector], MODEL, 1)
        must: list[dict[str, Any]] = []
        if expected_kind:
            must.append({"key": "kind", "match": {"value": expected_kind}})
        if type_ids:
            must.append({"key": "type_id", "match": {"any": sorted(type_ids)}})
        response = await self.http.request(
            "POST",
            self.path + "/points/query",
            {
                "query": vector,
                # Exact search avoids ANN omissions in the confidence margin.
                "params": {"exact": True},
                "limit": 6,
                "with_payload": True,
                "with_vector": False,
                "filter": {"must": must},
            },
        )
        assert response is not None
        hits: list[dict[str, Any]] = response["result"]["points"]
        if len(hits) > 6:
            raise ValueError("taxonomy_search_limit")
        return hits


def validated_proposals(
    raw: list[dict[str, Any]],
    digest: str,
    *,
    expected_kind: Kind | None = None,
    type_ids: set[str] | None = None,
) -> list[tuple[TaxonomyPayload, float]]:
    if len(raw) > 6:
        raise ValueError("taxonomy_search_limit")
    hits: list[tuple[TaxonomyPayload, float]] = []
    seen: set[str] = set()
    for hit in raw:
        payload = TaxonomyPayload.model_validate_json(json.dumps(hit["payload"], allow_nan=False))
        score = hit["score"]
        if (
            isinstance(score, bool)
            or not isinstance(score, (float, int))
            or not math.isfinite(score)
            or not -1 <= score <= 1
            or str(hit["id"]) != payload.point_id
            or payload.key in seen
            or payload.corpus_hash != digest
            or (expected_kind and payload.kind != expected_kind)
            or (type_ids and payload.type_id not in type_ids)
        ):
            raise ValueError("invalid_taxonomy_candidate")
        hits.append((payload, float(score)))
        seen.add(payload.key)
    return sorted(hits, key=lambda h: (-h[1], h[0].key))
