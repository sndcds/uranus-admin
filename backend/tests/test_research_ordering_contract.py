import json

import pytest
from pydantic import ValidationError

from app.schemas.research_planner import ResearchQueryPlan
from tests.test_research_plan_execution import planned


def make_plan(**changes):
    return planned(temporal="none", **changes).plan


@pytest.mark.parametrize("ordering", [None, "asc", "desc"])
@pytest.mark.parametrize("limit", [None, 1, 2, 20])
def test_independent_ordering_limit_contract(ordering, limit):
    plan = make_plan(ordering=ordering, limit=limit)
    assert plan.ordering == ordering and plan.limit == limit
    assert plan.temporal == "none"


@pytest.mark.parametrize(
    "changes",
    [
        *({"ordering": v} for v in ("none", "earliest", "latest", "best", True)),
        *({"limit": v} for v in (0, 21, True, "1", 1.0, 1.5)),
        {"ordering": "asc", "entity_type": "venue"},
        {"ordering": "desc", "entity_type": "organization"},
        {
            "ordering": "asc",
            "intent": "recommend",
            "answer_mode": "recommendation",
            "semantic_query": "interesting",
            "requires_semantic_relevance": True,
        },
        {
            "ordering": "asc",
            "intent": "search",
            "semantic_query": "interesting",
            "requires_semantic_relevance": True,
        },
    ],
)
def test_invalid_ordering_limit_contract(changes):
    with pytest.raises(ValidationError):
        make_plan(**changes)


@pytest.mark.parametrize(
    "intent,mode,extras",
    [
        ("count", "count", {"metric": "event_count"}),
        ("aggregate", "aggregate", {"metric": "event_count", "group_by": "venue"}),
        ("compare", "comparison", {"clarification": "needs_criteria"}),
    ],
)
@pytest.mark.parametrize("changes", [{"ordering": "asc"}, {"ordering": "desc"}, {"limit": 2}])
def test_metrics_reject_ordering_and_limit(intent, mode, extras, changes):
    with pytest.raises(ValidationError):
        make_plan(intent=intent, answer_mode=mode, **extras, **changes)


@pytest.mark.parametrize("entity", ["venue", "organization"])
def test_non_event_record_limit(entity):
    plan = make_plan(entity_type=entity, limit=2)
    assert plan.limit == 2 and plan.ordering is None


@pytest.mark.parametrize("intent,mode", [("search", "records"), ("recommend", "recommendation")])
def test_semantic_limit_without_ordering(intent, mode):
    plan = make_plan(
        intent=intent,
        answer_mode=mode,
        semantic_query="interesting",
        requires_semantic_relevance=True,
        limit=2,
    )
    assert plan.limit == 2 and plan.ordering is None


def test_hybrid_chronology_is_explicitly_unsupported():
    plan = make_plan(
        ordering="asc",
        intent="search",
        semantic_query="interesting",
        requires_semantic_relevance=True,
        unsupported_reason="unsupported_constraint",
    )
    assert plan.unsupported_reason == "unsupported_constraint"


@pytest.mark.parametrize("field", ["ordering", "limit"])
def test_ordering_limit_fields_required(field):
    data = make_plan().model_dump(mode="json")
    del data[field]
    with pytest.raises(ValidationError):
        ResearchQueryPlan.model_validate_json(json.dumps(data))
