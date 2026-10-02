"""Wire/domain boundary, context separation and shared execution regressions."""

import ast
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import get_type_hints
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from pydantic import SecretStr, TypeAdapter

from app.errors import APIError
from app.repositories.research_resolution import Resolution, resolve_plan
from app.research.context import ResearchExecutionContext
from app.research.geography import (
    NamedPlaceRef,
    SpatialConstraint,
    UnresolvedAdministrativeAreaRef,
    UserLocationRef,
)
from app.research.normalize import normalize, normalize_v3, normalize_v5, normalize_v6
from app.research.outcome import ResearchExecutionOutcome
from app.research.plan import (
    ComparisonTarget,
    InternalResearchPlan,
    NameFilters,
    SemanticSelection,
    TemporalSelection,
)
from app.schemas.research_execution import (
    AggregateItem,
    CountResult,
    ExecutionDiagnostics,
    ExecutionProvenance,
    ResolutionCandidate,
    ResolvedField,
    TaxonomyResult,
)
from app.schemas.research_geography import GeographicPlanResponse
from app.services import research_plan_execution as executor
from tests.research_plan_helpers import plan_context
from tests.test_research_analytics import CASES, envelope
from tests.test_research_geography import envelope as geographic_envelope
from tests.test_research_plan_execution import planned


def geographic(response):
    data = response.model_dump(mode="json")
    data.update(schema_version="research-query-plan-v6", prompt_version="research-planner-v11")
    data["diagnostics"]["planner_prompt_version"] = "research-planner-v11"
    data["plan"].update(place_query=None, location_relation="none")
    return TypeAdapter(GeographicPlanResponse).validate_json(json.dumps(data))


def test_explicit_v5_mapping_and_runtime_fields_excluded():
    data = CASES[0]["plan"] | {
        "original_query": "Zeige passende Einträge",
        "intent": "list",
        "answer_mode": "records",
        "taxonomy": None,
        "temporal": "explicit_range",
        "explicit_from_date": "2026-10-01",
        "explicit_to_date": "2026-10-31",
        "time_of_day": "evening",
        "area_query": "Flensburg",
        "area_relation": "outside",
        "venue_query": "Volksbad",
        "organization_query": "Veranstalter",
        "event_type_queries": ["Konzerte"],
        "category_queries": ["Musik"],
        "genre_queries": ["Jazz"],
        "ordering": "asc",
        "limit": 4,
    }
    response = envelope({"plan": data})
    internal = normalize_v5(response)
    assert internal == InternalResearchPlan(
        intent="list",
        entity_type="event",
        ordering="asc",
        limit=4,
        filters=NameFilters(
            venue_query="Volksbad",
            organization_query="Veranstalter",
            event_type_queries=("Konzerte",),
            category_queries=("Musik",),
            genre_queries=("Jazz",),
        ),
        temporal=TemporalSelection(
            period="explicit_range",
            from_date=date(2026, 10, 1),
            to_date=date(2026, 10, 31),
            time_of_day="evening",
        ),
        spatial_constraints=(
            SpatialConstraint("outside", UnresolvedAdministrativeAreaRef("Flensburg")),
        ),
    )
    names = {f.name for f in fields(internal)}
    assert not names & {
        "reference_date",
        "timezone",
        "location_context",
        "original_query",
        "schema_version",
        "prompt_version",
        "model",
        "diagnostics",
        "answer_mode",
    }
    response.plan.genre_queries.append("Soul")
    assert internal.filters.genre_queries == ("Jazz",)
    with pytest.raises(FrozenInstanceError):
        internal.limit = 20


def test_explicit_v6_place_and_nearby_mapping():
    place = normalize_v6(geographic_envelope())
    assert place.spatial_constraints == (
        SpatialConstraint("inside", NamedPlaceRef("Bachstraße Flensburg")),
    )
    assert place.temporal == TemporalSelection(period="today")
    nearby = normalize_v6(geographic_envelope(7))
    assert nearby.spatial_constraints == (SpatialConstraint("nearby", UserLocationRef()),)
    assert nearby.clarification == "needs_location"


@pytest.mark.parametrize(
    "case", [c for c in CASES if not c["plan"]["unsupported_reason"]], ids=lambda c: c["query"]
)
def test_equivalent_v5_v6_have_identical_domain_plans(case):
    v5 = envelope(case)
    v6 = geographic(v5).model_copy(update={"reference_date": date(2030, 1, 1), "timezone": "UTC"})
    assert normalize_v5(v5) == normalize_v6(v6)
    assert normalize(v5) == normalize(v6)
    assert plan_context(v5)[1] != plan_context(v6)[1]


