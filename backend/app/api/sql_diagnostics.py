"""Resolve persisted or canonical live identities to fixed read-only diagnostics."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.admin_database import connect_admin
from app.admin_tables import finding
from app.auth.dependencies import get_current_admin
from app.auth.service import AdminPrincipal
from app.database import SettingsDep
from app.errors import APIError, ErrorResponse
from app.sql_diagnostics.executor import definition, execute
from app.sql_diagnostics.identity import live_finding
from app.sql_diagnostics.models import (
    DiagnosticRequest,
    SqlDiagnosticDefinition,
    SqlDiagnosticResult,
    StoredFinding,
)

router = APIRouter(tags=["Finding SQL diagnostics"], responses={504: {"model": ErrorResponse}})


async def load_finding(request: Request, identity: str) -> StoredFinding:
    try:
        async with connect_admin(request) as connection:
            row = (
                (
                    await connection.execute(
                        select(
                            finding.c.id,
                            finding.c.rule,
                            finding.c.entity_type,
                            finding.c.entity_key.label("entity_key"),
                            finding.c.field,
                            finding.c.last_seen_at,
                        ).where(finding.c.id == identity)
                    )
                )
                .mappings()
                .one_or_none()
            )
    except SQLAlchemyError:
        raise APIError(503, "diagnostic_failed", "Diagnostic unavailable.") from None
    if row is None:
        raise APIError(404, "diagnostic_unavailable", "Persisted finding unavailable.")
    return StoredFinding(**row)


@router.get(
    "/findings/sql-diagnostic",
    response_model=SqlDiagnosticDefinition,
    description=(
        "Inspect a registered diagnostic for a persisted finding (default) or a canonical "
        "live finding identity. Does not execute source SQL or establish current rule status."
    ),
)
async def get_definition(
    request: Request, filters: Annotated[DiagnosticRequest, Query()]
) -> SqlDiagnosticDefinition:
    context = (
        live_finding(filters.finding_id)
        if filters.mode == "live"
        else await load_finding(request, filters.finding_id)
    )
    return definition(context)


@router.post(
    "/findings/sql-diagnostic/execute",
    response_model=SqlDiagnosticResult,
    description=(
        "Execute the server-registered read-only diagnostic. "
        "Accepts a persisted finding ID (default) or a canonical live finding identity. "
        "Only registered recipes and typed identity parameters; no SQL overrides."
    ),
)
async def run_diagnostic(
    request: Request,
    body: DiagnosticRequest,
    settings: SettingsDep,
    principal: Annotated[AdminPrincipal, Depends(get_current_admin)],
) -> SqlDiagnosticResult:
    if request.query_params:
        raise APIError(422, "invalid_input", "Query parameters are not accepted.")
    stored = (
        live_finding(body.finding_id)
        if body.mode == "live"
        else await load_finding(request, body.finding_id)
    )
    return await execute(request.app.state.engine, stored, settings, principal.subject)
