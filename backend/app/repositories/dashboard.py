from datetime import UTC

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import check_run
from app.repositories.creation_sources import RECORD_TABLES
from app.repositories.query import ReadQuery
from app.repositories.spatial import SPATIAL_TYPES, spatial_predicate
from app.schemas.dashboard import DashboardCheckRun, DashboardCheckStatus
from app.services.periods import PeriodWindow

NEW_RECORDS_UTC_SQL = " UNION ALL ".join(
    f"SELECT '{key}' AS kind, COUNT(*) AS count FROM uranus.{table} "
    "WHERE created_at >= :start_at AND created_at < :end_at"
    for key, table in RECORD_TABLES.items()
)
NEW_RECORDS_LOCAL_SQL = " UNION ALL ".join(
    f"SELECT '{key}' AS kind, COUNT(*) AS count FROM uranus.{table} "
    "WHERE created_at AT TIME ZONE :source_timezone >= :start_at "
    "AND created_at AT TIME ZONE :source_timezone < :end_at"
    for key, table in RECORD_TABLES.items()
)


def new_record_queries(
    window: PeriodWindow,
    source_timezone: str,
    geo_scope_wkb: bytes | None = None,
) -> dict[str, ReadQuery]:
    is_utc = source_timezone == "UTC"
    sql = NEW_RECORDS_UTC_SQL if is_utc else NEW_RECORDS_LOCAL_SQL
    if geo_scope_wkb is not None:
        queries = []
        for key, table in RECORD_TABLES.items():
            branch = f"SELECT '{key}' AS kind, COUNT(*) AS count FROM uranus.{table} r WHERE "
            branch += (
                "r.created_at >= :start_at AND r.created_at < :end_at"
                if is_utc
                else "r.created_at AT TIME ZONE :source_timezone >= :start_at AND "
                "r.created_at AT TIME ZONE :source_timezone < :end_at"
            )
            if table in SPATIAL_TYPES:
                branch += " AND " + spatial_predicate(table, key_expression="r.uuid")
            queries.append(branch)
        sql = " UNION ALL ".join(queries)
    params = {
        "start_at": window.start.astimezone(UTC).replace(tzinfo=None) if is_utc else window.start,
        "end_at": window.end.astimezone(UTC).replace(tzinfo=None) if is_utc else window.end,
        "source_timezone": source_timezone,
        "geo_scope_wkb": geo_scope_wkb,
    }
    return {
        "new_records": ReadQuery(text(sql), params),
        "unknown_images": ReadQuery(
            text("SELECT COUNT(*) FROM uranus.pluto_image WHERE created_at IS NULL")
        ),
    }


async def new_records(
    connection: AsyncConnection,
    window: PeriodWindow,
    source_timezone: str,
    geo_scope_wkb: bytes | None = None,
) -> tuple[dict[str, int], int]:
    queries = new_record_queries(window, source_timezone, geo_scope_wkb)
    result = await connection.execute(
        queries["new_records"].statement, queries["new_records"].parameters
    )
    counts = {row["kind"]: int(row["count"]) for row in result.mappings()}
    unknown = int((await connection.execute(queries["unknown_images"].statement)).scalar_one())
    return counts, unknown


async def check_status(connection: AsyncConnection) -> DashboardCheckStatus:
    """Two bounded lookups; status is current stock, independent of the dashboard period."""
    queries = check_status_queries()
    latest = (await connection.execute(queries["latest_run"].statement)).mappings().first()
    successful = (
        (await connection.execute(queries["last_successful_run"].statement)).mappings().first()
    )
    return DashboardCheckStatus(
        latest_run=DashboardCheckRun.model_validate(latest) if latest else None,
        last_successful_run=DashboardCheckRun.model_validate(successful) if successful else None,
    )


def check_status_queries() -> dict[str, ReadQuery]:
    return {
        "latest_run": ReadQuery(
            select(check_run)
            .order_by(check_run.c.started_at.desc(), check_run.c.id.desc())
            .limit(1)
        ),
        "last_successful_run": ReadQuery(
            select(check_run)
            .where(check_run.c.status == "success")
            .order_by(check_run.c.finished_at.desc().nulls_last(), check_run.c.id.desc())
            .limit(1)
        ),
    }
