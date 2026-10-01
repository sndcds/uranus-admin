"""v4 routing and exact SQL tests. No production connections or model calls."""

import json
from pathlib import Path
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
from tests.test_research_domain_contract import INVALID_ENVELOPES, QUESTION

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
    plan = KnowledgePlan(knowledge_query=question, fact="semantic_search_repository")
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
            plan=KnowledgePlan(knowledge_query=question, fact="founding_date"),
        )
        return httpx.Response(
            200, json=result.model_dump(mode="json"), headers={"set-cookie": "private=value"}
        )

    client = ResearchDomainClient(settings, transport=httpx.MockTransport(handler))
    await client.plan("  When was Kulturbytes founded?\n")
    await client.plan("  When was Kulturbytes founded?\n")
    assert all("cookie" not in r.headers for r in calls)
    assert all(r.url.path == "/v4/plan" for r in calls)
    await client.close()


@pytest.mark.parametrize("wire", INVALID_ENVELOPES)
async def test_injected_invalid_plans_never_reach_execution(
    client, headers, unified, monkeypatch, wire
):
    # Simulate injected providers bypassing Pydantic via model_construct/copy.
    class UnvalidatedEnvelope:
        def model_dump_json(self):
            return json.dumps(wire)

    unified.plan.return_value = UnvalidatedEnvelope()

    def forbidden(*args):
        raise AssertionError("Invalid plans must not reach a database")

    monkeypatch.setattr("app.services.research_unified.get_connection", forbidden)
    monkeypatch.setattr("app.services.research_unified.connect_admin", forbidden)
    response = await client.post(PATH, json={"query": QUESTION}, headers=headers)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "research_domain_invalid"
    unified.answer.assert_not_called()


def synthetic_evidence(fact):
    from datetime import UTC, datetime
    from hashlib import sha256

    from app.schemas.project_knowledge import Assertion, Chunk, Fact

    if fact == "founding_date":
        return AnswerResponse(
            supported=False,
            facts=[],
            evidence=[],
            indexed_commits={},
            reason="no_explicit_evidence",
        )
    repository = (
        "sndcds/uranus-admin"
        if fact == "semantic_search_repository"
        else "sndcds/uranus-research-encoder"
    )
    prose = f"Synthetic acceptance fixture: {repository}."
    chunk = Chunk(
        repository=repository,
        commit_sha="a" * 40,
        path="README.md",
        document_type="documentation",
        heading_or_symbol="Synthetic fixture",
        unit="fixture",
        source_url=f"https://github.com/{repository}/blob/{'a' * 40}/README.md",
        content_hash=sha256(prose.encode()).hexdigest(),
        indexed_at=datetime(2026, 1, 1, tzinfo=UTC),
        chunk_text=prose,
        line_start=1,
        line_end=1,
        license="synthetic",
        graph_node_ids=[],
        assertions=[Assertion(fact=fact, value=repository, quote=prose)],
    )
    return AnswerResponse(
        supported=True,
        facts=[Fact(key=fact, value=repository, evidence_ids=[chunk.point_id])],
        evidence=[chunk],
        indexed_commits={repository: ["a" * 40]},
        reason="supported",
    )


