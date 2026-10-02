"""Actual PostgreSQL occurrence ranking and full query API regression; no inference."""

from contextlib import asynccontextmanager
from datetime import date, time
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Request
from pydantic import SecretStr
from sqlalchemy import text

from app.repositories.research_execution import chronological_records, count_selection
from app.repositories.research_resolution import Resolution
from app.schemas.research_execution import ExecutionFilters
from app.services import research_plan_execution as service
from app.services.research_planner import ResearchPlannerClient
from tests.conftest import uid
from tests.research_plan_helpers import plan_context
from tests.test_research_plan_execution import execution_source as execution_source_fixture
from tests.test_research_plan_execution import planned

execution_source = execution_source_fixture


@pytest.fixture
async def chronology(execution_source):
    connection = execution_source
    await connection.execute(text("DELETE FROM uranus.event_date"))
    await connection.execute(
        text("UPDATE uranus.event SET title=CASE uuid WHEN :a THEN 'A' ELSE 'B' END"),
        {"a": uid(30)},
    )
    await connection.execute(
        text(
            "INSERT INTO uranus.event(uuid,org_uuid,venue_uuid,title,release_status) "
            "VALUES(:c,:org,:venue,'C','released'),(:undated,:org,:venue,'Undated','released')"
        ),
        {"c": uid(33), "org": uid(10), "venue": uid(20), "undated": uid(34)},
    )
    await connection.execute(
        text("UPDATE uranus.venue SET point=ST_SetSRID(ST_Point(9.5,54.5),4326) WHERE uuid=:v"),
        {"v": uid(20)},
    )
    await connection.execute(
        text(
            "UPDATE uranus.venue SET "
            "point=ST_SetSRID(ST_Point(11,56),4326),city='Kiel',"
            "street='Other',house_number='9' WHERE uuid=:v"
        ),
        {"v": uid(21)},
    )
    for key, event, start, clock, venue, space, status in [
        (501, 30, "2025-01-10", time(10), None, 25, "inherited"),
        (502, 30, "2026-12-20", time(20), 21, None, "inherited"),
        (503, 32, "2025-02-01", time(9), None, None, "inherited"),
        (504, 33, "2024-12-31", None, None, None, "inherited"),
        (505, 30, "2020-01-01", time(1), None, None, "draft"),
        (506, 31, "2019-01-01", time(1), None, None, "released"),
    ]:
        await connection.execute(
            text("""INSERT INTO uranus.event_date
            (uuid,event_uuid,start_date,start_time,end_date,end_time,venue_uuid,space_uuid,release_status,all_day)
            VALUES(:id,:event,:start,:time,:start,:end,:venue,:space,:status,false)"""),
            {
                "id": uid(key),
                "event": uid(event),
                "start": date.fromisoformat(start),
                "time": clock,
                "end": time(22),
                "venue": uid(venue) if venue else None,
                "space": uid(space) if space else None,
                "status": status,
            },
        )
    return connection


@pytest.mark.parametrize(
    "ordering,limit,keys,dates",
    [
        ("asc", 1, [33], ["2024-12-31"]),
        ("asc", 2, [33, 30], ["2024-12-31", "2025-01-10"]),
        ("desc", 1, [30], ["2026-12-20"]),
        ("desc", 20, [30, 32, 33], ["2026-12-20", "2025-02-01", "2024-12-31"]),
    ],
)
async def test_rank_distinct_events_by_matching_occurrence(
    chronology, settings, ordering, limit, keys, dates
):
    items = await chronological_records(
        chronology,
        settings,
        ExecutionFilters(entity_type="event"),
        None,
        ordering,
        limit,
    )
    assert [i.entity_key for i in items] == [uid(k) for k in keys]
    assert [i.start_date.isoformat() for i in items] == dates
    assert len({i.entity_key for i in items}) == len(items)


async def test_latest_returns_exact_occurrence_context(chronology, settings):
    item = (
        await chronological_records(
            chronology,
            settings,
            ExecutionFilters(entity_type="event"),
            None,
            "desc",
            1,
        )
    )[0]
    assert (item.start_date, item.start_time, item.end_date, item.end_time) == (
        date(2026, 12, 20),
        time(20),
        date(2026, 12, 20),
        time(22),
    )
    assert (
        item.venue_id,
        item.venue_name,
        item.space_id,
        item.space_name,
        item.city,
        item.address,
    ) == (uid(21), "Phänomenta", None, None, "Kiel", "Other 9, 24937 Kiel")
    item = (
        await chronological_records(
            chronology,
            settings,
            ExecutionFilters(entity_type="event", venue_id=uid(20)),
            None,
            "desc",
            1,
        )
    )[0]
    assert item.entity_key == uid(30) and item.start_date == date(2025, 1, 10)
    assert item.venue_id == uid(20) and item.space_id == uid(25) and item.space_name == "Saal"


