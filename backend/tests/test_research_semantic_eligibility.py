"""Top-K runs within complete SQL eligibility, using fake encoder/Qdrant HTTP only."""

import json
from datetime import date, time
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
from fastapi import Request
from sqlalchemy import text

from app.errors import APIError
from app.repositories import research_execution as repository
from app.repositories.research import rehydrate_semantic_events
from app.repositories.research_resolution import Resolution
from app.research.semantic_limits import MAX_ELIGIBLE_EVENTS
from app.research.vector_models import MODELS
from app.research.vector_transport import Encoder, Qdrant
from app.schemas.research_execution import ExecutionFilters, ResolutionCandidate, ResolvedField
from app.services import research_plan_execution as executor
from app.services import semantic_search as semantic
from tests.conftest import uid
from tests.test_research_plan_execution import eligible_population as eligible_population_fixture
from tests.test_research_plan_execution import execution_source as execution_source_fixture
from tests.test_research_plan_execution import planned
from tests.test_semantic_search import hit
from tests.test_semantic_search import retrieval as retrieval_fixture

eligible_population = eligible_population_fixture
execution_source = execution_source_fixture
retrieval = retrieval_fixture


def semantic_plan(**changes):
    return planned(
        intent="search", requires_semantic_relevance=True, semantic_query="culture", **changes
    )


@pytest.fixture
def ranking_transport(retrieval, settings, monkeypatch):
    """Model Qdrant's actual order: apply membership, score-sort, THEN limit.

    This deliberately also accepts an unfiltered request: the old executor would
    receive the 50 ineligible hits and lose rank 51, making the regression fail.
    """
    state = {"hits": [], "requests": [], "trace": [], "db_open": False}

    def respond(request):
        assert not state["db_open"], "Source snapshot held across external retrieval"
        state["requests"].append(request)
        body = json.loads(request.content)
        if request.url.path == "/embed":
            state["trace"].append("encoder")
            return httpx.Response(
                200,
                json={
                    "embedding_version": MODELS["jina-v3"].version,
                    "vectors": [[1.0] * 1024],
                },
            )
        state["trace"].append("qdrant")
        points = state["hits"]
        for condition in body.get("filter", {}).get("must", []):
            assert condition["key"] == "entity_id", "Stale payload must not narrow SQL eligibility"
            allowed = set(condition["match"]["any"])
            points = [p for p in points if p["payload"]["entity_id"] in allowed]
        points = sorted(points, key=lambda p: (-p["score"], p["payload"]["entity_id"]))
        return httpx.Response(200, json={"result": {"points": points[: body["limit"]]}})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(semantic, "Encoder", lambda s, m: Encoder(s, m, transport))
    monkeypatch.setattr(semantic, "Qdrant", lambda s, m, **kw: Qdrant(s, m, transport, **kw))
    return state


async def test_rank_51_and_snapshot_lifecycle(
    settings,
    monkeypatch,
    eligible_population,
    ranking_transport,
    retrieval,
):
    state = ranking_transport
    state["hits"] = [hit(i, 1 - (i - 100) / 100) for i in range(100, 150)] + [hit(30, 0.5)]
    assert len(state["hits"]) == 51
    assert state["hits"][-1]["score"] < min(p["score"] for p in state["hits"][:-1])
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=Resolution()))

    async def connection(request):
        assert not state["db_open"]
        state["db_open"] = True
        state["trace"].append("db_open")
        try:
            yield object()
        finally:
            state["db_open"] = False
            state["trace"].append("db_close")

    monkeypatch.setattr(executor, "get_connection", connection)
    monkeypatch.setattr(semantic, "get_connection", connection)
    page = retrieval["rehydrate"].return_value

    async def rehydrate(connection, settings, filters, candidates, now, area):
        return page.model_copy(
            update={
                "items": [item for item in page.items if item.entity_key in candidates],
            }
        )

    retrieval["rehydrate"].side_effect = rehydrate
    response = await executor.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        semantic_plan(time_of_day="evening"),
    )
    assert [item.entity_key for item in response.result.items] == [uid(30)]
    assert response.result.items[0].semantic.score == 0.5
    assert state["trace"] == ["db_open", "db_close", "encoder", "qdrant", "db_open", "db_close"]
    assert retrieval["rehydrate"].call_args.args[3] == [uid(30)]


@pytest.mark.parametrize("failure", [None, "encoder", "qdrant"])
async def test_empty_eligibility_never_calls_semantic(
    settings,
    monkeypatch,
    eligible_population,
    retrieval,
    failure,
):
    eligible_population.return_value = []
    retrieval["failure"] = failure
    settings.semantic_search_noncommercial_jina = False
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=Resolution()))
    response = await executor.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        semantic_plan(),
    )
    assert response.result.items == [] and response.result.total is None
    assert response.execution.semantic
    assert retrieval["requests"] == []
    retrieval["rehydrate"].assert_not_called()


