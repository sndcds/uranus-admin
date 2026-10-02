"""Deterministic PostGIS execution; only resolved identities, polygons and category IDs."""

import json
from typing import Any, Literal

from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.research import images, parameters, record, research_sql
from app.research.internal_plan import AdministrativeLevel, ResolvedResearchPlan
from app.schemas.research import ResearchRecord
from app.schemas.research_execution import ExecutionFilters
from app.schemas.research_planner import ClosedModel

COLUMNS = """entity_type,entity_key,name,description,status,categories,language,
    start_date,start_time,end_date,end_time,all_day,organization_id,organization_name,
    venue_id,venue_name,space_id,space_name,city,address,latitude,longitude,event_count,
    source_url,created_at,modified_at,date_key"""


class AdministrativeGroup(ClosedModel):
    area_id: str
    name: str
    level: AdministrativeLevel
    event_count: int = Field(ge=0)


class AdministrativeResult(ClosedModel):
    kind: Literal["records", "count", "groups"]
    records: list[ResearchRecord] = Field(default_factory=list, max_length=20)
    groups: list[AdministrativeGroup] = Field(default_factory=list, max_length=20)
    count: int | None = Field(default=None, ge=0)
    unknown_location_count: int = Field(ge=0)
    inventory_countries: list[str] = Field(default_factory=list, max_length=250)


def execution_sql(plan: ResolvedResearchPlan, settings: Settings) -> tuple[str, dict[str, Any]]:
    constraints = [
        {"relation": s.relation, "geometry": json.loads(s.boundary.geometry_json)}
        for s in plan.spatial
    ]
    areas = [
        {"area_id": a.area.area_id, "name": a.area.name, "geometry": json.loads(a.geometry_json)}
        for a in plan.inventory
    ]
    filters = ExecutionFilters(entity_type="event", category=plan.category_id)
    params = parameters(filters, settings)
    params.update(
        constraints=json.dumps(constraints), inventory=json.dumps(areas), limit=plan.limit
    )
    # Shared eligibility keeps public status and event-date venue/space inheritance.
    # A predicate conjunction is evaluated on ONE occurrence point, then deduplicated.
    sql = f"""WITH eligible AS ({research_sql(occurrences=True)}),
    located AS MATERIALIZED (
        SELECT {COLUMNS}, CASE WHEN latitude BETWEEN -90 AND 90
            AND longitude BETWEEN -180 AND 180 THEN
            ST_SetSRID(ST_MakePoint(longitude,latitude),4326) END point FROM eligible
    ), constraints AS MATERIALIZED (
        SELECT relation, ST_SetSRID(ST_GeomFromGeoJSON(geometry::text),4326) boundary
        FROM jsonb_to_recordset(CAST(:constraints AS jsonb)) AS x(relation text,geometry jsonb)
    ), inventory AS MATERIALIZED (
        SELECT area_id,name,ST_SetSRID(ST_GeomFromGeoJSON(geometry::text),4326) boundary
        FROM jsonb_to_recordset(CAST(:inventory AS jsonb))
        AS x(area_id text,name text,geometry jsonb)
    ), matched AS MATERIALIZED (
        SELECT {COLUMNS},point FROM located WHERE NOT EXISTS (
            SELECT 1 FROM constraints c WHERE located.point IS NULL OR
            NOT CASE c.relation WHEN 'inside' THEN ST_CoveredBy(located.point,c.boundary)
                ELSE NOT ST_CoveredBy(located.point,c.boundary) END
        )
    ), unknown AS (
        SELECT count(*) value FROM (SELECT entity_key FROM located GROUP BY entity_key
            HAVING bool_and(point IS NULL)) missing
    )"""
    return sql, params


async def execute_resolved(
    connection: AsyncConnection,
    settings: Settings,
    plan: ResolvedResearchPlan,
) -> AdministrativeResult:
    if not 1 <= plan.limit <= 20 or len(plan.spatial) > 4:
        raise ValueError("Invalid resolved plan bounds")
    sql, params = execution_sql(plan, settings)
    # Closed GeoJSON shape validation cannot prove topology; PostGIS must reject it.
    valid = (
        await connection.execute(
            text(
                sql
                + """ SELECT coalesce(bool_and(
        ST_IsValid(boundary) AND NOT ST_IsEmpty(boundary)),true)
        FROM (SELECT boundary FROM constraints UNION ALL SELECT boundary FROM inventory) b"""
            ),
            params,
        )
    ).scalar_one()
    if not valid:
        raise APIError(422, "research_area_invalid_boundary", "A resolved boundary is invalid.")
    unknown = int(
        (await connection.execute(text(sql + " SELECT value FROM unknown"), params)).scalar_one()
    )
    if plan.grouping is not None:
        direction = {"asc": "ASC", "desc": "DESC"}[plan.ordering]
        having = "HAVING count(DISTINCT m.entity_key)=0" if plan.zero_only else ""
        rows = (
            await connection.execute(
                text(
                    sql
                    + f"""
            SELECT i.area_id,i.name,count(DISTINCT m.entity_key) event_count FROM inventory i
            LEFT JOIN matched m ON m.point IS NOT NULL AND ST_CoveredBy(m.point,i.boundary)
            WHERE NOT EXISTS (SELECT 1 FROM constraints c WHERE
                NOT CASE c.relation WHEN 'inside' THEN ST_CoveredBy(i.boundary,c.boundary)
                    ELSE NOT ST_CoveredBy(i.boundary,c.boundary) END)
            GROUP BY i.area_id,i.name {having}
            ORDER BY event_count {direction},lower(i.name) COLLATE "C",i.area_id COLLATE "C"
            LIMIT :limit"""
                ),
                params,
            )
        ).mappings()
        return AdministrativeResult(
            kind="groups",
            groups=[
                AdministrativeGroup(
                    area_id=row["area_id"],
                    name=row["name"],
                    level=plan.grouping,
                    event_count=row["event_count"],
                )
                for row in rows
            ],
            unknown_location_count=unknown,
            inventory_countries=list(plan.inventory_countries),
        )
    count = int(
        (
            await connection.execute(
                text(sql + " SELECT count(DISTINCT entity_key) FROM matched"), params
            )
        ).scalar_one()
    )
    if plan.operation == "count":
        return AdministrativeResult(kind="count", count=count, unknown_location_count=unknown)
    rows = (
        await connection.execute(
            text(
                sql
                + f""" SELECT DISTINCT ON (entity_key) {COLUMNS} FROM matched
        ORDER BY entity_key,start_date NULLS LAST,start_time NULLS LAST,date_key LIMIT :limit"""
            ),
            params,
        )
    ).mappings()
    records = [record(row) for row in rows]
    await images(connection, records, settings)
    return AdministrativeResult(
        kind="records", records=records, count=count, unknown_location_count=unknown
    )
