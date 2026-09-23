from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.admin_database import connect_admin
from app.database import ConnectionDep, SettingsDep
from app.repositories.entities import entity_detail, entity_page, workflow_counts
from app.repositories.entity_search import entity_search, global_search
from app.schemas.entities import (
    EntityDetail,
    EntityFilters,
    EntityPage,
    EntitySearchFilters,
    EntitySearchResponse,
    EntitySection,
)
from app.schemas.search import GlobalSearchFilters, GlobalSearchResponse
from app.services.geo.scopes import request_geo_scope

router = APIRouter(tags=["Domain records"])


@router.get("/entity-search", response_model=EntitySearchResponse)
async def search(
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[EntitySearchFilters, Query()],
) -> EntitySearchResponse:
    scope = await request_geo_scope(request, filters.geo_scope_id)
    return await entity_search(
        connection, filters, settings, datetime.now(UTC), scope.ewkb if scope else None
    )


@router.get("/search", response_model=GlobalSearchResponse)
async def search_globally(
    connection: ConnectionDep,
    filters: Annotated[GlobalSearchFilters, Query()],
) -> GlobalSearchResponse:
    return await global_search(connection, filters)


# Register six explicit endpoints; no catch-all source table or arbitrary projection.
def register(section: EntitySection) -> None:
    async def listing(
        request: Request,
        connection: ConnectionDep,
        settings: SettingsDep,
        filters: Annotated[EntityFilters, Query()],
    ) -> EntityPage:
        scope = await request_geo_scope(request, filters.geo_scope_id)
        result = await entity_page(
            connection, settings, section, filters, datetime.now(UTC), scope.ewkb if scope else None
        )
        if settings.admin_database_url is not None:
            async with connect_admin(request) as admin:
                await workflow_counts(admin, result.items)
        return result

    async def detail(
        request: Request,
        key: UUID,
        connection: ConnectionDep,
        settings: SettingsDep,
        related_page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    ) -> EntityDetail:
        result = await entity_detail(
            connection, settings, section, key, related_page, datetime.now(UTC)
        )
        if settings.admin_database_url is not None:
            async with connect_admin(request) as admin:
                await workflow_counts(admin, [result.item])
        return result

    router.add_api_route(
        f"/{section}",
        listing,
        methods=["GET"],
        response_model=EntityPage,
        summary=f"List {section}",
        description="Read-only source records with bounded previews.",
        operation_id=f"list_{section}",
    )
    router.add_api_route(
        f"/{section}/{{key}}",
        detail,
        methods=["GET"],
        response_model=EntityDetail,
        summary=f"Read {section} detail",
        description="Safe metadata and paginated source relations.",
        operation_id=f"detail_{section}",
    )


for section in ("events", "venues", "spaces", "organizations", "users", "images"):
    register(section)
