"""Explicit typed read-view routes; the browser selects registered IDs, never SQL."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from pydantic import BaseModel

from app.auth.dependencies import get_current_admin
from app.auth.service import AdminPrincipal
from app.database import SettingsDep
from app.errors import APIError, ErrorResponse
from app.sql_diagnostics.provenance.models import ProvenanceDefinition, ProvenanceResult
from app.sql_diagnostics.provenance.registry import MODELS
from app.sql_diagnostics.provenance.service import definition, execute

router = APIRouter(
    prefix="/sql-provenance",
    tags=["SQL Provenance"],
    responses={409: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)


def register(view: str, model: type[BaseModel]) -> None:
    async def inspect(request: Request, settings: SettingsDep, params: Any) -> ProvenanceDefinition:
        if len(request.query_params.multi_items()) != len(request.query_params):
            raise APIError(422, "invalid_input", "Duplicate query parameters are not accepted.")
        if request.query_params.get("cursor") and "page" in request.query_params:
            raise APIError(422, "invalid_input", "Choose page or cursor.")
        return definition(view, params, settings)

    async def run(
        request: Request,
        source_id: Annotated[str, Path(max_length=150, pattern=r"^[a-z_0-9.-]+$")],
        settings: SettingsDep,
        params: Any,
        principal: Annotated[AdminPrincipal, Depends(get_current_admin)],
    ) -> ProvenanceResult:
        if request.query_params:
            raise APIError(422, "invalid_input", "Execute accepts only the typed view body.")
        return await execute(request, view, source_id, params, settings, principal.subject)

    # FastAPI receives the concrete registered model, not an unvalidated dictionary.
    inspect.__annotations__["params"] = Annotated[model, Query()]
    run.__annotations__["params"] = Annotated[model, Body()]
    router.add_api_route(
        "/" + view,
        inspect,
        methods=["GET"],
        response_model=ProvenanceDefinition,
        operation_id="provenance_" + view.replace(".", "_"),
    )
    router.add_api_route(
        "/" + view + "/{source_id}/execute",
        run,
        methods=["POST"],
        response_model=ProvenanceResult,
        operation_id="execute_provenance_" + view.replace(".", "_"),
    )


for view, model in MODELS.items():
    register(view, model)
