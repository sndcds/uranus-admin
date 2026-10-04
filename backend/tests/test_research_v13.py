"""Conversational routing, state ownership and grounded rendering across the real API."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.errors import APIError
from app.research.answer_facts import AnswerFacts, render_conversation, render_facts
from app.research.conversation_state import ConversationStore
from app.research.wire.research_v13_schema import ConversationV13, PlanResponseV13
from app.schemas.research_conversation_v12 import ResearchPlanSummaryV12
from app.services import research_conversational as service
from tests.test_research_grouping_flow import flow as flow_fixture

flow = flow_fixture
CASES = json.loads(Path("tests/fixtures/conversation_v13.json").read_text())
SOCIAL = [c for c in CASES if "conversation" in c["plan"]["interaction"]]
PATH = "/api/v1/research/query"
CONTEXT = json.loads(Path("tests/fixtures/modern_v12_context.json").read_text())


def envelope(plan):
    return dict(
        schema_version="research-query-plan-v13",
        prompt_version="research-planner-v19",
        model="fixture",
        plan=plan,
        reference_date="2026-10-04",
        timezone="Europe/Berlin",
        diagnostics=dict(
            request_id="a" * 32,
            interaction_kind=plan["interaction"]["kind"],
            validation_stage="validated",
            planner_model="fixture",
            planner_prompt_version="research-planner-v19",
            planner_ms=1,
            total_ms=1,
        ),
    )


def grouped(query, mode="new"):
    # Reuse the existing tested grouped executor with no source-resolution fixtures.
    from tests.test_research_grouping_flow import envelope as grouped_envelope

    plan = grouped_envelope()["plan"]
    plan.update(original_query=query, spatial=[])
    if plan["temporal"]:
        plan["temporal"].update(recurring_weekdays=[], recurring_months=[])
    return dict(
        original_query=query,
        language="de",
        interaction=dict(
            kind="correction" if mode == "correction" else "research",
            research_mode=mode,
            research_plan=plan,
        ),
    )


@pytest.mark.parametrize("case", SOCIAL, ids=lambda c: c["request"]["query"])
async def test_social_never_reaches_executor_resolver_sql_or_qdrant(
    client, settings, headers, flow, monkeypatch, case
):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v13"
    state["response"] = envelope(case["plan"])
    execute = AsyncMock(side_effect=AssertionError("no research execution"))
    monkeypatch.setattr(service.ResearchPlanExecutor, "execute", execute)
    response = await client.post(PATH, headers=headers, json={"query": case["request"]["query"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "conversation" and body["answer_text"]
    assert body["language"] == case["plan"]["language"]
    assert len(body["conversation_id"]) == 43
    assert set(body) == {"kind", "answer_text", "language", "conversation_id", "interaction"}
    assert len(requests) == 1 and requests[0].url.path == "/v13/plan"
    execute.assert_not_awaited()
    resolve.assert_not_awaited()
    sql.execute.assert_not_awaited()
    learn.assert_not_awaited()


async def test_research_social_correction_sequence_retains_backend_state(
    client, settings, headers, flow, caplog
):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v13"
    state["response"] = envelope(grouped("Welche Veranstaltungstypen nach Monaten?"))
    first = await client.post(
        PATH, headers=headers, json={"query": state["response"]["plan"]["original_query"]}
    )
    assert first.status_code == 200, first.text
    data = first.json()
    token = data["conversation_id"]
    assert data["conversation_summary"] is None and data["language"] == "de"
    assert "7 Termine" in data["answer_text"] and "September" in data["answer_text"]
    state["response"] = envelope(SOCIAL[0]["plan"])
    social = await client.post(
        PATH, headers=headers, json={"query": "danke", "conversation_id": token}
    )
    assert social.status_code == 200, social.text
    assert social.json()["conversation_id"] == token
    assert sql.execute.await_count == 1
    prior = json.loads(requests[-1].content)["conversation_context"]
    assert prior["previous_turns"][-1]["groupings"] == ["event_type", "month"]
    state["response"] = envelope(grouped("nein, nur sonntags", "correction"))
    wire = state["response"]["plan"]["interaction"]["research_plan"]
    wire["group_by"] = ["event_type"]
    temporal = deepcopy(
        next(
            c["plan"]["interaction"]["research_plan"]["temporal"]
            for c in CASES
            if c["request"]["query"] == "und sonntags?"
        )
    )
    wire["temporal"] = temporal
    sql.execute.return_value.mappings.return_value = [dict(key="1", name="Konzert", value=7)]
    result = await client.post(
        PATH, headers=headers, json={"query": "nein, nur sonntags", "conversation_id": token}
    )
    assert result.status_code == 200, result.text
    payload = json.loads(requests[-1].content)
    assert payload["conversation_context"] == prior
    assert payload["conversation_language"] == "de"
    assert resolve.await_args.args[2].temporal.weekdays == (7,)
    assert resolve.await_args.args[2].groupings == ("event_type",)
    assert sql.execute.await_count == 2
    learn.assert_not_awaited()
    assert "danke" not in caplog.text and token not in caplog.text
    assert "conversation_context" not in result.json()


async def test_no_client_context_and_no_invented_result_reference(client, settings, headers, flow):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v13"
    context = deepcopy(CONTEXT)
    result = await client.post(
        PATH, headers=headers, json={"query": "x", "conversation_context": context}
    )
    assert result.status_code == 422 and not requests
    case = next(c for c in SOCIAL if c["request"]["query"] == "der erste")
    state["response"] = envelope(case["plan"])
    result = await client.post(PATH, headers=headers, json={"query": "der erste"})
    assert result.status_code == 200
    assert result.json()["interaction"]["conversation"]["reason"] == "needs_context"
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()
    learn.assert_not_awaited()


async def test_expired_id_never_reuses_or_exposes_other_state(client, settings, headers, flow):
    state, requests, sql, _, _ = flow
    settings.research_planner_contract = "v13"
    value = deepcopy(SOCIAL[0]["plan"])
    value.update(original_query="und morgen?", language="da")
    state["response"] = envelope(value)
    response = await client.post(
        PATH, headers=headers, json={"query": "und morgen?", "conversation_id": "x" * 43}
    )
    assert response.status_code == 200
    assert response.json()["interaction"]["conversation"]["reason"] == "needs_context"
    assert response.json()["conversation_id"] != "x" * 43
    assert len(requests) == 1
    assert response.json()["language"] == "da"
    sql.execute.assert_not_awaited()


async def test_unsupported_execution_is_a_natural_response_without_dropping_filters(
    client, settings, headers, flow
):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v13"
    case = next(c for c in CASES if c["request"]["query"] == "und kostenlos?")
    state["response"] = envelope(case["plan"])
    response = await client.post(PATH, headers=headers, json={"query": "und kostenlos?"})
    assert response.status_code == 200, response.text
    assert response.json()["interaction"]["conversation"]["act"] == "unsupported"
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()
    learn.assert_not_awaited()


@pytest.mark.parametrize("change", ["extra_plan", "wrong_query", "wrong_kind", "wrong_prompt"])
async def test_invalid_planner_output_fails_closed_without_fallback(
    client, settings, headers, flow, change
):
    state, requests, sql, resolve, learn = flow
    settings.research_planner_contract = "v13"
    value = envelope(deepcopy(SOCIAL[0]["plan"]))
    if change == "extra_plan":
        value["plan"]["interaction"]["research_plan"] = grouped("danke")["interaction"][
            "research_plan"
        ]
    if change == "wrong_query":
        value["plan"]["original_query"] = "changed"
    if change == "wrong_kind":
        value["diagnostics"]["interaction_kind"] = "research"
    if change == "wrong_prompt":
        value["prompt_version"] = "research-planner-v18"
    state["response"] = value
    response = await client.post(PATH, headers=headers, json={"query": "danke"})
    assert response.status_code == 502
    assert len(requests) == 1
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()
    learn.assert_not_awaited()


def test_memory_is_bounded_expires_and_is_session_bound():
    now = [0]
    store = ConversationStore(ttl=30, capacity=2, per_session=1, clock=lambda: now[0])
    with store.turn("session-a", None) as (token, state, expired):
        assert not expired
        state.language = "da"
        with pytest.raises(APIError):
            with store.turn("session-a", token):
                pass
    with store.turn("session-b", token) as (other, new, expired):
        assert expired and other != token and new.language == "de"
    with store.turn("session-a", token) as (_, old, expired):
        assert not expired and old.language == "da"
    now[0] = 31
    with store.turn("session-a", token) as (replacement, _, expired):
        assert expired and replacement != token
    assert len(store.entries) == 1
    summary = ResearchPlanSummaryV12.model_validate(CONTEXT["previous_turns"][0])
    for _ in range(9):
        state.remember(summary)
    assert len(state.summaries) == 4
    state.remember(None)
    assert state.context() is None


@pytest.mark.parametrize(
    "language,noun", [("de", "Termine"), ("da", "forekomster"), ("en", "occurrences")]
)
def test_answers_are_grounded_localized_and_bounded(language, noun):
    facts = AnswerFacts(kind="count", metric="occurrence_count", value=7, shown=0)
    text = render_facts(facts, language)
    assert "7" in text and noun in text
    explanation = render_conversation(
        ConversationV13(act="explain_previous", reason=None), language, facts=facts
    )
    assert text in explanation and len(explanation) <= 1000
    with pytest.raises(ValidationError):
        AnswerFacts.model_validate({**facts.model_dump(), "sql": "private"})


def test_wire_snapshot_matches_planner():
    from tests.test_research_calendar import canonical_schema

    snapshot = json.loads(Path("tests/fixtures/conversation_v13_schema.json").read_text())
    assert canonical_schema(PlanResponseV13.model_json_schema()) == snapshot["response"]


async def test_today_thanks_tomorrow_preserves_area_and_subject(
    client, settings, headers, flow, monkeypatch
):
    from datetime import UTC, datetime

    from app.research.outcome import ResearchExecutionOutcome
    from app.schemas.research_execution import (
        ExecutionDiagnostics,
        ExecutionProvenance,
        RecordsResult,
    )

    state, requests, _, _, _ = flow
    settings.research_planner_contract = "v13"
    executor = AsyncMock(
        return_value=ResearchExecutionOutcome(
            resolution=[],
            result=RecordsResult(items=[], total=0),
            execution=ExecutionProvenance(structured=True),
            observed_at=datetime.now(UTC),
            diagnostics=ExecutionDiagnostics(planner_ms=1, total_ms=1),
        )
    )
    monkeypatch.setattr(service.ResearchPlanExecutor, "execute", executor)
    initial = next(
        c for c in CASES if c["request"]["query"] == "was kann ich heute in Flensburg machen?"
    )
    followup = next(c for c in CASES if c["request"]["query"] == "und morgen?")
    token = None
    for case in [initial, SOCIAL[0], followup]:
        state["response"] = envelope(case["plan"])
        response = await client.post(
            PATH,
            headers=headers,
            json={"query": case["request"]["query"], "conversation_id": token},
        )
        assert response.status_code == 200, response.text
        token = response.json()["conversation_id"]
    previous = json.loads(requests[-1].content)["conversation_context"]["previous_turns"][-1]
    assert previous["entity_type"] == "event"
    assert previous["temporal"]["period"] == "today"
    assert previous["areas"] == [
        dict(name="Flensburg", relation="inside", expected_level="municipality")
    ]
    actual = executor.await_args.args[2]
    assert actual.temporal.period == "tomorrow"
    assert actual.spatial_constraints[0].reference.name == "Flensburg"
    assert executor.await_count == 2
    assert "conversation_context" not in response.text


@pytest.mark.parametrize("version", ["v11", "v12"])
async def test_rollback_context_stays_in_backend(client, settings, headers, flow, version):
    from tests.test_research_calendar import CASES as CALENDAR
    from tests.test_research_calendar import set_response

    state, requests, _, _, _ = flow
    settings.research_planner_contract = version
    set_response(state, deepcopy(CALENDAR[0]))
    state["response"].update(
        schema_version=f"research-query-plan-{version}",
        prompt_version="research-planner-v17" if version == "v11" else "research-planner-v18",
    )
    state["response"]["diagnostics"]["planner_prompt_version"] = state["response"]["prompt_version"]
    if version == "v12":
        wire = state["response"]["plan"]
        wire["spatial"] = [{**wire["spatial"], "area_level": None}] if wire["spatial"] else []
    query = state["response"]["plan"]["original_query"]
    first = await client.post(PATH, headers=headers, json={"query": query})
    assert first.status_code == 200, first.text
    second = await client.post(
        PATH,
        headers=headers,
        json={"query": query, "conversation_id": first.json()["conversation_id"]},
    )
    assert second.status_code == 200, second.text
    assert json.loads(requests[-1].content)["conversation_context"]["previous_turns"]


def test_fact_projection_discards_keys_and_preserves_displayed_scope():
    from app.research.answer_facts import project_answer_facts
    from app.research.plan import InternalResearchPlan
    from app.schemas.research_execution import ExecutionProvenance, GroupedResult

    result = GroupedResult.model_validate(
        {
            "kind": "grouped",
            "metric": "occurrence_count",
            "dimensions": ["month"],
            "ordering": "desc",
            "limit": 20,
            "items": [
                {
                    "coordinates": [{"dimension": "month", "key": "PRIVATE-ID", "name": "09"}],
                    "value": 7,
                }
            ],
        }
    )
    facts = project_answer_facts(
        InternalResearchPlan(
            intent="aggregate", entity_type="event", metric="occurrence_count", groupings=("month",)
        ),
        result,
        ExecutionProvenance(),
    )
    assert "PRIVATE-ID" not in facts.model_dump_json()
    assert "September" in render_facts(facts, "de")
    assert "angezeigten Daten" in render_facts(facts, "de")
    assert "displayed data" in render_facts(facts, "en")


def test_ties_and_semantic_matches_are_not_global_or_unique_claims():
    from app.research.answer_facts import AnswerCell

    facts = AnswerFacts(
        kind="grouped",
        metric="occurrence_count",
        shown=2,
        ordering="desc",
        cells=[
            AnswerCell(labels=["A"], dimensions=["event_type"], value=7),
            AnswerCell(labels=["B"], dimensions=["event_type"], value=7),
        ],
    )
    text = render_facts(facts, "de")
    assert "2 Gruppen" in text and "höchste angezeigte Wert" in text
    assert "„A“" not in text
    facts = AnswerFacts(kind="records", shown=1, semantic=True)
    assert "keine vollständige Zählung" in render_facts(facts, "de")
    assert "not a complete count" in render_facts(facts, "en")
    assert "ikke en fuldstændig optælling" in render_facts(facts, "da")


async def test_clarification_does_not_replay_stale_facts(client, settings, headers, flow):
    state, _, _, _, _ = flow
    settings.research_planner_contract = "v13"
    state["response"] = envelope(grouped("Veranstaltungstypen nach Monaten"))
    first = await client.post(
        PATH, headers=headers, json={"query": "Veranstaltungstypen nach Monaten"}
    )
    token = first.json()["conversation_id"]
    case = next(c for c in SOCIAL if c["request"]["query"] == "der erste")
    state["response"] = envelope(case["plan"])
    await client.post(PATH, headers=headers, json={"query": "der erste", "conversation_id": token})
    stored = client._transport.app.state.research_conversations.entries[token]
    assert stored.summaries and stored.facts is None
