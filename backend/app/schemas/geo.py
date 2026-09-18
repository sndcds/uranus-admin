"""Provider-neutral cached areas; browser imports contain identity only."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

GeoAreaKind = Literal["country", "region", "county", "municipality", "city", "district", "other"]
SourceId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]


class GeoAreaImport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: Literal["osm"]
    source_type: Literal["relation"]
    source_id: SourceId


class GeoAreaSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=10, ge=1, le=10)

    @field_validator("q", mode="before")
    @classmethod
    def valid_query(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Control characters are not allowed")
        return value.strip()


class GeoAreaSearchItem(BaseModel):
    provider: Literal["osm"] = "osm"
    osm_type: Literal["relation"] = "relation"
    osm_id: SourceId
    name: str = Field(min_length=1, max_length=240)
    display_name: str = Field(min_length=1, max_length=1024)
    country_code: str | None
    admin_level: int | None
    kind: GeoAreaKind
    provider_class: str | None
    provider_type: str | None
    provider_addresstype: str | None
    # west, south, east, north; metadata only, never a membership geometry.
    bbox: tuple[float, float, float, float] | None
    hierarchy: dict[str, str]
    eligible_for_scope: bool = True


class GeoAreaSearchResponse(BaseModel):
    items: list[GeoAreaSearchItem]


class GeoArea(BaseModel):
    id: UUID
    source: str
    source_type: str
    source_id: str
    name: str
    display_name: str
    country_code: str | None
    admin_level: int | None
    kind: GeoAreaKind
    provider_class: str | None
    provider_type: str | None
    provider_addresstype: str | None
    bbox: tuple[float, float, float, float] | None
    hierarchy: dict[str, str]
    fetched_at: datetime
