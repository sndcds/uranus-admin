"""Lossless v12 spatial adapter to the shared research plan; no resolver or executor."""

import json
from dataclasses import replace
from typing import Literal, cast

from pydantic import ValidationError

from app.research.capabilities import require_supported
from app.research.geography import SpatialConstraint, UnresolvedAdministrativeAreaRef
from app.research.normalize import unsupported
from app.research.normalize_v9 import normalize_v9_spatial
from app.research.normalize_v10 import normalize_v10
from app.research.plan import InternalResearchPlan
from app.research.wire.research_v9_constraints import SpatialV9
from app.research.wire.research_v10_schema import ResearchQueryPlanV10
from app.research.wire.research_v12_schema import ResearchQueryPlanV12


def normalize_v12(wire: ResearchQueryPlanV12) -> InternalResearchPlan:
    wire = ResearchQueryPlanV12.model_validate_json(wire.model_dump_json())
    if wire.clarification == "needs_context" and wire.unsupported_reason is None:
        return InternalResearchPlan(
            intent="list", entity_type="event", clarification="needs_context"
        )
    spatial: list[SpatialConstraint] = []
    for geo in wire.spatial:
        if geo.relation in {"inside", "outside"} and geo.reference == "named" and geo.area_query:
            spatial.append(
                SpatialConstraint(
                    cast(Literal["inside", "outside"], geo.relation),
                    UnresolvedAdministrativeAreaRef(geo.area_query, geo.area_level),
                )
            )
        else:
            if geo.area_level is not None:
                raise unsupported()
            # Preserve every currently executable non-administrative v11 predicate.
            spatial.extend(
                normalize_v9_spatial(
                    SpatialV9.model_validate_json(geo.model_dump_json(exclude={"area_level"}))
                )
            )
    # Extract only the fully validated spatial dimension. Other v11 capabilities
    # use their existing normalizer, then all dimensions are checked together.
    data = wire.model_dump(mode="json")
    data["spatial"] = None
    try:
        base = normalize_v10(ResearchQueryPlanV10.model_validate_json(json.dumps(data)))
    except ValidationError:
        raise unsupported() from None
    plan = replace(base, spatial_constraints=tuple(spatial))
    require_supported(plan)
    return plan
