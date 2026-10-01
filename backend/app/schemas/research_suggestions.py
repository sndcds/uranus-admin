"""Bounded, identity-free suggestion telemetry."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SuggestionFilters(Closed):
    q: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=8, ge=1, le=8)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")


class SuggestionItem(Closed):
    id: UUID
    query: str = Field(max_length=300)
    position: int = Field(ge=1, le=8)


class Suggestions(Closed):
    request_id: UUID
    suggestions: list[SuggestionItem] = Field(max_length=8)


class ShownSuggestion(Closed):
    id: UUID
    position: Annotated[int, Field(strict=True, ge=1, le=8)]


class Impression(Closed):
    request_id: UUID
    prefix: str = Field(min_length=2, max_length=120)
    suggestions: list[ShownSuggestion] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len({s.id for s in self.suggestions}) != len(self.suggestions) or len(
            {s.position for s in self.suggestions}
        ) != len(self.suggestions):
            raise ValueError("duplicate_suggestions")
        return self


class Selection(Closed):
    request_id: UUID
    suggestion_id: UUID
    position: Annotated[int, Field(strict=True, ge=1, le=8)]


class TelemetryResult(Closed):
    ok: bool = True
    receipt: UUID | None = None
