"""Additive wire calendar fields become shared domain predicates; no execution."""

import json
from dataclasses import replace

from app.research.capabilities import require_supported
from app.research.normalize_v9 import normalize_v9
from app.research.plan import InternalResearchPlan
from app.research.wire.research_v9_schema import ResearchQueryPlanV9
from app.research.wire.research_v10_schema import ResearchQueryPlanV10


def normalize_v10(wire: ResearchQueryPlanV10) -> InternalResearchPlan:
    wire = ResearchQueryPlanV10.model_validate_json(wire.model_dump_json())
    data = wire.model_dump(mode="json")
    weekdays: tuple[int, ...] = ()
    months: tuple[int, ...] = ()
    if data["temporal"] is not None:
        temporal = data["temporal"]
        weekdays = tuple(temporal.pop("recurring_weekdays"))
        months = tuple(temporal.pop("recurring_months"))
        # Only a descriptor containing exclusively the extracted predicates is
        # absent from the v9 projection. All other fields retain strict validation.
        neutral = {
            "field": "start_date",
            "period": "none",
            "time_of_day": "none",
            "calendar_relation": "none",
            "overlap": False,
            "multi_day": False,
        }
        if all(v == neutral.get(k) for k, v in temporal.items()):
            data["temporal"] = None
    base = normalize_v9(ResearchQueryPlanV9.model_validate_json(json.dumps(data)))
    plan = replace(
        base,
        temporal=replace(base.temporal, weekdays=weekdays or base.temporal.weekdays, months=months),
    )
    require_supported(plan)
    return plan
