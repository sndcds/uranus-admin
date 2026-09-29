"""Dedicated read-only research routes, independently authorized from Operations."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.admin_database import AdminConnectionDep
from app.auth.dependencies import get_current_research_user
from app.database import ConnectionDep, SettingsDep
from app.errors import ErrorResponse
from app.repositories.research import (
    research_activity,
    research_detail,
    research_export,
    research_options,
    research_page,
)
from app.repositories.research_areas import area_metadata, area_page, request_area
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
from app.schemas.research_areas import AreaDossier, AreaFilters, AreaPage, ResearchArea
from app.services.semantic_search import semantic_search

router = APIRouter(
    prefix="/api/v1/research",
    tags=["Research"],
    dependencies=[Depends(get_current_research_user)],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422, 503)},
)


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
