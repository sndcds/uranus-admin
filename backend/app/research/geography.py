"""Internal geography: identity and administrative level are separate from names.

Unresolved names carry no asserted level. Only persisted boundary metadata can
supply one. Hierarchy references may have official identities without cached
boundaries; they must never be used as executable geometry.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

AdministrativeLevel = Literal["country", "state", "district", "municipality", "region"]
OfficialCodeSystem = Literal["ISO-3166-1", "ISO-3166-2", "DE-AGS", "DE-state", "DE-district"]
SpatialRelation = Literal[
    "inside",
    "outside",
    "nearby",
    "within_radius",
    "near_border",
    "across_border",
    "north_of",
    "south_of",
    "east_of",
    "west_of",
    "nearest",
]


@dataclass(frozen=True, slots=True)
class AdministrativeIdentity:
    level: AdministrativeLevel
    country_code: str
    official_code: str
    code_system: OfficialCodeSystem


@dataclass(frozen=True, slots=True)
class BoundaryReference:
    # Identity of the persisted admin.research_area geometry, not an upstream URL.
    area_id: UUID


@dataclass(frozen=True, slots=True)
class AdministrativeAreaRef:
    name: str
    level: AdministrativeLevel | None = None
    country_code: str | None = None
    official_code: str | None = None
    code_system: OfficialCodeSystem | None = None
    resolved_id: UUID | None = None
    boundary: BoundaryReference | None = None
    # Direct parent is deliberately absent if only a more distant ancestor is known.
    parent: AdministrativeIdentity | None = None
    ancestors: tuple[AdministrativeIdentity, ...] = ()


@dataclass(frozen=True, slots=True)
class AdministrativeHierarchy:
    areas: tuple[AdministrativeAreaRef, ...]

    def children(self, parent: AdministrativeIdentity) -> tuple[AdministrativeAreaRef, ...]:
        return tuple(area for area in self.areas if area.parent == parent)

    def descendants(self, ancestor: AdministrativeIdentity) -> tuple[AdministrativeAreaRef, ...]:
        return tuple(area for area in self.areas if ancestor in area.ancestors)


@dataclass(frozen=True, slots=True)
class NamedPlaceRef:
    name: str


@dataclass(frozen=True, slots=True)
class UserLocationRef:
    """Coordinates live only in ResearchExecutionContext."""


@dataclass(frozen=True, slots=True)
class BorderRef:
    area: AdministrativeAreaRef
    adjoining_area: AdministrativeAreaRef | None = None


@dataclass(frozen=True, slots=True)
class SpatialConstraint:
    relation: SpatialRelation
    reference: AdministrativeAreaRef | NamedPlaceRef | UserLocationRef | BorderRef
    radius_m: int | None = None


def administrative_constraints(
    constraints: tuple[SpatialConstraint, ...],
) -> tuple[SpatialConstraint, ...]:
    return tuple(c for c in constraints if isinstance(c.reference, AdministrativeAreaRef))


def uses_user_location(constraints: tuple[SpatialConstraint, ...]) -> bool:
    return any(isinstance(c.reference, UserLocationRef) for c in constraints)


def location_sensitive(constraints: tuple[SpatialConstraint, ...]) -> bool:
    return any(isinstance(c.reference, (UserLocationRef, NamedPlaceRef)) for c in constraints)
