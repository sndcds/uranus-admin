"""Venue scope is source data, never inferred from ownership or parent venues."""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import event, text

from app.database import get_connection
from app.main import create_app
from app.repositories.entity_search import entity_search, global_search
from app.schemas.action import Action
from app.schemas.activity import Activity
from app.schemas.entities import EntityRecord, EntitySearchFilters, EntitySearchItem
from app.schemas.graph import GraphNode
from app.schemas.search import GlobalSearchFilters, GlobalSearchItem
from app.schemas.statistics import RecentEntity
from tests.conftest import uid


def record_values():
    return {
        "entity_type": "venue",
        "entity_key": str(uid(20)),
        "entity_name": "Venue",
        "organization_id": str(uid(10)),
        "organization_name": "Organization",
        "created_at": "2026-09-24T10:00:00Z",
        "status": None,
        "label": "Venue",
        "subtitle": None,
        "facts": {},
        "matched_fields": ["name"],
        "id": f"venue:{uid(20)}",
        "type": "venue",
        "key": str(uid(20)),
        "action": Action(route="activity", entity_type="venue", entity_key=str(uid(20))),
    }


@pytest.mark.parametrize(
    "model", [Activity, EntityRecord, EntitySearchItem, GlobalSearchItem, GraphNode, RecentEntity]
)
def test_scope_contract_is_closed_and_optional(model):
    data = record_values()
    assert model.model_validate(data).venue_scope is None
    for scope in (None, "organization", "shared"):
        assert model.model_validate({**data, "venue_scope": scope}).venue_scope == scope
    for scope in ("standard", "SHARED", "", "unknown"):
        with pytest.raises(ValidationError):
            model.model_validate({**data, "venue_scope": scope})


async def test_invalid_source_scope_fails_without_exposing_or_remapping_it(
    settings, headers, monkeypatch
):
    from app.api import entities

    async def connection():
        yield None

    async def invalid_source(*args):
        return GlobalSearchItem.model_validate({**record_values(), "venue_scope": "standard"})

    app = create_app(settings)
    app.dependency_overrides[get_connection] = connection
    monkeypatch.setattr(entities, "global_search", invalid_source)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        result = await client.get("/api/v1/search?q=venue", headers=headers)
    assert result.status_code == 500
    assert result.json()["error"]["code"] == "internal_error"
    assert "standard" not in result.text and "shared" not in result.text


@pytest.mark.integration
@pytest.mark.parametrize("scope", ["organization", "shared"])
async def test_authoritative_scope_across_record_and_search_responses(
    db_connection, settings, now, headers, scope
):
    # Transaction-local synthetic data only. Both venues retain the same organization.
    await db_connection.execute(
        text("UPDATE uranus.venue SET scope=:scope,created_at=:stamp WHERE uuid=:id"),
        {"scope": scope, "stamp": now.replace(tzinfo=None) - timedelta(seconds=1), "id": uid(20)},
    )

    async def connection():
        yield db_connection

    app = create_app(settings)
    app.dependency_overrides[get_connection] = connection
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

        async def get(path):
            response = await client.get(f"/api/v1/{path}", headers=headers)
            assert response.status_code == 200, response.text
            return response.json()

        activity = await get("dashboard/activity?period=24h&page_size=100")
        assert (
            next(i for i in activity["items"] if i["entity_key"] == str(uid(20)))["venue_scope"]
            == scope
        )
        assert all(
            i["venue_scope"] is None for i in activity["items"] if i["entity_type"] != "venue"
        )
        venues = await get("venues")
        assert (
            next(i for i in venues["items"] if i["entity_key"] == str(uid(20)))["venue_scope"]
            == scope
        )
        assert (await get(f"venues/{uid(20)}"))["item"]["venue_scope"] == scope
        related = (await get(f"organizations/{uid(10)}"))["related"]["items"]
        assert next(i for i in related if i["entity_key"] == str(uid(20)))["venue_scope"] == scope
        for section, key in (("events", 30), ("spaces", 25)):
            assert (await get(f"{section}/{uid(key)}"))["item"]["venue_scope"] is None
        search = await get(f"entity-search?entity_type=venue&q={uid(20)}")
        assert search["items"][0]["venue_scope"] == scope
        global_result = await get(f"search?types=venue&q={uid(20)}")
        assert global_result["groups"][0]["items"][0]["venue_scope"] == scope
        graph_search = await get(f"graph/search?entity_type=venue&q={uid(20)}")
        assert graph_search["items"][0]["venue_scope"] == scope
        graph = await get(f"graph?root_type=venue&root_key={uid(20)}&depth=1")
        assert next(i for i in graph["nodes"] if i["key"] == str(uid(20)))["venue_scope"] == scope
        recent = (await get("statistics/entities?period=24h"))["recent"]
        assert next(i for i in recent if i["entity_key"] == str(uid(20)))["venue_scope"] == scope

    # Scope is output metadata, not a search field or another query per hit.
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        for limit in (1, 10):
            statements.clear()
            result = await entity_search(
                db_connection,
                EntitySearchFilters(q="Venue", entity_type="venue", limit=limit),
                settings,
                now,
            )
            assert len(statements) == 1
            assert result.items and all(i.venue_scope is not None for i in result.items)
            statements.clear()
            global_result = await global_search(
                db_connection, GlobalSearchFilters(q="Venue", types="venue", limit_per_type=limit)
            )
            assert len(statements) == 1
            assert global_result.groups and all(
                i.venue_scope is not None for i in global_result.groups[0].items
            )
        assert not (
            await entity_search(
                db_connection, EntitySearchFilters(q=scope, entity_type="venue"), settings, now
            )
        ).items
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)
