"""Resolve admin geometry once; Source SQL receives only a bound EWKB value."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_database import connect_admin
from app.errors import APIError
from app.schemas.geo import GeoArea

AREA_COLUMNS = """id,source,source_type,source_id,name,display_name,country_code,admin_level,kind,
provider_class,provider_type,provider_addresstype,hierarchy,fetched_at,
CASE WHEN bbox IS NULL THEN NULL ELSE
ARRAY[ST_XMin(bbox),ST_YMin(bbox),ST_XMax(bbox),ST_YMax(bbox)] END AS bbox"""


@dataclass(frozen=True)
class ResolvedGeoScope:
    area: GeoArea
    ewkb: bytes


async def resolve_geo_scope(admin: AsyncConnection, geo_scope_id: UUID) -> ResolvedGeoScope:
    row = (
        (
            await admin.execute(
                text(
                    f"SELECT {AREA_COLUMNS},ST_AsEWKB(geometry) ewkb "
                    "FROM admin.geo_area WHERE id=:id"
                ),
                {"id": geo_scope_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "geo_scope_not_found", "Geo scope was not found.")
    return ResolvedGeoScope(area=GeoArea.model_validate(row), ewkb=bytes(row["ewkb"]))


async def request_geo_scope(request: Request, geo_scope_id: UUID | None) -> ResolvedGeoScope | None:
    if geo_scope_id is None:
        return None
    async with connect_admin(request) as admin:
        return await resolve_geo_scope(admin, geo_scope_id)
