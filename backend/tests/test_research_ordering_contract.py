import json

import pytest
from pydantic import ValidationError

from app.schemas.research_planner import ResearchQueryPlan
from tests.test_research_plan_execution import planned


def make_plan(**changes):
    return planned(temporal="none", **changes).plan


@pytest.mark.parametrize("ordering,limit", [("earliest", 1), ("latest", 10), ("earliest", 20)])
def test_chronological_contract(ordering, limit):
    plan = make_plan(ordering=ordering, limit=limit)
    assert plan.ordering == ordering and plan.limit == limit
    assert plan.temporal == "none"


@pytest.mark.parametrize(
    "changes",
    [
        {"ordering": "earliest"},
        {"limit": 1},
        {"ordering": "best", "limit": 1},
        *({"ordering": "earliest", "limit": v} for v in (0, 21, True, "1", 1.5)),
        {"ordering": "earliest", "limit": 1, "entity_type": "venue"},
        {
            "ordering": "earliest",
            "limit": 1,
            "intent": "count",
            "answer_mode": "count",
            "metric": "event_count",
        },
        {
            "ordering": "latest",
            "limit": 1,
            "intent": "aggregate",
            "answer_mode": "aggregate",
            "metric": "event_count",
            "group_by": "venue",
        },
        {
            "ordering": "latest",
            "limit": 1,
            "intent": "compare",
            "answer_mode": "comparison",
            "clarification": "needs_criteria",
        },
        {
            "ordering": "earliest",
            "limit": 1,
            "intent": "recommend",
            "answer_mode": "recommendation",
            "semantic_query": "interesting",
            "requires_semantic_relevance": True,
        },
        {
            "ordering": "earliest",
            "limit": 1,
            "intent": "search",
            "semantic_query": "interesting",
            "requires_semantic_relevance": True,
        },
    ],
)
def test_invalid_chronological_contract(changes):
    with pytest.raises(ValidationError):
        make_plan(**changes)


def test_hybrid_chronology_is_explicitly_unsupported():
    plan = make_plan(
        ordering="earliest",
        limit=1,
        intent="search",
        semantic_query="interesting",
        requires_semantic_relevance=True,
        unsupported_reason="unsupported_constraint",
    )
    assert plan.unsupported_reason == "unsupported_constraint"


@pytest.mark.parametrize("field", ["ordering", "limit"])
def test_chronological_fields_required(field):
    data = make_plan().model_dump(mode="json")
    del data[field]
    with pytest.raises(ValidationError):
        ResearchQueryPlan.model_validate_json(json.dumps(data))
