from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repositories.activity import creation_activity_sql
from app.repositories.creation_sources import STATISTICS_SOURCES
from app.repositories.query import ReadQuery
from app.repositories.spatial import SPATIAL_TYPES, mixed_spatial_predicate, spatial_predicate
from app.schemas.action import Action
from app.schemas.statistics import EntityTimeSeries, RecentEntity
from app.services.periods import PeriodWindow


def aggregation_sql(source_timezone: str, geo: bool = False) -> str:
    queries = []
    for kind, (table, stamp, _) in STATISTICS_SOURCES.items():
        # Filter each source once; UTC preserves ordinary timestamp index scans.
        condition = (
            f"s.{stamp} >= CAST(:start AS timestamptz) AT TIME ZONE 'UTC' "
            f"AND s.{stamp} < CAST(:end AS timestamptz) AT TIME ZONE 'UTC'"
            if source_timezone == "UTC"
            else f"s.{stamp} AT TIME ZONE :tz >= :start AND s.{stamp} AT TIME ZONE :tz < :end"
        )
        if geo and kind in SPATIAL_TYPES:
            condition += " AND " + spatial_predicate(kind, key_expression="s.uuid")
        queries.append(
            f"SELECT '{kind}' AS entity_type, s.{stamp} AT TIME ZONE :tz AS stamp "
            f"FROM uranus.{table} s WHERE {condition}"
        )
    kinds = ",".join(f"('{kind}')" for kind in STATISTICS_SOURCES)
    return (
        "WITH buckets AS (SELECT * FROM unnest(CAST(:starts AS timestamptz[]), "
        "CAST(:ends AS timestamptz[])) WITH ORDINALITY AS b(start_at,end_at,id)), "
        "records AS (" + " UNION ALL ".join(queries) + "), "
        "counts AS (SELECT entity_type, width_bucket(stamp, CAST(:starts AS timestamptz[])) "
        "AS bucket, count(*) AS count FROM records GROUP BY entity_type,bucket) "
        "SELECT k.entity_type,b.start_at,b.end_at,COALESCE(c.count,0) AS count "
        f"FROM buckets b CROSS JOIN (VALUES {kinds}) AS k(entity_type) "
        "LEFT JOIN counts c ON c.bucket=b.id AND c.entity_type=k.entity_type "
        "ORDER BY k.entity_type,b.start_at"
    )


def aggregate_query(
    windows: list[PeriodWindow],
    timezone: str,
    geo_scope_wkb: bytes | None = None,
) -> ReadQuery:
    return ReadQuery(
        text(aggregation_sql(timezone, geo_scope_wkb is not None)),
        {
            "geo_scope_wkb": geo_scope_wkb,
            "starts": [w.start for w in windows],
            "ends": [w.end for w in windows],
            "tz": timezone,
            "start": windows[0].start,
            "end": windows[-1].end,
        },
    )


async def aggregate(
    connection: AsyncConnection,
    windows: list[PeriodWindow],
    timezone: str,
    geo_scope_wkb: bytes | None = None,
) -> list[EntityTimeSeries]:
    query = aggregate_query(windows, timezone, geo_scope_wkb)
    result = await connection.execute(query.statement, query.parameters)
    rows = result.mappings()
    grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in STATISTICS_SOURCES}
    for row in rows:
        grouped[row["entity_type"]].append(
            {"start_at": row["start_at"], "end_at": row["end_at"], "count": row["count"]}
        )
    return [
        EntityTimeSeries.model_validate(
            {
                "entity_type": kind,
                "label": STATISTICS_SOURCES[kind][2],
                "scope": "geo" if geo_scope_wkb is not None and kind in SPATIAL_TYPES else "global",
                "total": sum(point["count"] for point in points),
                "points": points,
            }
        )
        for kind, points in grouped.items()
    ]


def recent_query(
    window: PeriodWindow,
    timezone: str,
    geo_scope_wkb: bytes | None = None,
) -> ReadQuery:
    return ReadQuery(
        text(
            "SELECT entity_type, entity_key, entity_name, organization_name, "
            "created_at AT TIME ZONE :tz AS created_at "
            f"FROM ({creation_activity_sql(True)}) a "
            "WHERE created_at AT TIME ZONE :tz >= :start "
            "AND created_at AT TIME ZONE :tz < :end "
            + (" AND " + mixed_spatial_predicate() if geo_scope_wkb is not None else "")
            + " ORDER BY created_at DESC, entity_type, entity_key LIMIT 7"
        ),
        {
            "tz": timezone,
            "start": window.start,
            "end": window.end,
            "geo_scope_wkb": geo_scope_wkb,
        },
    )


async def recent_entities(
    connection: AsyncConnection,
    window: PeriodWindow,
    timezone: str,
    geo_scope_wkb: bytes | None = None,
) -> list[RecentEntity]:
    query = recent_query(window, timezone, geo_scope_wkb)
    result = await connection.execute(query.statement, query.parameters)
    rows = result.mappings()
    items = []
    for row in rows:
        item = dict(row)
        item["action"] = Action(
            route="activity", entity_type=item["entity_type"], entity_key=item["entity_key"]
        )
        if item["entity_type"] == "team_membership":
            item["entity_type"] = "team_invitation"
        items.append(RecentEntity.model_validate(item))
    return items
