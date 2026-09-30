"""Deterministic planner fixtures, mock vectors and disposable source-only SQL."""

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date, time
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from pydantic import TypeAdapter
from sqlalchemy import text

from app.auth.dependencies import get_identity
from app.auth.service import AdminPrincipal
from app.errors import APIError
from app.repositories.research import rehydrate_semantic_events, research_page
from app.repositories.research_execution import aggregate_selection, count_selection
from app.repositories.research_resolution import Resolution, candidates
from app.schemas.research_execution import ExecutionFilters, ExecutionSemanticFilters
from app.schemas.research_planner import ClarificationResponse, PlanResponse
from app.services import research_plan_execution as service
from tests.conftest import uid
from tests.test_research_planner import ENVELOPE
from tests.test_semantic_search import hit
from tests.test_semantic_search import retrieval as retrieval_fixture

retrieval = retrieval_fixture
PATH = "/api/v1/research/query"


def planned(**changes):
    envelope = deepcopy(ENVELOPE)
    envelope["plan"].update(
        intent="list",
        answer_mode="records",
        requires_semantic_relevance=False,
        semantic_query=None,
        area_query=None,
        time_of_day="none",
    )
    envelope["plan"].update(changes)
    envelope["diagnostics"]["planner_intent"] = envelope["plan"]["intent"]
    return TypeAdapter(PlanResponse).validate_json(json.dumps(envelope))


@pytest.mark.parametrize(
    "temporal,start,end",
    [
        ("none", None, None),
        ("today", "2026-09-30", "2026-09-30"),
        ("tomorrow", "2026-10-01", "2026-10-01"),
        ("this_weekend", "2026-10-03", "2026-10-04"),
        ("next_week", "2026-10-05", "2026-10-11"),
        ("this_month", "2026-09-01", "2026-09-30"),
        ("this_year", "2026-01-01", "2026-12-31"),
        ("past", None, "2026-09-29"),
        ("future", "2026-09-30", None),
    ],
)
def test_reference_date_translation(temporal, start, end):
    bounds = service.temporal_bounds(planned(temporal=temporal))
    assert bounds == tuple(date.fromisoformat(v) if v else None for v in (start, end))


@pytest.mark.parametrize(
    "ref,temporal,start,end",
    [
        ("2026-10-25", "this_weekend", "2026-10-24", "2026-10-25"),
        ("2026-03-29", "next_week", "2026-03-30", "2026-04-05"),
        ("2024-02-15", "this_month", "2024-02-01", "2024-02-29"),
        ("2026-12-31", "next_week", "2027-01-04", "2027-01-10"),
    ],
)
def test_calendar_dst_sunday_leap_year(ref, temporal, start, end):
    response = planned(temporal=temporal).model_copy(
        update={"reference_date": date.fromisoformat(ref)}
    )
    assert service.temporal_bounds(response) == (date.fromisoformat(start), date.fromisoformat(end))


def test_explicit_dates_and_evening():
    response = planned(
        temporal="explicit_range",
        explicit_from_date="2026-01-02",
        explicit_to_date="2026-02-03",
        time_of_day="evening",
    )
    filters = service.execution_filters(response, Resolution())
    assert filters.from_date == date(2026, 1, 2) and filters.to_date == date(2026, 2, 3)
    assert filters.time_from == time(18)


@pytest.fixture
def pipeline(client, monkeypatch):
    app = client._transport.app
    planner = AsyncMock()
    planner.plan.return_value = planned()
    monkeypatch.setattr(app.state, "research_planner", planner)
    return planner


async def test_reject_plan_tampering_and_body_limit(client, headers, pipeline):
    for extra in (
        "plan",
        "intent",
        "entity_type",
        "area_query",
        "venue_query",
        "organization_query",
        "semantic_query",
        "dates",
        "categories",
        "genres",
        "metric",
        "group_by",
        "comparison_targets",
        "model",
        "collection",
        "url",
        "geometry",
    ):
        response = await client.post(
            PATH, headers=headers, json={"query": "today", extra: "untrusted"}
        )
        assert response.status_code == 422
    assert (await client.post(PATH, headers=headers, content=b" " * 32769)).status_code == 413
    pipeline.plan.assert_not_called()


