"""Explicit public source identities; never infer scope from names or prose."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class EvidenceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: Literal["event", "venue", "space", "occurrence"]
    venue_id: UUID | None = None
    space_id: UUID | None = None
    occurrence_id: UUID | None = None

    @model_validator(mode="after")
    def valid_scope(self) -> "EvidenceContext":
        if self.scope == "event":
            valid = self.venue_id is self.space_id is self.occurrence_id is None
        elif self.scope == "venue":
            valid = self.venue_id is not None and self.space_id is self.occurrence_id is None
        elif self.scope == "space":
            valid = self.space_id is not None and self.occurrence_id is None
        else:
            valid = self.occurrence_id is not None
        if not valid:
            raise ValueError("invalid_evidence_context")
        return self

    def matches(
        self, venue_id: UUID | None, space_id: UUID | None, occurrence_id: UUID | None
    ) -> bool:
        if self.scope == "event":
            return True
        if self.scope == "venue":
            return self.venue_id == venue_id
        if self.scope == "space":
            return (self.venue_id, self.space_id) == (venue_id, space_id)
        # NULL is an exact part of a date's location, never a wildcard.
        return (self.venue_id, self.space_id, self.occurrence_id) == (
            venue_id,
            space_id,
            occurrence_id,
        )
