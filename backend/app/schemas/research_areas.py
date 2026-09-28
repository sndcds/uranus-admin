"""Bounded read-only area projections; polygons are only returned for dossiers."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.finding import Pagination
from app.schemas.research import ResearchLocation, ResearchMonth, ResearchPage, ResearchUsageItem

AreaType = Literal["region", "district", "municipality"]


class AreaFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country_code: Literal["DE", "DK"] | None = None
    area_type: AreaType = "municipality"
    q: str = Field(default="", max_length=120)
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=10, ge=1, le=50)


class ResearchPopulation(BaseModel):
    value: int = Field(ge=0)
    as_of: date
    source: Literal["bkg_vg250_ew"]
    municipality_name: str
    file_sha256: str
    imported_at: datetime


class ResearchArea(BaseModel):
    id: UUID
    area_type: AreaType
    country_code: Literal["DE", "DK"]
    region_code: str
    name: str
    display_name: str
    osm_type: Literal["R"]
    osm_id: str
    osm_admin_level: int
    population: ResearchPopulation | None = None
    centroid: ResearchLocation
    bbox: tuple[float, float, float, float]
    source: Literal["osm"]
    retrieved_at: datetime
    updated_at: datetime


class AreaPage(BaseModel):
    items: list[ResearchArea]
    pagination: Pagination


class AreaGeometry(BaseModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[tuple[float, float]]]]


class AreaDossier(BaseModel):
    area: ResearchArea
    geometry: AreaGeometry
    events: ResearchPage
    venues: ResearchPage
    organizations: ResearchPage
    months: list[ResearchMonth]
    usage: list[ResearchUsageItem]
    observed_at: datetime
