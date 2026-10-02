"""Internal administrative identity, hierarchy and fail-closed spatial execution."""

from contextlib import asynccontextmanager
from dataclasses import fields, replace
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from sqlalchemy import text

from app.errors import APIError
from app.repositories import research_resolution as resolver
from app.repositories.research_administrative import administrative_reference
from app.repositories.research_areas import ResolvedResearchArea
from app.repositories.research_execution import count_selection
from app.research.capabilities import require_supported
from app.research.context import ResearchExecutionContext
from app.research.geography import (
    AdministrativeAreaRef,
    AdministrativeHierarchy,
    AdministrativeIdentity,
    BorderRef,
    SpatialConstraint,
)
from app.research.plan import InternalResearchPlan
from app.schemas.research_areas import ResearchArea
from app.schemas.research_execution import ResolutionCandidate
from app.services.research_plan_execution import ResearchPlanExecutor, execution_filters
from tests.conftest import uid
from tests.test_research_plan_execution import execution_source as execution_source_fixture

execution_source = execution_source_fixture
CONTEXT = ResearchExecutionContext(date(2026, 10, 2), "Europe/Berlin", "Geographic query")


def boundary(name="Schleswig-Holstein", area_type="region", level=4, key=None, **changes):
    return ResolvedResearchArea(
        ResearchArea(
            id=uid(99),
            area_type=area_type,
            country_code="DE",
            region_code="DE-SH",
            name=name,
            display_name=name,
            osm_type="R",
            osm_id="99",
            osm_admin_level=level,
            centroid={"latitude": 54.5, "longitude": 9.5},
            bbox=(9.4, 54, 10, 55),
            source="osm",
            retrieved_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ).model_copy(update=changes),
        b"fixture-only-boundary",
        municipality_key=key,
    )


def plan(name="Schleswig-Holstein", relation="outside"):
    return InternalResearchPlan(
        intent="count",
        entity_type="event",
        metric="event_count",
        spatial_constraints=(SpatialConstraint(relation, AdministrativeAreaRef(name)),),
    )


@pytest.mark.parametrize(
    "name,area_type,osm_level,key,expected,code,system",
    [
        ("Schleswig-Holstein", "region", 4, None, "state", "01", "DE-state"),
        ("Schleswig-Flensburg", "district", 6, None, "district", None, None),
        ("Schleswig-Flensburg", "region", 6, None, "district", None, None),
        ("Flensburg", "municipality", 6, "01001000", "municipality", "01001000", "DE-AGS"),
        ("Gemeinde", "municipality", 8, None, "municipality", None, None),
        ("Deutschland", "region", 2, None, "country", "DE", "ISO-3166-1"),
        ("Sonstige Region", "region", 7, None, "region", None, None),
    ],
)
def test_metadata_classifies_identity(name, area_type, osm_level, key, expected, code, system):
    stored = boundary(name, area_type, osm_level, key)
    reference = administrative_reference(stored)
    assert reference.name == name
    assert reference.level == expected
    assert reference.official_code == code and reference.code_system == system
    assert reference.resolved_id == stored.area.id == reference.boundary.area_id
    assert reference.country_code == "DE"
    # The label never determines the administrative level or official identity.
    renamed = administrative_reference(
        replace(stored, area=stored.area.model_copy(update={"name": "X"}))
    )
    assert replace(renamed, name=name) == reference


def test_city_state_remains_municipality_and_danish_levels_are_not_guessed():
    hamburg = administrative_reference(
        boundary("Hamburg", "municipality", 4, "02000000", region_code="DE-HH")
    )
    assert hamburg.level == "municipality" and hamburg.official_code == "02000000"
    danish = administrative_reference(
        boundary("Sønderborg", "municipality", 7, country_code="DK", region_code="DK-83")
    )
    assert danish.level == "municipality" and danish.official_code is None
    assert danish.parent is None
    region = administrative_reference(
        boundary("Syddanmark", "region", 4, country_code="DK", region_code="DK-83")
    )
    assert region.level == "region"  # No unverified German level equivalence.