@pytest.mark.parametrize(
    "admin,journalist,status", [(False, False, 403), (True, False, 200), (False, True, 200)]
)
async def test_query_roles(client, headers, pipeline, admin, journalist, status):
    app = client._transport.app
    app.dependency_overrides[get_identity] = lambda: AdminPrincipal(
        subject=f"admin:{uid(1)}", system_admin=admin, journalist=journalist
    )
    response = planned(clarification="needs_location")
    pipeline.plan.return_value = ClarificationResponse.model_validate(
        {**response.model_dump(), "kind": "needs_clarification"}
    )
    result = await client.post(PATH, headers=headers, json={"query": "today"})
    assert result.status_code == status
    if status == 200:
        assert result.json()["result"]["planner_state"] == "needs_location"
        assert result.json()["execution"]["structured"] is False


async def test_anonymous_no_planner(client, pipeline):
    assert (await client.post(PATH, json={"query": "today"})).status_code == 401
    pipeline.plan.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        dict(
            intent="count",
            answer_mode="count",
            metric="event_count",
            requires_semantic_relevance=True,
            semantic_query="music",
        ),
        dict(
            intent="aggregate",
            answer_mode="aggregate",
            metric="event_count",
            group_by="venue",
            requires_semantic_relevance=True,
            semantic_query="music",
        ),
        dict(intent="aggregate", answer_mode="aggregate", metric="event_count", group_by="area"),
        dict(
            intent="recommend",
            answer_mode="recommendation",
            entity_type="venue",
            requires_semantic_relevance=True,
            semantic_query="interesting",
        ),
        dict(
            intent="search",
            entity_type="organization",
            requires_semantic_relevance=True,
            semantic_query="art",
        ),
        dict(
            intent="compare",
            answer_mode="comparison",
            metric="event_count",
            comparison_targets=[{"kind": "venue", "query": "a"}, {"kind": "venue", "query": "b"}],
            requires_semantic_relevance=True,
            semantic_query="art",
        ),
        dict(
            intent="compare",
            answer_mode="comparison",
            metric="event_count",
            venue_query="common",
            comparison_targets=[{"kind": "venue", "query": "a"}, {"kind": "venue", "query": "b"}],
        ),
    ],
)
async def test_unsupported_before_resolution(settings, monkeypatch, changes):
    resolve = AsyncMock(side_effect=AssertionError("no database work"))
    monkeypatch.setattr(service, "resolve_plan", resolve)
    with pytest.raises(APIError) as exc:
        await service.ResearchPlanExecutor().execute(
            Request({"type": "http"}), settings, planned(**changes)
        )
    assert exc.value.code == "research_execution_unsupported"
    resolve.assert_not_called()


