from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.action import Action
from app.schemas.finding import Pagination

QueueKind = Literal["partner_requests", "team_invitations", "user_activation"]


class QueueFilters(BaseModel):
    organization_id: UUID | None = None
    entity_key: str | None = Field(default=None, min_length=1, max_length=1024)
    status: str | None = Field(default=None, max_length=64)
    min_age_days: int | None = Field(default=None, ge=0, le=36500)
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=100)


class QueueItem(BaseModel):
    entity_key: str
    organization_id: UUID | None = None
    organization_name: str | None = None
    from_organization_id: UUID | None = None
    from_organization_name: str | None = None
    to_organization_id: UUID | None = None
    to_organization_name: str | None = None
    user_id: UUID
    user_name: str | None
    status: str
    created_at: datetime
    invited_at: datetime | None = None
    has_joined: bool | None = None
    age_days: int | None
    age_basis: Literal["created_at", "invited_at"]
    checks: list[str]
    action: Action


class QueuePage(BaseModel):
    kind: QueueKind
    items: list[QueueItem]
    pagination: Pagination
    observed_at: datetime
