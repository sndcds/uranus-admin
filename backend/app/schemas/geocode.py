"""Stored suggestions only; no acceptance or source-write contract."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.schemas.finding import Pagination

GeocodeEntity = Literal["organization", "venue"]
GeocodeStatus = Literal[
    "pending",
    "checking",
    "candidate",
    "ambiguous",
    "not_found",
    "insufficient_input",
    "failed",
    "stale",
]
MatchReason = Literal[
    "country_exact",
    "country_mismatch",
    "country_unknown",
    "postal_code_exact",
    "postal_code_mismatch",
    "postal_code_missing",
    "city_exact",
    "city_mismatch",
    "city_missing",
    "street_exact",
    "street_mismatch",
    "street_missing",
    "house_number_exact",
    "house_number_mismatch",
    "house_number_missing",
]
AddressKey = Literal[
    "road",
    "house_number",
    "postcode",
    "city",
    "town",
    "village",
    "municipality",
    "county",
    "state",
    "country",
    "country_code",
]


class GeocodeFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: GeocodeEntity | None = None
    status: GeocodeStatus | None = None
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=50, ge=1, le=100)


class GeocodeCandidate(BaseModel):
    id: UUID
    rank: int = Field(ge=1, le=5)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    display_name: str = Field(min_length=1, max_length=1024)
    osm_type: Literal["node", "way", "relation"] | None = None
    osm_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")] | None = None
    provider_class: str | None = None
    provider_type: str | None = None
    provider_addresstype: str | None = None
    provider_importance: float | None = Field(default=None, allow_inf_nan=False)
    match_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    match_reasons: list[MatchReason]
    address: dict[AddressKey, Annotated[str, Field(max_length=240)]]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def osm_url(self) -> str:
        if self.osm_type and self.osm_id:
            return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"
        return f"https://www.openstreetmap.org/?mlat={self.latitude}&mlon={self.longitude}"


class GeocodeRequestSummary(BaseModel):
    id: UUID
    entity_type: GeocodeEntity
    entity_key: UUID
    entity_name: str
    source_address: str
    status: GeocodeStatus
    source_fingerprint: str
    query_fingerprint: str
    generation: int
    query_version: int
    scoring_version: int
    attempt_count: int
    checked_at: datetime | None
    next_check_at: datetime | None
    last_error: Literal["provider_unavailable"] | None
    created_at: datetime
    updated_at: datetime
    candidate_count: int = Field(ge=0, le=5)
    best_candidate: GeocodeCandidate | None


class GeocodeRequestDetail(GeocodeRequestSummary):
    candidates: list[GeocodeCandidate] = Field(max_length=5)


class GeocodePage(BaseModel):
    items: list[GeocodeRequestSummary]
    pagination: Pagination
    counts: dict[GeocodeStatus, int]


class GeocodeRetryResponse(BaseModel):
    id: UUID
    status: Literal["pending"] = "pending"
