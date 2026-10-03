"""Real repository SQL against recording connections; no container/source DDL required."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import text

from app.repositories.administrative_execution import administrative_selection
from app.repositories.research_resolution import Resolution
from app.research.context import ResearchExecutionContext
from app.research.plan import (
    ComparisonTarget,
    InternalResearchPlan,
    ResolvedResearchPlan,
    SemanticSelection,
)
from app.research.sql_provenance import (
    LOCATION_REDACTED,
    VALUE_REDACTED,
    collect_research_sql,
    execute_research_sql,
    safe_value,
)
from app.schemas.research_execution import ExecutionFilters, ResolutionCandidate, ResolvedField
from app.schemas.research_location import PlaceFilter
from app.schemas.research_sql import ResearchSqlStatement, ResearchSqlStatements
from app.services import research_plan_execution as service
from tests.conftest import uid
from tests.test_research_plan_execution import planned

NOW = datetime.now(UTC)
CONTEXT = ResearchExecutionContext(date(2026, 9, 30), "Europe/Berlin", "Research SQL fixture")
ROW = {
    "entity_type": "event",
    "entity_key": uid(30),
    "name": "Result",
    "latitude": None,
    "longitude": None,
    "source_url": None,
    "date_key": uid(40),
    "venue_id": uid(20),
    "space_id": uid(25),
}


class Rows:
    def __init__(self, rows=(), scalar=2):
        self.rows, self.scalar = list(rows), scalar

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.rows)

    def all(self):
        return self.rows

    def scalars(self):
        return [uid(30)]

    def scalar_one(self):
        return self.scalar


class Connection:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((statement, params.copy()))
        return next(self.responses)


def install(monkeypatch, connection, resolution=None):
    async def source(_):
        yield connection

    monkeypatch.setattr(service, "get_connection", source)
    monkeypatch.setattr(service, "resolve_plan", AsyncMock(return_value=resolution or Resolution()))
    return source


def assert_actual(statements, calls):
    assert len(statements) == len(calls)
    for captured, (executed, params) in zip(statements, calls, strict=True):
        assert captured.sql == executed.text
        assert captured.parameters == {
            name: safe_value(name, params.get(name, value))
            for name, value in executed.compile().params.items()
        }
        assert len(captured.sql) < 65536
        assert len(captured.parameters) <= 64
    TypeAdapter(ResearchSqlStatements).validate_python(statements)


@pytest.mark.parametrize(
    "plan,rows,expected",
    [
        (InternalResearchPlan("list", "event"), [Rows([ROW]), Rows()], "records"),
        (InternalResearchPlan("list", "venue"), [Rows(), Rows([ROW]), Rows()], "records"),
        (InternalResearchPlan("count", "event", metric="event_count"), [Rows()], "count"),
        (
            InternalResearchPlan("aggregate", "event", metric="event_count", group_by="venue"),
            [Rows([{"key": "v", "name": "Venue", "value": 2}])],
            "aggregate",
        ),
        (
            InternalResearchPlan("taxonomy", "event", taxonomy="genre"),
            [Rows([{"key": "1:2", "name": "Jazz", "event_count": 2, "total": 1}])],
            "taxonomy",
        ),
        (
            InternalResearchPlan(
                "spatial_rank", "venue", spatial_metric="longitude", ordering="asc"
            ),
            [Rows([ROW]), Rows()],
            "spatial",
        ),
    ],
)
async def test_real_execution_paths_preserve_results(settings, monkeypatch, plan, rows, expected):
    connection = Connection(rows)
    install(monkeypatch, connection)
    executor = service.ResearchPlanExecutor()
    captured = await executor.execute(
        Request({"type": "http"}), settings, plan, CONTEXT, planner_ms=0
    )
    assert captured.result.kind == expected
    assert_actual(captured.sql_provenance, connection.calls)
    # The same repository path without the capture scope returns identical data and
    # executes identical templates and bindings. Provenance never adds source reads.
    plain = Connection(rows)
    install(monkeypatch, plain)
    baseline = await executor._execute(
        Request({"type": "http"}), settings, plan, CONTEXT, planner_ms=0
    )
    assert captured.result == baseline.result
    assert [(s.text, p) for s, p in connection.calls] == [(s.text, p) for s, p in plain.calls]


async def test_comparison_keeps_every_target(settings, monkeypatch):
    resolution = Resolution(
        fields=[
            ResolvedField(
                field="comparison_targets",
                query=name,
                target=ResolutionCandidate(
                    entity_type="venue",
                    id=str(uid(i)),
                    label=name,
                ),
            )
            for i, name in [(20, "Kiel"), (21, "Flensburg")]
        ]
    )
    plan = InternalResearchPlan(
        "compare",
        "event",
        metric="event_count",
        comparison_targets=(
            ComparisonTarget("venue", "Kiel"),
            ComparisonTarget("venue", "Flensburg"),
        ),
    )
    connection = Connection([Rows(scalar=7), Rows(scalar=11)])
    install(monkeypatch, connection, resolution)
    outcome = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        plan,
        CONTEXT,
        planner_ms=0,
    )
    assert [i.value for i in outcome.result.items] == [7, 11]
    assert [s.label for s in outcome.sql_provenance] == ["Vergleich: Kiel", "Vergleich: Flensburg"]
    assert [s.kind for s in outcome.sql_provenance] == ["comparison", "comparison"]
    assert [s.parameters["venue_id"] for s in outcome.sql_provenance] == [
        str(uid(20)),
        str(uid(21)),
    ]
    assert_actual(outcome.sql_provenance, connection.calls)


@pytest.mark.parametrize(
    "intent,grouping", [("list", None), ("count", None), ("aggregate", "district")]
)
async def test_administrative_sql(settings, intent, grouping):
    plan = ResolvedResearchPlan(ExecutionFilters(entity_type="event"), intent, grouping=grouping)
    responses = [Rows(scalar=True)]  # Geometry validity is internal, not result provenance.
    if grouping:
        responses += [
            Rows(scalar=0),
            Rows(scalar=3),
            Rows([{"area_id": "district-1", "name": "District", "event_count": 4}]),
        ]
    else:
        responses += [Rows(scalar=3), Rows(scalar=1)]
        if intent == "list":
            responses += [Rows([ROW]), Rows()]
    connection = Connection(responses)
    with collect_research_sql() as statements:
        result = await administrative_selection(connection, settings, plan)
    assert result.unknown_location_count == 3
    assert_actual(statements, connection.calls[2 if grouping else 1 :])
    assert "SELECT value FROM unknown" in statements[0].sql
    assert statements[0].parameters["inventory"] == LOCATION_REDACTED
    assert statements[0].parameters["constraints"] == LOCATION_REDACTED
    if grouping:
        assert "GROUP BY i.area_id,i.name" in statements[1].sql
        assert result.groups[0].event_count == 4


async def test_semantic_has_separate_actual_sql_stages(settings, monkeypatch):
    from app.services import semantic_search
    from tests.test_semantic_search import hit

    settings.semantic_search_noncommercial_jina = True
    encoder = SimpleNamespace(
        embed=AsyncMock(return_value=[[0.1]]), http=SimpleNamespace(close=AsyncMock())
    )
    vector = SimpleNamespace(
        search=AsyncMock(return_value=[hit(30)]), http=SimpleNamespace(close=AsyncMock())
    )
    monkeypatch.setattr(semantic_search, "Encoder", lambda *a, **k: encoder)
    monkeypatch.setattr(semantic_search, "Qdrant", lambda *a, **k: vector)
    connection = Connection([Rows(), Rows([ROW]), Rows()])
    source = install(monkeypatch, connection)
    monkeypatch.setattr(semantic_search, "get_connection", source)
    plan = InternalResearchPlan("search", "event", semantic=SemanticSelection("Jazz"))
    outcome = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        plan,
        CONTEXT,
        planner_ms=0,
    )
    assert [s.kind for s in outcome.sql_provenance] == ["eligibility", "rehydration", "rehydration"]
    assert [s.label for s in outcome.sql_provenance[:2]] == ["SQL-Vorauswahl", "SQL-Rehydration"]
    assert "candidate_ids" not in outcome.sql_provenance[0].parameters
    assert outcome.sql_provenance[1].parameters["candidate_ids"] == [str(uid(30))]
    assert_actual(outcome.sql_provenance, connection.calls)
    vector.search.assert_awaited_once()


async def test_early_clarification_does_not_claim_sql(settings, monkeypatch):
    connection = Connection([])
    install(monkeypatch, connection)
    outcome = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        InternalResearchPlan("list", "event", clarification="needs_location"),
        CONTEXT,
        planner_ms=0,
    )
    assert outcome.sql_provenance == [] and connection.calls == []


async def test_http_redacts_actual_bindings_and_does_not_learn_or_log_location(
    client,
    settings,
    headers,
    monkeypatch,
    caplog,
):
    from app.api import research as api
    from tests.test_research_administrative import boundary

    latitude, longitude = 54.791234567, 9.431234567
    wkb = b"private-area-geometry"
    area = replace(boundary(), ewkb=wkb)
    resolution = Resolution(
        area=area, place=PlaceFilter(mode="radius", latitude=latitude, longitude=longitude)
    )
    connection = Connection([Rows()])
    install(monkeypatch, connection, resolution)
    response_plan = planned(
        intent="count", metric="event_count", answer_mode="count", temporal="none"
    )
    client._transport.app.state.research_planner = AsyncMock(
        plan=AsyncMock(return_value=response_plan)
    )
    learn = AsyncMock()
    monkeypatch.setattr(api, "record_success", learn)
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={
            "query": response_plan.plan.original_query,
            "location_context": {
                "latitude": latitude,
                "longitude": longitude,
                "source": "browser_geolocation",
            },
        },
    )
    assert response.status_code == 200, response.text
    bindings = response.json()["sql_provenance"][0]["parameters"]
    assert bindings["place_latitude"] == bindings["place_longitude"] == LOCATION_REDACTED
    assert bindings["area_wkb"] == LOCATION_REDACTED
    assert connection.calls[0][1]["place_latitude"] == latitude
    assert connection.calls[0][1]["place_longitude"] == longitude
    assert connection.calls[0][1]["area_wkb"] == wkb
    for secret in [str(latitude), str(longitude), wkb.decode(), wkb.hex()]:
        assert secret not in response.text and secret not in caplog.text
    learn.assert_not_awaited()


@pytest.mark.parametrize(
    "update",
    [
        {"extra": True},
        {"copy_sql": "SELECT 1"},
        {"sql": "s" * 65537},
        {"sql": ""},
        {"label": "l" * 201},
        {"kind": "vector"},
        {"parameters": {"x": "v" * 4097}},
        {"parameters": {"x": list(range(101))}},
        {"parameters": {str(i): i for i in range(65)}},
        {"parameters": {"x" * 65: None}},
        {"parameters": {"x": {"nested": "not allowed"}}},
        {"parameters": {"x": float("nan")}},
        {"parameters": {"x": 9_007_199_254_740_992}},
    ],
)
def test_closed_bounded_statement(update):
    with pytest.raises(ValidationError):
        ResearchSqlStatement.model_validate(
            {"label": "SQL", "kind": "execution", "sql": "SELECT 1", "parameters": {}, **update}
        )


def test_statement_collection_and_safe_serialization():
    statement = ResearchSqlStatement(label="SQL", kind="execution", sql="SELECT 1", parameters={})
    with pytest.raises(ValidationError):
        TypeAdapter(ResearchSqlStatements).validate_python([statement] * 17)
    assert safe_value("candidate_ids", [uid(30)]) == [str(uid(30))]
    assert safe_value("from_date", date(2026, 1, 1)) == "2026-01-01"
    assert safe_value("time_from", time(18)) == "18:00:00"
    for name in ["password", "dsn", "token", "authorization", "new_unreviewed_field"]:
        assert safe_value(name, "secret") == VALUE_REDACTED
    for name in ["place_west", "place_house", "place_road", "area_wkb", "inventory", "constraints"]:
        assert safe_value(name, "secret") == LOCATION_REDACTED
    assert safe_value("q", "x" * 4097) == VALUE_REDACTED
    assert safe_value("ids", [uid(30)] * 101) == VALUE_REDACTED
    assert safe_value("q", b"binary") == VALUE_REDACTED
    assert safe_value("limit", 10**100) == VALUE_REDACTED


async def test_capture_is_opt_in_isolated_and_resets_on_error_and_cancellation(caplog):
    async def capture(value):
        connection = Connection([Rows()])
        with collect_research_sql() as statements:
            await asyncio.sleep(0)
            await execute_research_sql(
                connection, text("SELECT :q"), {"q": value, "token": "secret"}
            )
        return statements

    left, right = await asyncio.gather(capture("left private"), capture("right private"))
    assert left[0].parameters == {"q": "left private"}
    assert right[0].parameters == {"q": "right private"}
    for error in [RuntimeError, asyncio.CancelledError]:
        with pytest.raises(error), collect_research_sql() as discarded:
            raise error()
        await execute_research_sql(Connection([Rows()]), text("SELECT :q"), {"q": "outside"})
        assert discarded == []
    assert "private" not in caplog.text and "secret" not in caplog.text


async def test_learning_receives_only_existing_query_and_plan(client, monkeypatch):
    from app.schemas.research_execution import (
        CountResult,
        ExecutionDiagnostics,
        ExecutionProvenance,
    )
    from app.schemas.research_response import ResearchExecutionResponse
    from app.services import research_learning

    response = ResearchExecutionResponse(
        query="safe question",
        plan=planned(),
        resolution=[],
        result=CountResult(metric="event_count", value=1),
        execution=ExecutionProvenance(),
        observed_at=NOW,
        timezone="Europe/Berlin",
        diagnostics=ExecutionDiagnostics(planner_ms=0, total_ms=0),
        sql_provenance=[
            ResearchSqlStatement(
                label="SQL",
                kind="execution",
                sql="SELECT :q",
                parameters={"q": "private parameter"},
            )
        ],
    )

    @asynccontextmanager
    async def begin():
        yield None

    connection = SimpleNamespace(begin=begin)

    @asynccontextmanager
    async def admin(_):
        yield connection

    learn = AsyncMock()
    monkeypatch.setattr(research_learning, "connect_admin", admin)
    monkeypatch.setattr(research_learning, "learn", learn)
    await research_learning.record_success(Request({"type": "http"}), response, None)
    learn.assert_awaited_once_with(connection, response.query, response.plan.plan, None)
    assert "private parameter" not in repr(learn.await_args)


async def test_wrapper_preserves_statement_bindings_and_result_identity():
    original = text("SELECT :q, :place_latitude")
    bindings = {"q": "Jazz", "place_latitude": 54.712345, "unused": "not displayed"}
    result = object()
    connection = SimpleNamespace(execute=AsyncMock(return_value=result))
    with collect_research_sql() as statements:
        assert await execute_research_sql(connection, original, bindings) is result
    call = connection.execute.await_args
    assert call.args[0] is original and call.args[1] is bindings
    assert bindings == {"q": "Jazz", "place_latitude": 54.712345, "unused": "not displayed"}
    assert statements[0].parameters == {"q": "Jazz", "place_latitude": LOCATION_REDACTED}


@pytest.mark.parametrize("metric", ["occurrence_count", "description_characters"])
async def test_unified_metrics_capture_actual_source_selection(settings, metric):
    from app.repositories.research_metrics import rank_metric
    from app.schemas.research_domain import DataPlan

    plan = DataPlan(
        domain="data",
        operation="rank",
        entity_type="event",
        metric=metric,
        ordering="desc",
        limit=2,
    )
    rows = [{"entity_key": uid(30), "name": "Event", "description": "<p>Public prose</p>"}]
    if metric == "description_characters":

        class Size(Rows):
            def one(self):
                return {"count": 1, "characters": 20}

        connection = Connection([Size(), Rows(rows)])
    else:
        connection = Connection([Rows([{"key": str(uid(30)), "name": "Event", "value": 2}])])
    with collect_research_sql() as statements:
        result = await rank_metric(connection, settings, plan, ExecutionFilters(), None)
    assert result and len(statements) == 1
    assert_actual(statements, connection.calls[-1:])


async def test_unified_http_exposes_repository_sql(client, settings, headers, monkeypatch):
    from app.schemas.research_domain import DataPlan, PlanEnvelopeV4
    from app.services import research_unified

    question = "Which event has the most dates?"
    settings.research_domain_enabled = True
    plan = DataPlan(entity_type="event", metric="occurrence_count")
    client._transport.app.state.research_domain = AsyncMock(
        plan=AsyncMock(return_value=PlanEnvelopeV4(original_query=question, plan=plan))
    )
    connection = Connection([Rows([{"key": str(uid(30)), "name": "Event", "value": 2}])])

    async def source(_):
        yield connection

    monkeypatch.setattr(research_unified, "get_connection", source)
    response = await client.post(
        "/api/v1/research/v4/query", headers=headers, json={"query": question}
    )
    assert response.status_code == 200, response.text
    statements = TypeAdapter(ResearchSqlStatements).validate_python(
        response.json()["sql_provenance"]
    )
    assert_actual(statements, connection.calls)


async def test_shared_administrative_executor_attaches_provenance(settings, monkeypatch):
    connection = Connection([Rows(scalar=True), Rows(scalar=0), Rows(scalar=3), Rows()])
    install(monkeypatch, connection)
    outcome = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        InternalResearchPlan("aggregate", "event", metric="event_count", group_by="district"),
        CONTEXT,
        planner_ms=0,
    )
    assert outcome.administrative.sql_provenance == outcome.sql_provenance
    assert_actual(outcome.sql_provenance, connection.calls[2:])


async def test_empty_eligibility_never_fabricates_rehydration(settings, monkeypatch):
    from app.services import semantic_search

    class EmptyEligibility(Rows):
        def scalars(self):
            return []

    def forbidden(*args, **kwargs):
        raise AssertionError("Empty eligibility must not invoke the vector stage")

    monkeypatch.setattr(semantic_search, "Encoder", forbidden)
    connection = Connection([EmptyEligibility()])
    install(monkeypatch, connection)
    outcome = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        InternalResearchPlan("search", "event", semantic=SemanticSelection("Jazz")),
        CONTEXT,
        planner_ms=0,
    )
    assert outcome.result.items == []
    assert [statement.kind for statement in outcome.sql_provenance] == ["eligibility"]
    assert_actual(outcome.sql_provenance, connection.calls)
