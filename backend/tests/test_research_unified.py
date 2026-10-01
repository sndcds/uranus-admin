"""v4 routing and exact SQL tests. No production connections or model calls."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

from app.errors import APIError
from app.repositories.research_metrics import rank_metric
from app.schemas.project_knowledge import AnswerResponse
from app.schemas.research_domain import DataPlan, KnowledgePlan, PlanEnvelopeV4
from app.schemas.research_execution import ExecutionFilters
from app.services.research_domain_client import ResearchDomainClient
from tests.conftest import uid

PATH = "/api/v1/research/v4/query"


@pytest.fixture
def unified(client, monkeypatch):
    app = client._transport.app
    app.state.settings.research_domain_enabled = True
    provider = AsyncMock()
    monkeypatch.setattr(app.state, "research_domain", provider)
    return provider


async def test_project_routing_never_uses_database(client, headers, unified, monkeypatch):
    question = "Welches Repository implementiert die semantische Suche?"
    plan = KnowledgePlan(
        knowledge_query="Implementierung der semantischen Suche", fact="semantic_search_repository"
    )
    unified.plan.return_value = PlanEnvelopeV4(original_query=question, plan=plan)
    unified.answer.return_value = AnswerResponse(
        supported=False, facts=[], evidence=[], indexed_commits={}, reason="no_explicit_evidence"
    )

    def forbidden(*args):
        raise AssertionError("Knowledge must not open PostgreSQL")

    monkeypatch.setattr("app.services.research_unified.get_connection", forbidden)
    response = await client.post(PATH, json={"query": question}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["authoritative_source"] == "project_sources"
    unified.answer.assert_awaited_once_with(plan)


async def test_auth_bounds_and_server_side_routing(client, headers, unified):
    assert (await client.post(PATH, json={"query": "test"})).status_code == 401
    for field in ("domain", "plan", "collection", "repository", "executor", "url", "metric"):
        assert (
            await client.post(PATH, json={"query": "test", field: "malicious"}, headers=headers)
        ).status_code == 422
    assert (await client.post(PATH, content=b"x" * 33000, headers=headers)).status_code == 413
    unified.plan.assert_not_called()


async def test_source_query_envelope_match(client, headers, unified):
    unified.plan.return_value = PlanEnvelopeV4(
        original_query="different", plan=DataPlan(entity_type="organization", metric="event_count")
    )
    assert (await client.post(PATH, json={"query": "test"}, headers=headers)).status_code == 502


def test_metric_catalogue_fails_closed():
    for entity, metric in (
        ("venue", "description_characters"),
        ("area", "events_per_capita"),
        ("event", "duration_minutes"),
    ):
        with pytest.raises(ValidationError):
            DataPlan(entity_type=entity, metric=metric)


async def test_exact_metrics_use_distinct_public_population(db_connection, settings):
    expected = [
        ("organization", "event_count", str(uid(10)), 2),
        ("organization", "venue_count", str(uid(10)), 2),
        ("event", "occurrence_count", str(uid(30)), 6),
        ("venue", "occurrence_count", str(uid(20)), 6),
    ]
    for entity, metric, key, value in expected:
        rows = await rank_metric(
            db_connection,
            settings,
            DataPlan(entity_type=entity, metric=metric),
            ExecutionFilters(entity_type="event"),
            None,
        )
        assert (rows[0].key, rows[0].value) == (key, value)


async def test_description_counts_projected_unicode_not_markup(db_connection, settings):
    # Only the guarded disposable fixture connection has write access.
    await db_connection.execute(
        text("UPDATE uranus.event SET description=:text WHERE uuid=:id"),
        {"id": uid(30), "text": "<p>A&amp;B e\u0301 😀</p><script>" + "x" * 200 + "</script>"},
    )
    await db_connection.execute(
        text("UPDATE uranus.event SET description=:text WHERE uuid=:id"),
        {"id": uid(32), "text": "123456789"},
    )
    rows = await rank_metric(
        db_connection,
        settings,
        DataPlan(entity_type="event", metric="description_characters", limit=2),
        ExecutionFilters(entity_type="event"),
        None,
    )
    assert [(r.key, r.value) for r in rows] == [(str(uid(32)), 9), (str(uid(30)), 7)]


async def test_sql_overflow_never_returns_partial_ranking(db_connection, settings, monkeypatch):
    monkeypatch.setattr("app.repositories.research_metrics.MAX_TEXT_EVENTS", 1)
    with pytest.raises(APIError) as exc:
        await rank_metric(
            db_connection,
            settings,
            DataPlan(entity_type="event", metric="description_characters"),
            ExecutionFilters(entity_type="event"),
            None,
        )
    assert exc.value.code == "research_execution_too_broad"


@pytest.mark.parametrize(
    "question,entity,metric,expected",
    [
        (
            "Welches Event hat den längsten Veranstaltungstext?",
            "event",
            "description_characters",
            0,
        ),
        ("Welche Organisation hat die meisten Veranstaltungen?", "organization", "event_count", 2),
    ],
)
async def test_admin_data_question_to_postgresql(
    db_client, headers, monkeypatch, question, entity, metric, expected
):
    app = db_client._transport.app
    app.state.settings.research_domain_enabled = True
    provider = AsyncMock()
    provider.plan.return_value = PlanEnvelopeV4(
        original_query=question, plan=DataPlan(entity_type=entity, metric=metric)
    )
    monkeypatch.setattr(app.state, "research_domain", provider)
    response = await db_client.post(PATH, json={"query": question}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["authoritative_source"] == "postgresql"
    assert response.json()["records"][0]["value"] == expected
    provider.answer.assert_not_called()


async def test_client_no_cookies_and_query_binding(settings):
    settings.research_planner_url = "http://127.0.0.1:8090"
    settings.research_planner_api_key = SecretStr("p" * 32)
    calls = []

    def handler(request):
        calls.append(request)
        question = json.loads(request.content)["query"]
        result = PlanEnvelopeV4(
            original_query=question,
            plan=KnowledgePlan(knowledge_query="founding date", fact="founding_date"),
        )
        return httpx.Response(
            200, json=result.model_dump(mode="json"), headers={"set-cookie": "private=value"}
        )

    client = ResearchDomainClient(settings, transport=httpx.MockTransport(handler))
    await client.plan("When was Kulturbytes founded?")
    await client.plan("When was Kulturbytes founded?")
    assert all("cookie" not in r.headers for r in calls)
    assert all(r.url.path == "/v4/plan" for r in calls)
    await client.close()
