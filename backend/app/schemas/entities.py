from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.activity import Activity
from app.schemas.finding import Pagination

EntitySection = Literal["events", "venues", "spaces", "organizations", "users", "images"]


class EntityFilters(BaseModel):
    q: str = Field(default="", max_length=200)
    organization_id: UUID | None = None
    status: str | None = Field(default=None, max_length=32)
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=25, ge=1, le=100)


class EntityFacts(BaseModel):
    username: str | None = None
    description: str | None = None
    venue_name: str | None = None
    space_name: str | None = None
    event_dates: int | None = None
    venues: int | None = None
    spaces: int | None = None
    events: int | None = None
    memberships: int | None = None
    image_links: int | None = None
    orphan: bool | None = None


class EntityRecord(Activity):
    facts: EntityFacts
    finding_count: int | None = None
    mark_count: int | None = None


class EntityPage(BaseModel):
    items: list[EntityRecord]
    pagination: Pagination
    observed_at: datetime


class EntityRelations(BaseModel):
    items: list[Activity]
    pagination: Pagination


class EntityDetail(BaseModel):
    item: EntityRecord
    related: EntityRelations
    observed_at: datetime
