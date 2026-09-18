"""One configured origin, bounded HTTP/JSON, no redirects or provider text in logs."""

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.config import Settings
from app.errors import APIError
from app.schemas.geo import GeoAreaKind, GeoAreaSearchItem

logger = logging.getLogger("admin.geo")
HIERARCHY_KEYS = (
    "country",
    "state",
    "region",
    "state_district",
    "county",
    "municipality",
    "city",
    "town",
    "village",
    "city_district",
    "district",
    "borough",
    "suburb",
)


def normalize_kind(country: str | None, address_type: str | None, level: int | None) -> GeoAreaKind:
    # Explicit classifications first. Admin levels alone have no universal meaning.
    named: dict[str, GeoAreaKind] = {
        "country": "country",
        "state": "region",
        "region": "region",
        "county": "county",
        "municipality": "municipality",
        "city": "city",
        "town": "municipality",
        "village": "municipality",
        "city_district": "district",
        "district": "district",
        "borough": "district",
        "suburb": "district",
    }
    if address_type in named:
        return named[address_type]
    national: dict[str, dict[int, GeoAreaKind]] = {
        "de": {2: "country", 4: "region", 6: "county", 8: "municipality"},
        "dk": {2: "country", 4: "region", 7: "municipality"},
    }
    return national.get(country or "", {}).get(level or 0, "other")


def short_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())[:limit]
    return value or None


def area_item(row: dict[str, Any]) -> GeoAreaSearchItem | None:
    category = row.get("class", row.get("category"))
    identity = str(row.get("osm_id", ""))
    if (
        row.get("osm_type") != "relation"
        or category != "boundary"
        or row.get("type") != "administrative"
        or not re.fullmatch(r"[1-9][0-9]{0,18}", identity)
    ):
        return None
    address_raw, tags_raw = row.get("address"), row.get("extratags")
    address = address_raw if isinstance(address_raw, dict) else {}
    tags = tags_raw if isinstance(tags_raw, dict) else {}
    country = short_text(address.get("country_code"), 80)
    country = country.lower() if country and re.fullmatch(r"[A-Za-z]{2}", country) else None
    level_raw = str(tags.get("admin_level", ""))
    level = int(level_raw) if re.fullmatch(r"[0-9]{1,2}", level_raw) else None
    address_type = short_text(row.get("addresstype"), 80)
    hierarchy = {
        key: value for key in HIERARCHY_KEYS if (value := short_text(address.get(key), 240))
    }
    display = short_text(row.get("display_name"), 1024)
    name = short_text(row.get("name"), 240) or (display.split(",")[0][:240] if display else None)
    if not display or not name:
        return None
    bbox = None
    bounds = row.get("boundingbox")
    if isinstance(bounds, list) and len(bounds) == 4:
        try:
            south, north, west, east = map(float, bounds)
            if -90 <= south < north <= 90 and -180 <= west < east <= 180:
                bbox = (west, south, east, north)
        except (TypeError, ValueError, OverflowError):
            pass
    return GeoAreaSearchItem(
        osm_id=identity,
        name=name,
        display_name=display,
        country_code=country,
        admin_level=level,
        kind=normalize_kind(country, address_type, level),
        provider_class="boundary",
        provider_type="administrative",
        provider_addresstype=address_type,
        hierarchy=hierarchy,
        bbox=bbox,
    )


def validate_geometry(value: object, max_points: int) -> str:
    """Validate structure and complexity before invoking PostGIS; do not simplify."""
    invalid = APIError(422, "geo_area_geometry_invalid", "Area geometry is invalid.")
    if not isinstance(value, dict) or value.get("type") not in ("Polygon", "MultiPolygon"):
        raise invalid
    polygons = (
        [value.get("coordinates")] if value["type"] == "Polygon" else value.get("coordinates")
    )
    if not isinstance(polygons, list) or not polygons:
        raise invalid
    count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise invalid
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise invalid
            count += len(ring)
            if count > max_points:
                raise invalid
            for point in ring:
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(type(v) not in {int, float} for v in point)
                    or not -180 <= point[0] <= 180
                    or not -90 <= point[1] <= 90
                ):
                    raise invalid
    return json.dumps({"type": value["type"], "coordinates": value["coordinates"]}, allow_nan=False)


class NominatimClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def _get(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if not self.settings.nominatim_base_url:
            raise APIError(503, "geo_provider_unavailable", "Geo provider is not configured.")
        try:
            async with asyncio.timeout(self.settings.nominatim_timeout_seconds):
                async with httpx.AsyncClient(
                    base_url=self.settings.nominatim_base_url,
                    timeout=self.settings.nominatim_timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                    headers={
                        "User-Agent": "uranus-admin/0.1.0 geo-service",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as client:
                    async with client.stream(
                        "GET", path, params={"format": "jsonv2", **params}
                    ) as response:
                        response.raise_for_status()
                        if (
                            response.headers.get("content-type", "").split(";")[0]
                            != "application/json"
                            or response.headers.get("content-encoding", "identity") != "identity"
                        ):
                            raise ValueError("Invalid content")
                        limit = self.settings.nominatim_max_response_bytes
                        if int(response.headers.get("content-length", "0")) > limit:
                            raise ValueError("Oversized response")
                        body = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            if len(body) + len(chunk) > limit:
                                raise ValueError("Oversized response")
                            body.extend(chunk)
            data = json.loads(body)
            if (
                not isinstance(data, list)
                or len(data) > 10
                or any(not isinstance(r, dict) for r in data)
            ):
                raise ValueError("Invalid response")
            return data
        except (httpx.HTTPError, TimeoutError, ValueError, RecursionError):
            raise APIError(
                503, "geo_provider_unavailable", "Geo provider is unavailable."
            ) from None

    async def search_areas(self, query: str, limit: int) -> list[GeoAreaSearchItem]:
        rows = await self._get(
            "/search",
            {
                "q": query,
                "limit": str(limit),
                "addressdetails": "1",
                "namedetails": "1",
                "extratags": "1",
            },
        )
        logger.info("geo_area_search")
        return [item for row in rows if (item := area_item(row)) is not None][:limit]

    async def lookup_area(self, source_id: str) -> tuple[GeoAreaSearchItem, str]:
        rows = await self._get(
            "/lookup",
            {
                "osm_ids": f"R{source_id}",
                "polygon_geojson": "1",
                "addressdetails": "1",
                "namedetails": "1",
                "extratags": "1",
            },
        )
        for row in rows:
            item = area_item(row)
            if item is not None and item.osm_id == source_id:
                return item, validate_geometry(
                    row.get("geojson"), self.settings.nominatim_max_geometry_points
                )
        raise APIError(422, "geo_area_not_eligible", "Result is not an administrative boundary.")
