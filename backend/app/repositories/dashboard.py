from datetime import UTC

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services.periods import PeriodWindow

# Identifiers are fixed source-code constants, never request/configuration values.
RECORD_TABLES = {
    "organizations": "organization",
    "venues": "venue",
    "spaces": "space",
    "events": "event",
    "event_dates": "event_date",
    "users": '"user"',
    "partner_requests": "organization_partner_request",
    "team_memberships": "organization_member_link",
    "images": "pluto_image",
}
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


async def new_records(
    connection: AsyncConnection, window: PeriodWindow, source_timezone: str
) -> tuple[dict[str, int], int]:
    is_utc = source_timezone == "UTC"
    result = await connection.execute(
        text(NEW_RECORDS_UTC_SQL if is_utc else NEW_RECORDS_LOCAL_SQL),
        {
            "start_at": window.start.astimezone(UTC).replace(tzinfo=None)
            if is_utc
            else window.start,
            "end_at": window.end.astimezone(UTC).replace(tzinfo=None) if is_utc else window.end,
            "source_timezone": source_timezone,
        },
    )
    counts = {row["kind"]: int(row["count"]) for row in result.mappings()}
    unknown = int(
        (
            await connection.execute(
                text("SELECT COUNT(*) FROM uranus.pluto_image WHERE created_at IS NULL")
            )
        ).scalar_one()
    )
    return counts, unknown
