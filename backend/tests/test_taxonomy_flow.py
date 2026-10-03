"""Normal Research API -> real resolver -> shared executor, mocked source/transport only."""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.api import research as api
from app.repositories import research_resolution as resolver
from app.services import research_plan_execution as execution
from app.services.research_planner import ResearchPlannerClient
from tests.test_research_plan_execution import planned
from tests.test_taxonomy_semantic import retrieval as retrieval_fixture

retrieval = retrieval_fixture


@pytest.fixture
async def flow(client, settings, retrieval, monkeypatch):
    settings.research_planner_url = "http://127.0.0.1:8090"
    from pydantic import SecretStr

    settings.research_planner_api_key = SecretStr("fixture-only-key-" * 3)
    state, _, _ = retrieval
    state["planner"] = planned(event_type_queries=["Theater"])
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json=state["planner"].model_dump(mode="json"))

    planner = ResearchPlannerClient(settings, transport=httpx.MockTransport(transport))
    monkeypatch.setattr(client._transport.app.state, "research_planner", planner)
    source = AsyncMock()

    async def connection(request):
        yield source

    monkeypatch.setattr(resolver, "get_connection", connection)
    monkeypatch.setattr(execution, "get_connection", connection)
    rows = Mock()
    rows.mappings.return_value = []
    source.execute.return_value = rows
    monkeypatch.setattr(api, "record_success", AsyncMock())
    yield state, calls, source
    await planner.close()


@pytest.mark.parametrize(
    "concept,key,field,ids",
    [
        ("Theater", "event_type:2", "event_type_ids", [2]),
        ("Schauspiel", "event_type:2", "event_type_ids", [2]),
        ("Circus", "genre:2:2003", "genre_keys", ["2:2003"]),
    ],
)
async def test_normal_query_executes_authoritative_filter(
    client, headers, flow, concept, key, field, ids
):
    state, calls, source = flow
    state["planner"] = planned(
        event_type_queries=[concept],
        original_query=f"wo findet {concept.lower()} statt",
        temporal="none",
    )
    # Preserve exact original_query validation at the planner boundary.
    query = state["planner"].plan.original_query
    state["scores"] = [(key, 0.95), ("genre:2:2004", 0.7)]
    response = await client.post("/api/v1/research/query", headers=headers, json={"query": query})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"] == {"kind": "records", "items": [], "total": None}
    assert body["resolution"][0]["target"]["id"] == key.split(":", 1)[1]
    assert len(calls) == 1
    assert all("score" not in c for c in body["resolution"])
    statement, params = source.execute.await_args.args
    assert params[field] == ids
    assert "selected" in str(statement)
    assert body["sql_provenance"]


async def test_weak_quantitative_concept_never_runs_execution_or_event_vectors(
    client, headers, flow
):
    state, calls, source = flow
    state["planner"] = planned(
        intent="count", answer_mode="count", metric="event_count", event_type_queries=["Unbekannt"]
    )
    state["scores"] = [("event_type:2", 0.4), ("genre:2:2004", 0.3)]
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={"query": state["planner"].plan.original_query},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["reason"] == "no_match"
    assert response.json()["sql_provenance"] == []
    # Only the two exact vocabulary lookups, never the count population SQL.
    assert source.execute.await_count == 2
    assert len(calls) == 1


async def test_ambiguous_proposals_return_labels_not_vectors(client, headers, flow):
    state, _, source = flow
    state["scores"] = [("event_type:2", 0.9), ("genre:2:2004", 0.89)]
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={"query": state["planner"].plan.original_query},
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["reason"] == "ambiguous"
    assert [c["label"] for c in result["candidates"]] == ["Theater & Bühne", "Drama"]
    assert "score" not in response.text and "embedding_text" not in response.text
    assert [c["id"] for c in result["candidates"]] == ["choice-0", "choice-1"]
    assert source.execute.await_count == 2


async def test_cross_kind_genre_retains_explicit_type_conflict(client, headers, flow, monkeypatch):
    from app.schemas.research_execution import ResolutionCandidate

    state, _, _ = flow
    state["planner"] = planned(event_type_queries=["Konzert", "Circus"])
    exact = AsyncMock(
        side_effect=lambda connection, kind, query, types: (
            [ResolutionCandidate(entity_type="event_type", id="1", label="Konzert")]
            if kind == "event_type" and query == "Konzert"
            else []
        )
    )
    monkeypatch.setattr(resolver, "taxonomy_candidates", exact)
    state["scores"] = [("genre:2:2003", 0.95), ("genre:2:2004", 0.7)]
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={"query": state["planner"].plan.original_query},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["reason"] == "taxonomy_conflict"
    assert response.json()["sql_provenance"] == []


def test_http_choice_projection_preserves_internal_taxonomy_identities():
    from app.schemas.research_execution import ExecutionClarification, ResolutionCandidate

    internal = ExecutionClarification(
        reason="ambiguous",
        field="genre_queries",
        query="Jazz",
        candidates=[
            ResolutionCandidate(entity_type="genre", id="1:1003", label="Jazz"),
            ResolutionCandidate(entity_type="genre", id="2:2004", label="Jazz"),
        ],
    )
    public = api._public_execution_result(internal)
    assert [c.id for c in public.candidates] == ["choice-0", "choice-1"]
    assert [c.label for c in public.candidates] == ["Jazz", "Jazz"]
    assert [c.id for c in internal.candidates] == ["1:1003", "2:2004"]
    assert public is not internal


def test_http_choice_projection_keeps_non_taxonomy_candidates_and_success():
    from app.schemas.research_execution import (
        CountResult,
        ExecutionClarification,
        ResolutionCandidate,
    )

    internal = ExecutionClarification(
        reason="ambiguous",
        candidates=[
            ResolutionCandidate(entity_type="venue", id="venue-id", label="Venue"),
        ],
    )
    public = api._public_execution_result(internal)
    assert public.candidates == internal.candidates
    count = CountResult(metric="event_count", value=7)
    assert api._public_execution_result(count) is count
