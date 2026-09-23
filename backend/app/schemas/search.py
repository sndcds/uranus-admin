"""Bounded global search; CSV types avoids repeated proxy query parameters."""

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.action import Action
from app.schemas.entities import EntitySearchType

SEARCH_TYPES: tuple[EntitySearchType, ...] = get_args(EntitySearchType)


SearchFieldName = Literal[
    "uuid",
    "username",
    "display_name",
    "email",
    "first_name",
    "last_name",
    "name",
    "contact_email",
    "city",
    "postal_code",
    "street",
    "house_number",
    "venue_name",
    "space_type",
    "title",
    "subtitle",
    "external_id",
    "file_name",
    "alt_text",
    "creator_name",
    "mime_type",
]


class GlobalSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=2, max_length=120)
    limit_per_type: int = Field(default=5, ge=1, le=10)
    types: str | None = Field(
        default=None,
        max_length=48,
        description="Comma-separated unique types: user,organization,venue,space,event,image",
    )

    @field_validator("q", mode="before")
    @classmethod
    def trim_query(cls, value: str) -> str:
        return value.strip()

    @field_validator("types")
    @classmethod
    def validate_types(cls, value: str | None) -> str | None:
        if value is not None:
            parts = value.split(",")
            if len(parts) != len(set(parts)) or any(part not in SEARCH_TYPES for part in parts):
                raise ValueError("Invalid search types")
        return value

    @property
    def selected_types(self) -> tuple[EntitySearchType, ...]:
        return tuple(
            kind for kind in SEARCH_TYPES if self.types is None or kind in self.types.split(",")
        )


class GlobalSearchItem(BaseModel):
    entity_type: EntitySearchType
    entity_key: str
    label: str
    subtitle: str | None
    matched_fields: list[SearchFieldName] = Field(max_length=7)
    action: Action


class GlobalSearchGroup(BaseModel):
    entity_type: EntitySearchType
    items: list[GlobalSearchItem] = Field(min_length=1, max_length=10)


class GlobalSearchResponse(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    groups: list[GlobalSearchGroup] = Field(max_length=6)