@pytest.mark.parametrize(
    "temporal,ordering,key,day",
    [
        ("past", "desc", 32, "2025-02-01"),
        ("future", "asc", 30, "2026-12-20"),
    ],
)
async def test_temporal_chronology(chronology, settings, temporal, ordering, key, day):
    response = planned(temporal=temporal, ordering=ordering, limit=1)
    filters = service.execution_filters(*plan_context(response), Resolution())
    item = (await chronological_records(chronology, settings, filters, None, ordering, 1))[0]
    assert item.entity_key == uid(key) and item.start_date.isoformat() == day


async def test_chronology_filters_and_exact_counts(chronology, settings):
    # Shared eligibility: unpublished parent/date and undated rows cannot rank.
    assert (
        await count_selection(
            chronology,
            settings,
            ExecutionFilters(entity_type="event"),
            "event_count",
            None,
        )
        == 4
    )
    assert (
        await count_selection(
            chronology,
            settings,
            ExecutionFilters(entity_type="event"),
            "occurrence_count",
            None,
        )
        == 4
    )
    assert [
        i.entity_key
        for i in await chronological_records(
            chronology,
            settings,
            ExecutionFilters(entity_type="event", time_from=time(18)),
            None,
            "asc",
            20,
        )
    ] == [uid(30)]
    assert not await chronological_records(
        chronology,
        settings,
        ExecutionFilters(entity_type="event", organization_id=uid(11)),
        None,
        "asc",
        20,
    )
    assert not await chronological_records(
        chronology,
        settings,
        ExecutionFilters(entity_type="event", category_ids=[999]),
        None,
        "asc",
        20,
    )
    assert not await chronological_records(
        chronology,
        settings,
        ExecutionFilters(entity_type="event", genre_keys=["999:999"]),
        None,
        "asc",
        20,
    )


async def test_area_earliest_uses_matching_occurrences(admin_store, chronology, settings):
    from app.repositories.research_areas import resolve_area
    from tests.test_semantic_knowledge_index import insert_area

    await insert_area(
        chronology, uid(901), "Flensburg", "POLYGON((9 54,10 54,10 55,9 55,9 54))", 991
    )
    area = await resolve_area(chronology, uid(901))
    items = await chronological_records(
        chronology,
        settings,
        ExecutionFilters(entity_type="event", area_id=uid(901)),
        area,
        "asc",
        20,
    )
    assert [i.entity_key for i in items] == [uid(33), uid(30)]
    assert items[1].start_date == date(2025, 1, 10)


@pytest.mark.parametrize("ordering,first_date", [("asc", 501), ("desc", 507)])
async def test_uuid_ties_and_null_times_last(chronology, settings, ordering, first_date):
    await chronology.execute(
        text(
            "UPDATE uranus.event_date SET start_date='2025-01-10',start_time=NULL WHERE "
            "uuid IN (:a,:b,:c)"
        ),
        {"a": uid(502), "b": uid(503), "c": uid(504)},
    )
    await chronology.execute(
        text(
            "INSERT INTO "
            "uranus.event_date(uuid,event_uuid,start_date,start_time,venue_uuid,release_status) "
            "VALUES(:id,:event,'2025-01-10','10:00',:venue,'inherited')"
        ),
        {"id": uid(507), "event": uid(30), "venue": uid(21)},
    )
    items = await chronological_records(
        chronology,
        settings,
        ExecutionFilters(entity_type="event"),
        None,
        ordering,
        20,
    )
    assert items[0].entity_key == uid(30) and items[0].start_time == time(10)
    assert items[0].venue_id == uid(20 if first_date == 501 else 21)
    assert [i.entity_key for i in items[1:]] == (
        [uid(32), uid(33)] if ordering == "asc" else [uid(33), uid(32)]
    )


@pytest.mark.parametrize(
    "query,temporal,key,day",
    [
        ("wann war das erste event im system?", "none", 33, "2024-12-31"),
        ("was ist die nächste veranstaltung?", "future", 30, "2026-12-20"),
    ],
)
async def test_first_next_event_http_regression(
    client, headers, chronology, monkeypatch, query, temporal, key, day
):
    expected = planned(original_query=query, temporal=temporal, ordering="asc", limit=1)
    app = client._transport.app
    settings = app.state.settings
    settings.research_planner_url = "http://127.0.0.1:8090"
    settings.research_planner_api_key = SecretStr("synthetic-planner-service-key-for-tests-only")
    planner = ResearchPlannerClient(
        settings,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=expected.model_dump(mode="json"))
        ),
    )
    monkeypatch.setattr(app.state, "research_planner", planner)
    try:
        result = await client.post("/api/v1/research/query", headers=headers, json={"query": query})
    finally:
        await planner.close()
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["result"]["kind"] == "records"
    assert len(body["result"]["items"]) == 1
    assert body["result"]["items"][0]["entity_key"] == str(uid(key))
    assert body["result"]["items"][0]["start_date"] == day
    assert body["plan"]["plan"]["ordering"] == "asc" and body["plan"]["plan"]["limit"] == 1
    for code in ("planner_invalid_response", "research_planner_invalid_response", "upstream_error"):
        assert code not in result.text


