"""Full v5 wire corpus and source-only PostgreSQL execution (CI database fixtures)."""

import json
from datetime import UTC, datetime, time
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Request
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import text

from app.errors import APIError
from app.repositories.research_administrative import administrative_reference
from app.repositories.research_areas import ResolvedResearchArea
from app.repositories.research_execution import count_selection, spatial_records, taxonomy_selection
from app.repositories.research_resolution import Resolution
from app.research.geography import SpatialConstraint
from app.schemas.research_analytics import AnalyticalPlanResponse, AnalyticalQueryPlan
from app.schemas.research_analytics_guard import analytical_mismatch
from app.schemas.research_areas import ResearchArea
from app.schemas.research_execution import ExecutionFilters
from app.services import research_plan_execution as executor
from app.services.research_planner import ResearchPlannerClient
from tests.conftest import uid
from tests.research_plan_helpers import plan_context
from tests.test_research_plan_execution import execution_source as execution_source_fixture
from tests.test_research_planner import configured
from tests.test_research_taxonomy import taxonomy_source as taxonomy_source_fixture

execution_source = execution_source_fixture
taxonomy_source = taxonomy_source_fixture
CASES = json.loads((Path(__file__).parent / "fixtures/research_analytics.json").read_text())


def envelope(case):
    return TypeAdapter(AnalyticalPlanResponse).validate_json(
        json.dumps(
            dict(
                kind="plan",
                schema_version="research-query-plan-v5",
                prompt_version="research-planner-v10",
                model="synthetic",
                plan=case["plan"],
                reference_date="2026-10-02",
                timezone="Europe/Berlin",
                diagnostics=dict(
                    request_id="a" * 32,
                    planner_intent=case["plan"]["intent"],
                    planner_model="synthetic",
                    planner_prompt_version="research-planner-v10",
                    planner_ms=0,
                    total_ms=0,
                ),
            )
        )
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["query"])
def test_full_analytical_plan(case):
    assert envelope(case).plan.model_dump(mode="json") == case["plan"]


@pytest.mark.parametrize(
    "query",
    [
        "Welche Genres gibt es?",
        "Welche Veranstaltungstypen gibt es?",
        "Welche Instrumente kommen vor?",
        "Welche Veranstaltung liegt am westlichsten?",
        "Wie viele rollstuhlgerechte Veranstaltungen gibt es?",
        "Wo finden viele Veranstaltungen statt?",
    ],
)
async def test_admin_rejects_generic_fallback_before_source_access(settings, monkeypatch, query):
    from tests.test_research_plan_execution import planned

    resolve = AsyncMock(side_effect=AssertionError("no DB work"))
    monkeypatch.setattr(executor, "resolve_plan", resolve)
    with pytest.raises(APIError) as exc:
        await executor.ResearchPlanExecutor().execute(
            Request({"type": "http"}),
            settings,
            *plan_context(planned(original_query=query)),
            planner_ms=0,
        )
    assert exc.value.code == "research_plan_unsupported"
    resolve.assert_not_awaited()


async def test_v5_client_is_opt_in_and_auth_is_service_only():
    case = CASES[0]
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=envelope(case).model_dump(mode="json"))

    client = ResearchPlannerClient(configured(), transport=httpx.MockTransport(respond))
    try:
        result = await client.plan(case["query"], analytical=True)
        assert result.plan.model_dump(mode="json") == case["plan"]
        assert calls[0].url.path == "/v5/plan"
        assert json.loads(calls[0].content) == {
            "query": case["query"],
            "timezone": "Europe/Berlin",
            "language": "auto",
        }
    finally:
        await client.close()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["query"])
