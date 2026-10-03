"""The normal Research API carries grouped execution and full provenance."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.api import research as api
from app.config import Settings
from app.repositories.research_resolution import Resolution
from app.research.plan import InternalResearchPlan
from app.research.sql_provenance import LOCATION_REDACTED, safe_value
from app.schemas.research_location import PlaceFilter
from app.schemas.research_response import ResearchExecutionResponse
from app.services import research_plan_execution as execution
from app.services.research_planner import ResearchPlannerClient
from tests.test_research_grouping import wire

PATH = "/api/v1/research/query"


def envelope():
    return {
        "kind": "plan",
        "schema_version": "research-query-plan-v9",
        "prompt_version": "research-planner-v15",
        "model": "fixture",
        "plan": wire().model_dump(mode="json"),
        "reference_date": "2026-10-02",
        "timezone": "Europe/Berlin",
        "diagnostics": {
            "request_id": "a" * 32,
            "planner_intent": "aggregate",
            "planner_model": "fixture",
            "planner_prompt_version": "research-planner-v15",
            "planner_ms": 1,
            "total_ms": 1,
        },
    }


@pytest.fixture
async def flow(client, settings, monkeypatch):
    settings.research_planner_contract = "v9"
    settings.research_planner_url = "http://127.0.0.1:8090"
    settings.research_planner_api_key = SecretStr("fixture-only-planner-key-" * 2)
    state = {"response": envelope(), "status": 200}
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(state["status"], json=state["response"])

    planner = ResearchPlannerClient(settings, transport=httpx.MockTransport(transport))
    monkeypatch.setattr(client._transport.app.state, "research_planner", planner)
    # Run the real resolver, executor and grouped repository projection. Only the
    # SQL connection is a fixture; PostgreSQL population tests remain separate.
    sql = AsyncMock()
    rows = MagicMock()
    rows.mappings.return_value = [
        dict(key_0="1", name_0="Konzert", key_1="09", name_1="09", value=7)
    ]
    sql.execute.return_value = rows

    async def connection(_request):
        yield sql

    monkeypatch.setattr(execution, "get_connection", connection)
    resolve = AsyncMock(wraps=execution.resolve_plan)
    monkeypatch.setattr(execution, "resolve_plan", resolve)
    learn = AsyncMock()
    monkeypatch.setattr(api, "record_success", learn)
    yield state, requests, sql, resolve, learn
    await planner.close()


@pytest.mark.parametrize("private_location", [False, True])
async def test_normal_query_delivers_grouped_envelope(
    client, headers, flow, monkeypatch, caplog, private_location
):
    state, requests, sql, resolve, learn = flow
    ticks = iter([100.0, 100.125])
    monkeypatch.setattr(api, "perf_counter", lambda: next(ticks))
    body = {"query": wire().original_query}
    if private_location:
        from tests.test_research_administrative import boundary

        resolve.side_effect = None
        resolve.return_value = Resolution(
            area=replace(boundary(), ewkb=b"private-grouped-boundary"),
            place=PlaceFilter(mode="radius", latitude=54.791234567, longitude=9.431234567),
        )
        body["location_context"] = {
            "latitude": 54.791234567,
            "longitude": 9.431234567,
            "source": "browser_geolocation",
        }
    response = await client.post(PATH, headers=headers, json=body)
    assert response.status_code == 200, response.text
    value = response.json()
    ResearchExecutionResponse.model_validate_json(response.content)
    assert value["result"]["kind"] == "grouped"
    assert value["result"]["dimensions"] == ["event_type", "month"]
    assert value["result"]["items"][0]["value"] == 7
    assert value["plan"] == state["response"]
    assert value["query"] == wire().original_query
    assert value["resolution"] == []
    assert value["execution"]["structured"] is True
    assert value["observed_at"] and value["timezone"] == "Europe/Berlin"
    assert value["diagnostics"]["planner_ms"] == 125.0
    assert value["diagnostics"]["total_ms"] >= 125.0
    assert value["diagnostics"]["returned_count"] == 1
    assert len(requests) == 1 and requests[0].url.path == "/v9/plan"
    assert json.loads(requests[0].content) == {
        "query": wire().original_query,
        "timezone": "Europe/Berlin",
        "language": "auto",
    }
    internal = resolve.await_args.args[2]
    assert isinstance(internal, InternalResearchPlan)
    assert internal.groupings == ("event_type", "month")
    assert internal.metric == "occurrence_count"
    sql.execute.assert_awaited_once()
    statement, parameters = sql.execute.await_args.args
    provenance = value["sql_provenance"]
    assert len(provenance) == 1
    assert provenance[0]["kind"] == "execution"
    assert provenance[0]["label"] == "Mehrdimensionale Auswertung"
    assert provenance[0]["sql"] == statement.text
    assert provenance[0]["parameters"] == {
        name: safe_value(name, parameters.get(name, default))
        for name, default in statement.compile().params.items()
    }
    assert "count(DISTINCT selected.date_key)" in statement.text
    assert (
        "GROUP BY" in statement.text and "extract(month FROM selected.start_date)" in statement.text
    )
    assert "uranus.event_type" in statement.text
    assert statement.text not in caplog.text
    if private_location:
        assert parameters["area_wkb"] == b"private-grouped-boundary"
        assert parameters["place_latitude"] == 54.791234567
        for name in ("area_wkb", "place_latitude", "place_longitude"):
            assert provenance[0]["parameters"][name] == LOCATION_REDACTED
        for private in ("private-grouped-boundary", "54.791234567", "9.431234567"):
            assert private not in response.text and private not in caplog.text
        learn.assert_not_awaited()
    else:
        assert learn.await_args.kwargs["plan"] is internal
        fixture = (
            Path(__file__).parents[2] / "frontend/tests/fixtures/research-grouping-response.json"
        )
        recorded = json.loads(fixture.read_text())
        # The same real API envelope is consumed by frontend Zod/render tests.
        # Only runtime clocks differ between executions.
        for field in (
            "query",
            "plan",
            "resolution",
            "result",
            "execution",
            "timezone",
            "sql_provenance",
            "answer_text",
        ):
            assert value[field] == recorded[field]


@pytest.mark.parametrize(
    "change,status",
    [
        ({"group_by": ["event_type", "event_type"]}, 502),
        ({"group_by": ["sql"]}, 502),
        ({"group_by": ["event_type", "hour"]}, 422),
        ({"group_by": "venue"}, 502),
        ({"sql": "SELECT 1"}, 502),
        ({"original_query": "altered"}, 502),
    ],
)
async def test_invalid_or_unsupported_plan_never_executes(client, headers, flow, change, status):
    state, requests, sql, resolve, learn = flow
    state["response"]["plan"].update(change)
    response = await client.post(PATH, headers=headers, json={"query": wire().original_query})
    assert response.status_code == status, response.text
    assert len(requests) == 1
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()
    learn.assert_not_awaited()


@pytest.mark.parametrize(
    "change",
    [
        {"prompt_version": "research-planner-v14"},
        {"schema_version": "research-query-plan-v8"},
        {"timezone": "UTC"},
        {"kind": "unsupported"},
        {"diagnostics": {**envelope()["diagnostics"], "planner_model": "other"}},
        {"diagnostics": {**envelope()["diagnostics"], "planner_intent": "rank"}},
    ],
)
async def test_invalid_envelope_never_executes(client, headers, flow, change):
    state, requests, sql, resolve, _ = flow
    state["response"].update(deepcopy(change))
    response = await client.post(PATH, headers=headers, json={"query": wire().original_query})
    assert response.status_code == 502
    assert len(requests) == 1
    resolve.assert_not_awaited()
    sql.execute.assert_not_awaited()


async def test_dependency_failure_has_no_legacy_retry(client, headers, flow):
    state, requests, sql, _, _ = flow
    state["status"] = 503
    response = await client.post(PATH, headers=headers, json={"query": wire().original_query})
    assert response.status_code == 503
    assert len(requests) == 1 and requests[0].url.path == "/v9/plan"
    sql.execute.assert_not_awaited()


async def test_normal_body_auth_and_removed_endpoint(client, headers, flow):
    _, requests, _, _, _ = flow
    body = {"query": wire().original_query}
    assert (await client.post(PATH, json=body)).status_code == 401
    for extra in (
        {"plan": wire().model_dump(mode="json")},
        {"contract": "v9"},
        {"group_by": ["month"]},
    ):
        assert (await client.post(PATH, headers=headers, json={**body, **extra})).status_code == 422
    assert (await client.post(PATH, headers=headers, content=b"x" * 33000)).status_code == 413
    assert (
        await client.post("/api/v1/research/v9/query", headers=headers, json=body)
    ).status_code == 404
    assert not requests


async def test_location_context_stays_out_of_planner_and_learning(client, headers, flow):
    _, requests, _, resolve, learn = flow
    location = {"latitude": 54.79, "longitude": 9.43, "source": "browser_geolocation"}
    response = await client.post(
        PATH,
        headers=headers,
        json={
            "query": wire().original_query,
            "location_context": location,
        },
    )
    assert response.status_code == 200
    assert "location_context" not in json.loads(requests[0].content)
    assert resolve.await_args.args[3].location_context.latitude == 54.79
    learn.assert_not_awaited()
    assert "54.79" not in response.text


def test_contract_selection_is_explicit_and_closed():
    assert Settings(_env_file=None).research_planner_contract == "legacy"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, research_planner_contract="http://arbitrary/plan")


async def test_injected_client_cannot_bypass_wire_validation(client, headers, flow, monkeypatch):
    from app.research.wire.research_v9_schema import PlanResponseV9

    response = PlanResponseV9.model_validate_json(json.dumps(envelope()))
    invalid = response.model_copy(
        update={"plan": response.plan.model_copy(update={"group_by": ["month", "month"]})}
    )
    monkeypatch.setattr(
        client._transport.app.state,
        "research_planner",
        AsyncMock(plan_grouped=AsyncMock(return_value=invalid)),
    )
    result = await client.post(PATH, headers=headers, json={"query": wire().original_query})
    assert result.status_code == 502
    flow[2].execute.assert_not_awaited()
    flow[3].assert_not_awaited()


def test_executor_and_resolver_do_not_import_wire_versions():
    import ast
    from pathlib import Path

    for path in (
        "app/services/research_plan_execution.py",
        "app/repositories/research_resolution.py",
    ):
        for node in ast.walk(ast.parse(Path(path).read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("app.research.wire")


async def test_answer_uses_current_executed_values_without_extra_queries(client, headers, flow):
    state, requests, sql, resolve, _ = flow
    for value in (7, 47):
        rows = MagicMock()
        rows.mappings.return_value = [
            dict(key_0="1", name_0="Konzert", key_1="09", name_1="09", value=value)
        ]
        sql.execute.return_value = rows
        response = await client.post(PATH, headers=headers, json={"query": wire().original_query})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["answer_text"] == (
            "Unter den angezeigten Kombinationen hat „Konzert / September“ "
            f"mit {value} Terminen den höchsten angezeigten Wert."
        )
        assert len(body["sql_provenance"]) == 1
        assert body["sql_provenance"][0]["sql"] == sql.execute.await_args.args[0].text
    assert len(requests) == 2
    assert sql.execute.await_count == 2
    assert resolve.await_count == 2
