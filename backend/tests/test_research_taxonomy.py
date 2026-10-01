"""v3 taxonomy regressions; PostgreSQL cases run in CI."""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import text

from app.repositories import research_resolution as resolver
from app.repositories.research import parameters, rehydrate_semantic_events
from app.repositories.research_execution import eligible_event_ids
from app.schemas.research_execution import (
    ExecutionFilters,
    ExecutionSemanticFilters,
    ResolutionCandidate,
)
from app.schemas.research_planner import ResearchQueryPlan
from app.services import research_plan_execution as service
from tests.conftest import uid
from tests.test_research_plan_execution import execution_source as execution_source_fixture
from tests.test_research_plan_execution import planned

execution_source = execution_source_fixture
QUERY = "welche jazz konzerte finden heute statt\n"


@pytest.mark.parametrize("value", [None, "Konzerte", [" "], ["x"] * 9, [1]])
def test_event_type_contract_rejects_invalid(value):
    data = planned().plan.model_dump(mode="json") | {"event_type_queries": value}
    with pytest.raises(ValidationError):
        ResearchQueryPlan.model_validate_json(json.dumps(data))


def test_event_type_contract_required_and_neutral():
    data = planned().plan.model_dump(mode="json")
    del data["event_type_queries"]
    with pytest.raises(ValidationError):
        ResearchQueryPlan.model_validate_json(json.dumps(data))
    with pytest.raises(ValidationError, match="outside_research_requires_neutral_plan"):
        planned(
            unsupported_reason="outside_research", temporal="none", event_type_queries=["Konzerte"]
        )


@pytest.fixture
def taxonomy_lookup(monkeypatch):
    async def connection(request):
        yield object()

    monkeypatch.setattr(resolver, "get_connection", connection)
    monkeypatch.setattr(service, "get_connection", connection)
    lookup = AsyncMock(
        side_effect=lambda conn, kind, query, *args: [
            ResolutionCandidate(
                entity_type=kind,
                id={"event_type": "1", "genre": "1:2", "category": "7"}[kind],
                label=query,
            )
        ]
    )
    monkeypatch.setattr(resolver, "candidates", lookup)
    return lookup


@pytest.mark.parametrize(
    "field,kind",
    [
        ("event_type_queries", "event_type"),
        ("genre_queries", "genre"),
        ("category_queries", "category"),
    ],
)
async def test_each_taxonomy_resolves_independently(settings, taxonomy_lookup, field, kind):
    result = await resolver.resolve_plan(
        Request({"type": "http"}), settings, planned(**{field: ["Label"]}).plan
    )
    assert result.clarification is None
    assert result.fields[0].field == field and result.fields[0].target.entity_type == kind


@pytest.mark.parametrize("field", ["event_type_queries", "genre_queries"])
async def test_taxonomy_no_match(settings, taxonomy_lookup, field):
    taxonomy_lookup.side_effect = None
    taxonomy_lookup.return_value = []
    result = await resolver.resolve_plan(
        Request({"type": "http"}), settings, planned(**{field: ["Unknown"]}).plan
    )
    assert result.clarification.reason == "no_match"
    assert result.clarification.field == field and result.clarification.candidates == []


async def test_taxonomies_intersect_deduplicate_and_sort(settings, taxonomy_lookup):
    response = planned(
        event_type_queries=["Konzerte"] * 2,
        genre_queries=["Jazz"] * 2,
        category_queries=["Musik"] * 2,
    )
    result = await resolver.resolve_plan(Request({"type": "http"}), settings, response.plan)
    assert result.clarification is None
    assert [call.args[1] for call in taxonomy_lookup.await_args_list] == ["event_type"] * 2 + [
        "genre"
    ] * 2 + ["category"] * 2
    filters = service.execution_filters(response, result)
    assert (
        filters.event_type_ids == [1]
        and filters.genre_keys == ["1:2"]
        and filters.category_ids == [7]
    )
    assert parameters(filters, settings)["event_type_ids"] == [1]


async def test_incompatible_parent_fails_without_discarding_filters(settings, taxonomy_lookup):
    taxonomy_lookup.side_effect = [
        [ResolutionCandidate(entity_type="event_type", id="1", label="Konzerte")],
        [ResolutionCandidate(entity_type="genre", id="2:2", label="Jazz")],
    ]
    result = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        planned(event_type_queries=["Konzerte"], genre_queries=["Jazz"]),
    )
    assert result.result.reason == "taxonomy_conflict" and result.result.field == "genre_queries"
    assert [r.target.id for r in result.resolution] == ["1", "2:2"]
    assert not result.execution.structured


async def test_exact_bug_request_returns_empty_records(
    client, headers, taxonomy_lookup, monkeypatch
):
    response = planned(
        original_query=QUERY, event_type_queries=["Konzerte"], genre_queries=["Jazz"]
    )
    client._transport.app.state.research_planner = AsyncMock(plan=AsyncMock(return_value=response))
    records = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "chronological_records", records)
    result = await client.post("/api/v1/research/query", headers=headers, json={"query": QUERY})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["result"] == {"kind": "records", "items": [], "total": None}
    assert body["execution"]["structured"]
    assert body["execution"]["event_type_ids"] == [1]
    assert body["execution"]["genre_keys"] == ["1:2"] and body["execution"]["category_ids"] == []
    assert body["execution"]["from_date"] == body["execution"]["to_date"] == "2026-09-30"
    assert records.call_args.args[2].event_type_ids == [1]