async def test_semantic_required_failure_has_no_fallback(
    client, headers, pipeline, monkeypatch, settings
):
    pipeline.plan.return_value = planned(
        intent="recommend",
        answer_mode="recommendation",
        requires_semantic_relevance=True,
        semantic_query="kulturell interessant",
        time_of_day="evening",
    )
    monkeypatch.setattr(service, "resolve_plan", AsyncMock(return_value=Resolution()))
    structured = AsyncMock(side_effect=AssertionError("no fallback"))
    monkeypatch.setattr(service, "research_page", structured)
    settings.semantic_search_noncommercial_jina = False
    response = await client.post(
        PATH, headers=headers, json={"query": ENVELOPE["plan"]["original_query"]}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_semantic_unavailable"
    structured.assert_not_called()
    pipeline.plan.assert_awaited_once()


async def test_semantic_query_shared_retrieval(client, headers, pipeline, monkeypatch, retrieval):
    pipeline.plan.return_value = planned(
        intent="recommend",
        answer_mode="recommendation",
        requires_semantic_relevance=True,
        semantic_query="kulturell interessant",
        semantic_focus="Musik",
        time_of_day="evening",
    )
    monkeypatch.setattr(service, "resolve_plan", AsyncMock(return_value=Resolution()))
    retrieval["hits"] = [hit(30)]
    response = await client.post(
        PATH, headers=headers, json={"query": ENVELOPE["plan"]["original_query"]}
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["total"] is None and result["items"][0]["semantic"]["score"] == 0.8
    filters = retrieval["rehydrate"].call_args.args[2]
    assert filters.q == "kulturell interessant\nMusik"
    assert filters.time_from == time(18) and filters.from_date == date(2026, 9, 30)
    assert filters.page_size == 20


@pytest.fixture
async def execution_source(db_connection, settings, monkeypatch):
    from app.repositories import research_resolution

    await db_connection.execute(
        text(
            "UPDATE uranus.event_date SET start_date='2026-09-30',start_time='18:00',all_day=false"
        )
    )
    await db_connection.execute(
        text(
            "UPDATE uranus.venue SET name=CASE WHEN uuid=:a THEN 'Deutsches Haus' "
            "ELSE 'Phänomenta' END"
        ),
        {"a": uid(20)},
    )

    async def connection(request):
        yield db_connection

    monkeypatch.setattr(service, "get_connection", connection)
    monkeypatch.setattr(research_resolution, "get_connection", connection)
    return db_connection


async def test_structured_works_without_semantics(settings, execution_source, monkeypatch):
    monkeypatch.setattr(
        service, "semantic_research", AsyncMock(side_effect=AssertionError("structured only"))
    )
    result = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        planned(
            original_query="Welche Veranstaltungen finden im Deutschen Haus statt?",
            venue_query="Deutsches Haus",
        ),
    )
    assert result.result.kind == "records" and result.result.total == 2
    assert all(i.venue_id == uid(20) for i in result.result.items)
    assert result.execution.structured and not result.execution.semantic
    org = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        planned(
            original_query="Welche Veranstaltungen organisiert X?",
            organization_query="Organization 10",
        ),
    )
    assert org.result.total == 2


async def test_counts_aggregates_comparison(settings, execution_source):
    request = Request({"type": "http"})
    for metric, expected in (("event_count", 2), ("occurrence_count", 7)):
        result = await service.ResearchPlanExecutor().execute(
            request, settings, planned(intent="count", answer_mode="count", metric=metric)
        )
        assert result.result.value == expected
    aggregate = await service.ResearchPlanExecutor().execute(
        request,
        settings,
        planned(
            original_query="Wo ist heute am meisten los?",
            intent="aggregate",
            answer_mode="aggregate",
            metric="event_count",
            group_by="venue",
        ),
    )
    assert [(i.name, i.value) for i in aggregate.result.items] == [
        ("Deutsches Haus", 2),
        ("Phänomenta", 1),
    ]
    comparison = await service.ResearchPlanExecutor().execute(
        request,
        settings,
        planned(
            original_query=(
                "Wie viele Veranstaltungen gibt es im Deutschen Haus und in der Phänomenta?"
            ),
            intent="compare",
            answer_mode="comparison",
            metric="event_count",
            comparison_targets=[
                {"kind": "venue", "query": "Deutsches Haus"},
                {"kind": "venue", "query": "Phänomenta"},
            ],
        ),
    )
    assert [i.value for i in comparison.result.items] == [2, 1]
    assert "winner" not in comparison.model_dump_json()


@pytest.mark.parametrize("group", ["venue", "organization", "category"])
@pytest.mark.parametrize(
    "metric", ["event_count", "occurrence_count", "venue_count", "organization_count"]
)
async def test_sql_aggregate_metrics(settings, execution_source, group, metric):
    await execution_source.execute(text("UPDATE uranus.event SET categories=ARRAY[1,1]"))
    result = await aggregate_selection(
        execution_source, settings, ExecutionFilters(), metric, group, None
    )
    assert result and all(i.value > 0 for i in result)
    if group == "category":
        assert len(result) == 1
        assert (
            result[0].value
            == {"event_count": 2, "occurrence_count": 7, "venue_count": 2, "organization_count": 1}[
                metric
            ]
        )