async def test_authoritative_execution(settings, taxonomy_source, monkeypatch, case):
    c = taxonomy_source
    # No source changes outside this disposable transaction. Both public events at known points.
    await c.execute(
        text("UPDATE uranus.venue SET point=ST_SetSRID(ST_MakePoint(8,54),4326) WHERE uuid=:id"),
        {"id": uid(20)},
    )
    await c.execute(
        text(
            "UPDATE uranus.event_date SET start_date='2026-08-10',start_time='09:00',all_day=false"
        )
    )
    # Area resolution is isolated from the separately provisioned admin database.
    if case["plan"]["area_query"]:
        geometry = (
            await c.execute(text("SELECT ST_AsEWKB(ST_MakeEnvelope(9,54,10,55,4326))"))
        ).scalar_one()
        area = ResearchArea(
            id=uid(99),
            area_type="region",
            country_code="DE",
            region_code="DE-SH",
            name="Test",
            display_name="Test",
            osm_type="R",
            osm_id="99",
            osm_admin_level=4,
            centroid={"latitude": 54.5, "longitude": 9.5},
            bbox=(9, 54, 10, 55),
            source="osm",
            retrieved_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        monkeypatch.setattr(
            executor,
            "resolve_plan",
            AsyncMock(
                return_value=Resolution(
                    area=ResolvedResearchArea(area, bytes(geometry)),
                    spatial_constraints=(
                        SpatialConstraint(
                            case["plan"]["area_relation"],
                            administrative_reference(ResolvedResearchArea(area, bytes(geometry))),
                        ),
                    ),
                )
            ),
        )
    monkeypatch.setattr(
        executor, "semantic_research", AsyncMock(side_effect=AssertionError("no semantics"))
    )
    if case["plan"]["unsupported_reason"]:
        with pytest.raises(APIError) as exc:
            await executor.ResearchPlanExecutor().execute(
                Request({"type": "http"}), settings, *plan_context(envelope(case)), planner_ms=0
            )
        assert exc.value.code == "research_plan_unsupported"
        return
    response = await executor.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, *plan_context(envelope(case)), planner_ms=0
    )
    result = response.result
    assert response.execution.structured and not response.execution.semantic
    intent = case["plan"]["intent"]
    if intent == "taxonomy":
        assert result.kind == "taxonomy"
        expected = {
            "genre": [("Drama", 1), ("Jazz", 1)],
            "event_type": [("Konzert", 1), ("Theater", 1)],
            "category": [("Kategorie 7", 1)],
        }[case["plan"]["taxonomy"]]
        if case["plan"]["event_type_queries"] and result.taxonomy == "genre":
            expected = [("Jazz", 1)]
        assert [(i.name, i.event_count) for i in result.items] == expected
        assert result.total == len(expected)
    elif intent == "aggregate":
        assert result.kind == "aggregate" and result.group_by == case["plan"]["group_by"]
        expected = {
            "event": [("Event 30", 6), ("Event 32", 1)],
            "genre": [("Drama", 1), ("Jazz", 1)],
            "event_type": [("Konzert", 1), ("Theater", 1)],
            "organization": [("Organization 10", 2)],
            "venue": [("Deutsches Haus", 6), ("Phänomenta", 1)],
        }[result.group_by]
        if result.metric == "occurrence_count":
            expected = {
                "event": [("Event 30", 6), ("Event 32", 1)],
                "genre": [("Jazz", 6), ("Drama", 1)],
                "event_type": [("Konzert", 6), ("Theater", 1)],
                "venue": [("Deutsches Haus", 6), ("Phänomenta", 1)],
                "organization": [("Organization 10", 7)],
            }[result.group_by]
        expected = sorted(
            expected,
            key=lambda i: ((-i[1] if case["plan"]["ordering"] != "asc" else i[1]), i[0].lower()),
        )[: case["plan"]["limit"] or 20]
        assert [(i.name, i.value) for i in result.items] == expected
        if result.group_by == "event":
            assert [i.key for i in result.items] == [
                str(uid(int(name.split()[-1]))) for name, _ in expected
            ]
    elif intent == "spatial_rank":
        assert result.kind == "spatial" and len(result.items) == 1
        assert result.items[0].location is not None
        expected = (
            9.4
            if case["plan"]["ordering"] == "desc" and case["plan"]["spatial_metric"] == "longitude"
            else 54.8
            if case["plan"]["ordering"] == "desc"
            else 8
            if case["plan"]["spatial_metric"] == "longitude"
            else 54
        )
        assert getattr(result.items[0].location, case["plan"]["spatial_metric"]) == expected
    elif intent == "count":
        assert result.kind == "count"
        assert result.value == (
            2
            if case["plan"]["area_query"]
            else 6
            if case["plan"]["metric"] == "occurrence_count"
            else 1
        )
    else:
        assert result.kind == "records" and {i.entity_key for i in result.items} == {
            uid(30),
            uid(32),
        }


