"""Real PostGIS regression: Planner wire -> normalizer -> level-filtered resolver -> SQL."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.repositories import research_resolution as resolver
from app.research.geography import UnresolvedAdministrativeAreaRef
from app.services import research_plan_execution as execution
from tests.conftest import uid
from tests.test_research_grouping_flow import flow as flow_fixture
from tests.test_research_plan_execution import execution_source as execution_source_fixture
from tests.test_research_v12 import envelope
from tests.test_semantic_knowledge_index import insert_area

flow = flow_fixture
execution_source = execution_source_fixture
pytestmark = pytest.mark.integration
MUNICIPALITIES = ["Ahneby", "Arnis", "Ausacker", "Bollingstedt", "Boren"]
POLYGON = "POLYGON((9 54,10 54,10 55,9 55,9 54))"


@pytest.mark.parametrize("districts", [0, 1, 2])
@pytest.mark.parametrize(
    "query,area_name,level,relation,country,region",
    [
        (
            "Veranstaltungen am Wochenende im Kreis Schleswig",
            "Schleswig",
            "district",
            "inside",
            "DE",
            "DE-SH",
        ),
        (
            "Veranstaltungen im Bundesland Schleswig-Holstein",
            "Schleswig-Holstein",
            "state",
            "inside",
            "DE",
            "DE-SH",
        ),
        (
            "Veranstaltungen im Kreis Schleswig-Flensburg",
            "Schleswig-Flensburg",
            "district",
            "inside",
            "DE",
            "DE-SH",
        ),
        (
            "Veranstaltungen außerhalb Schleswig-Holsteins",
            "Schleswig-Holstein",
            "state",
            "outside",
            "DE",
            "DE-SH",
        ),
        (
            "Veranstaltungen im Kreis Nordfriesland",
            "Nordfriesland",
            "district",
            "inside",
            "DE",
            "DE-SH",
        ),
        (
            "Veranstaltungen in Region Syddanmark",
            "Region Syddanmark",
            "region",
            "inside",
            "DK",
            "DK-83",
        ),
        (
            "Arrangementer i Region Syddanmark",
            "Region Syddanmark",
            "region",
            "inside",
            "DK",
            "DK-83",
        ),
    ],
)
async def test_persistent_levels_end_to_end(
    client,
    settings,
    headers,
    flow,
    admin_store,
    execution_source,
    monkeypatch,
    districts,
    query,
    area_name,
    level,
    relation,
    country,
    region,
):
    state, requests, unused_sql, resolve, learn = flow
    settings.research_planner_contract = "v12"
    state["response"] = envelope("informal-district")
    # Planner responses are controlled fixtures: this proves Admin execution,
    # not a live Planner's German/Danish language interpretation.
    wire = state["response"]["plan"]
    wire["original_query"] = query
    wire["spatial"][0].update(area_query=area_name, area_level=level, relation=relation)
    c = execution_source
    for i, name in enumerate(MUNICIPALITIES, 901):
        await insert_area(c, uid(i), name, POLYGON, i)
        await c.execute(
            text("UPDATE admin.research_area SET display_name=:label WHERE id=:id"),
            dict(id=uid(i), label=f"{name}, {area_name}"),
        )
    # A same-name wrong-level row must never win even when no correct row exists.
    await insert_area(c, uid(950), area_name, POLYGON, 950)
    await c.execute(
        text("UPDATE admin.research_area SET area_type=:level WHERE id=:id"),
        dict(id=uid(950), level="district" if level == "state" else "state"),
    )
    for i in range(districts):
        stored_name = "Schleswig-Flensburg" if area_name == "Schleswig" else area_name
        await insert_area(c, uid(990 + i), stored_name, POLYGON, 990 + i)
        await c.execute(
            text(
                "UPDATE admin.research_area SET area_type=:level,osm_admin_level=:raw_level, "
                "country_code=:country,region_code=:region WHERE id=:id"
            ),
            dict(
                id=uid(990 + i),
                level=level,
                raw_level=6 if level == "district" else 4,
                country=country,
                region=region,
            ),
        )
    await c.execute(text("UPDATE uranus.event_date SET start_date='2026-10-03'"))
    # Transaction control is owned by the isolated fixture; every candidate and
    # execution SELECT below runs on real PostgreSQL/PostGIS with bound parameters.
    statements = []

    class Connection:
        @asynccontextmanager
        async def begin(self):
            yield

        async def execute(self, statement, params=None):
            statements.append((str(statement), params))
            if str(statement).startswith("SET TRANSACTION"):
                return None
            return await c.execute(statement, params or {})

    @asynccontextmanager
    async def connect(request):
        yield Connection()

    monkeypatch.setattr(resolver, "connect_admin", connect)
    spy = AsyncMock(wraps=resolver.candidates)
    monkeypatch.setattr(resolver, "candidates", spy)
    filters = []
    original = execution.execution_filters

    def capture(plan, context, resolution):
        result = original(plan, context, resolution)
        filters.append(result)
        return result

    monkeypatch.setattr(execution, "execution_filters", capture)
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={
            "query": query,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(requests) == 1 and requests[0].url.path == "/v12/plan"
    assert body["plan"]["plan"]["spatial"][0]["area_level"] == level
    internal = resolve.await_args.args[2]
    assert internal.spatial_constraints[0].reference == UnresolvedAdministrativeAreaRef(
        area_name, level
    )
    assert internal.temporal.weekdays == (6, 7)
    assert spy.await_args.kwargs["expected_level"] == level
    candidate_sql, params = next((s, p) for s, p in statements if p and "expected_area_level" in p)
    assert params["expected_area_level"] == level
    assert candidate_sql.index(":expected_area_level") < candidate_sql.index("ORDER BY")
    assert candidate_sql.index(":expected_area_level") < candidate_sql.index("LIMIT")
    if districts == 1:
        assert body["result"]["kind"] == "records"
        assert filters[0].area_id == uid(990)
        assert filters[0].area_relation == relation
        assert filters[0].weekdays == (6, 7)
        assert body["resolution"][0]["target"]["id"] == str(uid(990))
        assert body["sql_provenance"]
        assert any("ST_Covers" in s["sql"] for s in body["sql_provenance"])
        assert body["conversation_summary"]["areas"] == [
            dict(name=area_name, relation=relation, expected_level=level)
        ]
    else:
        assert body["result"]["kind"] == "needs_clarification"
        assert body["result"]["reason"] == ("no_match" if districts == 0 else "ambiguous")
        assert [v["id"] for v in body["result"]["candidates"]] == [
            str(uid(990 + i)) for i in range(districts)
        ]
        assert not filters and not body["sql_provenance"]
    visible = [item["label"] for item in body["result"].get("candidates", [])]
    assert all(not any(name in label for name in MUNICIPALITIES) for label in visible)
    assert all(str(uid(i)) not in str(body["resolution"]) for i in range(901, 906))
    assert str(uid(950)) not in str(body["resolution"])