@pytest.mark.parametrize("failure", ["encoder", "qdrant"])
async def test_nonempty_unavailable_never_falls_back(
    settings,
    monkeypatch,
    eligible_population,
    retrieval,
    failure,
):
    retrieval["failure"] = failure
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=Resolution()))
    structured = AsyncMock(side_effect=AssertionError("No structured fallback"))
    monkeypatch.setattr(executor, "research_page", structured)
    with pytest.raises(APIError) as exc:
        await executor.ResearchPlanExecutor().execute(
            Request({"type": "http"}), settings, semantic_plan()
        )
    assert (exc.value.status, exc.value.code) == (503, "research_semantic_unavailable")
    structured.assert_not_called()


@pytest.mark.parametrize("size", [MAX_ELIGIBLE_EVENTS, MAX_ELIGIBLE_EVENTS + 1])
async def test_complete_eligibility_or_error_not_slice(settings, size):
    identifiers = [uid(i) for i in range(size)]
    rows = Mock()
    rows.scalars.return_value = identifiers
    connection = AsyncMock()
    connection.execute.return_value = rows
    call = repository.eligible_event_ids(
        connection, settings, ExecutionFilters(entity_type="event"), None
    )
    if size > MAX_ELIGIBLE_EVENTS:
        with pytest.raises(APIError) as exc:
            await call
        assert (exc.value.status, exc.value.code) == (422, "research_execution_too_broad")
    else:
        assert await call == identifiers
    sql, params = connection.execute.call_args.args
    assert params["eligibility_probe_limit"] == MAX_ELIGIBLE_EVENTS + 1
    assert "SELECT DISTINCT entity_key" in str(sql)
    assert "e.description" not in str(sql) and "e.title name" not in str(sql)


async def test_too_broad_stops_before_encoder(
    settings, monkeypatch, eligible_population, retrieval
):
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=Resolution()))
    eligible_population.side_effect = APIError(
        422, "research_execution_too_broad", "Narrow the research request before semantic ranking."
    )
    with pytest.raises(APIError) as exc:
        await executor.ResearchPlanExecutor().execute(
            Request({"type": "http"}), settings, semantic_plan()
        )
    assert exc.value.code == "research_execution_too_broad"
    assert retrieval["requests"] == []


async def test_membership_request_bound(settings, retrieval):
    qdrant = Qdrant(
        settings,
        "jina-v3",
        httpx.MockTransport(lambda r: httpx.Response(200, json={"result": {"points": []}})),
        entity="event",
    )
    request = AsyncMock(return_value={"result": {"points": []}})
    qdrant.http.request = request
    try:
        ids = [uid(i) for i in range(MAX_ELIGIBLE_EVENTS)]
        await qdrant.search([1.0] * 1024, 50, entity_ids=ids)
        body = request.call_args.args[2]
        assert body["filter"] == {
            "must": [{"key": "entity_id", "match": {"any": [str(i) for i in ids]}}]
        }
        assert len(json.dumps(body).encode()) < 512 * 1024 < 2 * 1024 * 1024
        request.reset_mock()
        for invalid in ([], ids + [uid(MAX_ELIGIBLE_EVENTS)], ["not-a-uuid"]):
            with pytest.raises(ValueError, match="invalid_eligible_event_ids"):
                await qdrant.search([1.0] * 1024, 50, entity_ids=invalid)
        request.assert_not_called()
    finally:
        await qdrant.http.close()


