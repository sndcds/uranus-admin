"""Lossless parity with executable legacy semantics; no source or wire repair."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import TypeAdapter

from app.research.capabilities import require_supported
from app.research.normalize import normalize
from app.research.normalize_v9 import normalize_v9
from app.research.wire.research_v9_schema import ResearchQueryPlanV9
from app.schemas.research_analytics import AnalyticalPlanResponse
from app.schemas.research_geography import GeographicPlanResponse
from tests.test_research_grouping import wire
from tests.test_research_grouping_flow import envelope
from tests.test_research_grouping_flow import flow as flow_fixture
from tests.test_research_plan_execution import planned

flow = flow_fixture


def metric(operation, field=None):
    return {**wire().metric.model_dump(mode="json"), "operation": operation, "field": field}


def temporal(period="today", **changes):
    return (
        dict(
            field="start_date",
            period=period,
            from_date=None,
            to_date=None,
            time_of_day="none",
            before_time=None,
            after_time=None,
            weekday=None,
            calendar_relation="none",
            calendar_area_query=None,
            overlap=False,
            multi_day=False,
            lookback=None,
            lookback_unit=None,
        )
        | changes
    )


def spatial(relation="inside", area_query="Flensburg", **changes):
    return (
        dict(
            relation=relation,
            area_query=area_query,
            place_query=None,
            radius_m=None,
            reference="named",
        )
        | changes
    )


def v9(**changes):
    data = (
        wire().model_dump(mode="json")
        | dict(
            original_query="Research fixture",
            intent="list",
            metric=None,
            group_by=[],
            ordering=None,
            limit=None,
        )
        | changes
    )
    return ResearchQueryPlanV9.model_validate_json(json.dumps(data))


def legacy(**changes):
    data = planned(original_query="Research fixture").model_dump(mode="json")
    plan = (
        data["plan"]
        | dict(
            taxonomy=None,
            spatial_metric=None,
            area_relation="inside",
            temporal="none",
            area_query=None,
            venue_query=None,
            organization_query=None,
            time_of_day="none",
            semantic_query=None,
            semantic_focus=None,
            requires_semantic_relevance=False,
            event_type_queries=[],
            category_queries=[],
            genre_queries=[],
            ordering=None,
            limit=None,
        )
        | changes
    )
    geo = "place_query" in changes or "location_relation" in changes
    if geo:
        plan.setdefault("place_query", None)
        plan.setdefault("location_relation", "none")
    data.update(
        kind="plan" if plan["clarification"] == "none" else "needs_clarification",
        plan=plan,
        schema_version="research-query-plan-v6" if geo else "research-query-plan-v5",
        prompt_version="research-planner-v11" if geo else "research-planner-v10",
    )
    data["diagnostics"].update(
        planner_intent=plan["intent"], planner_prompt_version=data["prompt_version"]
    )
    return TypeAdapter(GeographicPlanResponse if geo else AnalyticalPlanResponse).validate_json(
        json.dumps(data)
    )


# Only semantic fixtures for implemented Admin operations, not a natural-language golden corpus.
PARITY = []
for entity in ("event", "venue", "organization"):
    PARITY.append((f"list-{entity}", {"entity_type": entity}, {"entity_type": entity}))
for operation, old_entity, new_entity in (
    ("event_count", "event", "event"),
    ("occurrence_count", "event", "occurrence"),
    ("venue_count", "venue", "venue"),
    ("organization_count", "organization", "organization"),
):
    PARITY.append(
        (
            operation,
            dict(intent="count", entity_type=old_entity, metric=operation, answer_mode="count"),
            dict(intent="count", entity_type=new_entity, metric=metric(operation)),
        )
    )
for group in ("venue", "organization", "genre", "event_type", "category", "event"):
    operation = "occurrence_count" if group == "event" else "event_count"
    PARITY.append(
        (
            f"aggregate-{group}",
            dict(
                intent="aggregate",
                group_by=group,
                metric=operation,
                answer_mode="aggregate",
                ordering="desc",
                limit=10,
            ),
            dict(
                intent="aggregate",
                group_by=[group],
                metric=metric(operation),
                ordering="desc",
                limit=10,
            ),
        )
    )
for taxonomy in ("genre", "event_type", "category"):
    PARITY.append(
        (
            f"taxonomy-{taxonomy}",
            dict(intent="taxonomy", taxonomy=taxonomy, answer_mode="taxonomy"),
            dict(intent="taxonomy", taxonomy=taxonomy),
        )
    )
PARITY.append(
    (
        "semantic",
        dict(
            intent="search",
            semantic_query="Musik für Kinder",
            semantic_focus="Familien",
            requires_semantic_relevance=True,
        ),
        dict(intent="search", semantic={"query": "Musik für Kinder", "focus": "Familien"}),
    )
)
for kind in ("venue", "organization", "area"):
    targets = [dict(kind=kind, query=n) for n in ("One", "Two")]
    new_targets = [
        dict(kind="region" if kind == "area" else kind, query=t["query"]) for t in targets
    ]
    PARITY.append(
        (
            f"compare-{kind}",
            dict(
                intent="compare",
                metric="event_count",
                comparison_targets=targets,
                answer_mode="comparison",
            ),
            dict(
                intent="compare",
                metric=metric("event_count"),
                entity_type="region" if kind == "area" else kind,
                comparison_targets=new_targets,
            ),
        )
    )
for direction in ("asc", "desc"):
    PARITY.append(
        (
            f"chronological-{direction}",
            dict(ordering=direction, limit=10),
            dict(
                intent="rank",
                metric=metric("value", "start_date"),
                group_by=["event"],
                ordering=direction,
                limit=10,
            ),
        )
    )
    for entity in ("event", "venue"):
        for coordinate in ("latitude", "longitude"):
            PARITY.append(
                (
                    f"spatial-{entity}-{coordinate}-{direction}",
                    dict(
                        intent="spatial_rank",
                        entity_type=entity,
                        spatial_metric=coordinate,
                        ordering=direction,
                        limit=1,
                    ),
                    dict(
                        intent="rank",
                        entity_type=entity,
                        group_by=[entity],
                        metric=metric("value", coordinate),
                        ordering=direction,
                        limit=1,
                    ),
                )
            )
for relation in ("inside", "outside"):
    PARITY.append(
        (
            f"area-{relation}",
            dict(area_query="Flensburg", area_relation=relation),
            dict(spatial=spatial(relation)),
        )
    )
PARITY += [
    (
        "named-place",
        dict(place_query="Bachstraße Flensburg"),
        dict(spatial=spatial("at", None, place_query="Bachstraße Flensburg")),
    ),
    (
        "nearby",
        dict(location_relation="nearby", clarification="needs_location"),
        dict(
            spatial=spatial("nearby", None, reference="user_location"),
            clarification="needs_location",
        ),
    ),
]
for field, slot in (
    ("venue", "venue_query"),
    ("organization", "organization_query"),
    ("event_type", "event_type_queries"),
    ("category", "category_queries"),
    ("genre", "genre_queries"),
):
    PARITY.append(
        (
            f"filter-{field}",
            {slot: ["Name"] if slot.endswith("queries") else "Name"},
            dict(filters=[dict(field=field, operator="eq", value="Name")]),
        )
    )
for period in (
    "today",
    "tomorrow",
    "this_weekend",
    "next_week",
    "this_month",
    "this_year",
    "past",
    "future",
):
    PARITY.append((f"period-{period}", dict(temporal=period), dict(temporal=temporal(period))))
for daypart in ("morning", "afternoon", "evening", "night"):
    PARITY.append(
        (
            f"daypart-{daypart}",
            dict(temporal="today", time_of_day=daypart),
            dict(temporal=temporal(time_of_day=daypart)),
        )
    )
PARITY.append(
    (
        "dates",
        dict(
            temporal="explicit_range",
            explicit_from_date="2026-10-01",
            explicit_to_date="2026-10-31",
        ),
        dict(temporal=temporal("explicit_range", from_date="2026-10-01", to_date="2026-10-31")),
    )
)
PARITY += [
    ("needs-date", dict(clarification="needs_date"), dict(clarification="needs_date")),
    ("needs-location", dict(clarification="needs_location"), dict(clarification="needs_location")),
    (
        "needs-criteria",
        dict(intent="compare", clarification="needs_criteria", answer_mode="comparison"),
        dict(intent="compare", clarification="needs_criteria"),
    ),
]


@pytest.mark.parametrize("name,old,new", PARITY, ids=[case[0] for case in PARITY])
def test_legacy_v9_internal_parity(name, old, new):
    expected = normalize(legacy(**old))
    actual = normalize_v9(v9(**new))
    assert actual == expected
    require_supported(actual)


def test_recommendation_uses_same_semantic_eligibility_and_ranking():
    old = normalize(
        legacy(
            intent="recommend",
            semantic_query="Jazz",
            requires_semantic_relevance=True,
            answer_mode="recommendation",
        )
    )
    new = normalize_v9(v9(intent="search", semantic={"query": "Jazz", "focus": None}))
    # v9 intentionally has no recommend intent; both share the exact semantic primitive.
    assert new == replace(old, intent="search")


def test_combined_hard_filters_survive_semantic_normalization():
    old = dict(
        intent="search",
        semantic_query="Jazz",
        requires_semantic_relevance=True,
        venue_query="Volksbad",
        organization_query="Team",
        event_type_queries=["Konzert"],
        category_queries=["Kultur"],
        genre_queries=["Jazz"],
        area_query="Flensburg",
        temporal="today",
        time_of_day="evening",
        limit=7,
    )
    filters = [
        dict(field=f, operator="eq", value=v)
        for f, v in (
            ("venue", "Volksbad"),
            ("organization", "Team"),
            ("event_type", "Konzert"),
            ("category", "Kultur"),
            ("genre", "Jazz"),
        )
    ]
    new = v9(
        intent="search",
        semantic={"query": "Jazz", "focus": None},
        filters=filters,
        spatial=spatial(),
        temporal=temporal(time_of_day="evening"),
        limit=7,
    )
    assert normalize_v9(new) == normalize(legacy(**old))


UNSUPPORTED = [
    dict(
        intent="trend",
        trend=dict(
            measure="event_count",
            comparison="previous_period",
            window="month",
            change="absolute_change",
        ),
    ),
    dict(intent="anomaly", anomaly=None, clarification="needs_criteria"),
    dict(
        intent="relation",
        relation=dict(
            operation="related",
            source="organization",
            target="event",
            via=[],
            source_query=None,
            target_query=None,
        ),
    ),
    dict(
        intent="explain",
        entity_type=None,
        explain=dict(target="definition", term="Population", context="definition"),
    ),
    dict(intent="knowledge", entity_type=None, knowledge=dict(query="Was ist Uranus?")),
    dict(price=dict(mode="free", minimum=None, maximum=None, currency=None)),
    dict(temporal=temporal(after_time="18:00:00")),
    dict(temporal=temporal(before_time="20:00:00")),
    dict(temporal=temporal(weekday="monday")),
    dict(temporal=temporal(overlap=True)),
    dict(temporal=temporal(multi_day=True)),
    dict(temporal=temporal(field="modified_at")),
    dict(temporal=temporal(calendar_relation="holiday", calendar_area_query="DE")),
    dict(temporal=temporal("past", lookback=2, lookback_unit="month")),
    dict(spatial=spatial("within_radius", radius_m=10000)),
    dict(spatial=spatial("north_of")),
    dict(spatial=spatial("near_border", reference="border", radius_m=500)),
    dict(intent="rank", metric=metric("field_length", "description"), ordering="desc", limit=1),
    dict(intent="rank", metric=metric("value", "end_date"), ordering="desc", limit=1),
    dict(
        intent="rank",
        entity_type="organization",
        metric=metric("value", "latitude"),
        ordering="desc",
        limit=1,
    ),
    dict(entity_type="occurrence"),
    dict(intent="search", entity_type="venue", semantic=dict(query="Musik", focus=None)),
    dict(intent="taxonomy", entity_type="venue", taxonomy="genre"),
    dict(
        intent="aggregate", entity_type="venue", metric=metric("event_count"), group_by=["category"]
    ),
    dict(intent="aggregate", metric=metric("event_count"), group_by=["hour"]),
    dict(
        intent="compare",
        entity_type="municipality",
        metric=metric("event_count"),
        comparison_targets=[dict(kind="municipality", query=n) for n in ("One", "Two")],
    ),
    dict(
        intent="compare",
        metric=metric("event_count"),
        group_by=["venue"],
        comparison_targets=[dict(kind="venue", query=n) for n in ("One", "Two")],
    ),
    dict(filters=[dict(field="venue", operator="neq", value="A")]),
    dict(filters=[dict(field="genre", operator="eq", value=v) for v in ("Jazz", "Rock")]),
    dict(filters=[dict(field="description", operator="missing")]),
    dict(
        intent="count",
        entity_type="event",
        metric=metric("event_count"),
        semantic=dict(query="Kinder", focus=None),
        unsupported_reason="insufficient_structured_data",
    ),
    dict(clarification="needs_definition"),
    dict(clarification="needs_context"),
]


@pytest.mark.parametrize("change", UNSUPPORTED)
async def test_unsupported_v9_fails_before_resolution_or_sql(client, headers, flow, change):
    state, requests, sql, resolve, learn = flow
    plan = v9(**change)  # All cases are valid wire plans, not merely malformed JSON.
    data = envelope()
    data.update(
        plan=plan.model_dump(mode="json"),
        kind="unsupported"
        if plan.unsupported_reason
        else "needs_clarification"
        if plan.clarification != "none"
        else "plan",
    )
    data["diagnostics"]["planner_intent"] = plan.intent
    state["response"] = data
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": plan.original_query}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "research_execution_unsupported"
    assert len(requests) == 1 and requests[0].url.path == "/v9/plan"
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()
    learn.assert_not_awaited()


def test_frontend_wire_fixtures_match_validated_parity_cases():
    path = Path(__file__).parents[2] / "frontend/tests/fixtures/research-v9-parity.json"
    recorded = json.loads(path.read_text())
    assert recorded == [
        dict(name=name, plan=v9(**new).model_dump(mode="json")) for name, _, new in PARITY
    ]


def test_legacy_v3_inclusive_evening_is_exact_only_with_gte_clock_filter():
    expected = normalize(planned(temporal="today", time_of_day="evening"))
    old = replace(expected, filters=normalize_v9(v9()).filters, spatial_constraints=())
    new = normalize_v9(
        v9(
            temporal=temporal(),
            filters=[dict(field="start_time", operator="gte", value="18:00:00", upper=None)],
        )
    )
    assert new.temporal == old.temporal
    # v5/v6 evening is a different bounded daypart, never silently substituted.
    assert new.temporal != normalize_v9(v9(temporal=temporal(time_of_day="evening"))).temporal


def set_response(state, plan):
    data = envelope()
    data.update(
        plan=plan.model_dump(mode="json"),
        kind="needs_clarification" if plan.clarification != "none" else "plan",
    )
    data["diagnostics"]["planner_intent"] = plan.intent
    state["response"] = data


@pytest.mark.parametrize(
    "name,old,new",
    [
        c
        for c in PARITY
        if c[0].startswith(
            ("list-", "aggregate-", "taxonomy-", "chronological-", "spatial-", "compare-")
        )
        or c[0] in {"event_count", "occurrence_count", "venue_count", "organization_count"}
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
async def test_v9_normal_api_uses_existing_sql_families(client, headers, flow, name, old, new):
    from app.repositories.research_resolution import Resolution
    from app.schemas.research_execution import ResolutionCandidate, ResolvedField
    from tests.conftest import uid
    from tests.test_research_administrative import boundary
    from tests.test_research_sql_provenance import Rows

    state, requests, sql, resolve, _ = flow
    plan = v9(**new)
    set_response(state, plan)
    sql.execute.side_effect = [Rows(scalar=7) for _ in range(4)]
    if plan.intent == "compare":
        internal = normalize_v9(plan)
        resolve.side_effect = None
        resolve.return_value = Resolution(
            fields=[
                ResolvedField(
                    field="comparison_targets",
                    query=t.query,
                    target=ResolutionCandidate(
                        entity_type=t.kind,
                        id=str(uid(i + 20)),
                        label=t.query,
                    ),
                )
                for i, t in enumerate(internal.comparison_targets)
            ],
            target_areas={str(uid(i + 20)): boundary() for i in range(2)},
        )
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": plan.original_query}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    expected = normalize(legacy(**old))
    assert resolve.await_args.args[2] == expected
    assert (
        body["result"]["kind"]
        == {
            "list": "records",
            "aggregate": "aggregate",
            "count": "count",
            "compare": "comparison",
            "taxonomy": "taxonomy",
            "spatial_rank": "spatial",
        }[expected.intent]
    )
    assert body["sql_provenance"]
    assert len(requests) == 1 and requests[0].url.path == "/v9/plan"
    for statement, call in zip(body["sql_provenance"], sql.execute.await_args_list, strict=True):
        assert statement["sql"] == call.args[0].text
    if plan.intent == "compare":
        assert len(body["sql_provenance"]) == 2
        assert all(s["kind"] == "comparison" for s in body["sql_provenance"])


@pytest.mark.parametrize("state_name", ["needs_criteria", "needs_date", "needs_location"])
async def test_v9_clarification_is_a_normal_response_without_sql(client, headers, flow, state_name):
    state, requests, sql, resolve, learn = flow
    plan = v9(
        intent="compare" if state_name == "needs_criteria" else "list", clarification=state_name
    )
    set_response(state, plan)
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": plan.original_query}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["planner_state"] == state_name
    assert body["sql_provenance"] == []
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()
    assert len(requests) == 1


@pytest.mark.parametrize("manual", [False, True])
async def test_v9_nearby_context_resolves_without_sending_coordinates_to_planner(
    client, headers, flow, monkeypatch, manual
):
    from types import SimpleNamespace

    from app.schemas.research_location import Place
    from tests.test_research_geocoder import PLACE
    from tests.test_research_sql_provenance import Rows

    state, requests, sql, _, learn = flow
    plan = v9(
        spatial=spatial("nearby", None, reference="user_location"), clarification="needs_location"
    )
    set_response(state, plan)
    geocoder = SimpleNamespace(
        reverse=AsyncMock(return_value=Place.model_validate_json(json.dumps(PLACE))),
        search=AsyncMock(return_value=[Place.model_validate_json(json.dumps(PLACE))]),
    )
    monkeypatch.setattr(client._transport.app.state, "research_geocoder", geocoder)
    sql.execute.side_effect = [Rows()]
    context = (
        dict(display_name="Flensburg", source="manual")
        if manual
        else dict(latitude=54.791234567, longitude=9.431234567, source="browser_geolocation")
    )
    response = await client.post(
        "/api/v1/research/query",
        headers=headers,
        json={"query": plan.original_query, "location_context": context},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["kind"] == "records"
    assert len(requests) == 1
    assert "location_context" not in json.loads(requests[0].content)
    assert "54.791234567" not in response.text
    if manual:
        geocoder.search.assert_awaited_once_with("Flensburg")
        geocoder.reverse.assert_not_awaited()
    else:
        geocoder.reverse.assert_awaited_once_with(54.791234567, 9.431234567)
        assert (
            body["sql_provenance"][0]["parameters"]["place_latitude"] == "[Standort ausgeblendet]"
        )
    learn.assert_not_awaited()


async def test_v9_semantic_route_preserves_eligibility_and_rehydration_sql(
    client, settings, headers, flow, monkeypatch
):
    from types import SimpleNamespace

    from app.services import semantic_search
    from tests.test_research_sql_provenance import ROW, Rows
    from tests.test_semantic_search import hit

    state, requests, sql, resolve, _ = flow
    plan = v9(intent="search", semantic=dict(query="Musik", focus="Familien"), temporal=temporal())
    set_response(state, plan)
    settings.semantic_search_noncommercial_jina = True
    encoder = SimpleNamespace(
        embed=AsyncMock(return_value=[[0.1]]), http=SimpleNamespace(close=AsyncMock())
    )
    vector = SimpleNamespace(
        search=AsyncMock(return_value=[hit(30)]), http=SimpleNamespace(close=AsyncMock())
    )
    monkeypatch.setattr(semantic_search, "Encoder", lambda *a, **k: encoder)
    monkeypatch.setattr(semantic_search, "Qdrant", lambda *a, **k: vector)

    async def connection(_request):
        yield sql

    monkeypatch.setattr(semantic_search, "get_connection", connection)
    sql.execute.side_effect = [Rows(), Rows([ROW]), Rows()]
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": plan.original_query}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["kind"] == "records" and body["execution"]["semantic"]
    assert body["execution"]["from_date"] == "2026-10-02"
    assert [s["kind"] for s in body["sql_provenance"]] == [
        "eligibility",
        "rehydration",
        "rehydration",
    ]
    assert resolve.await_args.args[2].semantic.focus == "Familien"
    vector.search.assert_awaited_once()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "entity,operation",
    [
        ("event", "event_count"),
        ("occurrence", "occurrence_count"),
        ("venue", "venue_count"),
        ("organization", "organization_count"),
    ],
)
def test_distinct_count_alias_preserves_existing_count_identity(entity, operation):
    actual = normalize_v9(
        v9(
            intent="count",
            entity_type=entity,
            metric=metric("distinct_count") | {"distinct_by": entity},
        )
    )
    assert actual == normalize_v9(v9(intent="count", entity_type=entity, metric=metric(operation)))


@pytest.mark.parametrize("level", ["municipality", "region", "country"])
@pytest.mark.parametrize("zero", [False, True])
def test_existing_v8_inventory_grouping_has_lossless_v9_mapping(level, zero):
    from app.research.normalize import normalize_v8
    from app.research.wire.research_v8_schema import ResearchQueryPlanV8

    new = v9(
        intent="aggregate",
        entity_type="region" if level == "country" else level,
        group_by=[level],
        metric=metric("event_count"),
        metric_filter=dict(operator="eq", value=0, upper=None) if zero else None,
    )
    data = new.model_dump(mode="json") | dict(entity_type=level, group_by=level, spatial=[])
    old = ResearchQueryPlanV8.model_validate_json(json.dumps(data))
    assert normalize_v9(new) == normalize_v8(old)


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_ranked_venue_subject_is_not_mistaken_for_measured_event_population(direction):
    new = v9(
        intent="rank",
        entity_type="venue",
        group_by=["venue"],
        metric=metric("event_count"),
        ordering=direction,
        limit=3,
    )
    old = legacy(
        intent="aggregate",
        entity_type="event",
        group_by="venue",
        metric="event_count",
        answer_mode="aggregate",
        ordering=direction,
        limit=3,
    )
    assert normalize_v9(new) == normalize(old)


@pytest.mark.parametrize(
    "change",
    [
        dict(filters=[dict(field="start_time", operator="gt", value="18:00:00", upper=None)]),
        dict(
            filters=[
                dict(field="start_time", operator="gte", value=v, upper=None)
                for v in ("18:00:00", "19:00:00")
            ]
        ),
        dict(
            intent="count",
            entity_type="event",
            metric=metric("distinct_count") | {"distinct_by": "genre"},
        ),
        dict(
            intent="compare",
            metric=metric("event_count"),
            comparison_targets=[dict(kind="venue", query=n) for n in ("One", "Two")],
            filters=[dict(field="venue", operator="eq", value="Common")],
        ),
    ],
)
async def test_unrepresentable_predicates_do_not_reach_sql(client, headers, flow, change):
    await test_unsupported_v9_fails_before_resolution_or_sql(client, headers, flow, change)


async def test_rank_without_criteria_remains_clarification_not_guessed_count(client, headers, flow):
    state, _, sql, resolve, _ = flow
    plan = v9(
        intent="rank", group_by=["event"], ordering="desc", limit=1, clarification="needs_criteria"
    )
    set_response(state, plan)
    actual = normalize_v9(plan)
    assert actual.metric == "none" and actual.groupings == ("event",)
    response = await client.post(
        "/api/v1/research/query", headers=headers, json={"query": plan.original_query}
    )
    assert response.status_code == 200
    assert response.json()["result"]["planner_state"] == "needs_criteria"
    sql.execute.assert_not_awaited()
    resolve.assert_not_awaited()


@pytest.mark.parametrize("level", ["region", "country"])
def test_admin_grouping_accepts_the_measured_event_subject(level):
    data = dict(intent="aggregate", group_by=[level], metric=metric("event_count"))
    measured = normalize_v9(v9(**data, entity_type="event"))
    target = normalize_v9(v9(**data, entity_type="region"))
    assert measured == target
