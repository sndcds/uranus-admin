"""Assemble resolved identities from the administrative metadata boundary.

Administrative level/codes belong to metadata providers, not domain execution.
The current metadata adapter supports the persisted schema without a migration.
"""

from app.repositories.research_administrative_metadata import administrative_metadata
from app.repositories.research_areas import ResolvedResearchArea
from app.research.geography import BoundaryReference, ResolvedAdministrativeAreaRef


def administrative_reference(area: ResolvedResearchArea) -> ResolvedAdministrativeAreaRef:
    metadata = administrative_metadata(area)
    return ResolvedAdministrativeAreaRef(
        name=area.area.name,
        level=metadata.level,
        country_code=metadata.country_code,
        official_code=metadata.official_code,
        code_system=metadata.code_system,
        resolved_id=area.area.id,
        boundary=BoundaryReference(area.area.id),
        parent=metadata.parent,
        ancestors=metadata.ancestors,
    )
