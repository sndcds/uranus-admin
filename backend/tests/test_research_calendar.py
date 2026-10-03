"""Recurring calendar predicates use the common population and actual SQL provenance."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

from app.errors import APIError
from app.repositories.research_grouping import grouped_selection
from app.research.normalize_v10 import normalize_v10
from app.research.plan import ResolvedResearchPlan, TemporalSelection
from app.research.wire.research_v10_schema import ResearchQueryPlanV10
from app.schemas.research_execution import ExecutionFilters
from app.schemas.research_response import ResearchExecutionResponse
from tests.test_research_grouping_flow import flow as flow_fixture
from tests.test_research_plan_execution import execution_source as execution_source_fixture

flow = flow_fixture
execution_source = execution_source_fixture
CASES = json.loads(Path("tests/fixtures/recurring_calendar_v10.json").read_text())
EXECUTABLE = [
    c
    for c in CASES
    if c["plan"]["clarification"] == "none" and c["plan"]["unsupported_reason"] is None
]


def calendar_plan(case):
    return ResearchQueryPlanV10.model_validate_json(json.dumps(case["plan"]))


def set_response(state, case):
    p = case["plan"]
    state["response"].update(
        schema_version="research-query-plan-v10",
        prompt_version="research-planner-v16",
        plan=p,
        kind="unsupported"
        if p["unsupported_reason"]
        else "needs_clarification"
        if p["clarification"] != "none"
        else "plan",
    )
    state["response"]["diagnostics"].update(
        planner_prompt_version="research-planner-v16", planner_intent=p["intent"]
    )


@pytest.mark.parametrize("case", EXECUTABLE, ids=lambda c: c["name"])
def test_normalized_recurring_sets(case):
    plan = normalize_v10(calendar_plan(case))
    temporal = case["plan"]["temporal"]
    assert (
        plan.temporal.weekdays == tuple(temporal["recurring_weekdays"])
        if temporal
        else not plan.temporal.weekdays
    )
    assert (
        plan.temporal.months == tuple(temporal["recurring_months"])
        if temporal
        else not plan.temporal.months
    )
    assert plan.temporal.period == (temporal["period"] if temporal else "none")
    assert plan.groupings == tuple(case["plan"]["group_by"])
    if case["plan"]["semantic"]:
        assert plan.semantic.query == case["plan"]["semantic"]["query"]


@pytest.mark.parametrize("values", [(7, 7), (0,), (8,), (True,), ("7",), [7]])
def test_internal_weekday_validation(values):
    with pytest.raises(ValueError):
        TemporalSelection(weekdays=values)


def test_internal_set_normalization():
    assert TemporalSelection(weekdays=(7, 6), months=(9, 7, 8)) == TemporalSelection(
        weekdays=(6, 7), months=(7, 8, 9)
    )


@pytest.mark.parametrize("case", EXECUTABLE, ids=lambda c: c["name"])
async def test_normal_query_calendar_or_audience(
    client, settings, headers, flow, monkeypatch, case
):
    from app.services import semantic_search
    from tests.test_research_sql_provenance import ROW, Rows
    from tests.test_semantic_search import hit

    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v10"
    set_response(state, case)
    plan = normalize_v10(calendar_plan(case))
    is_semantic = plan.semantic is not None
    if is_semantic:
        settings.semantic_search_noncommercial_jina = True
        encoder = SimpleNamespace(
            embed=AsyncMock(return_value=[[0.1]]), http=SimpleNamespace(close=AsyncMock())
        )
        vector = SimpleNamespace(
            search=AsyncMock(return_value=[hit(30)]), http=SimpleNamespace(close=AsyncMock())
        )
        monkeypatch.setattr(semantic_search, "Encoder", lambda *a, **k: encoder)
        monkeypatch.setattr(semantic_search, "Qdrant", lambda *a, **k: vector)

        async def connection(_):
            yield sql

        monkeypatch.setattr(semantic_search, "get_connection", connection)
        sql.execute.side_effect = [Rows(), Rows([ROW]), Rows()]
    elif len(plan.groupings) == 1 and plan.group_by != "none":
        rows = MagicMock()
        rows.mappings.return_value = [dict(key="1", name="Konzert", value=7)]
        sql.execute.return_value = rows
    else:
        row = {"value": 7}
        for index, dimension in enumerate(plan.groupings):
            key = "7" if dimension == "weekday" else "09" if dimension == "month" else "1"
            row[f"key_{index}"] = key
            row[f"name_{index}"] = "Konzert" if dimension == "event_type" else key
        rows = MagicMock()
        rows.mappings.return_value = [row]
        sql.execute.return_value = rows
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": case["plan"]["original_query"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    ResearchExecutionResponse.model_validate_json(response.content)
    assert len(requests) == 1 and requests[0].url.path == "/v10/plan"
    assert resolve.await_args.args[2] == plan
    assert body["diagnostics"]["planner_ms"] > 0
    assert body["result"]["kind"] == (
        "records" if is_semantic else "aggregate" if plan.group_by != "none" else "grouped"
    )
    assert body["sql_provenance"]
    statements = body["sql_provenance"]
    for statement, call in zip(statements, sql.execute.await_args_list, strict=True):
        assert statement["sql"] == call.args[0].text
        for name, values in [
            ("weekdays", plan.temporal.weekdays),
            ("months", plan.temporal.months),
        ]:
            if name in call.args[1]:
                assert tuple(call.args[1][name]) == values
            if name in statement["parameters"]:
                assert statement["parameters"][name] == list(values)
    if is_semantic:
        vector.search.assert_awaited_once()
        assert body["result"]["total"] is None
        assert statements[0]["kind"] == "eligibility"
        assert statements[1]["kind"] == "rehydration"
    else:
        assert "extract(isodow FROM d.start_date)" in statements[0]["sql"]
        assert "extract(month FROM d.start_date)" in statements[0]["sql"]
        if "weekday" in plan.groupings:
            assert "extract(isodow FROM selected.start_date)" in statements[0]["sql"]


@pytest.mark.parametrize("case", [c for c in CASES if c not in EXECUTABLE], ids=lambda c: c["name"])
async def test_unsupported_audience_fails_before_sql(client, settings, headers, flow, case):
    state, requests, sql, resolve, _ = flow
    settings.research_planner_contract = "v10"
    set_response(state, case)
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": case["plan"]["original_query"]}
    )
    assert response.status_code == 422
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"recurring_weekdays": [7, 7]},
        {"recurring_months": [13]},
        {"recurring_weekdays": ["7"]},
        {"field": "modified_at"},
    ],
)
async def test_malformed_calendar_before_sql(client, settings, headers, flow, change):
    state, requests, sql, resolve, _ = flow
    settings.research_planner_contract = "v10"
    case = deepcopy(CASES[2])
    case["plan"]["temporal"].update(change)
    set_response(state, case)
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": case["plan"]["original_query"]}
    )
    assert response.status_code == 502
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"overlap": True},
        {"calendar_relation": "holiday", "calendar_area_query": "DE"},
        {"after_time": "18:00:00"},
    ],
)
def test_unsupported_constraints_not_dropped(change):
    case = deepcopy(CASES[2])
    case["plan"]["temporal"].update(change)
    with pytest.raises(APIError):
        normalize_v10(calendar_plan(case))


async def test_recurring_calendar_postgres(settings, execution_source):
    from datetime import date

    from app.repositories.research_execution import count_selection, eligible_event_ids
    from tests.conftest import uid

    # Distinct dates in several years, both sides of recurring bounds, plus an
    # event without any occurrence. All mutations are disposable test fixtures.
    await execution_source.execute(text("DELETE FROM uranus.event_date"))
    for i, day in enumerate(
        ["2025-07-06", "2026-07-05", "2026-07-04", "2026-07-06", "2026-10-04", "2026-09-06"]
    ):
        await execution_source.execute(
            text("""INSERT INTO uranus.event_date
                (uuid,event_uuid,start_date,start_time,release_status)
            VALUES (:id,:event,:day,'18:00','published')"""),
            dict(id=uid(500 + i), event=uid(30), day=date.fromisoformat(day)),
        )
    base = normalize_v10(calendar_plan(CASES[0]))
    # Single weekday dimension isolates weekday counts from taxonomy fixture data.
    plan = replace(base, groupings=("weekday",))
    filters = ExecutionFilters(weekdays=(6, 7), months=(7, 8, 9))
    resolved = ResolvedResearchPlan(filters=filters, intent="aggregate")
    result = await grouped_selection(execution_source, settings, plan, resolved, None)
    assert {i.coordinates[0].key: i.value for i in result.items} == {"7": 3, "6": 1}
    filters = filters.model_copy(
        update={"from_date": date(2026, 1, 1), "to_date": date(2026, 12, 31)}
    )
    result = await grouped_selection(
        execution_source, settings, plan, replace(resolved, filters=filters), None
    )
    assert {i.coordinates[0].key: i.value for i in result.items} == {"7": 2, "6": 1}
    assert await eligible_event_ids(execution_source, settings, filters, None) == [uid(30)]
    assert (await count_selection(execution_source, settings, filters, "event_count", None)) == 1


def test_v9_scalar_weekday_maps_to_shared_calendar():
    from app.research.normalize_v9 import normalize_v9
    from tests.test_research_v9_adapter import temporal, v9

    plan = normalize_v9(v9(temporal=temporal("none", weekday="sunday")))
    assert plan.temporal.weekdays == (7,)


def test_shared_v10_contract_snapshot_and_witnesses():
    snapshot = canonical_schema(ResearchQueryPlanV10.model_json_schema())
    pin = json.loads(Path("tests/fixtures/research_v10_contract.json").read_text())
    assert (
        hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == pin["schema_sha256"]
    )
    assert canonical_schema(ResearchQueryPlanV10.model_json_schema()) == json.loads(
        Path("tests/fixtures/research_v10_schema.json").read_text()
    )
    assert CASES == json.loads(
        Path("../frontend/tests/fixtures/research-calendar-v10.json").read_text()
    )


def canonical_schema(value):
    # Literal enum order can differ with Python's process-wide type interning.
    # Enum members are a set; preserve every other schema keyword/array exactly.
    if isinstance(value, dict):
        return {
            key: sorted(item) if key == "enum" else canonical_schema(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [canonical_schema(item) for item in value]
    return value


async def test_audience_calendar_filters_survive_eligibility_and_rehydration(
    client, settings, headers, flow, monkeypatch
):
    case = deepcopy(next(c for c in CASES if c["name"] == "audience-0"))
    case["plan"]["temporal"] = deepcopy(
        next(c for c in CASES if c["name"] == "sundays-2026")["plan"]["temporal"]
    )
    case["plan"]["temporal"]["recurring_months"] = [7, 8, 9]
    await test_normal_query_calendar_or_audience(client, settings, headers, flow, monkeypatch, case)


def test_unsupported_calendar_entity_combination():
    case = deepcopy(CASES[0])
    case["plan"]["entity_type"] = "venue"
    case["plan"]["metric"]["operation"] = "venue_count"
    with pytest.raises(APIError):
        normalize_v10(calendar_plan(case))