async def test_semantic_path_preserves_event_type(settings, taxonomy_lookup, monkeypatch):
    response = planned(
        intent="search",
        semantic_query="ruhig",
        requires_semantic_relevance=True,
        event_type_queries=["Konzerte"],
        genre_queries=["Jazz"],
    )
    eligible = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "eligible_event_ids", eligible)
    result = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}), settings, response
    )
    assert result.result.kind == "records" and result.result.items == []
    assert eligible.call_args.args[2].event_type_ids == [1]
    filters = ExecutionSemanticFilters(
        **eligible.call_args.args[2].model_dump(exclude={"q", "sort"}), q="ruhig"
    )
    assert filters.event_type_ids == [1] and parameters(filters, settings)["event_type_ids"] == [1]


@pytest.fixture
async def taxonomy_source(execution_source):
    c = execution_source
    await c.execute(
        text(
            "INSERT INTO uranus.event_type(type_id,iso_639_1,name) "
            "VALUES (1,'de','Konzerte'),(1,'en','Concerts'),(2,'de','Theater'),"
            "(3,'de','Privat'),(4,'de','Unbenutzt')"
        )
    )
    await c.execute(
        text(
            "INSERT INTO uranus.genre_type(type_id,genre_id,iso_639_1,name) "
            "VALUES (1,2,'de','Jazz'),(2,2,'de','Drama')"
        )
    )
    await c.execute(
        text(
            "INSERT INTO uranus.event_type_link(event_uuid,type_id,genre_id) "
            "VALUES (:a,1,2),(:b,2,2),(:private,3,0)"
        ),
        {"a": uid(30), "b": uid(32), "private": uid(31)},
    )
    await c.execute(
        text("UPDATE uranus.event SET categories=ARRAY[7] WHERE uuid=:id"), {"id": uid(30)}
    )
    return c


async def test_exact_public_taxonomy_lookup(settings, taxonomy_source):
    for kind, label, identifier in [("event_type", " konzerte ", "1"), ("genre", "Jazz", "1:2")]:
        assert [
            c.id for c in await resolver.candidates(taxonomy_source, kind, label, settings)
        ] == [identifier]
    for label in ("Konz", "Konzerte extra", "Privat", "Unbenutzt", "1"):
        assert await resolver.candidates(taxonomy_source, "event_type", label, settings) == []
    assert await resolver.candidates(taxonomy_source, "genre", "Jaz", settings) == []


@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"event_type_ids": [1]}, [30]),
        ({"genre_keys": ["1:2"]}, [30]),
        ({"event_type_ids": [1], "genre_keys": ["1:2"]}, [30]),
        ({"event_type_ids": [2], "genre_keys": ["1:2"]}, []),
        ({"event_type_ids": [1], "category_ids": [7]}, [30]),
        ({"event_type_ids": [2], "category_ids": [7]}, []),
        (
            {
                "event_type_ids": [1],
                "genre_keys": ["1:2"],
                "from_date": "2026-09-30",
                "to_date": "2026-09-30",
            },
            [30],
        ),
        ({"event_type_ids": [1], "genre_keys": ["1:2"], "from_date": "2026-10-01"}, []),
    ],
)
async def test_authoritative_taxonomy_intersection(
    settings, taxonomy_source, now, filters, expected
):
    selection = ExecutionFilters.model_validate(filters)
    ids = await eligible_event_ids(taxonomy_source, settings, selection, None)
    assert ids == [uid(n) for n in expected]
    semantic = ExecutionSemanticFilters(**selection.model_dump(exclude={"q", "sort"}), q="music")
    page = await rehydrate_semantic_events(
        taxonomy_source, settings, semantic, [uid(30), uid(32)], now
    )
    assert [r.entity_key for r in page.items] == ids


@pytest.mark.parametrize("temporal,expected", [("today", [30]), ("tomorrow", [])])
async def test_postgres_bug_regression_records_even_when_empty(
    settings, taxonomy_source, temporal, expected
):
    result = await service.ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        planned(
            original_query=QUERY,
            event_type_queries=["Konzerte"],
            genre_queries=["Jazz"],
            temporal=temporal,
        ),
    )
    assert result.result.kind == "records"
    assert [r.entity_key for r in result.result.items] == [uid(n) for n in expected]
    assert result.execution.structured
    assert result.execution.event_type_ids == [1] and result.execution.genre_keys == ["1:2"]


@pytest.mark.parametrize("kind,identifier", [("event_type", "1"), ("genre", "1:2")])
async def test_exact_taxonomy_sql_and_bound_label(settings, kind, identifier):
    from unittest.mock import Mock

    rows = Mock()
    rows.mappings.return_value = [{"id": identifier, "label": "Label"}]
    connection = AsyncMock()
    connection.execute.return_value = rows
    choices = await resolver.candidates(connection, kind, " Label ", settings)
    assert choices == [ResolutionCandidate(entity_type=kind, id=identifier, label="Label")]
    statement, params = connection.execute.call_args.args
    sql = str(statement)
    assert "ILIKE" not in sql
    assert "lower(trim(label))=lower(:exact)" in sql
    assert "uranus.event_type_link" in sql and "EXISTS" in sql
    assert params["exact"] == "Label"