async def test_ambiguous_unknown_private_and_injection(settings, execution_source):
    for query in ("unknown", "%' OR true --", "fixture@example.invalid", str(uid(22))):
        assert await candidates(execution_source, "venue", query, settings) == []
    await execution_source.execute(text("UPDATE uranus.venue SET name='Same'"))
    result = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, planned(venue_query="Same")
    )
    assert result.result.reason == "ambiguous"
    assert len(result.result.candidates) == 2
    assert {c.id for c in result.result.candidates} == {str(uid(20)), str(uid(21))}
    # Exact UUID outranks name, and substring input stays literal.
    assert (await candidates(execution_source, "venue", str(uid(20)), settings))[0].id == str(
        uid(20)
    )
    missing = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, planned(venue_query="unknown")
    )
    assert missing.result.reason == "no_match"


async def test_evening_authoritative_eligibility(settings, execution_source, now):
    filters = ExecutionFilters(entity_type="event", time_from=time(18), venue_id=uid(20))
    assert (await count_selection(execution_source, settings, filters, "event_count", None)) == 2
    for assignments in ("start_time='17:59'", "all_day=true", "start_time=NULL", "all_day=NULL"):
        async with execution_source.begin_nested():
            await execution_source.execute(text(f"UPDATE uranus.event_date SET {assignments}"))
            assert (
                await count_selection(execution_source, settings, filters, "event_count", None)
            ) == 0
        # Restore explicitly; begin_nested commits on success.
        await execution_source.execute(
            text("UPDATE uranus.event_date SET start_time='18:00',all_day=false")
        )
    semantic = ExecutionSemanticFilters(q="music", time_from=time(18), venue_id=uid(21))
    page = await rehydrate_semantic_events(
        execution_source, settings, semantic, [uid(31), uid(32), uid(30)], now
    )
    assert [i.entity_key for i in page.items] == [uid(30)]
    assert page.items[0].venue_id == uid(21)


async def test_taxonomy_resolution_and_hard_filters(settings, execution_source, now):
    await execution_source.execute(
        text(
            "INSERT INTO uranus.event_category(category_id,iso_639_1,name) "
            "VALUES(1,'de','Musik'),(2,'de','Kunst')"
        )
    )
    await execution_source.execute(
        text("UPDATE uranus.event SET categories=ARRAY[1] WHERE uuid=:id"), {"id": uid(30)}
    )
    await execution_source.execute(
        text(
            "INSERT INTO uranus.genre_type(type_id,genre_id,iso_639_1,name) "
            "VALUES(1,2,'de','Jazz'),(2,2,'de','Jazz')"
        )
    )
    await execution_source.execute(
        text(
            "INSERT INTO uranus.event_type_link(event_uuid,type_id,genre_id) "
            "VALUES(:a,1,2),(:b,2,2)"
        ),
        {"a": uid(30), "b": uid(32)},
    )
    assert len(await candidates(execution_source, "genre", "Jazz", settings)) == 2
    assert (await candidates(execution_source, "category", "musik", settings))[0].id == "1"
    filters = ExecutionFilters(
        entity_type="event", category_ids=[1, 2], genre_keys=["1:2"], time_from=time(18)
    )
    assert [
        i.entity_key for i in (await research_page(execution_source, settings, filters, now)).items
    ] == [uid(30)]
    filters.genre_keys = ["2:2"]
    assert not (await research_page(execution_source, settings, filters, now)).items


