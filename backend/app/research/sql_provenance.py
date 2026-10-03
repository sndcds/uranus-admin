"""Opt-in source execution capture, never a SQLAlchemy listener or query logger.

Only explicitly instrumented Research repository calls participate. The context is
local to one awaited execution and is reset on success, error and cancellation.
Only safe display values enter the collector; original bindings are never mutated.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time
from math import isfinite
from typing import Any
from uuid import UUID

from sqlalchemy import Result
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.elements import TextClause

from app.schemas.research_sql import (
    MAX_SQL_NUMBER,
    ResearchSqlKind,
    ResearchSqlStatement,
    SqlScalar,
    SqlValue,
)

LOCATION_REDACTED = "[Standort ausgeblendet]"
VALUE_REDACTED = "[Wert ausgeblendet]"
# Explicit allowlist: new parameters must be reviewed before becoming browser-visible.
PUBLIC_PARAMETERS = frozenset(
    {
        "q",
        "city",
        "tz",
        "entity_type",
        "from_date",
        "to_date",
        "time_from",
        "time_of_day",
        "weekdays",
        "months",
        "area_relation",
        "event_type_ids",
        "category_ids",
        "genre_keys",
        "category_id",
        "venue_id",
        "organization_id",
        "key",
        "page_size",
        "offset",
        "candidate_ids",
        "eligibility_probe_limit",
        "aggregate_limit",
        "chronological_limit",
        "taxonomy_limit",
        "spatial_limit",
        "rank_limit",
        "limit",
        "kinds",
        "ids",
        "place_mode",
        "place_radius",
    }
)
LOCATION_PARAMETERS = frozenset({"area_wkb", "constraints", "inventory"})
_current: ContextVar[list[ResearchSqlStatement] | None] = ContextVar("research_sql", default=None)


def scalar(value: object) -> SqlScalar:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) <= MAX_SQL_NUMBER else VALUE_REDACTED
    if isinstance(value, float):
        return value if isfinite(value) and abs(value) <= MAX_SQL_NUMBER else VALUE_REDACTED
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str) and len(value) <= 4096:
        return value
    return VALUE_REDACTED


def safe_value(name: str, value: object) -> SqlValue:
    if name in LOCATION_PARAMETERS or (name.startswith("place_") and name not in PUBLIC_PARAMETERS):
        return None if value is None else LOCATION_REDACTED
    if name not in PUBLIC_PARAMETERS:
        return VALUE_REDACTED
    if isinstance(value, (list, tuple)):
        return [scalar(item) for item in value] if len(value) <= 100 else VALUE_REDACTED
    return scalar(value)


@contextmanager
def collect_research_sql() -> Iterator[list[ResearchSqlStatement]]:
    statements: list[ResearchSqlStatement] = []
    token = _current.set(statements)
    try:
        yield statements
    finally:
        _current.reset(token)


async def execute_research_sql(
    connection: AsyncConnection,
    statement: TextClause,
    parameters: Mapping[str, Any],
    *,
    label: str = "Ergebnisabfrage",
    kind: ResearchSqlKind = "execution",
) -> Result[Any]:
    result = await connection.execute(statement, parameters)
    statements = _current.get()
    if statements is not None:
        # SQLAlchemy's public compilation API identifies effective binds, excluding
        # unused filter metadata. The exact TextClause and mapping above are executed.
        bound = statement.compile().params
        statements.append(
            ResearchSqlStatement(
                label=label[:200],
                kind=kind,
                sql=statement.text,
                parameters={
                    name: safe_value(name, parameters.get(name, value))
                    for name, value in bound.items()
                },
            )
        )
    return result
