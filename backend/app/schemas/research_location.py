"""Untrusted browser context and bounded geocoder output; never persisted."""

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.research_conversation import ResearchConversationContext
from app.schemas.research_conversation_v12 import ResearchConversationContextV12
from app.schemas.research_planner import ClosedModel, ResearchPlanRequest, Slot

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class LocationContext(ClosedModel):
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    display_name: Slot | None = None
    source: Literal["browser_geolocation", "nominatim_reverse", "manual"]

    @field_validator("display_name")
    @classmethod
    def valid_text(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("invalid_unicode") from None
        return value

    @model_validator(mode="after")
    def usable(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Coordinates require latitude and longitude")
        if self.latitude is None and self.display_name is None:
            raise ValueError("Location requires coordinates or a name")
        return self


class ResearchQueryRequest(ResearchPlanRequest):
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{43}$")
    conversation_context: ResearchConversationContextV12 | ResearchConversationContext | None = None
    location_context: LocationContext | None = None


class PlaceAddress(ClosedModel):
    road: str | None = Field(default=None, max_length=300)
    house_number: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=300)
    municipality: str | None = Field(default=None, max_length=300)
    locality: str | None = Field(default=None, max_length=300)
    district: str | None = Field(default=None, max_length=300)
    county: str | None = Field(default=None, max_length=300)
    state: str | None = Field(default=None, max_length=300)
    postcode: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=300)


class Place(ClosedModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=2000)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    osm_type: Literal["node", "way", "relation"] | None = None
    osm_id: int | None = Field(default=None, gt=0)
    place_type: str | None = Field(default=None, max_length=100)
    country_code: str | None = Field(default=None, max_length=3)
    address: PlaceAddress | None = None
    # Service contract: south, west, north, east.
    bbox: tuple[Latitude, Longitude, Latitude, Longitude] | None = None

    @model_validator(mode="after")
    def geometry(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Incomplete coordinates")
        if self.bbox and (self.bbox[0] > self.bbox[2] or self.bbox[1] > self.bbox[3]):
            raise ValueError("Invalid bounding box")
        return self


class PlaceSearch(ClosedModel):
    query: str = Field(max_length=300)
    items: list[Place] = Field(max_length=5)


class PlaceFilter(ClosedModel):
    """Internal only: every value originates from validated resolution, never the browser."""

    mode: Literal["address", "bbox", "radius"]
    road: str | None = None
    city: str | None = None
    house_number: str | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    bbox: tuple[Latitude, Longitude, Latitude, Longitude] | None = None
    radius_m: Literal[250, 500] = 250
