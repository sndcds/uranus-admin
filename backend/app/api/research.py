"""Research routes with source read-only access and admin-only suggestion learning."""

from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import TypeAdapter

from app.admin_database import AdminConnectionDep
from app.auth.dependencies import get_current_research_user
from app.database import ConnectionDep, SettingsDep
from app.errors import ErrorResponse
from app.repositories import research_suggestions
from app.repositories.research import (
    research_activity,
    research_detail,
    research_export,
    research_options,
    research_page,
)
from app.repositories.research_areas import area_metadata, area_page, request_area
from app.research.context import ResearchExecutionContext
from app.research.geography import location_sensitive
from app.research.normalize import normalize
from app.schemas.research import (
    ResearchDetail,
    ResearchExport,
    ResearchFilters,
    ResearchOptions,
    ResearchPage,
    ResearchType,
    SemanticResearchFilters,
    SemanticResearchPage,
)
from app.schemas.research_administrative_result import AdministrativeResult
from app.schemas.research_areas import AreaDossier, AreaFilters, AreaPage, ResearchArea
from app.schemas.research_location import ResearchQueryRequest
from app.schemas.research_planner import PlanResponse, ResearchPlanRequest
from app.schemas.research_response import ResearchExecutionResponse
from app.schemas.research_suggestions import (
    Impression,
    Selection,
    SuggestionFilters,
    Suggestions,
    TelemetryResult,
)
from app.schemas.research_unified import UnifiedAnswer
from app.services.research_administrative import execute as execute_administrative
from app.services.research_learning import record_success
from app.services.research_plan_execution import ResearchPlanExecutor
from app.services.research_planner import ResearchPlannerClient, unavailable
from app.services.research_unified import execute as execute_unified
from app.services.semantic_search import semantic_search

router = APIRouter(
    prefix="/api/v1/research",
    tags=["Research"],
    dependencies=[Depends(get_current_research_user)],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422, 503)},
)


@router.post(
    "/plan",
    response_model=PlanResponse,
    responses={code: {"model": ErrorResponse} for code in (413, 502)},
)
async def plan(request: Request, body: ResearchPlanRequest) -> PlanResponse:
    """Interpret a research question; no source or vector retrieval and no plan execution."""
    planner: ResearchPlannerClient | None = request.app.state.research_planner
    if planner is None:
        raise unavailable()
    response = await planner.plan(body.query)
    return TypeAdapter(PlanResponse).validate_json(response.model_dump_json())


@router.post(
    "/query",
    response_model=ResearchExecutionResponse,
    responses={code: {"model": ErrorResponse} for code in (413, 502)},
)
async def query(
    request: Request,
    body: ResearchQueryRequest,
    settings: SettingsDep,
    x_research_selection: Annotated[UUID | None, Header()] = None,
) -> ResearchExecutionResponse:
    planner: ResearchPlannerClient | None = request.app.state.research_planner
    if planner is None:
        raise unavailable()
    started = perf_counter()
    response = (
        await planner.plan(body.query, geographic=True)
        if settings.research_geocoder_api_key
        else await planner.plan(body.query, analytical=True)
        if settings.research_analytics_enabled
        else await planner.plan(body.query)
    )
    planner_ms = (perf_counter() - started) * 1000
    internal = normalize(response)
    context = ResearchExecutionContext(
        reference_date=response.reference_date,
        timezone=response.timezone,
        original_query=response.plan.original_query,
        location_context=body.location_context,
    )
    outcome = await ResearchPlanExecutor().execute(
        request,
        settings,
        internal,
        context,
        planner_ms=planner_ms,
    )
    result = ResearchExecutionResponse(
        query=context.original_query,
        plan=response,
        resolution=outcome.resolution,
        result=outcome.result,
        execution=outcome.execution,
        sql_provenance=outcome.sql_provenance,
        observed_at=outcome.observed_at,
        timezone=context.timezone,
        diagnostics=outcome.diagnostics,
    )
    sensitive_location = context.location_context is not None or (
        location_sensitive(internal.spatial_constraints)
    )
    if not sensitive_location:
        await record_success(request, result, x_research_selection)
    return result


@router.get("/search", response_model=ResearchPage)
async def search(
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[ResearchFilters, Query()],
) -> ResearchPage:
    return await research_page(
        connection,
        settings,
        filters,
        datetime.now(UTC),
        await request_area(request, filters.area_id),
    )


@router.get("/semantic-search", response_model=SemanticResearchPage)
async def semantic(
    request: Request,
    settings: SettingsDep,
    filters: Annotated[SemanticResearchFilters, Query()],
) -> SemanticResearchPage:
    """Experimental event-only retrieval; repeated area_ids are ORed at rehydration."""
    return await semantic_search(request, settings, filters)


