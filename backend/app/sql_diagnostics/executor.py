import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.errors import APIError
from app.sql_diagnostics.evaluation import evaluate
from app.sql_diagnostics.models import SqlDiagnosticDefinition, SqlDiagnosticResult, StoredFinding
from app.sql_diagnostics.registry import HARD_MAX_ROWS, parameters_for, resolve
from app.sql_diagnostics.render import copy_sql, json_value


def definition(finding: StoredFinding) -> SqlDiagnosticDefinition:
    item = resolve(finding)
    parameters = parameters_for(finding)
    return SqlDiagnosticDefinition(
        recipe_id=item.id,
        title=item.title,
        sql=item.sql,
        copy_sql=copy_sql(item.sql, dict(parameters)),
        parameters={key: json_value(value) for key, value in parameters.items()},
        explanation=item.explanation,
        columns=list(item.result_fields),
        last_seen_at=finding.last_seen_at,
    )


async def execute(
    engine: AsyncEngine, finding: StoredFinding, settings: Settings, actor_subject: str
) -> SqlDiagnosticResult:
    started = perf_counter()
    count = 0
    recipe_id = "unavailable"
    category = "diagnostic_failed"
    try:
        item = resolve(finding)
        recipe_id = item.id
        parameters = parameters_for(finding)
        # Bound pool acquisition + execution + rendering. Per-query DB timeout is
        # stricter; timeout/cancellation always exits through rollback and close.
        async with asyncio.timeout(8), engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                await connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                await connection.execute(text("SET LOCAL lock_timeout = '1000ms'"))
                await connection.execute(
                    text("SET LOCAL idle_in_transaction_session_timeout = '10000ms'")
                )
                now = datetime.now(UTC)
                rows = [
                    dict(row)
                    for row in (await connection.execute(text(item.sql), parameters)).mappings()
                ]
                if len(rows) > HARD_MAX_ROWS:
                    raise ValueError("Diagnostic row limit exceeded")
                if any(set(row) != set(item.result_fields) for row in rows):
                    raise ValueError("Unexpected diagnostic projection")
                evaluation = evaluate(finding, rows, settings, now)
                safe_rows = [
                    {
                        key: json_value(row[key], url=key.endswith("_link"))
                        for key in item.result_fields
                    }
                    for row in rows
                ]
                if len(json.dumps(safe_rows).encode()) > 256 * 1024:
                    raise ValueError("Diagnostic result exceeds limit")
            finally:
                await transaction.rollback()
        count = len(safe_rows)
        category = "success"
        return SqlDiagnosticResult(
            recipe_id=item.id,
            columns=list(item.result_fields),
            rows=safe_rows,
            row_count=count,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            observed_at=now,
            evaluation=evaluation,
        )
    except APIError:
        category = "diagnostic_unavailable"
        raise
    except Exception as exc:
        # Never stringify DB exceptions, which can contain source values even with
        # hide_parameters enabled. Suppress chaining, including debug tracebacks.
        code = getattr(getattr(exc, "orig", None), "sqlstate", None)
        timeout = isinstance(exc, TimeoutError) or code in {"57014", "55P03"}
        category = "diagnostic_timeout" if timeout else "diagnostic_failed"
        raise APIError(
            504 if timeout else 503,
            category,
            "Diagnostic timed out." if timeout else "Diagnostic failed.",
        ) from None
    finally:
        logging.getLogger("admin.sql_diagnostics").info(
            "sql_diagnostic",
            extra={
                "actor_subject": actor_subject,
                "recipe_id": recipe_id,
                "finding_id_hash": hashlib.sha256(finding.id.encode()).hexdigest(),
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "row_count": count,
                "error_type": category,
            },
        )
