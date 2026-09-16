"""Real PostgreSQL relationship semantics and bounded explorer contracts."""

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.repositories import graph
from app.schemas.graph import GraphFilters, GraphSearchFilters
from app.services.quality.core import effective_location
from tests.conftest import uid


@pytest.mark.parametrize(
    "values",
    [
        {"root_type": "event;DROP TABLE", "root_key": str(uid(1))},
        {"root_type": "venue", "root_key": "bad"},
        {"root_type": "venue", "root_key": str(uid(1)), "depth": 4},
        {"root_type": "venue", "root_key": str(uid(1)), "depth": 0},
    ],
)
def test_graph_validation(values):
    with pytest.raises(ValidationError):
        GraphFilters(**values)


@pytest.mark.parametrize(
    "values", [{"q": ""}, {"q": " "}, {"q": "x" * 121}, {"q": "ab", "limit": 21}]
)
def test_search_validation(values):
    with pytest.raises(ValidationError):
        GraphSearchFilters(**values)


@pytest.mark.parametrize(
    "kind,key",
    [
        ("organization", 10),
        ("venue", 20),
        ("space", 25),
        ("event", 30),
        ("event_date", 40),
        ("user", 1),
    ],
)
async def test_each_root_and_search(db_connection, settings, kind, key):
    result = await graph.explore(
        db_connection, settings, GraphFilters(root_type=kind, root_key=uid(key), depth=1)
    )
    assert f"{kind}:{uid(key)}" in {n.id for n in result.nodes}
    assert result.edges
    assert not result.truncated
    assert len({n.id for n in result.nodes}) == len(result.nodes)
    assert all(
        e.source in {n.id for n in result.nodes} and e.target in {n.id for n in result.nodes}
        for e in result.edges
    )
    found = await graph.search(db_connection, GraphSearchFilters(q=str(uid(key)), entity_type=kind))
    assert len(found.items) == 1 and found.items[0].key == uid(key)
    for secret in ("password", "token", "email", "created_at", "joined_at"):
        assert secret not in str(result.model_dump())
        assert secret not in str(found.model_dump())


async def test_depth_partners_membership_and_filter(db_connection, settings):
    filters = GraphFilters(root_type="organization", root_key=uid(10), depth=1)
    one = await graph.explore(db_connection, settings, filters)
    assert "space" not in {n.type for n in one.nodes}
    assert {e.type for e in one.edges} >= {
        "organization_has_venue",
        "organization_has_event",
        "user_invited_to_organization",
        "organization_partner_request",
    }
    assert "user_member_of_organization" not in {e.type for e in one.edges}
    two = await graph.explore(db_connection, settings, filters.model_copy(update={"depth": 2}))
    assert {"space", "event_date"} <= {n.type for n in two.nodes}
    again = await graph.explore(db_connection, settings, filters.model_copy(update={"depth": 2}))
    assert two == again
    assert len({e.id for e in two.edges}) == len(two.edges)
    await db_connection.execute(
        text("UPDATE uranus.organization_partner_request SET status='accepted'")
    )
    missing = await graph.explore(db_connection, settings, filters)
    assert not any(e.type.startswith("organization_partner") for e in missing.edges)
    await db_connection.execute(
        text(
            "INSERT INTO uranus.organization_access_grants "
            "(src_org_uuid,dst_org_uuid,permissions) VALUES (:b,:a,0)"
        ),
        {"a": uid(10), "b": uid(11)},
    )
    await db_connection.execute(text("UPDATE uranus.organization_member_link SET has_joined=true"))
    accepted = await graph.explore(db_connection, settings, filters)
    assert any(
        e.type == "organization_partner_of" and e.direction == "undirected" for e in accepted.edges
    )
    assert any(e.type == "user_member_of_organization" for e in accepted.edges)
    filtered = await graph.explore(
        db_connection,
        settings,
        filters.model_copy(update={"relation_type": "organization_has_venue"}),
    )
    assert {e.type for e in filtered.edges} == {"organization_has_venue"}


async def test_effective_location_matches_central_helper(db_connection, settings):
    await db_connection.execute(
        text("UPDATE uranus.event SET space_uuid=:space WHERE uuid=:event"),
        {"space": uid(25), "event": uid(30)},
    )
    for date_key, override in [(40, None), (42, uid(21))]:
        venue, space = effective_location(
            {"venue_uuid": override, "space_uuid": None},
            {"venue_uuid": uid(20), "space_uuid": uid(25)},
        )
        result = await graph.explore(
            db_connection,
            settings,
            GraphFilters(root_type="event_date", root_key=uid(date_key), depth=1),
        )
        locations = {e.target for e in result.edges if e.type.startswith("event_date_uses_")}
        assert locations == {f"venue:{venue}"} | ({f"space:{space}"} if space else set())
    # Reverse traversal must find the inherited date-space relation, but not overridden date42.
    reverse = await graph.explore(
        db_connection, settings, GraphFilters(root_type="space", root_key=uid(25), depth=1)
    )
    assert f"event_date:{uid(40)}" in {n.id for n in reverse.nodes}
    assert f"event_date:{uid(42)}" not in {n.id for n in reverse.nodes}


async def test_limits_and_literal_search(db_connection, settings, monkeypatch):
    monkeypatch.setattr(graph, "MAX_NODES", 4)
    result = await graph.explore(
        db_connection, settings, GraphFilters(root_type="organization", root_key=uid(10), depth=3)
    )
    assert len(result.nodes) == 4 and result.truncated
    monkeypatch.setattr(graph, "MAX_NODES", 100)
    monkeypatch.setattr(graph, "MAX_EDGES", 2)
    result = await graph.explore(
        db_connection, settings, GraphFilters(root_type="organization", root_key=uid(10), depth=3)
    )
    assert len(result.edges) == 2 and result.truncated
    assert (await graph.search(db_connection, GraphSearchFilters(q="%%"))).items == []
    assert (
        len((await graph.search(db_connection, GraphSearchFilters(q="venue", limit=1))).items) == 1
    )
    assert (
        len(
            (
                await graph.search(
                    db_connection, GraphSearchFilters(q="venue", organization_id=uid(11))
                )
            ).items
        )
        == 1
    )


async def test_graph_api_security(db_client, headers):
    for path in ["/api/v1/graph", "/api/v1/graph/search"]:
        assert (await db_client.get(path)).status_code == 401
    for params in [
        {"root_type": "invalid", "root_key": str(uid(10))},
        {"root_type": "organization", "root_key": "invalid"},
        {"root_type": "organization", "root_key": str(uid(10)), "depth": 4},
    ]:
        assert (
            await db_client.get("/api/v1/graph", params=params, headers=headers)
        ).status_code == 422
    assert (
        await db_client.get(
            "/api/v1/graph",
            params={"root_type": "venue", "root_key": str(uid(999))},
            headers=headers,
        )
    ).status_code == 404
    result = await db_client.get(
        "/api/v1/graph",
        params={"root_type": "organization", "root_key": str(uid(10))},
        headers=headers,
    )
    assert result.status_code == 200 and result.json()["nodes"]
