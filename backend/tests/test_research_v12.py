"""Combined version normalization, identity-free context and existing execution paths."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.research.conversation import summarize_plan
from app.research.geography import UnresolvedAdministrativeAreaRef
from app.research.normalize import normalize
from app.research.normalize_v12 import normalize_v12
from app.research.wire.research_v12_schema import PlanResponseV12, ResearchQueryPlanV12
from app.schemas.research_conversation_v12 import ResearchConversationContextV12
from app.schemas.research_location import ResearchQueryRequest
from app.schemas.research_response import ResearchExecutionResponse
from tests.test_research_grouping_flow import flow as flow_fixture

flow = flow_fixture
CASES = json.loads(Path("tests/fixtures/modern_v12.json").read_text())
BY_NAME = {c["name"]: c for c in CASES}
CONTEXT = json.loads(Path("tests/fixtures/modern_v12_context.json").read_text())


def wire(name):
    return ResearchQueryPlanV12.model_validate_json(json.dumps(BY_NAME[name]["plan"]))


def envelope(name):
    plan = BY_NAME[name]["plan"]
    return dict(
        kind="plan" if plan["clarification"] == "none" else "needs_clarification",
        schema_version="research-query-plan-v12",
        prompt_version="research-planner-v18",
        model="fixture",
        plan=deepcopy(plan),
        reference_date="2026-10-03",
        timezone="Europe/Berlin",
        diagnostics=dict(
            request_id="a" * 32,
            planner_intent=plan["intent"],
            planner_model="fixture",
            planner_prompt_version="research-planner-v18",
            planner_ms=1,
            total_ms=1,
        ),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_v12_normalization_preserves_every_supported_dimension(case):
    p = ResearchQueryPlanV12.model_validate_json(json.dumps(case["plan"]))
    plan = normalize_v12(p)
    if p.clarification == "needs_context":
        assert plan.clarification == "needs_context"
        return
    assert [(c.relation, c.reference) for c in plan.spatial_constraints] == [
        (g.relation, UnresolvedAdministrativeAreaRef(g.area_query, g.area_level)) for g in p.spatial
    ]
    if p.temporal:
        assert plan.temporal.weekdays == tuple(p.temporal.recurring_weekdays)
        assert plan.temporal.months == tuple(p.temporal.recurring_months)
        assert plan.temporal.from_date == p.temporal.from_date
        assert plan.temporal.to_date == p.temporal.to_date
    assert (
        plan.groupings == tuple(p.group_by)
        if len(p.group_by) > 1
        else (plan.group_by == p.group_by[0] if p.group_by else not plan.groupings)
    )
    assert (
        normalize(PlanResponseV12.model_validate_json(json.dumps(envelope(case["name"])))) == plan
    )


def test_safe_summaries_preserve_levels_and_bounded_and():
    for name in ["district", "multi-and", "followup"]:
        plan = normalize_v12(wire(name))
        summary = summarize_plan(plan, administrative=True)
        assert summary is not None
        assert [a.model_dump() for a in summary.areas] == [
            dict(name=g.area_query, relation=g.relation, expected_level=g.area_level)
            for g in wire(name).spatial
        ]
        assert summarize_plan(plan) is None  # Frozen v11 cannot remember these losslessly.
        ResearchConversationContextV12.model_validate({"previous_turns": [summary]})
        for key in [
            "sql",
            "parameters",
            "geometry",
            "latitude",
            "longitude",
            "entity_id",
            "answer_text",
            "request_id",
            "results",
            "user_id",
        ]:
            assert key not in summary.model_dump_json()
    assert summarize_plan(replace(plan, clarification="needs_context"), administrative=True) is None


@pytest.mark.parametrize(
    "field",
    [
        "sql",
        "parameters",
        "geometry",
        "coordinates",
        "id",
        "ags",
        "osm_id",
        "iso_code",
        "parent_id",
    ],
)
def test_context_rejects_private_metadata(field):
    context = deepcopy(CONTEXT)
    context["previous_turns"][0]["areas"][0][field] = "private"
    with pytest.raises(ValidationError):
        ResearchQueryRequest.model_validate(
            {"query": "Und sonntags?", "conversation_context": context}
        )


async def test_v12_followup_uses_one_request_and_preserves_provenance(
    client, settings, headers, flow, monkeypatch
):
    from app.repositories import research_resolution as resolver
    from app.repositories.research_administrative import administrative_reference
    from app.research.geography import SpatialConstraint
    from tests.test_research_administrative import boundary

    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v12"
    state["response"] = envelope("group-weekday")
    state["response"]["plan"]["original_query"] = "Und nach Wochentagen?"
    stored = boundary("Schleswig-Flensburg", "district", 6)
    resolve.side_effect = None
    resolve.return_value = resolver.Resolution(
        area=stored,
        spatial_constraints=(SpatialConstraint("inside", administrative_reference(stored)),),
    )
    rows = MagicMock()
    rows.mappings.return_value = [dict(key_0="1", name_0="Konzert", key_1="7", name_1="7", value=3)]
    sql.execute.return_value = rows
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={
            "query": "Und nach Wochentagen?",
            "conversation_context": CONTEXT,
        },
    )
    assert response.status_code == 200, response.text
    parsed = ResearchExecutionResponse.model_validate_json(response.content)
    assert parsed.result.kind == "grouped"
    assert parsed.result.dimensions == ["event_type", "weekday"]
    assert parsed.conversation_summary.areas[0].expected_level == "district"
    assert len(requests) == 1 and requests[0].url.path == "/v12/plan"
    payload = json.loads(requests[0].content)
    assert payload["conversation_context"] == CONTEXT
    assert set(payload) == {"query", "language", "timezone", "conversation_context"}
    assert resolve.await_args.args[2].spatial_constraints[0].reference.expected_level == "district"
    sql.execute.assert_awaited_once()
    assert parsed.sql_provenance[0].sql == sql.execute.await_args.args[0].text
    learn.assert_not_awaited()


@pytest.mark.parametrize("contract", ["legacy", "v9", "v10", "v11"])
async def test_rollback_never_strips_context_level(client, settings, headers, flow, contract):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = contract
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={
            "query": "Und sonntags?",
            "conversation_context": CONTEXT,
        },
    )
    assert response.status_code == 422
    assert requests == []
    sql.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "failure", ["wrong_version", "changed_query", "provider_error", "invalid_spatial"]
)
async def test_invalid_v12_never_retries_or_falls_back(client, settings, headers, flow, failure):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v12"
    state["response"] = envelope("district")
    query = state["response"]["plan"]["original_query"]
    if failure == "wrong_version":
        state["response"]["schema_version"] = "research-query-plan-v11"
    elif failure == "changed_query":
        state["response"]["plan"]["original_query"] = "private"
    elif failure == "provider_error":
        state["status"] = 500
    else:
        state["response"]["plan"]["spatial"][0]["area_level"] = "official-id"
    response = await client.post("/api/v1/research/query", headers=headers, json={"query": query})
    assert response.status_code == 502
    assert len(requests) == 1 and requests[0].url.path == "/v12/plan"
    assert "private" not in response.text
    sql.execute.assert_not_awaited()


def test_shared_snapshot_and_all_contract_configurations(settings):
    from app.config import Settings
    from tests.test_research_calendar import canonical_schema

    snapshot = json.loads(Path("tests/fixtures/modern_v12_schema.json").read_text())
    assert canonical_schema(PlanResponseV12.model_json_schema()) == snapshot["response"]
    assert (
        canonical_schema(ResearchConversationContextV12.model_json_schema()) == snapshot["context"]
    )
    for name in ["legacy", "v9", "v10", "v11", "v12"]:
        Settings(_env_file=None, research_planner_contract=name)


async def test_v12_wrong_loaded_level_clarifies_before_execution(settings, monkeypatch):
    from contextlib import asynccontextmanager

    from fastapi import Request

    from app.repositories import research_resolution as resolver
    from app.schemas.research_execution import ResolutionCandidate
    from app.services import research_plan_execution as execution
    from tests.test_research_administrative import CONTEXT as execution_context
    from tests.test_research_administrative import boundary

    @asynccontextmanager
    async def transaction():
        yield

    admin = AsyncMock()
    admin.begin = transaction

    @asynccontextmanager
    async def connect(request):
        yield admin

    monkeypatch.setattr(resolver, "connect_admin", connect)
    wrong = boundary("Schleswig", "municipality", 8)
    monkeypatch.setattr(
        resolver,
        "candidates",
        AsyncMock(
            return_value=[
                ResolutionCandidate(
                    entity_type="area", id=str(wrong.area.id), label="Kreis Schleswig"
                )
            ]
        ),
    )
    monkeypatch.setattr(resolver, "resolve_area", AsyncMock(return_value=wrong))
    source = AsyncMock(side_effect=AssertionError("must not execute wrong level"))
    monkeypatch.setattr(execution, "research_page", source)
    result = await execution.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        normalize_v12(wire("informal-district")),
        execution_context,
        planner_ms=0,
    )
    assert result.result.kind == "needs_clarification"
    assert result.result.reason == "no_match" and result.result.candidates == []
    assert not result.resolution and not result.sql_provenance
    source.assert_not_awaited()


@pytest.mark.parametrize("name", ["result-reference-20", "result-reference-21"])
async def test_result_identity_context_never_executes(client, settings, headers, flow, name):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v12"
    state["response"] = envelope(name)
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={
            "query": BY_NAME[name]["query"],
            "conversation_context": CONTEXT,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["planner_state"] == "needs_context"
    assert response.json()["conversation_summary"] is None
    resolve.assert_not_awaited()
    sql.execute.assert_not_awaited()


def test_wire_mirror_and_snapshot_pin():
    import hashlib

    pin = json.loads(Path("tests/fixtures/modern_v12_pin.json").read_text())
    assert pin["schema_version"] == "research-query-plan-v12"
    assert pin["prompt_version"] == "research-planner-v18"
    for name, digest in pin["mirror_sha256"].items():
        assert hashlib.sha256((Path("app/research/wire") / name).read_bytes()).hexdigest() == digest


def test_v12_scalar_group_summary_retains_grouping():
    summary = summarize_plan(normalize_v12(wire("months-state")), administrative=True)
    assert summary.groupings == ["event_type"]
    assert summary.temporal.months == [7, 8, 9]
    assert summary.areas[0].expected_level == "state"
