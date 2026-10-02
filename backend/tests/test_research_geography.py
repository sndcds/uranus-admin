"""Geographic plans through resolution and execution; no live geocoder calls."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from pydantic import TypeAdapter
from sqlalchemy import text

from app.errors import APIError
from app.repositories.research_place import place_filter
from app.schemas.research_geography import GeographicPlanResponse
from app.schemas.research_location import LocationContext, Place
from app.services import research_plan_execution as executor
from tests.test_research_geocoder import PLACE
from tests.test_research_plan_execution import execution_source as execution_source_fixture
from tests.test_research_plan_execution import planned

execution_source = execution_source_fixture
CASES = json.loads((Path(__file__).parent / "fixtures/research_geography.json").read_text())


def envelope(index=0):
    data = planned().model_dump(mode="json")
    plan = CASES[index]["plan"]
    data.update(
        schema_version="research-query-plan-v6",
        prompt_version="research-planner-v9",
        plan=plan,
        kind="plan" if plan["clarification"] == "none" else "needs_clarification",
    )
    data["diagnostics"].update(
        planner_prompt_version="research-planner-v9", planner_intent=plan["intent"]
    )
    return TypeAdapter(GeographicPlanResponse).validate_json(json.dumps(data))


def request_with(geocoder):
    return Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(research_geocoder=geocoder))}
    )


@pytest.fixture
def geocoder():
    return SimpleNamespace(
        search=AsyncMock(return_value=[Place.model_validate_json(json.dumps(PLACE))]),
        reverse=AsyncMock(return_value=Place.model_validate_json(json.dumps(PLACE))),
    )


@pytest.fixture
def execution(monkeypatch):
    async def connection(request):
        yield object()

    monkeypatch.setattr(executor, "get_connection", connection)
    records = AsyncMock(return_value=[])
    monkeypatch.setattr(executor, "chronological_records", records)
    return records


@pytest.mark.parametrize("index", range(len(CASES)))
def test_reviewed_geographic_corpus(index):
    assert envelope(index).plan.model_dump(mode="json") == CASES[index]["plan"]


async def test_bachstrasse_today_reaches_postgres_and_zero_is_success(
    settings, geocoder, execution
):
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope()
    )
    geocoder.search.assert_awaited_once_with("Bachstraße Flensburg")
    assert result.result.kind == "records" and result.result.items == []
    execution.assert_awaited_once()
    filters = execution.call_args.args[2]
    assert filters.from_date == filters.to_date == date(2026, 9, 30)
    assert filters.place.mode == "address" and filters.place.road == "Bachstraße"
    assert filters.place.city == "Flensburg"


@pytest.mark.parametrize("index", [9, 10, 11, 12])
async def test_where_is_not_near_me(settings, geocoder, execution, index):
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope(index)
    )
    assert result.result.kind == "records"
    assert execution.call_args.args[2].place is None
    geocoder.search.assert_not_awaited()
    geocoder.reverse.assert_not_awaited()


async def test_near_me_needs_context_then_reverses_and_keeps_coordinates(
    settings, geocoder, execution
):
    response = envelope(7)
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, response
    )
    assert result.result.planner_state == "needs_location"
    execution.assert_not_awaited()
    geocoder.reverse.assert_not_awaited()
    context = LocationContext(latitude=54.79, longitude=9.43, source="browser_geolocation")
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, response, location_context=context
    )
    assert result.result.kind == "records"
    geocoder.reverse.assert_awaited_once_with(54.79, 9.43)
    filters = execution.call_args.args[2]
    assert filters.place.mode == "radius" and filters.place.radius_m == 500
    assert filters.place.latitude == 54.79 and filters.place.longitude == 9.43
    assert "54.79" not in result.diagnostics.model_dump_json()
    geocoder.reverse.reset_mock()
    await executor.ResearchPlanExecutor().execute(
        request_with(geocoder),
        settings,
        response,
        location_context=context.model_copy(update={"display_name": "Flensburg"}),
    )
    geocoder.reverse.assert_not_awaited()


@pytest.mark.parametrize(
    "items,reason",
    [
        ([], "no_match"),
        ([PLACE, PLACE | {"osm_id": 124}], "ambiguous"),
        ([{"display_name": "unknown"}], "no_match"),
    ],
)
async def test_fail_closed_candidates(settings, geocoder, execution, items, reason):
    geocoder.search.return_value = [Place.model_validate_json(json.dumps(p)) for p in items]
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope()
    )
    assert result.result.reason == reason
    execution.assert_not_awaited()


async def test_safe_geocoder_error_prevents_execution(settings, geocoder, execution):
    geocoder.search.side_effect = APIError(503, "geocoder_unavailable", "Location unavailable.")
    with pytest.raises(APIError) as exc:
        await executor.ResearchPlanExecutor().execute(request_with(geocoder), settings, envelope())
    assert exc.value.code == "geocoder_unavailable"
    execution.assert_not_awaited()


@pytest.mark.parametrize(
    "mode,place",
    [
        ("address", PLACE),
        ("bbox", PLACE | {"address": None}),
        ("radius", PLACE | {"address": None, "osm_type": "node"}),
    ],
)
async def test_postgis_modes_today_and_missing_geometry(
    settings, execution_source, geocoder, mode, place
):
    connection = execution_source
    await connection.execute(
        text("""UPDATE uranus.venue SET street='Bachstraße',city='Flensburg',
        point=ST_SetSRID(ST_MakePoint(9.43,54.79),4326)""")
    )
    geocoder.search.return_value = [Place.model_validate_json(json.dumps(place))]
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope()
    )
    assert result.result.kind == "records" and result.result.items
    assert place_filter(Place.model_validate_json(json.dumps(place))).mode == mode
    # A nearby-looking street prefix or a distant point cannot pass the selection.
    if mode == "address":
        await connection.execute(text("UPDATE uranus.venue SET street='Bachstraße West'"))
    else:
        await connection.execute(
            text("UPDATE uranus.venue SET point=ST_SetSRID(ST_MakePoint(10,55),4326)")
        )
    outside = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope()
    )
    assert outside.result.items == []
    await connection.execute(text("UPDATE uranus.venue SET street='Bachstraße'"))
    # Address matches remain authoritative without a point; geometry matches cannot.
    await connection.execute(text("UPDATE uranus.venue SET point=NULL"))
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope()
    )
    assert bool(result.result.items) == (mode == "address")
    await connection.execute(text("UPDATE uranus.event_date SET start_date='2026-10-01'"))
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope()
    )
    assert result.result.items == []


async def test_query_api_passes_context_and_never_learns_location(
    client, settings, headers, monkeypatch, geocoder, execution
):
    from pydantic import SecretStr

    from app.api import research

    app = client._transport.app
    settings.research_geocoder_api_key = SecretStr("g" * 32)
    planner = SimpleNamespace(plan=AsyncMock(return_value=envelope(7)))
    app.state.research_planner = planner
    app.state.research_geocoder = geocoder
    learn = AsyncMock()
    monkeypatch.setattr(research, "record_success", learn)
    context = {"latitude": 54.79, "longitude": 9.43, "source": "browser_geolocation"}
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={"query": CASES[7]["query"], "location_context": context},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["kind"] == "records"
    planner.plan.assert_awaited_once_with(CASES[7]["query"], geographic=True)
    geocoder.reverse.assert_awaited_once_with(54.79, 9.43)
    learn.assert_not_awaited()
    planner.plan.return_value = envelope()
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": CASES[0]["query"]}
    )
    assert response.status_code == 200
    learn.assert_not_awaited()
    for invalid in [
        context | {"url": "http://evil.invalid"},
        context | {"latitude": 91},
        context | {"osm_id": 1},
        context | {"longitude": None},
    ]:
        response = await client.post(
            "/api/v1/research/query",
            headers=headers,
            json={"query": CASES[7]["query"], "location_context": invalid},
        )
        assert response.status_code == 422


async def test_geographic_client_never_forwards_browser_context():
    import httpx

    from app.services.research_planner import ResearchPlannerClient
    from tests.test_research_planner import configured

    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=envelope().model_dump(mode="json"))

    planner = ResearchPlannerClient(configured(), transport=httpx.MockTransport(respond))
    try:
        result = await planner.plan(CASES[0]["query"], geographic=True)
        assert result.plan.place_query == "Bachstraße Flensburg"
        assert calls[0].url.path == "/v6/plan"
        assert set(json.loads(calls[0].content)) == {"query", "timezone", "language"}
    finally:
        await planner.close()


async def test_manual_context_searches_and_unrelated_question_ignores_context(
    settings, geocoder, execution
):
    context = LocationContext(display_name="Nordermarkt", source="manual")
    result = await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope(7), location_context=context
    )
    assert result.result.kind == "records"
    geocoder.search.assert_awaited_once_with("Nordermarkt")
    geocoder.search.reset_mock()
    await executor.ResearchPlanExecutor().execute(
        request_with(geocoder), settings, envelope(9), location_context=context
    )
    geocoder.search.assert_not_awaited()
    assert execution.call_args.args[2].place is None


async def test_semantic_eligibility_and_rehydration_receive_same_place(
    settings, geocoder, execution, monkeypatch
):
    from app.schemas.research_geography import GeographicQueryPlan

    response = envelope()
    response = response.model_copy(
        update={
            "plan": GeographicQueryPlan.model_validate(
                response.plan.model_dump()
                | {
                    "intent": "search",
                    "semantic_query": "gemütlich",
                    "requires_semantic_relevance": True,
                }
            )
        }
    )
    eligible = AsyncMock(return_value=[])
    semantic = AsyncMock(return_value=SimpleNamespace(items=[], observed_at=None))
    from datetime import UTC, datetime

    semantic.return_value.observed_at = datetime.now(UTC)
    monkeypatch.setattr(executor, "eligible_event_ids", eligible)
    monkeypatch.setattr(executor, "semantic_research", semantic)
    await executor.ResearchPlanExecutor().execute(request_with(geocoder), settings, response)
    assert eligible.call_args.args[2].place == semantic.call_args.args[2].place
    assert semantic.call_args.args[2].place.mode == "address"
    execution.assert_not_awaited()
