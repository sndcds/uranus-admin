"""Persisted areas are resolved once; no provider access in a Research request."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_database import connect_admin
from app.errors import APIError
from app.repositories.entities import pagination
from app.repositories.entity_search import escape_search
from app.schemas.research_areas import AreaFilters, AreaGeometry, AreaPage, ResearchArea

AREA_COLUMNS = """id,area_type,country_code,region_code,name,display_name,
    osm_type,osm_id::text,osm_admin_level,source,retrieved_at,updated_at,
    CASE WHEN population_count IS NULL THEN NULL ELSE jsonb_build_object(
        'value',population_count,'as_of',population_date,'source',population_source,
        'municipality_name',population_name,'file_sha256',population_file_sha256,
        'imported_at',population_imported_at) END population,
    jsonb_build_object('longitude',ST_X(centroid),'latitude',ST_Y(centroid)) centroid,
    ARRAY[ST_XMin(geometry),ST_YMin(geometry),ST_XMax(geometry),ST_YMax(geometry)] bbox"""


@dataclass(frozen=True)
class ResolvedResearchArea:
    area: ResearchArea
    ewkb: bytes
    geometry: AreaGeometry | None = None


async def area_page(admin: AsyncConnection, filters: AreaFilters) -> AreaPage:
    predicate = """area_type=:area_type
        AND (CAST(:country_code AS text) IS NULL OR country_code=:country_code)
        AND (name ILIKE :q ESCAPE '\\' OR id::text=:identity)"""
    params = {
        **filters.model_dump(),
        "q": f"%{escape_search(filters.q)}%",
        "identity": filters.q,
        "offset": (filters.page - 1) * filters.page_size,
    }
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        total = (
            await admin.execute(
                text(f"SELECT count(*) FROM admin.research_area WHERE {predicate}"), params
            )
        ).scalar_one()
        rows = (
            await admin.execute(
                text(f"""SELECT {AREA_COLUMNS} FROM admin.research_area
            WHERE {predicate} ORDER BY lower(name) COLLATE "C",id
            LIMIT :page_size OFFSET :offset"""),
                params,
            )
        ).mappings()
        items = [ResearchArea.model_validate(row) for row in rows]
    return AreaPage(items=items, pagination=pagination(filters.page, filters.page_size, total))


async def resolve_area(
    admin: AsyncConnection, identifier: UUID, *, boundary: bool = False
) -> ResolvedResearchArea:
    geometry = ",ST_AsGeoJSON(geometry)::jsonb boundary" if boundary else ""
    row = (
        (
            await admin.execute(
                text(
                    f"SELECT {AREA_COLUMNS},ST_AsEWKB(geometry) ewkb {geometry} "
                    "FROM admin.research_area WHERE id=:id"
                ),
                {"id": identifier},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "research_area_not_found", "Research area was not found.")
    return ResolvedResearchArea(
        ResearchArea.model_validate(row),
        bytes(row["ewkb"]),
        AreaGeometry.model_validate(row["boundary"]) if boundary else None,
    )


async def area_metadata(admin: AsyncConnection, identifier: UUID) -> ResearchArea:
    """Selected-value hydration reads neither polygons nor Uranus dossier records."""
    row = (
        (
            await admin.execute(
                text(f"SELECT {AREA_COLUMNS} FROM admin.research_area WHERE id=:id"),
                {"id": identifier},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "research_area_not_found", "Research area was not found.")
    return ResearchArea.model_validate(row)


async def request_area(
    request: Request, identifier: UUID | None, *, boundary: bool = False
) -> ResolvedResearchArea | None:
    if identifier is None:
        return None
    async with connect_admin(request) as admin:
        return await resolve_area(admin, identifier, boundary=boundary)
