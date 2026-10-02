"""Synthetic contract-to-PostGIS examples; no live Planner or Nominatim access."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Request
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

from app.clients.research_geocoder import ResearchGeocoderClient
from app.errors import APIError
from app.repositories.administrative_execution import execute_resolved
from app.research.administrative_catalog import Catalog, Catalogs, load_inventory
from app.research.administrative_resolver import resolved_boundary, select_candidate
from app.research.internal_plan import AreaRequest, ResolvedResearchPlan, ResolvedSpatialConstraint
from app.research.normalizer import normalize_plan
from app.research.wire.research_v8_schema import PlanResponseV8, ResearchQueryPlanV8
from app.schemas.research_administrative import AdministrativePlace
from app.services import research_administrative as service
from app.services.research_planner import ResearchPlannerClient
from tests.conftest import uid

EXAMPLES = json.loads(Path("tests/fixtures/administrative_planner_v8.json").read_text())


def polygon(west=9, south=54, east=10, north=55):
    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


def place(name="Schleswig-Holstein", level="state", identity=1, geometry=None):
    return AdministrativePlace.model_validate_json(
        json.dumps(
            {
                "name": name,
                "display_name": name,
                "osm_type": "relation",
                "osm_id": identity,
                "administrative_level": level,
                "administrative_levels": [level],
                "country_code": "de",
                "boundary": geometry or polygon(),
            }
        )
    )


def envelope(example):
    return PlanResponseV8.model_validate_json(
        json.dumps(
            {
                "kind": "plan",
                "schema_version": "research-query-plan-v8",
                "prompt_version": "research-planner-v14",
                "model": "test-model",
                "plan": example,
                "reference_date": "2026-10-02",
                "timezone": "Europe/Berlin",
                "diagnostics": {
                    "request_id": "a" * 32,
                    "planner_intent": example["intent"],
                    "planner_model": "test-model",
                    "planner_prompt_version": "research-planner-v14",
                    "planner_ms": 1,
                    "total_ms": 1,
                },
            }
        )
    )


def test_wire_snapshot_matches_planner_and_no_execution_fields():
    assert ResearchQueryPlanV8.model_json_schema() == json.loads(
        Path("tests/fixtures/administrative_planner_v8_schema.json").read_text()
    )
    plan = normalize_plan(envelope(EXAMPLES[6]).plan)
    assert [(s.relation, s.area.expected_level) for s in plan.spatial] == [
        ("outside", "state"),
        ("inside", "country"),
    ]
    assert not hasattr(plan, "osm_id")


@pytest.mark.parametrize("index", range(len(EXAMPLES)))
def test_examples_normalize_without_dropping_predicates(index):
    normalized = normalize_plan(envelope(EXAMPLES[index]).plan)
    assert len(normalized.spatial) == len(EXAMPLES[index]["spatial"])
    assert normalized.grouping == (
        EXAMPLES[index]["group_by"] if EXAMPLES[index]["group_by"] != "none" else None
    )


def test_mismatch_ambiguity_country_and_canonical_name():
    with pytest.raises(APIError, match="requested level") as failure:
        select_candidate([place()], AreaRequest("Schleswig-Holstein", "district"))
    assert failure.value.code == "research_area_level_mismatch"
    with pytest.raises(APIError):
        select_candidate(
            [place("Schleswig", identity=1), place("Schleswig", identity=2)],
            AreaRequest("Schleswig", "state"),
        )
    assert (
        select_candidate(
            [place("Schleswig", identity=2), place("Schleswig-Holstein")],
            AreaRequest("Schleswig-Holstein", "state"),
        ).osm_id
        == 1
    )
    with pytest.raises(APIError):
        select_candidate([place()], AreaRequest("Schleswig-Holstein", "state", "dk"))


def test_no_incomplete_metadata_or_implied_codes():
    assert resolved_boundary(place(), "state").area.official_code is None
    with pytest.raises(ValidationError):
        AdministrativePlace.model_validate_json(
            json.dumps({"administrative_level": "state", "administrative_levels": ["district"]})
        )
    with pytest.raises(APIError):
        resolved_boundary(place().model_copy(update={"boundary": None}), "state")


async def test_incomplete_inventory_does_not_prove_zero(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(
        Catalogs(
            catalogs=[
                Catalog(
                    schema_version="administrative-catalog-v1",
                    level="state",
                    parent_area_id=None,
                    country_codes=["de"],
                    complete=False,
                    inventory_source="synthetic",
                    items=[place()],
                )
            ]
        ).model_dump_json()
    )
    with pytest.raises(APIError) as failure:
        await load_inventory(path, "state", ())
    assert failure.value.code == "research_inventory_unavailable"


async def test_geocoder_private_metadata_validated_but_not_leaked_to_old_place(settings):
    settings.research_geocoder_api_key = SecretStr("test-key-with-at-least-thirty-two-characters")

    def respond(request):
        if request.url.path == "/lookup":
            return httpx.Response(200, json=place(identity=99).model_dump(mode="json"))
        return httpx.Response(
            200, json={"query": "Schleswig-Holstein", "items": [place().model_dump(mode="json")]}
        )

    client = ResearchGeocoderClient(settings, transport=httpx.MockTransport(respond))
    try:
        old = await client.search("Schleswig-Holstein")
        assert "boundary" not in old[0].model_dump()
        with pytest.raises(APIError) as failure:
            await client.administrative_boundary("R", 1)
        assert failure.value.code == "geocoder_unavailable"
    finally:
        await client.close()


@pytest.fixture
async def source(db_connection, monkeypatch):
    await db_connection.execute(text("UPDATE uranus.event SET release_status='draft'"))
    points = ["POINT(9.5 54.5)", "POINT(9 54.5)", "POINT(11 54.5)", "POINT(15 60)", None]
    for index, point in enumerate(points):
        await db_connection.execute(
            text(
                "INSERT INTO uranus.venue(uuid,org_uuid,name,scope,point) "
                "VALUES(:id,:org,:name,'organization',ST_GeomFromText(:point,4326))"
            ),
            {"id": uid(1000 + index), "org": uid(10), "name": f"Synthetic {index}", "point": point},
        )
        await db_connection.execute(
            text(
                "INSERT INTO uranus.event(uuid,org_uuid,venue_uuid,title,release_status,"
                "categories) "
                "VALUES(:id,:org,:venue,:name,'released',ARRAY[1])"
            ),
            {
                "id": uid(2000 + index),
                "org": uid(10),
                "venue": uid(1000 + index),
                "name": f"Synthetic {index}",
            },
        )
        await db_connection.execute(
            text(
                "INSERT INTO uranus.event_date(uuid,event_uuid,start_date) "
                "VALUES(:id,:event,'2026-10-02')"
            ),
            {"id": uid(3000 + index), "event": uid(2000 + index)},
        )
    # This event has two occurrences, neither satisfying outside SH AND inside DE.
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event(uuid,org_uuid,title,release_status) "
            "VALUES(:id,:org,'Split occurrence','released')"
        ),
        {"id": uid(2005), "org": uid(10)},
    )
    for index, venue in enumerate([1000, 1003]):
        await db_connection.execute(
            text(
                "INSERT INTO uranus.event_date(uuid,event_uuid,venue_uuid,start_date) "
                "VALUES(:id,:event,:venue,'2026-10-02')"
            ),
            {"id": uid(3005 + index), "event": uid(2005), "venue": uid(venue)},
        )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event_category(category_id,iso_639_1,name) VALUES(1,'de','Kultur')"
        )
    )

    async def connection(request):
        yield db_connection

    monkeypatch.setattr(service, "get_connection", connection)
    return db_connection


@pytest.mark.parametrize(
    "index,expected", [(0, {2002, 2003, 2005}), (1, {2000, 2001, 2005}), (6, {2002})]
)
async def test_full_pipeline_membership_and_conjunction(source, settings, index, expected):
    example = EXAMPLES[index]
    names = {
        "Schleswig-Holstein": place(),
        "Schleswig-Flensburg": place("Schleswig-Flensburg", "district", 2),
        "Deutschland": place("Deutschland", "country", 3, polygon(5, 47, 13, 56)),
    }
    calls = []

    def planner_response(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=envelope(example).model_dump(mode="json"))

    def geocode_response(request):
        body = json.loads(request.content)
        if request.url.path == "/search":
            item = names[body["query"]].model_dump(mode="json")
            item.pop("boundary")
            return httpx.Response(200, json={"query": body["query"], "items": [item]})
        item = next(p for p in names.values() if p.osm_id == body["osm_id"])
        return httpx.Response(200, json=item.model_dump(mode="json"))

    settings.research_planner_url = "http://127.0.0.1:6334"
    settings.research_planner_api_key = SecretStr("test-key-with-at-least-thirty-two-characters")
    settings.research_geocoder_api_key = settings.research_planner_api_key
    planner = ResearchPlannerClient(settings, transport=httpx.MockTransport(planner_response))
    geocoder = ResearchGeocoderClient(settings, transport=httpx.MockTransport(geocode_response))
    request = Request(
        {
            "type": "http",
            "app": SimpleNamespace(
                state=SimpleNamespace(research_planner=planner, research_geocoder=geocoder)
            ),
        }
    )
    try:
        result = await service.execute(request, settings, example["original_query"])
        assert {r.entity_key for r in result.records} == {uid(i) for i in expected}
        assert result.unknown_location_count == 1
        assert calls == ["/v8/plan"]
    finally:
        await planner.close()
        await geocoder.close()


@pytest.mark.parametrize("index,level", [(3, "district"), (4, "state"), (5, "municipality")])
async def test_rank_category_and_empty_children(source, settings, tmp_path, index, level):
    example = EXAMPLES[index]
    areas = [place("A", level, 10), place("B", level, 11, polygon(10, 54, 12, 55))]
    if index == 5:
        areas = [
            place("Occupied", level, 10, polygon(9.1, 54.1, 9.6, 54.6)),
            place("Empty", level, 11, polygon(9.7, 54.7, 9.9, 54.9)),
        ]
    path = tmp_path / "catalog.json"
    path.write_text(
        Catalogs(
            catalogs=[
                Catalog(
                    schema_version="administrative-catalog-v1",
                    level=level,
                    parent_area_id=None,
                    country_codes=["de"],
                    complete=True,
                    inventory_source="synthetic reviewed inventory",
                    items=areas,
                )
            ]
        ).model_dump_json()
    )
    settings.research_administrative_catalog_path = path
    planner = SimpleNamespace(plan_administrative=AsyncMock(return_value=envelope(example)))
    geocoder = SimpleNamespace(
        search_administrative=AsyncMock(return_value=[place("Nordfriesland", "district", 20)]),
        administrative_boundary=AsyncMock(return_value=place("Nordfriesland", "district", 20)),
    )
    request = Request(
        {
            "type": "http",
            "app": SimpleNamespace(
                state=SimpleNamespace(research_planner=planner, research_geocoder=geocoder)
            ),
        }
    )
    result = await service.execute(request, settings, example["original_query"])
    assert result.kind == "groups" and result.inventory_countries == ["de"]
    if index == 5:
        assert [(g.name, g.event_count) for g in result.groups] == [("Empty", 0)]
    else:
        assert [(g.name, g.event_count) for g in result.groups] == [
            ("A", 2 if index == 4 else 3),
            ("B", 1),
        ]
    assert all(g.level == level for g in result.groups)


async def test_boundary_points_inside_and_outside_are_complements(source, settings):
    boundary = resolved_boundary(place(), "state")
    plan = ResolvedResearchPlan(
        "count", None, (ResolvedSpatialConstraint("inside", boundary),), None, False, "desc", 20
    )
    inside = await execute_resolved(source, settings, plan)
    outside = await execute_resolved(
        source, settings, replace(plan, spatial=(ResolvedSpatialConstraint("outside", boundary),))
    )
    assert inside.count == 3 and outside.count == 3
    # The multi-location event appears in both; an unknown event appears in neither.
    assert inside.unknown_location_count == outside.unknown_location_count == 1


async def test_endpoint_auth_and_rejects_browser_plans(client, headers):
    assert (
        await client.post("/api/v1/research/v8/query", json={"query": "test"})
    ).status_code == 401
    response = await client.post(
        "/api/v1/research/v8/query", headers=headers, json={"query": "test", "plan": EXAMPLES[0]}
    )
    assert response.status_code == 422
