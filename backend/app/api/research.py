"""Dedicated read-only research routes, independently authorized from Operations."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_research_user
from app.database import ConnectionDep, SettingsDep
from app.errors import ErrorResponse
from app.repositories.research import (
    research_detail,
    research_export,
    research_options,
    research_page,
)
from app.schemas.research import (
    ResearchDetail,
    ResearchExport,
    ResearchFilters,
    ResearchOptions,
    ResearchPage,
    ResearchType,
)

router = APIRouter(
    prefix="/api/v1/research",
    tags=["Research"],
    dependencies=[Depends(get_current_research_user)],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422, 503)},
)


@router.get("/search", response_model=ResearchPage)
async def search(
    connection: ConnectionDep, settings: SettingsDep, filters: Annotated[ResearchFilters, Query()]
) -> ResearchPage:
    return await research_page(connection, settings, filters, datetime.now(UTC))


@router.get("/export", response_model=ResearchExport)
async def export(
    connection: ConnectionDep, settings: SettingsDep, filters: Annotated[ResearchFilters, Query()]
) -> ResearchExport:
    """All filtered records in one snapshot; reject oversized exports, never truncate."""
    return await research_export(connection, settings, filters, datetime.now(UTC))


@router.get("/options", response_model=ResearchOptions)
async def options(connection: ConnectionDep) -> ResearchOptions:
    return await research_options(connection)


# Explicit collection routes follow the existing entity router registration pattern.
def register(section: str, kind: ResearchType) -> None:
    async def listing(
        connection: ConnectionDep,
        settings: SettingsDep,
        filters: Annotated[ResearchFilters, Query()],
    ) -> ResearchPage:
        return await research_page(
            connection,
            settings,
            filters.model_copy(update={"entity_type": kind}),
            datetime.now(UTC),
        )

    async def detail(
        key: UUID,
        connection: ConnectionDep,
        settings: SettingsDep,
        filters: Annotated[ResearchFilters, Query()],
    ) -> ResearchDetail:
        return await research_detail(connection, settings, kind, key, filters, datetime.now(UTC))

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