@pytest.mark.parametrize(
    "period,hours",
    [
        ("morning", ["06:00", "11:59"]),
        ("afternoon", ["12:00", "17:59"]),
        ("evening", ["18:00", "21:59"]),
        ("night", ["00:00", "05:59", "22:00", "23:59"]),
    ],
)
async def test_time_boundaries_and_all_day(settings, execution_source, period, hours):
    c = execution_source
    for clock in [
        "00:00",
        "05:59",
        "06:00",
        "11:59",
        "12:00",
        "17:59",
        "18:00",
        "21:59",
        "22:00",
        "23:59",
        None,
    ]:
        await c.execute(
            text("UPDATE uranus.event_date SET start_time=CAST(:clock AS time),all_day=false"),
            {"clock": time.fromisoformat(clock) if clock is not None else None},
        )
        filters = ExecutionFilters(entity_type="event", time_of_day=period)
        assert await count_selection(c, settings, filters, "occurrence_count", None) == (
            7 if clock in hours else 0
        )
    await c.execute(text("UPDATE uranus.event_date SET start_time='09:00',all_day=true"))
    assert (
        await count_selection(
            c,
            settings,
            ExecutionFilters(entity_type="event", time_of_day=period),
            "occurrence_count",
            None,
        )
        == 0
    )


async def test_null_and_empty_geometry_never_spatial_candidates(settings, execution_source):
    items = await spatial_records(
        execution_source,
        settings,
        ExecutionFilters(entity_type="event"),
        None,
        "longitude",
        "asc",
        20,
    )
    assert [i.entity_key for i in items] == [uid(30)]
    assert items[0].venue_id == uid(21)  # date override, not the event's NULL venue point


async def test_taxonomy_filters_and_empty_population(settings, taxonomy_source):
    result = await taxonomy_selection(
        taxonomy_source,
        settings,
        ExecutionFilters(entity_type="event", genre_keys=["1:1003"], organization_id=uid(11)),
        "genre",
        None,
    )
    assert result.items == [] and result.total == 0


def test_planner_schema_parity():
    expected = json.loads(
        (Path(__file__).parent / "fixtures/research_analytics_schema.json").read_text()
    )
    assert TypeAdapter(AnalyticalPlanResponse).json_schema() == expected