async def test_area_resolution_and_execution(admin_store, execution_source, settings, monkeypatch):
    from app.repositories import research_resolution
    from app.repositories.research_areas import resolve_area
    from tests.test_semantic_knowledge_index import insert_area

    await insert_area(
        execution_source, uid(901), "Flensburg", "POLYGON((9 54,10 54,10 55,9 55,9 54))", 991
    )
    await insert_area(
        execution_source, uid(902), "Husum", "POLYGON((8 54,9 54,9 55,8 55,8 54))", 992
    )
    await execution_source.execute(
        text("UPDATE uranus.venue SET point=ST_SetSRID(ST_Point(9.5,54.5),4326) WHERE uuid=:id"),
        {"id": uid(20)},
    )
    resolved_area = await resolve_area(execution_source, uid(901))
    assert (await candidates(execution_source, "area", "flensburg", settings))[0].id == str(
        uid(901)
    )
    assert not await candidates(execution_source, "area", "unknown", settings)
    assert (
        len(await candidates(execution_source, "venue", "Deutsches Haus", settings, resolved_area))
        == 1
    )

    # Exercise the full service with real SQL resolution, allowing its explicit
    # read-only admin transaction on a separate connection. Fixture rows stay local.
    @asynccontextmanager
    async def admin(request):
        class FixtureConnection:
            def begin(self):
                return execution_source.begin_nested()

            async def execute(self, statement, params=None):
                if str(statement).startswith("SET TRANSACTION"):
                    return None  # Fixture already owns its outer mutation transaction.
                return await execution_source.execute(statement, params or {})

        yield FixtureConnection()

    monkeypatch.setattr(research_resolution, "connect_admin", admin)
    for intent, mode, metric in (("list", "records", "none"), ("count", "count", "event_count")):
        response = await service.ResearchPlanExecutor().execute(
            Request({"type": "http"}),
            settings,
            planned(
                original_query="Welche Veranstaltungen gibt es heute in Flensburg?",
                area_query="Flensburg",
                intent=intent,
                answer_mode=mode,
                metric=metric,
            ),
        )
        assert response.resolution[0].target.id == str(uid(901))
        assert response.result.total == 2 if intent == "list" else response.result.value == 2
    missing = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, planned(area_query="Atlantis")
    )
    assert missing.result.reason == "no_match"
    await insert_area(
        execution_source, uid(903), "Flensburg", "POLYGON((8 54,9 54,9 55,8 55,8 54))", 993
    )
    ambiguous = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, planned(area_query="Flensburg")
    )
    assert ambiguous.result.reason == "ambiguous"
    assert len(ambiguous.result.candidates) == 2


