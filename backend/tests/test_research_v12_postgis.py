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
async def test_kreis_schleswig_end_to_end(
    client,
    settings,
    headers,
    flow,
    admin_store,
    execution_source,
    monkeypatch,
    districts,
):
    state, requests, unused_sql, resolve, learn = flow
    settings.research_planner_contract = "v12"
    state["response"] = envelope("informal-district")
    c = execution_source
    for i, name in enumerate(MUNICIPALITIES, 901):
        await insert_area(c, uid(i), name, POLYGON, i)
        await c.execute(
            text("UPDATE admin.research_area SET display_name=:label WHERE id=:id"),
            dict(id=uid(i), label=f"{name}, Kreis Schleswig-Flensburg, Schleswig-Holstein"),
        )
    for i in range(districts):
        await insert_area(c, uid(990 + i), "Schleswig-Flensburg", POLYGON, 990 + i)
        await c.execute(
            text(
                "UPDATE admin.research_area SET area_type='district',osm_admin_level=6 WHERE id=:id"
            ),
            dict(id=uid(990 + i)),
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
            "query": "Veranstaltungen am Wochenende im Kreis Schleswig",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(requests) == 1 and requests[0].url.path == "/v12/plan"
    assert body["plan"]["plan"]["spatial"][0]["area_level"] == "district"
    internal = resolve.await_args.args[2]
    assert internal.spatial_constraints[0].reference == UnresolvedAdministrativeAreaRef(
        "Schleswig", "district"
    )
    assert internal.temporal.weekdays == (6, 7)
    assert spy.await_args.kwargs["expected_level"] == "district"
    candidate_sql, params = next((s, p) for s, p in statements if p and "expected_area_level" in p)
    assert params["expected_area_level"] == "district"
    assert candidate_sql.index(":expected_area_level") < candidate_sql.index("ORDER BY")
    assert candidate_sql.index(":expected_area_level") < candidate_sql.index("LIMIT")
    if districts == 1:
        assert body["result"]["kind"] == "records"
        assert filters[0].area_id == uid(990)
        assert filters[0].weekdays == (6, 7)
        assert body["resolution"][0]["target"]["id"] == str(uid(990))
        assert body["sql_provenance"]
        assert any("ST_Covers" in s["sql"] for s in body["sql_provenance"])
        assert body["conversation_summary"]["areas"] == [
            dict(name="Schleswig", relation="inside", expected_level="district")
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
