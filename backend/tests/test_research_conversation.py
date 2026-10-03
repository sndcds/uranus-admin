"""Bounded advisory context; execution still consumes a normalized current plan."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.research.conversation import summarize_plan
from app.research.geography import SpatialConstraint, UserLocationRef
from app.research.normalize import normalize
from app.research.plan import InternalResearchPlan, TemporalSelection
from app.research.wire.research_v11_schema import PlanResponseV11
from app.schemas.research_conversation import ResearchConversationContext, ResearchPlanSummary
from app.schemas.research_location import ResearchQueryRequest
from tests.test_research_calendar import CASES, set_response
from tests.test_research_grouping_flow import flow as flow_fixture

flow = flow_fixture
SUMMARY = json.loads(Path("tests/fixtures/conversation_summary.json").read_text())


def test_projection_is_semantic_not_result_or_runtime_data():
    p = InternalResearchPlan(
        intent="aggregate",
        entity_type="event",
        metric="occurrence_count",
        groupings=("event_type", "month"),
        ordering="desc",
        limit=20,
    )
    assert summarize_plan(p).model_dump(mode="json") == SUMMARY
    assert summarize_plan(
        replace(p, temporal=TemporalSelection(weekdays=(7,)))
    ).temporal.weekdays == [7]
    assert (
        summarize_plan(
            replace(p, spatial_constraints=(SpatialConstraint("nearby", UserLocationRef()),))
        )
        is None
    )
    assert summarize_plan(replace(p, intent="compare")) is None
    assert summarize_plan(replace(p, clarification="needs_context")) is None


@pytest.mark.parametrize(
    "key",
    ["sql", "parameters", "latitude", "longitude", "geometry", "entity_id", "question", "results"],
)
def test_forbidden_context_fields(key):
    with pytest.raises(ValidationError):
        ResearchPlanSummary.model_validate({**SUMMARY, key: "private"})


def test_context_bounds_and_backwards_compatibility():
    ResearchQueryRequest.model_validate({"query": "Eine Frage"})
    for value in [[], [SUMMARY] * 5]:
        with pytest.raises(ValidationError):
            ResearchConversationContext.model_validate({"previous_turns": value})
    for patch in [{"semantic_query": "x" * 161}, {"groupings": ["month", "month"]}]:
        with pytest.raises(ValidationError):
            ResearchPlanSummary.model_validate({**SUMMARY, **patch})
    with pytest.raises(ValidationError):
        ResearchQueryRequest.model_validate({"query": "Eine Frage", "plan": SUMMARY})


def use_v11(state, case):
    set_response(state, case)
    state["response"]["schema_version"] = "research-query-plan-v11"
    state["response"]["prompt_version"] = "research-planner-v17"
    state["response"]["diagnostics"]["planner_prompt_version"] = "research-planner-v17"


async def test_context_normal_endpoint_one_request_no_learning(client, settings, headers, flow):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v11"
    case = deepcopy(CASES[0])
    case["plan"]["original_query"] = "Und nur sonntags?"
    use_v11(state, case)
    context = {"previous_turns": [SUMMARY]}
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={"query": case["plan"]["original_query"], "conversation_context": context},
    )
    assert response.status_code == 200, response.text
    assert len(requests) == 1 and requests[0].url.path == "/v11/plan"
    payload = json.loads(requests[0].content)
    assert payload["query"] == "Und nur sonntags?"
    assert payload["conversation_context"] == context
    assert isinstance(resolve.await_args.args[2], InternalResearchPlan)
    assert response.json()["conversation_summary"] is not None
    assert response.json()["sql_provenance"]
    learn.assert_not_awaited()


async def test_needs_context_never_executes_sql(client, settings, headers, flow):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v11"
    case = deepcopy(CASES[0])
    case["plan"]["original_query"] = "Welcher davon?"
    case["plan"]["clarification"] = "needs_context"
    use_v11(state, case)
    parsed = PlanResponseV11.model_validate_json(json.dumps(state["response"]))
    assert normalize(parsed).clarification == "needs_context"
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": "Welcher davon?"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["planner_state"] == "needs_context"
    assert response.json()["conversation_summary"] is None
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()


async def test_old_transport_cannot_silently_ignore_context(client, settings, headers, flow):
    _, requests, sql, _, _ = flow
    settings.research_planner_contract = "v10"
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={"query": "Und sonntags?", "conversation_context": {"previous_turns": [SUMMARY]}},
    )
    assert response.status_code == 422
    assert requests == []
    sql.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "extra", [{"latitude": 54.79}, {"sql": "SELECT secret"}, {"entity_id": "private"}]
)
async def test_request_rejects_private_context_before_planner(client, headers, flow, extra):
    _, requests, sql, _, _ = flow
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={
            "query": "Und sonntags?",
            "conversation_context": {"previous_turns": [{**SUMMARY, **extra}]},
        },
    )
    assert response.status_code == 422
    assert requests == []


async def test_browser_location_stays_outside_planner_memory(client, settings, headers, flow):
    state, requests, _, _, learn = flow
    settings.research_planner_contract = "v11"
    use_v11(state, deepcopy(CASES[0]))
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={
            "query": state["response"]["plan"]["original_query"],
            "location_context": {
                "latitude": 54.791234,
                "longitude": 9.431234,
                "source": "browser_geolocation",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["conversation_summary"] is None
    assert b"54.791234" not in requests[0].content
    assert b"9.431234" not in requests[0].content
    assert b"location_context" not in requests[0].content
    learn.assert_not_awaited()


def test_mirrored_conversation_contract_snapshot():
    import hashlib

    from tests.test_research_calendar import canonical_schema

    path = Path("tests/fixtures/conversation_v11_schema.json")
    pin = json.loads(Path("tests/fixtures/conversation_v11_contract.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["schema_sha256"]
    snapshot = json.loads(path.read_text())
    assert canonical_schema(PlanResponseV11.model_json_schema()) == snapshot["response"]
    assert canonical_schema(ResearchConversationContext.model_json_schema()) == snapshot["context"]


CONVERSATIONS = json.loads(Path("tests/fixtures/conversation_v11.json").read_text())


@pytest.mark.parametrize("case", CONVERSATIONS, ids=lambda c: c["name"])
def test_followup_semantics_do_not_drop_subject_or_calendar(case):
    from app.research.normalize_v10 import normalize_v10
    from app.research.wire.research_v11_schema import ResearchQueryPlanV11

    ResearchConversationContext.model_validate_json(json.dumps(case["context"]))
    wire = ResearchQueryPlanV11.model_validate_json(json.dumps(case["plan"]))
    if wire.clarification != "none":
        assert wire.clarification == "needs_context"
        return
    plan = normalize_v10(wire)
    if case["name"] == "independent":
        assert plan.entity_type == "organization"
        assert not plan.spatial_constraints and not plan.temporal.weekdays
        assert not plan.groupings
    else:
        assert plan.groupings == ("event_type",)
        assert plan.metric == "occurrence_count"
        assert plan.temporal.weekdays == (7,)
        assert plan.temporal.months == ((8,) if case["name"] == "august" else ())
        assert plan.temporal.period == "none"
        if case["name"] in {"flensburg", "august"}:
            assert plan.spatial_constraints[0].reference.name == "Flensburg"


async def test_context_dates_accept_only_canonical_iso_at_http_boundary(
    client, settings, headers, flow
):
    state, requests, _, _, _ = flow
    settings.research_planner_contract = "v11"
    use_v11(state, deepcopy(CASES[0]))
    summary = deepcopy(SUMMARY)
    summary["temporal"].update(
        period="explicit_range", from_date="2026-01-01", to_date="2026-12-31"
    )
    body = {
        "query": state["response"]["plan"]["original_query"],
        "conversation_context": {"previous_turns": [summary]},
    }
    response = await client.post("/api/v1/research/query", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert json.loads(requests[0].content)["conversation_context"] == body["conversation_context"]
    for invalid in ["20260101", "2026-01-01T00:00:00", 1, True]:
        summary["temporal"]["from_date"] = invalid
        assert (
            await client.post("/api/v1/research/query", headers=headers, json=body)
        ).status_code == 422
    assert len(requests) == 1