async def test_stage_failure_is_not_empty_success(settings, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    for error in (SQLAlchemyError("private provider data"), TimeoutError("private")):
        monkeypatch.setattr(service, "resolve_plan", AsyncMock(side_effect=error))
        with pytest.raises(APIError) as exc:
            await service.ResearchPlanExecutor().execute(
                Request({"type": "http"}), settings, planned()
            )
        assert exc.value.status == 503 and exc.value.code == "research_execution_unavailable"
        assert "private" not in exc.value.message


async def test_planner_clarification_and_unsupported_do_no_work(settings, monkeypatch):
    resolver = AsyncMock(side_effect=AssertionError("no source work"))
    monkeypatch.setattr(service, "resolve_plan", resolver)
    response = planned(clarification="needs_date")
    response = ClarificationResponse.model_validate(
        {**response.model_dump(), "kind": "needs_clarification"}
    )
    assert (
        await service.ResearchPlanExecutor().execute(Request({"type": "http"}), settings, response)
    ).result.planner_state == "needs_date"
    with pytest.raises(APIError) as exc:
        await service.ResearchPlanExecutor().execute(
            Request({"type": "http"}),
            settings,
            planned(unsupported_reason="unsupported_constraint"),
        )
    assert exc.value.code == "research_plan_unsupported"
    resolver.assert_not_called()


@pytest.mark.parametrize(
    "csrf,expected",
    [
        ({}, 403),
        ({"Origin": "https://evil.test", "X-Admin-CSRF": "1"}, 403),
        ({"Origin": "https://admin.test", "X-Admin-CSRF": "1"}, 200),
    ],
)
async def test_query_cookie_csrf(client, pipeline, monkeypatch, csrf, expected):
    from app.auth import dependencies

    app = client._transport.app
    app.state.settings.auth_public_origin = "https://admin.test"
    monkeypatch.setattr(
        dependencies,
        "session_identity",
        AsyncMock(return_value=AdminPrincipal(subject=f"admin:{uid(1)}", journalist=True)),
    )
    client.cookies.set("admin_session", "a" * 43)
    response = planned(clarification="needs_date")
    pipeline.plan.return_value = ClarificationResponse.model_validate(
        {**response.model_dump(), "kind": "needs_clarification"}
    )
    result = await client.post(PATH, json={"query": "today"}, headers=csrf)
    assert result.status_code == expected
    if expected == 403:
        pipeline.plan.assert_not_called()


async def test_semantic_pipeline_hard_filters_with_source(
    execution_source, settings, retrieval, monkeypatch, now
):
    from app.services import semantic_search

    # Keep fake Jina/Qdrant, replace mock rehydration with real SQL.
    async def connection(request):
        yield execution_source

    monkeypatch.setattr(semantic_search, "get_connection", connection)
    monkeypatch.setattr(semantic_search, "rehydrate_semantic_events", rehydrate_semantic_events)
    retrieval["hits"] = [hit(31, 0.99), hit(32, 0.98), hit(30, 0.7)]
    response = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        planned(
            intent="recommend",
            answer_mode="recommendation",
            semantic_query="interesting",
            requires_semantic_relevance=True,
            venue_query="Phänomenta",
            time_of_day="evening",
        ),
    )
    assert [i.entity_key for i in response.result.items] == [uid(30)]
    assert response.result.items[0].semantic.score == 0.7
    await execution_source.execute(text("UPDATE uranus.event_date SET start_time='17:59'"))
    empty = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        planned(
            intent="search",
            semantic_query="interesting",
            requires_semantic_relevance=True,
            time_of_day="evening",
        ),
    )
    assert empty.result.items == [] and empty.result.total is None


async def test_execution_logs_exclude_query_and_plan(
    client, headers, pipeline, monkeypatch, caplog
):
    import logging

    from app.logging import JsonFormatter

    sentinel = "private-execution-query-marker"
    pipeline.plan.return_value = planned(original_query=sentinel, venue_query=sentinel)
    monkeypatch.setattr(service, "resolve_plan", AsyncMock(side_effect=TimeoutError(sentinel)))
    with caplog.at_level(logging.INFO):
        response = await client.post(PATH, headers=headers, json={"query": sentinel})
    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"
    assert sentinel not in response.text
    for record in caplog.records:
        assert sentinel not in JsonFormatter().format(record)
        assert "venue_query" not in JsonFormatter().format(record)


async def test_query_planner_failure_stops_execution(client, headers, pipeline, monkeypatch):
    pipeline.plan.side_effect = APIError(
        503, "research_planner_unavailable", "Planner unavailable."
    )
    resolve = AsyncMock(side_effect=AssertionError("no source work"))
    monkeypatch.setattr(service, "resolve_plan", resolve)
    assert (await client.post(PATH, headers=headers, json={"query": "today"})).status_code == 503
    resolve.assert_not_called()


async def test_records_bounds_and_stable_tie_order(settings, execution_source, now):
    await execution_source.execute(
        text("""INSERT INTO uranus.event
        (uuid,org_uuid,title,release_status)
        SELECT md5(n::text)::uuid,:org,'Same title','released'
        FROM generate_series(1000,1024) n"""),
        {"org": uid(10)},
    )
    response = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, planned(temporal="none")
    )
    assert response.result.total == 27 and len(response.result.items) == 20
    undated = [i for i in response.result.items if i.start_date is None]
    assert [i.entity_key for i in undated] == sorted(i.entity_key for i in undated)


