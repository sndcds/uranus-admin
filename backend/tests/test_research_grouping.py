"""Grouping has no wire-version executor and never projects away a requested axis."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.repositories.research_grouping import grouped_selection, grouped_sql
from app.research.capabilities import require_supported
from app.research.normalize_grouping import normalize_v7_grouping, normalize_v9
from app.research.plan import InternalResearchPlan, ResolvedResearchPlan
from app.research.wire.research_v7_schema import ResearchQueryPlanV7
from app.research.wire.research_v9_schema import ResearchQueryPlanV9
from app.schemas.research_execution import ExecutionFilters
from tests.test_research_plan_execution import execution_source as execution_source_fixture
from tests.test_research_taxonomy import taxonomy_source as taxonomy_source_fixture

execution_source = execution_source_fixture
taxonomy_source = taxonomy_source_fixture


def wire():
    return ResearchQueryPlanV9.model_validate_json(
        Path("tests/fixtures/research_grouping_v9.json").read_text()
    )


@pytest.mark.parametrize(
    "dims",
    [
        ("event_type", "month"),
        ("genre", "month"),
        ("category", "municipality"),
        ("month", "event_type"),
        ("event_type", "genre", "month"),
    ],
)
def test_normalization_and_sql_order(settings, dims):
    data = wire().model_dump(mode="json")
    data["group_by"] = list(dims)
    plan = normalize_v9(ResearchQueryPlanV9.model_validate_json(json.dumps(data)))
    require_supported(plan)
    assert plan.groupings == dims and plan.group_by == "none"
    resolved = ResolvedResearchPlan(filters=ExecutionFilters(), intent="aggregate")
    sql, params = grouped_sql(plan, resolved, settings, None)
    assert "count(DISTINCT selected.date_key)" in sql
    assert "count(DISTINCT selected.entity_key)" not in sql
    assert "LIMIT :cell_limit" in sql and params["cell_limit"] == 20
    assert "value DESC" in sql
    assert sql.index("key_0") < sql.index("key_1")
    assert "matched_events" in sql  # shared eligible population
    if "month" in dims:
        assert "extract(month FROM selected.start_date)" in sql
    if "municipality" in dims:
        assert "ST_CoveredBy(selected.point,municipality.boundary)" in sql


@pytest.mark.parametrize("dims", [("month", "month"), ("sql",), ("month",) * 4])
def test_bad_dimensions_rejected(dims):
    with pytest.raises(ValueError):
        InternalResearchPlan(intent="aggregate", entity_type="event", groupings=dims)
    data = wire().model_dump(mode="json")
    data["group_by"] = list(dims)
    with pytest.raises(ValidationError):
        ResearchQueryPlanV9.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("dimension", ["venue", "event_type"])
def test_old_scalar_normalizes_without_loss(dimension):
    data = wire().model_dump(mode="json")
    data["group_by"] = dimension
    old = ResearchQueryPlanV7.model_validate_json(json.dumps(data))
    assert normalize_v7_grouping(old).groupings == (dimension,)
    assert InternalResearchPlan(
        intent="aggregate", entity_type="event", group_by="genre"
    ).groupings == ("genre",)
    assert InternalResearchPlan(intent="list", entity_type="event").groupings == ()


async def test_rows_keep_each_axis(settings):
    plan = normalize_v9(wire())
    connection = AsyncMock()
    rows = MagicMock()
    rows.mappings.return_value = [
        dict(key_0="2", name_0="Konzert", key_1="09", name_1="09", value=7)
    ]
    connection.execute.return_value = rows
    result = await grouped_selection(
        connection,
        settings,
        plan,
        ResolvedResearchPlan(filters=ExecutionFilters(), intent="aggregate"),
        None,
    )
    assert result.dimensions == ["event_type", "month"]
    assert [c.key for c in result.items[0].coordinates] == ["2", "09"]
    assert result.items[0].value == 7
    assert connection.execute.await_count == 1


async def test_occurrences_not_events_and_join_multiplicity(settings, execution_source):
    # Disposable PostgreSQL CI fixture only. Duplicate categories must not multiply dates.
    await execution_source.execute(text("UPDATE uranus.event SET categories=ARRAY[1,1]"))
    plan = InternalResearchPlan(
        intent="aggregate",
        entity_type="event",
        metric="occurrence_count",
        groupings=("category", "month"),
        ordering="desc",
        limit=20,
    )
    resolved = ResolvedResearchPlan(filters=ExecutionFilters(), intent="aggregate")
    result = await grouped_selection(execution_source, settings, plan, resolved, None)
    assert len(result.items) == 1
    assert result.items[0].value == 7
    assert result.items[0].coordinates[1].key == "09"
    events = await grouped_selection(
        execution_source, settings, replace(plan, metric="event_count"), resolved, None
    )
    assert events.items[0].value == 2


async def test_category_municipality_shared_boundaries(settings, execution_source):
    from app.research.geography import BoundaryReference, ResolvedAdministrativeAreaRef

    geometry = json.dumps(
        {
            "type": "Polygon",
            "coordinates": [[[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]]],
        }
    )
    municipality = ResolvedAdministrativeAreaRef(
        name="Fixture municipality",
        level="municipality",
        country_code="DE",
        official_code="01001000",
        code_system="DE-AGS",
        resolved_id="fixture-area",
        boundary=BoundaryReference("fixture-area", geometry),
    )
    await execution_source.execute(text("UPDATE uranus.event SET categories=ARRAY[1,1]"))
    plan = InternalResearchPlan(
        intent="aggregate",
        entity_type="event",
        metric="occurrence_count",
        groupings=("category", "municipality"),
        ordering="desc",
        limit=20,
    )
    resolved = ResolvedResearchPlan(
        filters=ExecutionFilters(),
        intent="aggregate",
        grouping="municipality",
        inventory=(municipality,),
    )
    result = await grouped_selection(execution_source, settings, plan, resolved, None)
    assert result.items and result.items[0].coordinates[1].key == "fixture-area"
    assert all(item.value > 0 for item in result.items)


@pytest.mark.parametrize("dimension", ["event_type", "genre"])
async def test_taxonomy_month_population(settings, taxonomy_source, dimension):
    from tests.conftest import uid

    if dimension == "event_type":
        # Same type through a second genre link: still one occurrence per type cell.
        await taxonomy_source.execute(
            text(
                "INSERT INTO uranus.event_type_link(event_uuid,type_id,genre_id) VALUES (:id,1,0)"
            ),
            {"id": uid(30)},
        )
    plan = InternalResearchPlan(
        intent="aggregate",
        entity_type="event",
        metric="occurrence_count",
        groupings=(dimension, "month"),
        ordering="desc",
        limit=20,
    )
    resolved = ResolvedResearchPlan(filters=ExecutionFilters(), intent="aggregate")
    result = await grouped_selection(taxonomy_source, settings, plan, resolved, None)
    assert len(result.items) == 2 and sum(item.value for item in result.items) == 7
    assert all(item.coordinates[1].key == "09" for item in result.items)
    reversed_result = await grouped_selection(
        taxonomy_source, settings, replace(plan, groupings=("month", dimension)), resolved, None
    )
    assert all(item.coordinates[0].key == "09" for item in reversed_result.items)
    limited = await grouped_selection(
        taxonomy_source, settings, replace(plan, limit=1), resolved, None
    )
    assert len(limited.items) == 1 and limited.items[0].value == result.items[0].value


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("dimension", ["event_type", "genre"])
def test_axis_aliases_preserve_authoritative_taxonomy_subqueries(axis, dimension):
    from app.repositories.research_execution import grouping_sql
    from app.repositories.research_resolution import EVENT_TYPES_SQL, GENRES_SQL

    key, name, join = grouping_sql(dimension, axis=axis)
    source = GENRES_SQL if dimension == "genre" else EVENT_TYPES_SQL
    assert f"JOIN ({source}) taxonomy_{axis}" in join
    assert f"event_type_link l_{axis} ON l_{axis}.event_uuid=selected.entity_key" in join
    assert key == f"taxonomy_{axis}.id" and name == f"taxonomy_{axis}.label"