def test_hierarchy_distinguishes_direct_parents_from_known_ancestors():
    state = administrative_reference(boundary())
    district = administrative_reference(boundary("Schleswig-Flensburg", "district", 6))
    municipality = administrative_reference(boundary("Flensburg", "municipality", 6, "01001000"))
    country_id = AdministrativeIdentity("country", "DE", "DE", "ISO-3166-1")
    state_id = AdministrativeIdentity("state", "DE", "01", "DE-state")
    hierarchy = AdministrativeHierarchy((state, district, municipality))
    assert state.parent == country_id
    assert district.parent == state_id
    assert municipality.parent is None  # No invented Schleswig-Flensburg membership.
    assert hierarchy.children(state_id) == (district,)
    assert hierarchy.descendants(state_id) == (district, municipality)
    assert hierarchy.children(country_id) == (state,)
    # A future authoritative district key can establish the final hierarchy edge.
    district_id = AdministrativeIdentity("district", "DE", "fixture-code", "DE-district")
    child = replace(municipality, parent=district_id, ancestors=(district_id, state_id, country_id))
    assert AdministrativeHierarchy((child,)).children(district_id) == (child,)


@pytest.mark.parametrize(
    "name,area_type,level,relation",
    [
        ("Schleswig-Holstein", "region", 4, "outside"),
        ("Schleswig-Flensburg", "district", 6, "inside"),
        ("Flensburg", "municipality", 6, "inside"),
    ],
)
async def test_resolver_replaces_name_with_typed_boundary(
    settings, monkeypatch, name, area_type, level, relation
):
    stored = boundary(name, area_type, level)
    admin = AsyncMock()
    admin.begin = lambda: transaction()

    @asynccontextmanager
    async def transaction():
        yield

    @asynccontextmanager
    async def connect(request):
        yield admin

    monkeypatch.setattr(resolver, "connect_admin", connect)
    monkeypatch.setattr(
        resolver,
        "candidates",
        AsyncMock(
            return_value=[
                ResolutionCandidate(entity_type="area", id=str(stored.area.id), label=name)
            ]
        ),
    )
    monkeypatch.setattr(resolver, "resolve_area", AsyncMock(return_value=stored))
    internal = plan(name, relation)
    result = await resolver.resolve_plan(Request({"type": "http"}), settings, internal, CONTEXT)
    reference = result.spatial_constraints[0].reference
    assert reference == administrative_reference(stored)
    assert reference in result.administrative_hierarchy.areas
    assert result.spatial_constraints[0].relation == relation
    filters = execution_filters(internal, CONTEXT, result)
    assert filters.area_id == stored.area.id and filters.area_relation == relation
    assert "area_query" not in {f.name for f in fields(internal)}
    assert name not in filters.model_dump_json()


@pytest.mark.parametrize("count,reason", [(0, "no_match"), (2, "ambiguous")])
async def test_area_ambiguity_never_picks_first(settings, monkeypatch, count, reason):
    @asynccontextmanager
    async def transaction():
        yield

    admin = AsyncMock()
    admin.begin = transaction

    @asynccontextmanager
    async def connect(request):
        yield admin

    monkeypatch.setattr(resolver, "connect_admin", connect)
    monkeypatch.setattr(
        resolver,
        "candidates",
        AsyncMock(
            return_value=[
                ResolutionCandidate(entity_type="area", id=str(uid(i + 1)), label="Schleswig")
                for i in range(count)
            ]
        ),
    )
    load = AsyncMock(side_effect=AssertionError("ambiguous identity must not load geometry"))
    monkeypatch.setattr(resolver, "resolve_area", load)
    result = await resolver.resolve_plan(
        Request({"type": "http"}), settings, plan("Schleswig"), CONTEXT
    )
    assert result.clarification.reason == reason
    assert result.area is None and result.spatial_constraints == ()
    load.assert_not_awaited()


