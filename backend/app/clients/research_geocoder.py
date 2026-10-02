"""Bounded private geocoder transport. No redirects, cookies, retries or body logging."""

import asyncio
import json
from typing import Literal

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.errors import APIError
from app.schemas.research_administrative import AdministrativePlace, AdministrativeSearch
from app.schemas.research_location import Place

MAX_RESPONSE_BYTES = 256 * 1024


def unavailable() -> APIError:
    return APIError(503, "geocoder_unavailable", "Location resolution is temporarily unavailable.")


class ResearchGeocoderClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        if settings.research_geocoder_api_key is None:
            raise ValueError("Geocoder key required")
        self._key = settings.research_geocoder_api_key
        self._url = settings.research_geocoder_url
        self._timeout = settings.research_geocoder_timeout_seconds
        self._http = httpx.AsyncClient(
            timeout=self._timeout, trust_env=False, follow_redirects=False, transport=transport
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        path: Literal["search", "reverse", "lookup", "ready"],
        payload: dict[str, object] | None = None,
        *,
        maximum: int = MAX_RESPONSE_BYTES,
    ) -> bytes | None:
        try:
            async with asyncio.timeout(self._timeout):
                request = httpx.Request(
                    "GET" if payload is None else "POST",
                    self._url + "/" + path,
                    headers={
                        "Authorization": f"Bearer {self._key.get_secret_value()}",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    json=payload,
                )
                response = await self._http.send(request, stream=True)
                try:
                    if response.status_code == 404 and path != "ready":
                        return None
                    if (
                        response.status_code != 200
                        or (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                            != "application/json"
                        )
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise unavailable()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > maximum:
                            raise unavailable()
                        body.extend(chunk)
                    return bytes(body)
                finally:
                    await response.aclose()
        except (httpx.HTTPError, TimeoutError):
            raise unavailable() from None

    async def search(self, query: str, limit: int = 5) -> list[Place]:
        return [
            Place.model_validate(p.model_dump(include=set(Place.model_fields)))
            for p in await self.search_administrative(query, limit)
        ]

    async def search_administrative(self, query: str, limit: int = 5) -> list[AdministrativePlace]:
        if not query.strip() or len(query) > 300 or not 1 <= limit <= 5:
            raise ValueError("Invalid geocoder search")
        body = await self._request("search", {"query": query, "limit": limit})
        if body is None:
            return []
        try:
            result = AdministrativeSearch.model_validate_json(body)
            if result.query != query or len(result.items) > limit:
                raise ValueError
            return result.items
        except (ValidationError, ValueError):
            raise unavailable() from None

    async def reverse(self, latitude: float, longitude: float) -> Place | None:
        # Validate before sending; callers cannot supply arbitrary provider parameters.
        Place(latitude=latitude, longitude=longitude)
        return await self._place("reverse", {"latitude": latitude, "longitude": longitude})

    async def lookup(self, osm_type: str, osm_id: int) -> Place | None:
        if osm_type not in {"N", "W", "R"} or type(osm_id) is not int or osm_id <= 0:
            raise ValueError("Invalid OSM identity")
        return await self._place("lookup", {"osm_type": osm_type, "osm_id": osm_id})

    async def _place(
        self, path: Literal["reverse", "lookup"], payload: dict[str, object]
    ) -> Place | None:
        body = await self._request(path, payload)
        if body is None:
            return None
        try:
            return Place.model_validate(
                AdministrativePlace.model_validate_json(body).model_dump(
                    include=set(Place.model_fields)
                )
            )
        except ValidationError:
            raise unavailable() from None

    async def ready(self) -> bool:
        try:
            body = await self._request("ready")
            return body is not None and json.loads(body).get("status") == "ready"
        except (APIError, ValueError, AttributeError, RecursionError):
            return False

    async def administrative_boundary(
        self, osm_type: str, osm_id: int
    ) -> AdministrativePlace | None:
        if osm_type not in {"N", "W", "R"} or type(osm_id) is not int or osm_id <= 0:
            raise ValueError("Invalid OSM identity")
        body = await self._request(
            "lookup",
            {"osm_type": osm_type, "osm_id": osm_id, "include_boundary": True},
            maximum=8 * 1024 * 1024,
        )
        if body is None:
            return None
        try:
            place = AdministrativePlace.model_validate_json(body)
            if (
                place.osm_id != osm_id
                or place.osm_type != {"N": "node", "W": "way", "R": "relation"}[osm_type]
            ):
                raise ValueError("OSM identity mismatch")
            return place
        except ValueError:
            raise unavailable() from None
