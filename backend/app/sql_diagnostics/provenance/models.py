from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from app.schemas.activity import ActivityFilters
from app.schemas.dashboard import Period
from app.schemas.entities import EntityFilters, EntitySearchFilters
from app.schemas.event_content import EventContentFilters
from app.schemas.finding import FindingFilters, Severity
from app.schemas.geocode import GeocodeFilters
from app.schemas.graph import GraphFilters, GraphSearchFilters
from app.schemas.marks import MarkFilters
from app.schemas.notifications import (
    DeliveryKind,
    DeliveryStatus,
    NotificationStatus,
    NotificationType,
)
from app.schemas.queues import QueueFilters
from app.schemas.search import GlobalSearchFilters
from app.schemas.statistics import StatisticsFilters


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: AwareDatetime | None = None


class DashboardParameters(Parameters):
    severity: Severity | None = None
    period: Period = "24h"
    mode: Literal["persisted", "live"] = "persisted"
    geo_scope_id: UUID | None = None


class ActivityParameters(ActivityFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class FindingParameters(FindingFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class EntityParameters(EntityFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class QueueParameters(QueueFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class GeocodeParameters(GeocodeFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class MarkParameters(MarkFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class GraphParameters(GraphFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class GraphSearchParameters(GraphSearchFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class EntitySearchParameters(EntitySearchFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class StatisticsParameters(StatisticsFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class ContentParameters(EventContentFilters, Parameters):
    model_config = ConfigDict(extra="forbid")


class PageParameters(Parameters):
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=100)


class DetailParameters(Parameters):
    id: UUID


class EntityDetailParameters(DetailParameters):
    related_page: int = Field(default=1, ge=1, le=100_000)


class NotificationParameters(PageParameters):
    status: NotificationStatus | None = None
    notification_type: NotificationType | None = None
    organization_id: UUID | None = None
    days: int | None = Field(default=None, ge=1, le=365)


class DeliveryParameters(PageParameters):
    status: DeliveryStatus | None = None
    delivery_kind: DeliveryKind | None = None
    organization_id: UUID | None = None
    days: int | None = Field(default=None, ge=1, le=365)


class VenueQualityParameters(PageParameters):
    organization_id: UUID | None = None


class ProvenanceSource(BaseModel):
    id: str
    title: str
    datasource: Literal["uranus", "admin"]
    description: str
    sql: str
    copy_sql: str | None
    parameters: dict[str, JsonValue]
    columns: list[str]
    executable: bool
    readonly: Literal[True] = True
    implementation_ref: str
    dependencies: list[str] = Field(default_factory=list)


class ProvenanceDefinition(BaseModel):
    view_id: str
    title: str
    endpoint: str
    sources: list[ProvenanceSource]
    post_processing: list[str]
    notes: list[str]
    observed_at: datetime
    parameters: dict[str, JsonValue]


class ProvenanceResult(BaseModel):
    source_id: str
    datasource: Literal["uranus", "admin"]
    columns: list[str]
    rows: list[dict[str, JsonValue]]
    row_count: int
    duration_ms: float
    observed_at: datetime
    truncated: bool


class GlobalSearchParameters(GlobalSearchFilters, Parameters):
    model_config = ConfigDict(extra="forbid")