async def test_multiple_and_predicates_remain_intact_and_fail_before_resolution(
    settings, monkeypatch
):
    from app.services import research_plan_execution as executor

    internal = replace(
        plan(),
        spatial_constraints=(
            SpatialConstraint("outside", AdministrativeAreaRef("Schleswig-Holstein")),
            SpatialConstraint("inside", AdministrativeAreaRef("Deutschland")),
        ),
    )
    resolve = AsyncMock(side_effect=AssertionError("no SQL or dropped predicates"))
    monkeypatch.setattr(executor, "resolve_plan", resolve)
    with pytest.raises(APIError) as exc:
        await ResearchPlanExecutor().execute(
            Request({"type": "http"}), settings, internal, CONTEXT, planner_ms=0
        )
    assert exc.value.code == "research_execution_unsupported"
    assert [c.relation for c in internal.spatial_constraints] == ["outside", "inside"]
    resolve.assert_not_awaited()


@pytest.mark.parametrize("level", ["district", "state", "municipality", "country", "region"])
def test_administrative_grouping_is_distinct_but_not_silently_executable(level):
    internal = replace(plan(), group_by=level, intent="aggregate")
    assert internal.group_by == level
    with pytest.raises(APIError) as exc:
        require_supported(internal)
    assert exc.value.code == "research_execution_unsupported"


@pytest.mark.parametrize(
    "relation", ["near_border", "across_border", "within_radius", "north_of", "nearest"]
)
def test_unimplemented_spatial_semantics_never_become_outside(relation):
    internal = replace(
        plan(),
        spatial_constraints=(
            SpatialConstraint(relation, BorderRef(AdministrativeAreaRef("Deutschland"))),
        ),
    )
    with pytest.raises(APIError) as exc:
        require_supported(internal)
    assert exc.value.code == "research_execution_unsupported"


@pytest.mark.parametrize("failure", ["missing", "wrong_id", "missing_boundary", "wrong_relation"])
def test_unresolved_area_cannot_become_unfiltered_sql(failure):
    stored = boundary()
    reference = administrative_reference(stored)
    if failure == "wrong_id":
        reference = replace(reference, resolved_id=uid(100))
    if failure == "missing_boundary":
        reference = replace(reference, boundary=None)
    resolution = (
        resolver.Resolution(
            area=stored,
            spatial_constraints=(
                SpatialConstraint(
                    "inside" if failure == "wrong_relation" else "outside", reference
                ),
            ),
        )
        if failure != "missing"
        else resolver.Resolution()
    )
    with pytest.raises(APIError) as exc:
        execution_filters(plan(), CONTEXT, resolution)
    assert exc.value.code == "research_execution_invalid_plan"


@pytest.mark.parametrize("relation,expected", [("inside", 2), ("outside", 0)])
async def test_typed_boundary_uses_existing_postgis_membership(
    settings, execution_source, relation, expected
):
    # Real PostGIS fixture in CI, never a substitute SQLite or mocked SQL result.
    c = execution_source
    ewkb = (
        await c.execute(text("SELECT ST_AsEWKB(ST_MakeEnvelope(9.4,54,10,55,4326))"))
    ).scalar_one()
    stored = replace(boundary(), ewkb=bytes(ewkb))
    resolved = resolver.Resolution(
        area=stored,
        spatial_constraints=(SpatialConstraint(relation, administrative_reference(stored)),),
    )
    filters = execution_filters(plan(relation=relation), CONTEXT, resolved)
    assert await count_selection(c, settings, filters, "event_count", stored) == expected
    for geometry in ("NULL", "ST_GeomFromText('POINT EMPTY',4326)"):
        await c.execute(
            text(f"UPDATE uranus.venue SET point={geometry} WHERE uuid=:id"), {"id": uid(20)}
        )
        assert await count_selection(c, settings, filters, "event_count", stored) == 0