@pytest.mark.parametrize("extra", [{"ordering": "asc"}, {"limit": 1}, {"plan": {}}])
async def test_browser_cannot_submit_ordering(client, headers, monkeypatch, extra):
    planner = AsyncMock()
    monkeypatch.setattr(client._transport.app.state, "research_planner", planner)
    result = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": "events", **extra}
    )
    assert result.status_code == 422
    planner.plan.assert_not_called()


@pytest.mark.parametrize("ordering,keys", [(None, [33, 30]), ("asc", [33, 30]), ("desc", [30, 32])])
async def test_structured_executor_effective_ordering(chronology, settings, ordering, keys):
    response = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        *plan_context(planned(temporal="none", ordering=ordering, limit=2)),
        planner_ms=0,
    )
    assert [i.entity_key for i in response.result.items] == [uid(k) for k in keys]
    assert response.result.total is None


@pytest.mark.parametrize("limit,expected", [(None, 20), (2, 2)])
async def test_sql_limit_after_deduplication(chronology, settings, limit, expected):
    await chronology.execute(
        text("""INSERT INTO uranus.event(uuid,org_uuid,title,release_status)
        SELECT md5(n::text)::uuid,:org,'Extra','released' FROM generate_series(1000,1024) n"""),
        {"org": uid(10)},
    )
    await chronology.execute(
        text("""INSERT INTO uranus.event_date(uuid,event_uuid,start_date,release_status)
        SELECT md5((n+100)::text)::uuid,md5(n::text)::uuid,'2025-03-01','inherited'
        FROM generate_series(1000,1024) n""")
    )
    from sqlalchemy import event

    statements = []

    def capture(conn, cursor, statement, params, context, executemany):
        statements.append((statement, params))

    event.listen(chronology.sync_connection, "before_cursor_execute", capture)
    try:
        response = await service.ResearchPlanExecutor().execute(
            Request({"type": "http"}),
            settings,
            *plan_context(planned(temporal="none", limit=limit)),
            planner_ms=0,
        )
    finally:
        event.remove(chronology.sync_connection, "before_cursor_execute", capture)
    assert len(response.result.items) == expected and response.result.total is None
    query, params = next((q, p) for q, p in statements if "occurrence_rank=1" in q)
    assert "LIMIT" in query and params[-1] == expected
    assert len({i.entity_key for i in response.result.items}) == expected


@pytest.mark.parametrize("ordering", [None, "asc"])
async def test_area_sorted_limit_http_regression(
    admin_store, chronology, client, headers, monkeypatch, ordering
):
    from app.repositories import research_resolution
    from tests.test_semantic_knowledge_index import insert_area

    await insert_area(
        chronology, uid(901), "Flensburg", "POLYGON((9 54,10 54,10 55,9 55,9 54))", 991
    )

    @asynccontextmanager
    async def admin(request):
        class FixtureConnection:
            def begin(self):
                return chronology.begin_nested()

            async def execute(self, statement, params=None):
                if str(statement).startswith("SET TRANSACTION"):
                    return None  # Only this fixture transaction; all resolution SQL is real.
                return await chronology.execute(statement, params or {})

        yield FixtureConnection()

    monkeypatch.setattr(research_resolution, "connect_admin", admin)
    semantic = AsyncMock(side_effect=AssertionError("No semantic retrieval for structured lists"))
    monkeypatch.setattr(service, "semantic_research", semantic)
    query = (
        "welche veranstaltungen sind in flensburg? sortiere die nach datum. zeige nur 2 ergebnisse."
        if ordering
        else "zeige nur 2 veranstaltungen in flensburg"
    )
    expected = planned(
        original_query=query, temporal="none", ordering=ordering, limit=2, area_query="Flensburg"
    )
    settings = client._transport.app.state.settings
    settings.research_planner_url = "http://127.0.0.1:8090"
    settings.research_planner_api_key = SecretStr("synthetic-planner-service-key-for-tests-only")
    planner = ResearchPlannerClient(
        settings,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=expected.model_dump(mode="json"))
        ),
    )
    monkeypatch.setattr(client._transport.app.state, "research_planner", planner)
    try:
        response = await client.post(
            "/api/v1/research/query", headers=headers, json={"query": query}
        )
    finally:
        await planner.close()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["kind"] == "records" and body["result"]["total"] is None
    assert [i["entity_key"] for i in body["result"]["items"]] == [str(uid(33)), str(uid(30))]
    assert [i["start_date"] for i in body["result"]["items"]] == ["2024-12-31", "2025-01-10"]
    assert body["resolution"][0]["target"]["label"] == "Flensburg"
    assert body["plan"]["plan"]["unsupported_reason"] is None
    assert "research_plan_unsupported" not in response.text
    semantic.assert_not_called()


async def test_category_before_order_and_limit(chronology, settings):
    await chronology.execute(
        text("UPDATE uranus.event SET categories=ARRAY[7] WHERE uuid=:id"), {"id": uid(32)}
    )
    items = await chronological_records(
        chronology,
        settings,
        ExecutionFilters(entity_type="event", category_ids=[7]),
        None,
        "asc",
        1,
    )
    assert [i.entity_key for i in items] == [uid(32)]