@pytest.mark.parametrize(
    "case",
    json.loads(Path("tests/fixtures/research_domain_acceptance.json").read_text())["cases"],
    ids=lambda case: case["id"],
)
async def test_cross_repo_synthetic_acceptance(client, headers, monkeypatch, case):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import Mock

    from app.schemas.research_unified import MetricRecord

    app = client._transport.app
    settings = app.state.settings
    settings.research_domain_enabled = True
    settings.research_planner_url = "http://127.0.0.1:8090"
    settings.research_planner_api_key = SecretStr("p" * 32)
    settings.research_knowledge_url = "http://127.0.0.1:6336"
    settings.research_knowledge_api_key = SecretStr("k" * 32)
    plan = case["plan"]
    question = case["query"]
    calls = []
    answer = synthetic_evidence(plan["fact"]) if plan["domain"] == "project_knowledge" else None

    def handler(request):
        calls.append(request)
        assert "cookie" not in request.headers
        assert request.method == "POST"
        if len(calls) == 1:
            assert str(request.url) == "http://127.0.0.1:8090/v4/plan"
            assert request.headers["authorization"] == "Bearer " + "p" * 32
            assert json.loads(request.content) == {"query": question}
            return httpx.Response(
                200,
                json={
                    "schema_version": "research-query-plan-v4",
                    "interpreter_version": "research-domain-planner-v2",
                    "original_query": question,
                    "plan": plan,
                },
            )
        assert str(request.url) == "http://127.0.0.1:6336/evidence-answer"
        assert request.headers["authorization"] == "Bearer " + "k" * 32
        assert json.loads(request.content) == {"query": question, "fact": plan["fact"]}
        assert answer is not None
        return httpx.Response(200, json=answer.model_dump(mode="json"))

    provider = ResearchDomainClient(settings, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(app.state, "research_domain", provider)
    connection = object()
    admin = AsyncMock()
    admin.begin = Mock(return_value=AsyncMock())
    area = SimpleNamespace(area=SimpleNamespace(id=uid(90)), ewkb=b"synthetic-boundary")
    resolve = AsyncMock(return_value=area)
    candidates = AsyncMock(return_value=[SimpleNamespace(id=str(uid(90)))])
    rank = AsyncMock(return_value=[MetricRecord(key=str(uid(30)), name="Synthetic", value=42)])

    async def source(request):
        assert plan["domain"] == "data"
        yield connection

    @asynccontextmanager
    async def admin_connection(request):
        assert plan.get("area_query") == "Flensburg"
        yield admin

    monkeypatch.setattr("app.services.research_unified.get_connection", source)
    monkeypatch.setattr("app.services.research_unified.connect_admin", admin_connection)
    monkeypatch.setattr("app.services.research_unified.rank_metric", rank)
    monkeypatch.setattr("app.services.research_unified.candidates", candidates)
    monkeypatch.setattr("app.services.research_unified.resolve_area", resolve)
    try:
        response = await client.post(PATH, json={"query": question}, headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
        if answer is not None:
            assert result == answer.model_dump(mode="json")
            assert len(calls) == 2
            rank.assert_not_called()
        else:
            assert result["authoritative_source"] == "postgresql"
            assert result["records"][0]["value"] == 42
            expected_area = area if plan["area_query"] else None
            rank.assert_awaited_once_with(
                connection,
                settings,
                DataPlan.model_validate(plan),
                ExecutionFilters(entity_type="event", area_id=uid(90) if expected_area else None),
                expected_area,
            )
            assert len(calls) == 1
        if plan.get("area_query"):
            candidates.assert_awaited_once_with(admin, "area", "Flensburg", settings)
            resolve.assert_awaited_once_with(admin, uid(90))
        else:
            candidates.assert_not_called()
            resolve.assert_not_called()
    finally:
        await provider.close()


@pytest.mark.parametrize(
    "tamper",
    [
        "fact",
        "content_hash",
        "source_url",
        "indexed_commits",
        "authoritative_source",
        "schema_version",
    ],
)
async def test_evidence_contract_remains_validated(settings, tamper):
    payload = synthetic_evidence("embedding_component").model_dump(mode="json")
    requested_fact = "embedding_component"
    if tamper == "fact":
        requested_fact = "embedding_model"  # Internally valid evidence, wrong requested fact.
    elif tamper in {"content_hash", "source_url", "schema_version"}:
        payload["evidence"][0][tamper] = "invalid"
    elif tamper == "indexed_commits":
        payload["indexed_commits"] = {}
    else:
        payload["authoritative_source"] = "postgresql"
    settings.research_knowledge_url = "http://127.0.0.1:6336"
    settings.research_knowledge_api_key = SecretStr("k" * 32)
    provider = ResearchDomainClient(
        settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    try:
        with pytest.raises(APIError) as exc:
            await provider.answer(
                KnowledgePlan(fact=requested_fact, knowledge_query="original question")
            )
        assert (exc.value.status, exc.value.code) == (502, "research_domain_invalid")
    finally:
        await provider.close()
