"""Strict internal geocoder metadata and bounded polygon shapes."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.research_location import Latitude, Longitude, Place
from app.schemas.research_values import ClosedModel

AdministrativeLevel = Literal["municipality", "district", "state", "country", "region", "unknown"]

Coordinate = tuple[Longitude, Latitude]
Ring = Annotated[list[Coordinate], Field(min_length=4, max_length=50000)]
PolygonCoordinates = Annotated[list[Ring], Field(min_length=1, max_length=1000)]


class PolygonBoundary(ClosedModel):
    type: Literal["Polygon"]
    coordinates: PolygonCoordinates

    @model_validator(mode="after")
    def closed_rings(self) -> Self:
        if any(ring[0] != ring[-1] for ring in self.coordinates):
            raise ValueError("Boundary rings must be closed")
        return self


class MultiPolygonBoundary(ClosedModel):
    type: Literal["MultiPolygon"]
    coordinates: Annotated[list[PolygonCoordinates], Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def closed_rings(self) -> Self:
        if any(ring[0] != ring[-1] for polygon in self.coordinates for ring in polygon):
            raise ValueError("Boundary rings must be closed")
        return self


BoundaryGeometry = Annotated[PolygonBoundary | MultiPolygonBoundary, Field(discriminator="type")]


class AdministrativePlace(Place):
    country_code: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    name: str | None = Field(default=None, max_length=300)
    administrative_level: AdministrativeLevel = "unknown"
    administrative_levels: list[AdministrativeLevel] = Field(default_factory=list, max_length=5)
    official_code: str | None = Field(default=None, max_length=32)
    official_code_type: str | None = Field(default=None, max_length=80)
    boundary: BoundaryGeometry | None = None

    @model_validator(mode="after")
    def metadata_consistency(self) -> Self:
        if (
            self.administrative_level != "unknown"
            and self.administrative_level not in self.administrative_levels
        ):
            raise ValueError("Administrative primary level must be a supported role")
        if "unknown" in self.administrative_levels or len(set(self.administrative_levels)) != len(
            self.administrative_levels
        ):
            raise ValueError("Invalid administrative roles")
        if (self.official_code is None) != (self.official_code_type is None):
            raise ValueError("Official code must retain its scheme")
        return self


class AdministrativeSearch(ClosedModel):
    query: str = Field(max_length=300)
    items: list[AdministrativePlace] = Field(max_length=5)
