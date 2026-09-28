"""Resolve admin geometry once; Source SQL receives only a bound EWKB value."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_database import connect_admin
from app.errors import APIError
from app.repositories.query import ReadQuery
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
    query = geo_scope_query(geo_scope_id)
    row = (await admin.execute(query.statement, query.parameters)).mappings().first()
    if row is None:
        raise APIError(404, "geo_scope_not_found", "Geo scope was not found.")
    return ResolvedGeoScope(area=GeoArea.model_validate(row), ewkb=bytes(row["ewkb"]))


async def request_geo_scope(request: Request, geo_scope_id: UUID | None) -> ResolvedGeoScope | None:
    if geo_scope_id is None:
        return None
    async with connect_admin(request) as admin:
        return await resolve_geo_scope(admin, geo_scope_id)


def geo_scope_query(geo_scope_id: UUID) -> ReadQuery:
    return ReadQuery(
        text(f"""WITH canonical AS MATERIALIZED (
            SELECT r.id,r.source,r.osm_id,r.name,r.display_name,r.country_code,
                r.osm_admin_level,r.area_type,r.region_code,r.retrieved_at,r.geometry
            FROM admin.research_area r
            WHERE r.id=:id OR EXISTS (
                SELECT 1 FROM admin.geo_area old WHERE old.id=:id
                AND old.source='osm' AND old.source_type='relation'
                AND old.source_id=r.osm_id::text AND r.osm_type='R')
            ORDER BY (r.id=:id) DESC LIMIT 1
        ) SELECT id,source,'relation' source_type,osm_id::text source_id,name,display_name,
            lower(country_code) country_code,osm_admin_level admin_level,area_type kind,
            'boundary' provider_class,'administrative' provider_type,
            area_type provider_addresstype,jsonb_build_object('state',region_code) hierarchy,
            retrieved_at fetched_at,
            ARRAY[ST_XMin(geometry),ST_YMin(geometry),ST_XMax(geometry),ST_YMax(geometry)] bbox,
            id area_id,ST_AsEWKB(geometry) ewkb FROM canonical
        UNION ALL
        SELECT {AREA_COLUMNS},NULL::uuid area_id,ST_AsEWKB(geometry) ewkb
            FROM admin.geo_area WHERE id=:id AND NOT EXISTS(SELECT 1 FROM canonical)"""),
        {"id": geo_scope_id},
    )
