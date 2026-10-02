"""Local architecture, resolution and transport gates; PostGIS cases live separately."""

import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Request
from pydantic import SecretStr

from app.clients.research_geocoder import ResearchGeocoderClient
from app.errors import APIError
from app.research.administrative_resolver import resolve_administrative_area
from app.research.capabilities import require_supported
from app.research.context import ResearchExecutionContext
from app.research.geography import (
    ResolvedAdministrativeAreaRef,
    UnresolvedAdministrativeAreaRef,
)
from app.research.normalize import normalize_v8
from app.research.plan import InternalResearchPlan, ResolvedResearchPlan, SemanticSelection
from app.schemas.research_administrative_result import AdministrativeResult
from app.services import research_administrative, research_plan_execution
from app.services.research_planner import MAX_RESPONSE_BYTES, ResearchPlannerClient
from tests.test_administrative_geography import EXAMPLES, envelope, place


def test_single_domain_and_normalizer_architecture():
    root = Path("app")
    definitions = {}
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef) and node.name in {
                "InternalResearchPlan",
                "ResolvedResearchPlan",
                "ResearchPlanExecutor",
            }:
                definitions.setdefault(node.name, []).append(path)
    assert definitions == {
        "InternalResearchPlan": [root / "research/plan.py"],
        "ResolvedResearchPlan": [root / "research/plan.py"],
        "ResearchPlanExecutor": [root / "services/research_plan_execution.py"],
    }
    assert not (root / "research/normalizer.py").exists()
    assert not (root / "research/internal_plan.py").exists()
    for path in [
        root / "repositories/administrative_execution.py",
        root / "research/administrative_resolver.py",
    ]:
        assert "research_v8" not in path.read_text()
        assert "osm_admin_level" not in path.read_text()


def test_wire_pin_is_coordinated_snapshot():
    pin = json.loads(Path("tests/fixtures/administrative_contract_pin.json").read_text())
    for name, digest in pin["mirror_sha256"].items():
        assert hashlib.sha256((Path("app/research/wire") / name).read_bytes()).hexdigest() == digest
    assert (
        hashlib.sha256(
            Path("tests/fixtures/administrative_planner_v8_schema.json").read_bytes()
        ).hexdigest()
        == pin["schema_snapshot_sha256"]
    )
    assert pin["schema_version"] == "research-query-plan-v8"
    assert pin["prompt_version"] == "research-planner-v14"


@pytest.mark.parametrize("index", [0, 1, 3, 4, 5, 6])
async def test_wire_edge_always_uses_shared_executor(settings, monkeypatch, index):
    wire = envelope(EXAMPLES[index])
    result = AdministrativeResult(kind="count", count=0, unknown_location_count=0)
    execute = AsyncMock(return_value=SimpleNamespace(administrative=result))
    monkeypatch.setattr(research_plan_execution.ResearchPlanExecutor, "execute", execute)
    request = Request(
        {
            "type": "http",
            "app": SimpleNamespace(
                state=SimpleNamespace(
                    research_planner=SimpleNamespace(
                        plan_administrative=AsyncMock(return_value=wire)
                    )
                )
            ),
        }
    )
    assert (
        await research_administrative.execute(request, settings, wire.plan.original_query) == result
    )
    args = execute.await_args.args
    assert isinstance(args[2], InternalResearchPlan)
    assert isinstance(args[3], ResearchExecutionContext)
    assert args[2] == normalize_v8(wire.plan)


async def test_shared_resolver_then_executor_preserves_all_constraints(settings, monkeypatch):
    wire = envelope(EXAMPLES[6])
    plan = normalize_v8(wire.plan)
    context = ResearchExecutionContext(wire.reference_date, wire.timezone, wire.plan.original_query)
    places = [place(), place("Deutschland", "country", 2)]
    provider = SimpleNamespace(
        search_administrative=AsyncMock(side_effect=[[p] for p in places]),
        administrative_boundary=AsyncMock(side_effect=places),
    )
    request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(research_geocoder=provider))}
    )
    connection = object()

    # get_connection is an async generator in the real service.
    async def get_connection(_):
        yield connection

    monkeypatch.setattr(research_plan_execution, "get_connection", get_connection)
    primitive = AsyncMock(
        return_value=AdministrativeResult(kind="count", count=0, unknown_location_count=3)
    )
    monkeypatch.setattr(research_plan_execution, "administrative_selection", primitive)
    outcome = await research_plan_execution.ResearchPlanExecutor().execute(
        request, settings, plan, context, planner_ms=2
    )
    resolved = primitive.await_args.args[2]
    assert isinstance(resolved, ResolvedResearchPlan)
    assert [(c.relation, c.reference.level) for c in resolved.administrative_constraints] == [
        ("outside", "state"),
        ("inside", "country"),
    ]
    assert all(
        isinstance(c.reference, ResolvedAdministrativeAreaRef)
        for c in resolved.administrative_constraints
    )
    assert not hasattr(resolved, "area_query")
    assert outcome.result.value == 0
    assert outcome.administrative.unknown_location_count == 3
    assert outcome.execution.structured


@pytest.mark.parametrize("level", ["state", "district", "municipality"])
async def test_lookup_authoritative_level_rechecked(level):
    selected = place("Same name", level)
    changed = place("Same name", "country")
    provider = SimpleNamespace(
        search_administrative=AsyncMock(return_value=[selected]),
        administrative_boundary=AsyncMock(return_value=changed),
    )
    with pytest.raises(APIError) as failure:
        await resolve_administrative_area(
            provider, UnresolvedAdministrativeAreaRef("Same name", level)
        )
    assert failure.value.code == "research_area_level_mismatch"