async def test_v5_query_route_preserves_question_only_boundary(
    client, headers, settings, monkeypatch
):
    from app.api import research
    from app.schemas.research_execution import TaxonomyResult

    learning = AsyncMock()
    monkeypatch.setattr(research, "record_success", learning)
    selection_id = uid(900)
    app = client._transport.app
    app.state.settings.research_analytics_enabled = True
    planner = AsyncMock()
    planner.plan.return_value = envelope(CASES[0])
    monkeypatch.setattr(app.state, "research_planner", planner)
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=Resolution()))

    async def connection(request):
        yield object()

    monkeypatch.setattr(executor, "get_connection", connection)
    monkeypatch.setattr(
        executor,
        "taxonomy_selection",
        AsyncMock(return_value=TaxonomyResult(taxonomy="genre", items=[], total=0)),
    )
    response = await client.post(
        "/api/v1/research/query",
        headers={**headers, "X-Research-Selection": str(selection_id)},
        json={"query": CASES[0]["query"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["kind"] == "taxonomy"
    planner.plan.assert_awaited_once_with(CASES[0]["query"], analytical=True)
    learning.assert_awaited_once()
    assert learning.await_args.args[1].result.kind == "taxonomy"
    assert learning.await_args.args[1].plan == planner.plan.return_value
    assert learning.await_args.args[2] == selection_id
    for field in ["plan", "sql", "taxonomy", "spatial_metric", "area_relation"]:
        response = await client.post(
            "/api/v1/research/query",
            headers=headers,
            json={"query": CASES[0]["query"], field: "untrusted"},
        )
        assert response.status_code == 422


async def test_genre_parent_filter_survives_multi_type_event(settings, taxonomy_source):
    await taxonomy_source.execute(
        text("INSERT INTO uranus.event_type_link(event_uuid,type_id,genre_id) VALUES (:id,2,2004)"),
        {"id": uid(30)},
    )
    result = await taxonomy_selection(
        taxonomy_source,
        settings,
        ExecutionFilters(entity_type="event", event_type_ids=[1]),
        "genre",
        None,
    )
    assert [(i.key, i.name, i.event_count) for i in result.items] == [("1:1003", "Jazz", 1)]


async def test_outside_excludes_missing_empty_and_boundary_points(settings, execution_source):
    c = execution_source
    geometry = (
        await c.execute(text("SELECT ST_AsEWKB(ST_MakeEnvelope(9.4,54,10,55,4326))"))
    ).scalar_one()
    area = ResearchArea(
        id=uid(99),
        area_type="region",
        country_code="DE",
        region_code="DE-SH",
        name="Test",
        display_name="Test",
        osm_type="R",
        osm_id="99",
        osm_admin_level=4,
        centroid={"latitude": 54.5, "longitude": 9.5},
        bbox=(9.4, 54, 10, 55),
        source="osm",
        retrieved_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    resolved = ResolvedResearchArea(area, bytes(geometry))
    filters = ExecutionFilters(entity_type="event", area_id=area.id, area_relation="outside")
    assert await count_selection(c, settings, filters, "event_count", resolved) == 0
    await c.execute(
        text("UPDATE uranus.venue SET point=ST_GeomFromText('POINT EMPTY',4326) WHERE uuid=:id"),
        {"id": uid(20)},
    )
    assert await count_selection(c, settings, filters, "event_count", resolved) == 0
    await c.execute(
        text("UPDATE uranus.venue SET point=ST_SetSRID(ST_MakePoint(8,54),4326) WHERE uuid=:id"),
        {"id": uid(20)},
    )
    assert await count_selection(c, settings, filters, "event_count", resolved) == 2
    from app.repositories.research_execution import aggregate_selection

    ranked = await aggregate_selection(c, settings, filters, "occurrence_count", "event", resolved)
    assert [(i.key, i.value) for i in ranked] == [(str(uid(30)), 5), (str(uid(32)), 1)]
    await c.execute(
        text("UPDATE uranus.venue SET point=ST_SetSRID(ST_MakePoint(999,54),4326) WHERE uuid=:id"),
        {"id": uid(20)},
    )
    assert await count_selection(c, settings, filters, "event_count", resolved) == 0


@pytest.mark.parametrize(
    "query,intent,grouping,taxonomy,relation,period",
    [
        (
            "Wie viele rollstuhlgerechte Veranstaltungen gibt es?",
            "count",
            "none",
            None,
            "inside",
            "none",
        ),
        ("Welche Genres gibt es?", "taxonomy", "none", "category", "inside", "none"),
        ("Zeige die häufigsten Genres", "aggregate", "category", None, "inside", "none"),
        ("Veranstaltungen außerhalb Schleswig-Holsteins", "list", "none", None, "inside", "none"),
        ("Veranstaltungen am Vormittag", "list", "none", None, "inside", "none"),
    ],
)
def test_dropped_analytical_conditions_are_vetoed(
    query, intent, grouping, taxonomy, relation, period
):
    from app.schemas.research_analytics_guard import analytical_mismatch

    assert analytical_mismatch(query, intent, grouping, taxonomy, relation, period)


async def test_jazz_august_count_pipeline_without_semantic_service(settings, monkeypatch):
    from app.schemas.research_execution import ResolutionCandidate, ResolvedField

    case = next(c for c in CASES if c["query"] == "Wie viele Jazz Konzerte gab es im August 2026?")
    fields = [
        ResolvedField(
            field="event_type_queries",
            query="Konzert",
            target=ResolutionCandidate(entity_type="event_type", id="1", label="Konzert"),
        ),
        ResolvedField(
            field="genre_queries",
            query="Jazz",
            target=ResolutionCandidate(entity_type="genre", id="1:1003", label="Jazz"),
        ),
    ]
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=Resolution(fields=fields)))

    async def connection(request):
        yield object()

    monkeypatch.setattr(executor, "get_connection", connection)
    count = AsyncMock(return_value=37)
    semantic = AsyncMock(side_effect=AssertionError("structured only"))
    monkeypatch.setattr(executor, "count_selection", count)
    monkeypatch.setattr(executor, "semantic_research", semantic)
    response = await executor.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, *plan_context(envelope(case)), planner_ms=0
    )
    assert response.result.kind == "count" and response.result.value == 37
    filters = count.await_args.args[2]
    assert str(filters.from_date) == "2026-08-01" and str(filters.to_date) == "2026-08-31"
    assert filters.event_type_ids == [1] and filters.genre_keys == ["1:1003"]
    assert count.await_args.args[3] == "event_count"
    semantic.assert_not_awaited()


RANKING_CASES = [
    c
    for c in CASES
    if c["plan"]["metric"] == "occurrence_count"
    and c["plan"]["intent"] == "aggregate"
    and c["plan"]["limit"] is not None
]


@pytest.mark.parametrize("case", RANKING_CASES, ids=lambda c: c["query"])
@pytest.mark.parametrize(
    "grouping", ["event", "event_type", "genre", "venue", "organization", "category", "none"]
)
def test_ranking_never_substitutes_dimensions(case, grouping):
    assert analytical_mismatch(case["query"], "aggregate", grouping) == (
        grouping != case["plan"]["group_by"]
    )


@pytest.mark.parametrize(
    "metric,entity",
    [("event_count", "event"), ("venue_count", "venue"), ("organization_count", "organization")],
)
def test_event_grouping_requires_occurrences(metric, entity):
    case = next(c for c in CASES if c["query"] == "Welches Event hat die meisten Termine?")
    with pytest.raises(ValidationError, match="event_grouping_requires_occurrence_count"):
        AnalyticalQueryPlan.model_validate_json(
            json.dumps(case["plan"] | {"metric": metric, "entity_type": entity})
        )


async def test_event_type_substitution_rejected_before_resolution(settings, monkeypatch):
    case = next(c for c in CASES if c["query"] == "Welches Event hat die meisten Termine?")
    wrong = {**case, "plan": case["plan"] | {"group_by": "event_type"}}
    resolve = AsyncMock(side_effect=AssertionError("no DB work"))
    monkeypatch.setattr(executor, "resolve_plan", resolve)
    with pytest.raises(APIError) as exc:
        await executor.ResearchPlanExecutor().execute(
            Request({"type": "http"}), settings, *plan_context(envelope(wrong)), planner_ms=0
        )
    assert exc.value.code == "research_plan_unsupported"
    resolve.assert_not_awaited()


async def test_exact_event_question_route_to_aggregate_sql(client, headers, monkeypatch):
    from unittest.mock import Mock

    from app.api import research

    case = next(c for c in CASES if c["query"] == "Welches Event hat die meisten Termine?")
    app = client._transport.app
    app.state.settings.research_analytics_enabled = True
    app.state.research_planner = AsyncMock()
    app.state.research_planner.plan.return_value = envelope(case)
    monkeypatch.setattr(research, "record_success", AsyncMock())
    monkeypatch.setattr(executor, "resolve_plan", AsyncMock(return_value=Resolution()))
    connection = AsyncMock()
    rows = Mock()
    rows.mappings.return_value = [{"key": str(uid(30)), "name": "Event 30", "value": 6}]
    connection.execute.return_value = rows

    async def connect(request):
        yield connection

    monkeypatch.setattr(executor, "get_connection", connect)
    semantic = AsyncMock(side_effect=AssertionError("no semantic ranking"))
    monkeypatch.setattr(executor, "semantic_research", semantic)
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": case["query"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"] == {
        "kind": "aggregate",
        "metric": "occurrence_count",
        "group_by": "event",
        "items": [{"key": str(uid(30)), "name": "Event 30", "value": 6}],
    }
    statement, params = connection.execute.await_args.args
    sql = str(statement)
    assert "count(DISTINCT date_key)" in sql
    assert "GROUP BY selected.entity_key::text,selected.name" in sql
    assert (
        'ORDER BY value DESC,lower(selected.name) COLLATE "C",'
        '(selected.entity_key::text) COLLATE "C"' in sql
    )
    assert params["aggregate_limit"] == 1
    assert "FROM matched_events" in sql
    semantic.assert_not_awaited()
    app.state.research_planner.plan.assert_awaited_once_with(case["query"], analytical=True)


