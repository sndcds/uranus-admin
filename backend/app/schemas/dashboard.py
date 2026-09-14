from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Period = Literal["today", "24h", "7d"]


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
    mode: Literal["live"] = "live"


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
    # No persisted runs exist in milestone 1. A request is not a historical check run.
    check_status: None = None
