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
    AdministrativeHierarchy,
    AdministrativeIdentity,
    BorderRef,
    ResolvedAdministrativeAreaRef,
    SpatialConstraint,
    UnresolvedAdministrativeAreaRef,
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


def plan(name="Schleswig-Holstein", relation="outside", expected_level=None):
    return InternalResearchPlan(
        intent="count",
        entity_type="event",
        metric="event_count",
        spatial_constraints=(
            SpatialConstraint(relation, UnresolvedAdministrativeAreaRef(name, expected_level)),
        ),
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
    assert type(reference) is ResolvedAdministrativeAreaRef
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
    expected = administrative_reference(stored).level
    internal = plan(name, relation, expected)
    result = await resolver.resolve_plan(Request({"type": "http"}), settings, internal, CONTEXT)
    reference = result.spatial_constraints[0].reference
    assert reference == administrative_reference(stored)
    assert internal.spatial_constraints[0].reference.expected_level == expected
    assert resolver.candidates.await_args.kwargs["expected_level"] == expected
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


def test_multiple_and_predicates_remain_intact_for_shared_boundary_execution():
    from app.research.capabilities import boundary_execution

    internal = replace(
        plan(),
        spatial_constraints=(
            SpatialConstraint("outside", UnresolvedAdministrativeAreaRef("Schleswig-Holstein")),
            SpatialConstraint("inside", UnresolvedAdministrativeAreaRef("Deutschland")),
        ),
    )
    require_supported(internal)
    assert boundary_execution(internal)
    assert [c.relation for c in internal.spatial_constraints] == ["outside", "inside"]


@pytest.mark.parametrize("level", ["district", "state", "municipality", "country", "region"])
def test_administrative_grouping_requires_exact_event_count(level):
    internal = replace(plan(), group_by=level, intent="aggregate")
    assert internal.group_by == level
    require_supported(internal)
    with pytest.raises(APIError) as exc:
        require_supported(replace(internal, metric="occurrence_count"))
    assert exc.value.code == "research_execution_unsupported"


@pytest.mark.parametrize(
    "relation", ["near_border", "across_border", "within_radius", "north_of", "nearest"]
)
def test_unimplemented_spatial_semantics_never_become_outside(relation):
    internal = replace(
        plan(),
        spatial_constraints=(
            SpatialConstraint(relation, BorderRef(UnresolvedAdministrativeAreaRef("Deutschland"))),
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


@pytest.mark.parametrize("relation,expected", [("inside", 1), ("outside", 0)])
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
    # Only event30's occurrence override reaches venue21 on the boundary.
    # Event32 overrides its own venue21 with venue20, whose point is NULL.
    assert await count_selection(c, settings, filters, "event_count", stored) == expected
    for geometry in (
        "NULL",
        "ST_GeomFromText('POINT EMPTY',4326)",
        "ST_SetSRID(ST_MakePoint(999,54),4326)",
    ):
        await c.execute(
            text(f"UPDATE uranus.venue SET point={geometry} WHERE uuid=:id"), {"id": uid(21)}
        )
        assert await count_selection(c, settings, filters, "event_count", stored) == 0


def test_normalizer_carries_expectation_without_asserting_resolved_truth():
    from app.research.normalize import _area_constraints, normalize_v3, normalize_v5, normalize_v6
    from tests.test_research_analytics import CASES, envelope
    from tests.test_research_internal_plan import geographic
    from tests.test_research_plan_execution import planned

    constraints = _area_constraints("Schleswig-Flensburg", "inside", "district")
    assert constraints[0].reference == UnresolvedAdministrativeAreaRef(
        "Schleswig-Flensburg", "district"
    )
    assert not hasattr(constraints[0].reference, "level")
    assert not hasattr(constraints[0].reference, "boundary")
    v3 = planned(area_query="Flensburg")
    v5 = envelope(
        {
            "plan": CASES[0]["plan"]
            | {
                "original_query": "Zeige Veranstaltungen",
                "intent": "list",
                "answer_mode": "records",
                "taxonomy": None,
                "area_query": "Flensburg",
                "area_relation": "inside",
            }
        }
    )
    for internal in (normalize_v3(v3), normalize_v5(v5), normalize_v6(geographic(v5))):
        assert internal.spatial_constraints[0].reference == UnresolvedAdministrativeAreaRef(
            "Flensburg"
        )


async def test_loaded_metadata_rechecks_expected_level_before_execution(settings, monkeypatch):
    from app.services import research_plan_execution as executor

    @asynccontextmanager
    async def transaction():
        yield

    admin = AsyncMock()
    admin.begin = transaction

    @asynccontextmanager
    async def connect(request):
        yield admin

    monkeypatch.setattr(resolver, "connect_admin", connect)
    # Simulate a stale/misclassified candidate. Its loaded boundary is a state,
    # even though the candidate query requested a district.
    monkeypatch.setattr(
        resolver,
        "candidates",
        AsyncMock(
            return_value=[
                ResolutionCandidate(entity_type="area", id=str(uid(99)), label="Schleswig-Holstein")
            ]
        ),
    )
    monkeypatch.setattr(resolver, "resolve_area", AsyncMock(return_value=boundary()))
    source = AsyncMock(side_effect=AssertionError("wrong level must not execute"))
    monkeypatch.setattr(executor, "count_selection", source)
    result = await ResearchPlanExecutor().execute(
        Request({"type": "http"}),
        settings,
        plan(expected_level="district"),
        CONTEXT,
        planner_ms=0,
    )
    assert result.result.kind == "needs_clarification" and result.result.reason == "no_match"
    assert result.resolution == []
    assert not result.execution.structured
    source.assert_not_awaited()


def test_executor_defense_rejects_wrong_resolved_level():
    stored = boundary()
    resolution = resolver.Resolution(
        area=stored,
        spatial_constraints=(SpatialConstraint("outside", administrative_reference(stored)),),
    )
    with pytest.raises(APIError) as exc:
        execution_filters(plan(expected_level="district"), CONTEXT, resolution)
    assert exc.value.code == "research_execution_invalid_plan"


@pytest.mark.parametrize(
    "area_type,number,expected",
    [
        ("municipality", 2, "municipality"),
        ("municipality", 4, "municipality"),
        ("district", 2, "district"),
        ("district", 4, "district"),
    ],
)
def test_persisted_type_precedes_transitional_level_mapping(area_type, number, expected):
    assert administrative_reference(boundary(area_type=area_type, level=number)).level == expected


@pytest.mark.parametrize(
    "expected,ids",
    [(None, [901, 902]), ("district", [902]), ("municipality", [901]), ("state", [])],
)
async def test_level_filter_before_name_ranking_and_limit(
    admin_store, execution_source, settings, expected, ids
):
    from tests.test_semantic_knowledge_index import insert_area

    c = execution_source
    for identity, name, area_type in [(901, "Same", "municipality"), (902, "Same", "district")]:
        await insert_area(c, uid(identity), name, "POLYGON((9 54,10 54,10 55,9 55,9 54))", identity)
        await c.execute(
            text("UPDATE admin.research_area SET area_type=:type WHERE id=:id"),
            {"id": uid(identity), "type": area_type},
        )
    choices = await resolver.candidates(c, "area", "Same", settings, expected_level=expected)
    assert [candidate.id for candidate in choices] == [str(uid(i)) for i in ids]
    result = resolver.Resolution()
    result.select("area_query", "Same", choices)
    assert (result.clarification.reason if result.clarification else None) == (
        "ambiguous" if expected is None else "no_match" if not ids else None
    )
    # Six wrong-level exact matches cannot conceal a valid district match after
    # the candidate cap. Filtering must happen inside the population, before LIMIT.
    for identity in range(903, 909):
        await insert_area(
            c, uid(identity), "Same", "POLYGON((9 54,10 54,10 55,9 55,9 54))", identity
        )
    assert [
        r.id
        for r in await resolver.candidates(c, "area", "Same", settings, expected_level="district")
    ] == [str(uid(902))]
    assert len(await resolver.candidates(c, "area", "Same", settings)) == 5
    await c.execute(
        text("UPDATE admin.research_area SET area_type='district' WHERE id=:id"), {"id": uid(903)}
    )
    matching = await resolver.candidates(c, "area", "Same", settings, expected_level="district")
    assert [r.id for r in matching] == [str(uid(902)), str(uid(903))]
    selection = resolver.Resolution()
    assert selection.select("area_query", "Same", matching) is None
    assert selection.clarification.reason == "ambiguous"


@pytest.mark.parametrize(
    "area_type,osm_level,country,region,expected",
    [
        ("region", 4, "DE", "DE-SH", "state"),
        ("region", 6, "DE", "DE-SH", "district"),
        ("region", 2, "DE", "DE-SH", "country"),
        ("region", 7, "DE", "DE-SH", "region"),
        ("municipality", 6, "DE", "DE-SH", "municipality"),
        ("district", 4, "DE", "DE-SH", "district"),
        ("region", 4, "DK", "DK-83", "region"),
    ],
)
async def test_transitional_sql_and_loaded_metadata_agree(
    admin_store, execution_source, settings, area_type, osm_level, country, region, expected
):
    from app.repositories.research_areas import resolve_area
    from tests.test_semantic_knowledge_index import insert_area

    c = execution_source
    await insert_area(c, uid(901), "Boundary", "POLYGON((9 54,10 54,10 55,9 55,9 54))", 901)
    await c.execute(
        text(
            "UPDATE admin.research_area SET area_type=:type,osm_admin_level=:level,"
            "country_code=:country,region_code=:region WHERE id=:id"
        ),
        {
            "id": uid(901),
            "type": area_type,
            "level": osm_level,
            "country": country,
            "region": region,
        },
    )
    rows = await resolver.candidates(c, "area", "Boundary", settings, expected_level=expected)
    assert [r.id for r in rows] == [str(uid(901))]
    assert administrative_reference(await resolve_area(c, uid(901))).level == expected