def test_semantic_and_comparison_fields_survive_normalization():
    semantic = normalize_v3(
        planned(
            intent="search",
            semantic_query="ruhig",
            semantic_focus="Musik",
            requires_semantic_relevance=True,
        )
    )
    assert semantic.semantic == SemanticSelection("ruhig", "Musik")
    comparison = normalize_v3(
        planned(
            intent="compare",
            answer_mode="comparison",
            metric="event_count",
            comparison_targets=[
                {"kind": "venue", "query": "Volksbad"},
                {"kind": "venue", "query": "Kühlhaus"},
            ],
        )
    )
    assert comparison.comparison_targets == (
        ComparisonTarget("venue", "Volksbad"),
        ComparisonTarget("venue", "Kühlhaus"),
    )
    assert comparison.metric == "event_count"


def test_legacy_evening_is_preserved_without_version_checks_downstream():
    legacy = planned(temporal="today", time_of_day="evening")
    v5 = envelope(
        {
            "plan": legacy.plan.model_dump(mode="json")
            | {"taxonomy": None, "spatial_metric": None, "area_relation": "inside"}
        }
    )
    a, ac = plan_context(legacy)
    b, bc = plan_context(v5)
    assert a.temporal.time_from == time(18) and a.temporal.time_of_day == "none"
    assert b.temporal.time_from is None and b.temporal.time_of_day == "evening"
    assert executor.execution_filters(a, ac, Resolution()).time_from == time(18)
    assert executor.execution_filters(b, bc, Resolution()).time_of_day == "evening"


@pytest.mark.parametrize(
    "intent", ["rank", "relation", "trend", "anomaly", "explain", "knowledge", "unrecognized"]
)
async def test_unimplemented_intents_never_fall_back(settings, monkeypatch, intent):
    plan, context = plan_context(planned())
    resolve = AsyncMock(side_effect=AssertionError("must not resolve"))
    monkeypatch.setattr(executor, "resolve_plan", resolve)
    with pytest.raises(APIError) as exc:
        await executor.ResearchPlanExecutor().execute(
            Request({"type": "http"}), settings, replace(plan, intent=intent), context, planner_ms=7
        )
    assert exc.value.code == "research_execution_unsupported"
    resolve.assert_not_awaited()


@pytest.mark.parametrize("slot", ["price", "relation", "trend", "anomaly", "explain", "knowledge"])
async def test_future_constraints_cannot_be_ignored(settings, monkeypatch, slot):
    plan, context = plan_context(planned())
    monkeypatch.setattr(
        executor, "resolve_plan", AsyncMock(side_effect=AssertionError("no fallback"))
    )
    # Simulate an incorrect future adapter. Unsupported slots cannot silently fall through.
    with pytest.raises(APIError) as exc:
        await executor.ResearchPlanExecutor().execute(
            Request({"type": "http"}),
            settings,
            replace(plan, **{slot: object()}),
            context,
            planner_ms=0,
        )
    assert exc.value.code == "research_execution_unsupported"


@pytest.mark.parametrize("intent", ["count", "aggregate", "taxonomy", "spatial_rank"])
async def test_versions_use_identical_primitives_and_provenance(settings, monkeypatch, intent):
    case = next(
        c
        for c in CASES
        if c["plan"]["intent"] == intent
        and not c["plan"]["unsupported_reason"]
        and c["plan"]["area_query"] is None
    )
    response = envelope(case)
    resolution = Resolution(
        fields=[
            ResolvedField(
                field="event_type_queries",
                query="Konzerte",
                target=ResolutionCandidate(entity_type="event_type", id="1", label="Konzert"),
            )
        ]
    )
    resolver = AsyncMock(return_value=resolution)
    monkeypatch.setattr(executor, "resolve_plan", resolver)
    connection = object()

    async def connect(request):
        yield connection

    monkeypatch.setattr(executor, "get_connection", connect)
    names = {
        "count": "count_selection",
        "aggregate": "aggregate_selection",
        "taxonomy": "taxonomy_selection",
        "spatial_rank": "spatial_records",
    }
    returns = {
        "count": 7,
        "aggregate": [AggregateItem(key="x", name="Name", value=7)],
        "taxonomy": TaxonomyResult(taxonomy=case["plan"]["taxonomy"] or "genre", items=[], total=0),
        "spatial_rank": [],
    }
    primitive = AsyncMock(return_value=returns[intent])
    monkeypatch.setattr(executor, names[intent], primitive)
    values = []
    for wire in (response, geographic(response)):
        plan, context = plan_context(wire)
        outcome = await executor.ResearchPlanExecutor().execute(
            Request({"type": "http"}), settings, plan, context, planner_ms=12.5
        )
        assert resolver.await_args.args[2] is plan
        assert resolver.await_args.args[3] is context
        assert outcome.diagnostics.planner_ms == 12.5
        assert outcome.diagnostics.total_ms >= 12.5
        assert outcome.resolution == resolution.fields
        assert outcome.execution.event_type_ids == [1]
        assert outcome.execution.structured
        values.append(outcome)
    assert primitive.await_args_list[0].args == primitive.await_args_list[1].args
    assert primitive.await_args_list[0].kwargs == primitive.await_args_list[1].kwargs
    assert values[0].result == values[1].result
    assert values[0].execution == values[1].execution