@router.get("/export", response_model=ResearchExport)
async def export(
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[ResearchFilters, Query()],
) -> ResearchExport:
    """All filtered records in one snapshot; reject oversized exports, never truncate."""
    return await research_export(
        connection,
        settings,
        filters,
        datetime.now(UTC),
        await request_area(request, filters.area_id),
    )


@router.get("/options", response_model=ResearchOptions)
async def options(connection: ConnectionDep) -> ResearchOptions:
    return await research_options(connection)


# Explicit collection routes follow the existing entity router registration pattern.
def register(section: str, kind: ResearchType) -> None:
    async def listing(
        request: Request,
        connection: ConnectionDep,
        settings: SettingsDep,
        filters: Annotated[ResearchFilters, Query()],
    ) -> ResearchPage:
        return await research_page(
            connection,
            settings,
            filters.model_copy(update={"entity_type": kind}),
            datetime.now(UTC),
            await request_area(request, filters.area_id),
        )

    async def detail(
        request: Request,
        key: UUID,
        connection: ConnectionDep,
        settings: SettingsDep,
        filters: Annotated[ResearchFilters, Query()],
    ) -> ResearchDetail:
        return await research_detail(
            connection,
            settings,
            kind,
            key,
            filters,
            datetime.now(UTC),
            await request_area(request, filters.area_id),
        )

    router.add_api_route(
        f"/{section}",
        listing,
        methods=["GET"],
        response_model=ResearchPage,
        operation_id=f"research_list_{section}",
    )
    router.add_api_route(
        f"/{section}/{{key}}",
        detail,
        methods=["GET"],
        response_model=ResearchDetail,
        operation_id=f"research_detail_{section}",
    )


register("events", "event")
register("venues", "venue")
register("organizations", "organization")


@router.get("/areas", response_model=AreaPage)
async def areas(admin: AdminConnectionDep, filters: Annotated[AreaFilters, Query()]) -> AreaPage:
    return await area_page(admin, filters)


@router.get("/areas/{identifier}", response_model=AreaDossier)
async def area_detail(
    identifier: UUID,
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[ResearchFilters, Query()],
) -> AreaDossier:
    resolved = await request_area(request, identifier, boundary=True)
    assert resolved is not None and resolved.geometry is not None
    selected = filters.model_copy(update={"area_id": identifier})
    now = datetime.now(UTC)
    events = await research_page(
        connection, settings, selected.model_copy(update={"entity_type": "event"}), now, resolved
    )
    venues = await research_page(
        connection, settings, selected.model_copy(update={"entity_type": "venue"}), now, resolved
    )
    organizations = await research_page(
        connection,
        settings,
        selected.model_copy(update={"entity_type": "organization"}),
        now,
        resolved,
    )
    months, usage = await research_activity(connection, settings, selected, resolved)
    return AreaDossier(
        area=resolved.area,
        geometry=resolved.geometry,
        events=events,
        venues=venues,
        organizations=organizations,
        months=months,
        usage=usage,
        observed_at=now,
    )


@router.get("/areas/{identifier}/metadata", response_model=ResearchArea)
async def selected_area(identifier: UUID, admin: AdminConnectionDep) -> ResearchArea:
    return await area_metadata(admin, identifier)


@router.post(
    "/v4/query",
    response_model=UnifiedAnswer,
    responses={code: {"model": ErrorResponse} for code in (413, 502)},
)
async def unified_query(
    request: Request, body: ResearchPlanRequest, settings: SettingsDep
) -> UnifiedAnswer:
    return await execute_unified(request, settings, body.query)


@router.get("/suggestions", response_model=Suggestions)
async def suggestions(
    admin: AdminConnectionDep, filters: Annotated[SuggestionFilters, Query()]
) -> Suggestions:
    """Rank learned questions using only admin PostgreSQL data."""
    return await research_suggestions.lookup(admin, filters)


@router.post("/suggestions/impression", response_model=TelemetryResult)
async def suggestion_impression(admin: AdminConnectionDep, body: Impression) -> TelemetryResult:
    async with admin.begin():
        await research_suggestions.impression(admin, body)
    return TelemetryResult()


@router.post("/suggestions/select", response_model=TelemetryResult)
async def suggestion_select(admin: AdminConnectionDep, body: Selection) -> TelemetryResult:
    async with admin.begin():
        receipt = await research_suggestions.select(admin, body)
    return TelemetryResult(receipt=receipt)


@router.post(
    "/v8/query",
    response_model=AdministrativeResult,
    responses={code: {"model": ErrorResponse} for code in (413, 502)},
)
async def administrative_query(
    request: Request, body: ResearchPlanRequest, settings: SettingsDep
) -> AdministrativeResult:
    """Resolve administrative geography and execute a validated internal plan."""
    return await execute_administrative(request, settings, body.query)
