"""Literal rendering is for copying only; execution always binds values separately."""

import math
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import bindparam, literal, text
from sqlalchemy.dialects.postgresql import dialect as PGDialect


def copy_sql(sql: str, parameters: dict[str, object]) -> str:
    allowed = (UUID, int, str, bool, date, datetime)
    if any(type(value) not in allowed for value in parameters.values()):
        raise ValueError("Unsupported diagnostic parameter type")
    statement = text(sql).bindparams(
        *(
            bindparam(key, value=value, type_=literal(value).type)
            for key, value in parameters.items()
        )
    )
    # PostgreSQL's default standard_conforming_strings; no home-grown replacement.
    dialect = PGDialect(paramstyle="named")  # type: ignore[no-untyped-call]
    dialect._backslash_escapes = False
    return (
        str(
            statement.compile(
                dialect=dialect,
                compile_kwargs={"literal_binds": True},
            )
        )
        + ";"
    )


def json_value(value: object, *, url: bool = False) -> JsonValue:
    if value is None or type(value) in (bool, int):
        return value  # type: ignore[return-value]
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, str):
        if len(value) > 4096:
            raise ValueError("Diagnostic cell exceeds limit")
        # URL credentials/query/fragment values may contain tokens. Evaluate the
        # original only inside the server, return no such values to the browser.
        if url and any(marker in value for marker in ("@", "?", "#")):
            return "[URL mit möglicherweise sensiblen Bestandteilen ausgeblendet]"
        return value
    raise ValueError("Unsupported diagnostic result type")