async def test_resolver_ranking_and_candidate_bound(settings, execution_source):
    await execution_source.execute(
        text("""UPDATE uranus.venue SET name=
        CASE WHEN uuid=:id THEN 'Haus' ELSE 'Haus Nord' END"""),
        {"id": uid(20)},
    )
    assert [c.id for c in await candidates(execution_source, "venue", "haus", settings)] == [
        str(uid(20))
    ]
    assert len(await candidates(execution_source, "venue", "ha", settings)) == 2
    assert [c.id for c in await candidates(execution_source, "venue", "Nord", settings)] == [
        str(uid(21))
    ]
    await execution_source.execute(
        text("""INSERT INTO uranus.organization(uuid,name)
        SELECT md5(n::text)::uuid,'Same' FROM generate_series(1100,1106) n""")
    )
    await execution_source.execute(
        text("""INSERT INTO uranus.event(uuid,org_uuid,title,release_status)
        SELECT md5((n+100)::text)::uuid,md5(n::text)::uuid,'Public','released'
        FROM generate_series(1100,1106) n""")
    )
    choices = await candidates(execution_source, "organization", "same", settings)
    assert len(choices) == 5 and [c.id for c in choices] == sorted(c.id for c in choices)


async def test_uuid_and_taxonomy_normalization(settings, execution_source):
    from uuid import UUID

    org = UUID("abcdefab-abcd-abcd-abcd-abcdefabcdef")
    await execution_source.execute(
        text("INSERT INTO uranus.organization(uuid,name) VALUES(:id,'Upper UUID')"), {"id": org}
    )
    await execution_source.execute(
        text(
            "INSERT INTO uranus.event(uuid,org_uuid,title,release_status) "
            "VALUES(:id,:org,'Public','released')"
        ),
        {"id": uid(1200), "org": org},
    )
    assert (await candidates(execution_source, "organization", str(org).upper(), settings))[
        0
    ].id == str(org)
    await execution_source.execute(
        text(
            "INSERT INTO uranus.event_category(category_id,iso_639_1,name) "
            "VALUES(101,'de','Musik'),(102,'de',' Musik ')"
        )
    )
    await execution_source.execute(
        text("UPDATE uranus.event SET categories=ARRAY[101,102] WHERE uuid=:id"), {"id": uid(30)}
    )
    assert len(await candidates(execution_source, "category", "musik", settings)) == 2


async def test_query_cannot_select_vector_model_collection_or_url(
    client, headers, pipeline, monkeypatch, retrieval
):
    response = planned(
        intent="search",
        requires_semantic_relevance=True,
        semantic_query="http://private.invalid/arbitrary-collection",
    )
    # The trusted planner's model is provenance, never a retrieval configuration input.
    response.model = "arbitrary-planner-model"
    response.diagnostics.planner_model = response.model
    pipeline.plan.return_value = response
    monkeypatch.setattr(service, "resolve_plan", AsyncMock(return_value=Resolution()))
    result = await client.post(PATH, headers=headers, json={"query": "today"})
    assert result.status_code == 200
    requests = retrieval["requests"]
    assert [(r.url.host, r.url.path) for r in requests] == [
        ("127.0.0.1", "/embed"),
        ("127.0.0.1", "/collections/kulturbytes_events_jina_v3_v1/points/query"),
    ]
    assert json.loads(requests[0].content)["model"] == "jina-v3"


async def test_execution_sql_is_read_only_and_public(settings, execution_source):
    from sqlalchemy import event

    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(execution_source.sync_connection, "before_cursor_execute", capture)
    try:
        await service.ResearchPlanExecutor().execute(
            Request({"type": "http"}), settings, planned(venue_query="Deutsches Haus")
        )
        await service.ResearchPlanExecutor().execute(
            Request({"type": "http"}),
            settings,
            planned(
                intent="aggregate", answer_mode="aggregate", metric="event_count", group_by="venue"
            ),
        )
    finally:
        event.remove(execution_source.sync_connection, "before_cursor_execute", capture)
    assert statements
    assert all(s.lstrip().startswith(("SELECT", "WITH")) for s in statements)
    assert all(
        private not in " ".join(statements).lower()
        for private in (
            "contact_email",
            "password",
            "auth_account",
            "admin.finding",
            "custom_fields",
        )
    )
