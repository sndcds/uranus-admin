"""Operator-invoked source catalog audit; never infers timestamp storage semantics."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.database import create_engine

TABLES = (
    "venue",
    "space",
    "space_feature_link",
    "organization_partner_request",
    "organization_member_link",
    "user_organization_link",
    "user_venue_link",
    "user_space_link",
    "user_event_link",
    "organization",
    "user",
    "event",
    "event_date",
    "pluto_image",
    "pluto_image_link",
)


async def verify(connection: AsyncConnection, settings: Settings) -> dict[str, Any]:
    """Call within a read-only transaction. Report metadata, never arbitrary domain rows."""
    columns = (
        (
            await connection.execute(
                text("""
        SELECT table_name, column_name, data_type, udt_name, column_default, is_nullable
        FROM information_schema.columns
        WHERE table_schema='uranus' AND table_name=ANY(:tables)
        ORDER BY table_name, ordinal_position
    """),
                {"tables": list(TABLES)},
            )
        )
        .mappings()
        .all()
    )
    constraints = (
        (
            await connection.execute(
                text("""
        SELECT c.relname table_name, k.conname name, k.contype::text kind,
               pg_get_constraintdef(k.oid) definition
        FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='uranus' AND c.relname=ANY(:tables)
        ORDER BY c.relname,k.conname
    """),
                {"tables": list(TABLES)},
            )
        )
        .mappings()
        .all()
    )
    indexes = (
        (
            await connection.execute(
                text("""
        SELECT tablename table_name, indexname name, indexdef definition
        FROM pg_indexes WHERE schemaname='uranus' AND tablename=ANY(:tables)
        ORDER BY tablename,indexname
    """),
                {"tables": list(TABLES)},
            )
        )
        .mappings()
        .all()
    )
    available = {(row["table_name"], row["column_name"]) for row in columns}
    observations: dict[str, Any] = {}
    for table, field in (("venue", "scope"), ("organization_partner_request", "status")):
        if (table, field) in available:
            values = (
                (
                    await connection.execute(
                        text(
                            f'SELECT left("{field}"::text,80) AS value, '
                            f'coalesce(bool_or(length("{field}"::text)>80),false) '
                            "AS value_truncated "
                            f'FROM uranus."{table}" GROUP BY left("{field}"::text,80) '
                            "ORDER BY value NULLS LAST LIMIT 101"
                        )
                    )
                )
                .mappings()
                .all()
            )
            observations[f"{table}.{field}"] = {
                "values": [row["value"] for row in values[:100]],
                "truncated": len(values) > 100,
                "values_truncated": any(row["value_truncated"] for row in values[:100]),
            }
        else:
            observations[f"{table}.{field}"] = {"missing": True}
    return {
        "database": (await connection.execute(text("SELECT current_database()"))).scalar_one(),
        "verified_at": datetime.now(UTC).isoformat(),
        "transaction_read_only": (
            await connection.execute(text("SELECT current_setting('transaction_read_only')"))
        ).scalar_one()
        == "on",
        "uranus_timestamp_timezone": settings.uranus_timestamp_timezone,
        "timestamp_note": (
            "Database type does not establish storage timezone; operator confirmation required."
        ),
        "missing_tables": sorted(set(TABLES) - {row["table_name"] for row in columns}),
        "columns": [dict(row) for row in columns],
        "constraints": [dict(row) for row in constraints],
        "indexes": [dict(row) for row in indexes],
        "observed_values": observations,
    }


async def run(settings: Settings) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            return await verify(connection, settings)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()
    try:
        report = asyncio.run(run(Settings()))
    except Exception:
        print(
            "Source verification failed; check the read-only connection and source catalog access."
        )
        return 1
    if not args.json:
        print("Read-only source schema verification")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