@pytest.mark.parametrize(
    "ordering,expected", [("desc", [(30, 6), (32, 1)]), ("asc", [(32, 1), (30, 6)])]
)
async def test_event_occurrences_deduplicate_before_limit(
    settings, taxonomy_source, monkeypatch, ordering, expected
):
    from app.repositories import research_execution as repository

    # Deliberately duplicate the selected rows to exercise count(DISTINCT date_key).
    original_sql = repository.research_sql

    def duplicated_sql(**kwargs):
        return (
            f"WITH population AS ({original_sql(**kwargs)}) "
            "SELECT entity_key,name,date_key FROM population UNION ALL "
            "SELECT entity_key,name,date_key FROM population"
        )

    monkeypatch.setattr(repository, "research_sql", duplicated_sql)
    result = await repository.aggregate_selection(
        taxonomy_source,
        settings,
        ExecutionFilters(entity_type="event"),
        "occurrence_count",
        "event",
        None,
        ordering,
        1,
    )
    assert [(i.key, i.name, i.value) for i in result] == [
        (str(uid(expected[0][0])), f"Event {expected[0][0]}", expected[0][1])
    ]


async def test_event_ranking_ties_use_title_then_uuid(settings, taxonomy_source):
    from app.repositories.research_execution import aggregate_selection

    await taxonomy_source.execute(
        text("DELETE FROM uranus.event_date WHERE event_uuid=:id AND uuid!=:date"),
        {"id": uid(30), "date": uid(40)},
    )
    for title, expected in [("alpha", [32, 30]), ("Event 30", [30, 32])]:
        await taxonomy_source.execute(
            text("UPDATE uranus.event SET title=:title WHERE uuid=:id"),
            {"title": title, "id": uid(32)},
        )
        for direction in ("asc", "desc"):
            result = await aggregate_selection(
                taxonomy_source,
                settings,
                ExecutionFilters(entity_type="event"),
                "occurrence_count",
                "event",
                None,
                direction,
            )
            assert [(i.key, i.value) for i in result] == [(str(uid(i)), 1) for i in expected]


