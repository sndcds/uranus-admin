"""Compatibility adapter for the frozen scalar v7 representation."""

import json

from app.research.normalize_v9 import normalize_v9
from app.research.plan import InternalResearchPlan
from app.research.wire.research_v7_schema import ResearchQueryPlanV7
from app.research.wire.research_v9_schema import ResearchQueryPlanV9


def normalize_v7_grouping(wire: "ResearchQueryPlanV7") -> InternalResearchPlan:
    """Existing public scalar representation becomes one axis; no dimension inference."""

    validated = ResearchQueryPlanV7.model_validate_json(wire.model_dump_json())
    data = validated.model_dump(mode="json")
    data["group_by"] = [] if validated.group_by == "none" else [validated.group_by]
    return normalize_v9(ResearchQueryPlanV9.model_validate_json(json.dumps(data)))