async def test_inventory_required_before_any_source_execution(settings, monkeypatch):
    wire = envelope(EXAMPLES[3])
    plan = normalize_v8(wire.plan)
    settings.research_administrative_catalog_path = None
    connection = AsyncMock(side_effect=AssertionError("source must not be queried"))
    monkeypatch.setattr(research_plan_execution, "get_connection", connection)
    with pytest.raises(APIError) as failure:
        await research_plan_execution.ResearchPlanExecutor().execute(
            Request({"type": "http"}),
            settings,
            plan,
            ResearchExecutionContext(wire.reference_date, wire.timezone, wire.plan.original_query),
            planner_ms=0,
        )
    assert failure.value.code == "research_inventory_unavailable"
    connection.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("semantic", SemanticSelection("Kinder")),
        ("metric", "occurrence_count"),
        ("intent", "knowledge"),
    ],
)
def test_unsupported_constraints_never_downgrade(field, value):
    plan = normalize_v8(envelope(EXAMPLES[3]).plan)
    with pytest.raises(APIError):
        require_supported(replace(plan, **{field: value}))


@pytest.mark.parametrize(
    "fault",
    [
        "redirect",
        "oversize",
        "invalid_json",
        "wrong_query",
        "wrong_timezone",
        "wrong_prompt",
        "wrong_model",
        "wrong_intent",
        "extra",
        "not_deployed",
    ],
)
async def test_v8_transport_fail_closed(settings, fault):
    settings.research_planner_url = "http://127.0.0.1:8090"
    settings.research_planner_api_key = SecretStr("test-key-with-at-least-thirty-two-characters")
    payload = envelope(EXAMPLES[0]).model_dump(mode="json")
    calls = []

    def respond(request):
        calls.append(request.url.path)
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers
        if fault == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8090/plan"})
        if fault == "not_deployed":
            return httpx.Response(404)
        if fault in {"oversize", "invalid_json"}:
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=b"x" * (MAX_RESPONSE_BYTES + 1 if fault == "oversize" else 3),
            )
        if fault == "wrong_query":
            payload["plan"]["original_query"] = "different question"
        elif fault == "wrong_timezone":
            payload["timezone"] = "UTC"
        elif fault == "wrong_prompt":
            payload["prompt_version"] = "research-planner-v13"
        elif fault == "wrong_model":
            payload["diagnostics"]["planner_model"] = "other"
        elif fault == "wrong_intent":
            payload["diagnostics"]["planner_intent"] = "count"
        elif fault == "extra":
            payload["plan"]["sql"] = "SELECT 1"
        return httpx.Response(200, json=payload)

    client = ResearchPlannerClient(settings, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as failure:
            await client.plan_administrative(EXAMPLES[0]["original_query"])
        assert failure.value.code == "research_planner_invalid_response"
        assert calls == ["/v8/plan"]
    finally:
        await client.close()


@pytest.mark.parametrize("method,budget", [("search", 256 * 1024), ("boundary", 8 * 1024 * 1024)])
async def test_geocoder_separate_response_budgets(settings, method, budget):
    settings.research_geocoder_api_key = SecretStr("test-key-with-at-least-thirty-two-characters")
    response = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"content-type": "application/json"}, content=b" " * (budget + 1)
        )
    )
    client = ResearchGeocoderClient(settings, transport=response)
    try:
        with pytest.raises(APIError) as failure:
            if method == "search":
                await client.search("Flensburg")
            else:
                await client.administrative_boundary("R", 1)
        assert failure.value.code == "geocoder_unavailable"
    finally:
        await client.close()


async def test_grouping_cost_guard_precedes_join(settings):
    from app.repositories.administrative_execution import administrative_selection
    from app.research.administrative_resolver import resolved_boundary
    from app.schemas.research_execution import ExecutionFilters

    boundary = resolved_boundary(place(), "state")
    plan = ResolvedResearchPlan(
        filters=ExecutionFilters(entity_type="event"),
        intent="rank",
        grouping="state",
        inventory=(boundary,),
    )
    connection = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one=lambda: True),
                SimpleNamespace(scalar_one=lambda: 2_000_001),
            ]
        )
    )
    with pytest.raises(APIError) as failure:
        await administrative_selection(connection, settings, plan)
    assert failure.value.code == "research_execution_too_broad"
    assert connection.execute.await_count == 2


async def test_complete_inventory_cannot_claim_another_country(tmp_path):
    from app.research.administrative_catalog import Catalog, Catalogs, load_inventory
    from app.research.administrative_resolver import resolved_boundary
    from app.research.geography import ResolvedAdministrativeConstraint

    catalog = Catalog(
        schema_version="administrative-catalog-v1",
        level="state",
        parent_area_id=None,
        country_codes=["de"],
        complete=True,
        inventory_source="synthetic reviewed DE states 2026-10-02",
        items=[place()],
    )
    path = tmp_path / "catalog.json"
    path.write_text(Catalogs(catalogs=[catalog]).model_dump_json())
    reference = resolved_boundary(
        place("France", "country").model_copy(update={"country_code": "fr"}), "country"
    )
    with pytest.raises(APIError) as failure:
        await load_inventory(
            path, "state", (ResolvedAdministrativeConstraint("inside", reference),)
        )
    assert failure.value.code == "research_inventory_unavailable"


@pytest.mark.parametrize("chunked", [False, True])
async def test_new_endpoint_has_same_streaming_body_limit(client, headers, chunked):
    payload = b'{"query":"' + b"x" * (32 * 1024) + b'"}'

    async def stream():
        for offset in range(0, len(payload), 1024):
            yield payload[offset : offset + 1024]

    response = await client.post(
        "/api/v1/research/v8/query",
        headers={**headers, "content-type": "application/json"},
        content=stream() if chunked else payload,
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