@pytest.mark.parametrize(
    "dimension",
    [
        "date",
        "evening",
        "venue",
        "organization",
        "category",
        "genre",
        "event_type",
        "area",
        "event_status",
        "date_status",
    ],
)
async def test_rank_51_real_sql_hard_filters(
    admin_store,
    execution_source,
    settings,
    monkeypatch,
    ranking_transport,
    dimension,
):
    """Actual PostgreSQL eligibility + real HTTP adapter + ordered 51-hit fake Qdrant."""
    connection = execution_source
    valid = uid(2050)
    events, dates = [], []
    for n in range(2000, 2051):
        wrong = n != 2050
        events.append(
            {
                "id": uid(n),
                "org": uid(11 if wrong and dimension == "organization" else 10),
                "venue": uid(20 if wrong and dimension in {"venue", "area"} else 21),
                "categories": [102 if wrong and dimension == "category" else 101],
                "status": "draft" if wrong and dimension == "event_status" else "released",
            }
        )
        dates.append(
            {
                "id": uid(n + 1000),
                "event": uid(n),
                "date": date(2026, 10, 1) if wrong and dimension == "date" else date(2026, 9, 30),
                "time": time(17, 59) if wrong and dimension == "evening" else time(20),
                "status": "draft" if wrong and dimension == "date_status" else "inherited",
            }
        )
    await connection.execute(
        text("""INSERT INTO uranus.event(uuid,org_uuid,venue_uuid,title,categories,release_status)
        VALUES(:id,:org,:venue,'Rank regression',:categories,:status)"""),
        events,
    )
    await connection.execute(
        text("""INSERT INTO uranus.event_date
        (uuid,event_uuid,start_date,start_time,all_day,release_status)
        VALUES(:id,:event,:date,:time,false,:status)"""),
        dates,
    )
    await connection.execute(
        text("""INSERT INTO uranus.event_type_link(event_uuid,type_id,genre_id)
        VALUES(:id,:type,:genre)"""),
        [
            {
                "id": uid(n),
                "type": 2 if n != 2050 and dimension == "event_type" else 1,
                "genre": 3 if n != 2050 and dimension == "genre" else 2,
            }
            for n in range(2000, 2051)
        ],
    )
    resolution = Resolution()
    changes = {}
    if dimension in {"venue", "organization", "category", "genre", "event_type"}:
        field, identifier = {
            "venue": ("venue_query", str(uid(21))),
            "organization": ("organization_query", str(uid(10))),
            "category": ("category_queries", "101"),
            "genre": ("genre_queries", "1:2"),
            "event_type": ("event_type_queries", "1"),
        }[dimension]
        resolution.fields = [
            ResolvedField(
                field=field,
                query="Resolved",
                target=ResolutionCandidate(entity_type=dimension, id=identifier, label="Public"),
            )
        ]
    if dimension == "area":
        from app.repositories.research_areas import resolve_area
        from tests.test_semantic_knowledge_index import insert_area

        await insert_area(
            connection, uid(901), "Flensburg", "POLYGON((9 54,10 54,10 55,9 55,9 54))", 991
        )
        resolution.area = await resolve_area(connection, uid(901))
    if dimension == "evening":
        changes["time_of_day"] = "evening"
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=resolution))

    async def source(request):
        yield connection

    monkeypatch.setattr(semantic, "get_connection", source)
    monkeypatch.setattr(semantic, "rehydrate_semantic_events", rehydrate_semantic_events)
    state = ranking_transport
    # No area/genre payload membership at all: PostgreSQL alone establishes scope.
    state["hits"] = [hit(n, 1 - (n - 2000) / 100) for n in range(2000, 2051)]
    response = await executor.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, semantic_plan(**changes)
    )
    assert [i.entity_key for i in response.result.items] == [valid]
    assert response.result.items[0].semantic.score == 0.5
    body = json.loads(state["requests"][-1].content)
    eligible = {UUID(key) for key in body["filter"]["must"][0]["match"]["any"]}
    assert eligible.intersection(uid(n) for n in range(2000, 2051)) == {valid}

    # Simulate source changes between eligibility and rehydration. Payload cannot
    # preserve an event that is now ineligible (including PostGIS and genre scope).
    async def changed_source(request):
        if dimension == "area":
            await connection.execute(
                text("UPDATE uranus.venue SET point=NULL WHERE uuid=:id"), {"id": uid(21)}
            )
        elif dimension in {"genre", "event_type"}:
            await connection.execute(
                text("DELETE FROM uranus.event_type_link WHERE event_uuid=:id"), {"id": valid}
            )
        else:
            await connection.execute(
                text("UPDATE uranus.event SET release_status='draft' WHERE uuid=:id"),
                {"id": valid},
            )
        yield connection

    monkeypatch.setattr(semantic, "get_connection", changed_source)
    response = await executor.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, semantic_plan(**changes)
    )
    assert response.result.items == []


async def test_sql_eligibility_bound_is_unique_population(execution_source, settings, monkeypatch):
    # Existing fixture has two public events and multiple matching dates each.
    filters = ExecutionFilters(entity_type="event", from_date=date(2026, 9, 30))
    monkeypatch.setattr(repository, "MAX_ELIGIBLE_EVENTS", 2)
    assert await repository.eligible_event_ids(execution_source, settings, filters, None) == [
        uid(30),
        uid(32),
    ]
    monkeypatch.setattr(repository, "MAX_ELIGIBLE_EVENTS", 1)
    with pytest.raises(APIError) as exc:
        await repository.eligible_event_ids(execution_source, settings, filters, None)
    assert exc.value.code == "research_execution_too_broad"


@pytest.mark.parametrize("score,expected_count", [(0.07, 0), (0.15, 1)])
async def test_planner_semantic_records_apply_relevance_gate(
    settings, monkeypatch, eligible_population, retrieval, score, expected_count
):
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=Resolution()))
    retrieval["hits"] = [hit(30, score)]
    response = await executor.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, semantic_plan()
    )
    assert response.result.kind == "records"
    assert len(response.result.items) == expected_count
    assert response.result.total is None
    assert response.execution.semantic
    assert len(retrieval["requests"]) == 2
    if expected_count:
        assert response.result.items[0].semantic.score == score