@pytest.mark.parametrize("geographic_enabled", [False, True])
async def test_http_boundary_passes_internal_plan_and_separate_context(
    client, settings, headers, monkeypatch, geographic_enabled
):
    from app.api import research

    response = envelope(CASES[0])
    if geographic_enabled:
        response = geographic(response)
        settings.research_geocoder_api_key = SecretStr("g" * 32)
    else:
        settings.research_analytics_enabled = True
    client._transport.app.state.research_planner = AsyncMock(plan=AsyncMock(return_value=response))
    context_input = {"latitude": 54.79, "longitude": 9.43, "source": "browser_geolocation"}
    captured = []

    async def execute(self, request, settings, plan, context, *, planner_ms):
        assert type(plan) is InternalResearchPlan
        assert type(context) is ResearchExecutionContext
        assert context.location_context.latitude == 54.79
        assert context.reference_date == response.reference_date
        assert context.timezone == response.timezone
        assert "54.79" not in repr(plan)
        captured.append(plan)
        return ResearchExecutionOutcome(
            resolution=[],
            result=CountResult(metric="event_count", value=0),
            execution=ExecutionProvenance(structured=True),
            observed_at=datetime.now(UTC),
            diagnostics=ExecutionDiagnostics(planner_ms=planner_ms, total_ms=planner_ms),
        )

    monkeypatch.setattr(research.ResearchPlanExecutor, "execute", execute)
    learn = AsyncMock(side_effect=AssertionError("location context must not be learned"))
    monkeypatch.setattr(research, "record_success", learn)
    result = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={"query": response.plan.original_query, "location_context": context_input},
    )
    assert result.status_code == 200, result.text
    assert result.json()["plan"] == response.model_dump(mode="json")
    assert result.json()["query"] == response.plan.original_query
    assert captured == [normalize(response)]
    learn.assert_not_awaited()


def test_architecture_guard():
    root = Path(__file__).parents[1] / "app"
    protected = [
        root / "services/research_plan_execution.py",
        root / "repositories/research_resolution.py",
        root / "research/plan.py",
        root / "research/context.py",
        root / "research/geography.py",
        root / "repositories/research_administrative.py",
        root / "research/capabilities.py",
    ]
    forbidden = {"research_planner", "research_analytics", "research_geography", "research_v7"}
    for path in protected:
        source = path.read_text()
        assert "osm_admin_level" not in source, path
        assert "REGION_PREFIX" not in source, path
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not forbidden.intersection((node.module or "").split(".")), path
            if isinstance(node, ast.Import):
                assert not any(
                    forbidden.intersection(alias.name.split(".")) for alias in node.names
                ), path
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"schema_version", "prompt_version"}, path
                if path.name == "research_plan_execution.py":
                    assert node.attr != "area_query", path
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "isinstance"
            ):
                assert not any(
                    word in ast.unparse(node)
                    for word in ("Analytical", "Geographic", "PlanResponse")
                ), path
    assert get_type_hints(executor.ResearchPlanExecutor.execute)["plan"] is InternalResearchPlan
    assert (
        get_type_hints(executor.ResearchPlanExecutor.execute)["context"] is ResearchExecutionContext
    )
    assert get_type_hints(resolve_plan)["plan"] is InternalResearchPlan
    assert get_type_hints(resolve_plan)["context"] is ResearchExecutionContext


def test_internal_models_not_exposed_in_openapi(client):
    schema = client._transport.app.openapi()
    assert not {
        "InternalResearchPlan",
        "ResearchExecutionContext",
        "NameFilters",
        "TemporalSelection",
        "UnresolvedAdministrativeAreaRef",
        "ResolvedAdministrativeAreaRef",
        "SpatialConstraint",
        "AdministrativeHierarchy",
        "SemanticSelection",
        "ResearchExecutionOutcome",
    }.intersection(schema["components"]["schemas"])


def test_explicit_unsupported_wire_reason_is_preserved():
    response = planned(unsupported_reason="unsupported_constraint")
    assert normalize(response).unsupported_reason == "unsupported_constraint"


def test_normalization_does_not_repair_or_mutate_wire_values():
    response = envelope(CASES[0])
    before = response.model_dump_json()
    normalize(response)
    assert response.model_dump_json() == before
    inconsistent = response.model_copy(update={"kind": "needs_clarification"})
    with pytest.raises(APIError) as exc:
        normalize(inconsistent)
    assert exc.value.code == "research_execution_invalid_plan"
