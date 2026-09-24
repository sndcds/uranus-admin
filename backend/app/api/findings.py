from contextlib import aclosing
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select, tuple_

from app.admin_database import connect_admin
from app.admin_tables import geocode_request
from app.database import SettingsDep, get_connection
from app.errors import APIError
from app.repositories.query import ReadQuery
from app.schemas.finding import FindingFilters, FindingPage
from app.services.checks import persisted_page
from app.services.finding_previews import enrich_images, image_identities
from app.services.geo.scopes import request_geo_scope
from app.services.quality.engine import get_findings

router = APIRouter(tags=["Findings"])


@router.get(
    "/findings",
    response_model=FindingPage,
    summary="List persisted or explicit live quality findings",
    description="Defaults to persisted findings without a source scan. Explicit mode=live runs "
    "a full diagnostic scan. Only open findings exist in live mode; "
    "other status filters return an empty live result, not historical workflow data. "
    "active_only=true excludes resolved findings and combines with other filters. "
    "Ordered by priority_score descending and stable finding ID. "
    "Public record thumbnails are enriched for the current page using a bounded source read.",
)
async def findings(
    request: Request,
    settings: SettingsDep,
    filters: Annotated[FindingFilters, Query()],
) -> FindingPage:
    if filters.cursor is not None and (
        "page" in request.query_params or filters.mode != "persisted"
    ):
        raise APIError(
            422, "invalid_input", "Cursor pagination requires persisted mode without page."
        )
    geo = await request_geo_scope(request, filters.geo_scope_id)
    if filters.mode == "persisted" and geo is None:
        async with connect_admin(request) as admin:
            page = await persisted_page(admin, filters, datetime.now(UTC))
        if image_identities(page.items, settings):
            async with aclosing(get_connection(request)) as connections:
                await enrich_images(
                    await anext(connections), settings, page.items, datetime.now(UTC)
                )
        return await with_suggestions(request, page)
    async with aclosing(get_connection(request)) as connections:
        connection = await anext(connections)
        if filters.mode == "persisted":
            async with connect_admin(request) as admin:
                page = await persisted_page(
                    admin, filters, datetime.now(UTC), connection, geo.ewkb if geo else None
                )
            await enrich_images(connection, settings, page.items, datetime.now(UTC))
            return await with_suggestions(request, page)
        page = await get_findings(
            connection, settings, filters, datetime.now(UTC), geo.ewkb if geo else None
        )
        await enrich_images(connection, settings, page.items, datetime.now(UTC))
        return await with_suggestions(request, page)


async def with_suggestions(request: Request, page: FindingPage) -> FindingPage:
    identities = []
    for item in page.items:
        if item.rule in {"organization_missing_location", "venue_missing_location"}:
            try:
                identities.append((item.entity_type, UUID(item.entity_key)))
            except ValueError:
                continue
    if not identities or request.app.state.admin_engine is None:
        return page
    query = suggestions_query(identities)
    async with connect_admin(request) as admin:
        rows = (await admin.execute(query.statement, query.parameters)).mappings()
        by_entity = {(row["entity_type"], str(row["entity_key"])): row["id"] for row in rows}
    for item in page.items:
        if item.rule in {"organization_missing_location", "venue_missing_location"}:
            item.location_suggestion_request_id = by_entity.get((item.entity_type, item.entity_key))
    return page


def suggestions_query(identities: list[tuple[str, UUID]]) -> ReadQuery:
    return ReadQuery(
        select(
            geocode_request.c.id,
            geocode_request.c.entity_type,
            geocode_request.c.entity_key,
        ).where(
            tuple_(geocode_request.c.entity_type, geocode_request.c.entity_key).in_(identities)
        ),
        {},
    )
