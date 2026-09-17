from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.periods import Period as Period


class NewRecords(BaseModel):
    total: int
    organizations: int
    venues: int
    spaces: int
    events: int
    event_dates: int
    users: int
    partner_requests: int
    team_memberships: int
    images: int


class QualityCounts(BaseModel):
    total: int
    errors: int = 0
    warnings: int
    info: int = 0
    rules: list[str] = ["venue_missing_geolocation"]
    rule_counts: dict[str, int] = {}
    mode: Literal["live", "persisted"] = "persisted"


class DashboardCheckRun(BaseModel):
    id: UUID
    status: Literal["queued", "running", "success", "failed"]
    started_at: datetime
    finished_at: datetime | None
    finding_count: int
    rule_count: int


class DashboardCheckStatus(BaseModel):
    latest_run: DashboardCheckRun | None
    last_successful_run: DashboardCheckRun | None


class DashboardSummary(BaseModel):
    period: Period
    from_at: datetime
    to_at: datetime
    admin_timezone: str
    source_timestamp_timezone: str
    new_records: NewRecords
    images_without_created_at: int
    urgent_findings: int
    quality: QualityCounts
    check_status: DashboardCheckStatus | None = None