@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"venue_id": uid(21)}, [(30, 1)]),
        ({"venue_id": uid(20)}, [(30, 5), (32, 1)]),
        ({"organization_id": uid(11)}, []),
        ({"category_ids": [7]}, [(30, 6)]),
        ({"event_type_ids": [2]}, [(32, 1)]),
        ({"genre_keys": ["1:1003"]}, [(30, 6)]),
        ({"from_date": "2026-10-01"}, []),
    ],
)
async def test_event_ranking_retains_population_filters(
    settings, taxonomy_source, filters, expected
):
    from app.repositories.research_execution import aggregate_selection

    selection = ExecutionFilters.model_validate_json(
        json.dumps({"entity_type": "event", **filters}, default=str)
    )
    result = await aggregate_selection(
        taxonomy_source, settings, selection, "occurrence_count", "event", None
    )
    assert [(i.key, i.value) for i in result] == [(str(uid(i)), n) for i, n in expected]


async def test_fewest_occurrences_includes_eligible_undated_events(settings, taxonomy_source):
    from app.repositories.research_execution import aggregate_selection

    await taxonomy_source.execute(
        text("DELETE FROM uranus.event_date WHERE event_uuid=:id"), {"id": uid(32)}
    )
    result = await aggregate_selection(
        taxonomy_source,
        settings,
        ExecutionFilters(entity_type="event"),
        "occurrence_count",
        "event",
        None,
        "asc",
        1,
    )
    assert [(i.key, i.name, i.value) for i in result] == [(str(uid(32)), "Event 32", 0)]
