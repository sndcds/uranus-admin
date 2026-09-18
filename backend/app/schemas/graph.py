"""Compact, explicitly typed relationship explorer contracts."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

GraphEntityType = Literal["organization", "venue", "space", "event", "event_date", "user"]
GraphRelationType = Literal[
    "organization_has_venue",
    "venue_has_space",
    "organization_has_event",
    "event_has_date",
    "event_uses_venue",
    "event_uses_space",
    "event_date_uses_venue",
    "event_date_uses_space",
    "user_member_of_organization",
    "user_invited_to_organization",
    "organization_partner_request",
    "organization_partner_of",
]


class GraphRoot(BaseModel):
    type: GraphEntityType
    key: UUID


class GraphFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_type: GraphEntityType
    root_key: UUID
    depth: int = Field(default=2, ge=1, le=3)
    relation_type: GraphRelationType | None = None


class GraphSearchFilters(BaseModel):
    geo_scope_id: UUID | None = None
    model_config = ConfigDict(extra="forbid")

    q: str = Field(min_length=2, max_length=120)

    @field_validator("q", mode="before")
    @classmethod
    def trim_query(cls, value: str) -> str:
        return value.strip()

    entity_type: GraphEntityType | None = None
    organization_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=20)


class GraphNode(BaseModel):
    id: str
    type: GraphEntityType
    key: UUID
    label: str
    subtitle: str | None = None
    status: str | None = None
    public_url: str | None = None
    admin_url: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: GraphRelationType
    label: str
    direction: Literal["directed", "undirected"] = "directed"


class GraphResponse(BaseModel):
    root: GraphRoot
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool
    max_nodes: int = 100
    max_edges: int = 200


class GraphSearchResponse(BaseModel):
    items: list[GraphNode]
