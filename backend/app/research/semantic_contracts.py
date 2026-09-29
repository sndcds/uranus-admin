"""Internal, closed contracts for the next semantic index; no public API changes."""

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.research.vector_documents import POINT_NAMESPACE, Chunk, Kind, Section
from app.schemas.genre import GenreKey

EntityType = Literal["event", "venue", "organization"]
OWNER = "kulturbytes-semantic-search-v1"


@dataclass(frozen=True)
class Collection:
    name: str
    document_version: str


COLLECTIONS: dict[EntityType, Collection] = {
    "event": Collection("kulturbytes_events_jina_v3_v1", "event-public-v3"),
    "venue": Collection("kulturbytes_venues_jina_v3_v1", "venue-public-v1"),
    "organization": Collection("kulturbytes_organizations_jina_v3_v1", "organization-public-v1"),
}


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PayloadCore(ClosedModel):
    index_owner: Literal["kulturbytes-semantic-search-v1"] = "kulturbytes-semantic-search-v1"
    entity_id: UUID
    display_name: str = Field(max_length=200_000)
    source_updated_at: str | None = None
    area_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    area_names: list[str] = Field(default_factory=list, max_length=10000)
    area_assignment_available: bool = False


class EffectiveLocation(ClosedModel):
    effective_venue_id: UUID | None = None
    effective_venue_name: str | None = None
    effective_space_id: UUID | None = None
    effective_space_name: str | None = None
    effective_latitude: float | None = Field(default=None, ge=-90, le=90)
    effective_longitude: float | None = Field(default=None, ge=-180, le=180)


class EventPayload(PayloadCore, EffectiveLocation):
    entity_type: Literal["event"] = "event"
    document_schema_version: Literal["event-public-v3"] = "event-public-v3"
    title: str
    organization_id: UUID
    category_ids: list[int] = Field(default_factory=list)
    genre_keys: list[GenreKey] = Field(default_factory=list)
    genre_names: list[str] = Field(default_factory=list)
    status: Literal["released", "cancelled", "deferred", "rescheduled"]
    language: str | None = None
    venue_ids: list[UUID] = Field(default_factory=list)
    space_ids: list[UUID] = Field(default_factory=list)
    first_date: str | None = None
    next_date: str | None = None
    last_date: str | None = None
    # Multiple public occurrences may have different locations. Never pair unrelated arrays.
    effective_locations: list[EffectiveLocation] = Field(default_factory=list, max_length=100000)


class VenuePayload(PayloadCore):
    entity_type: Literal["venue"] = "venue"
    document_schema_version: Literal["venue-public-v1"] = "venue-public-v1"
    name: str
    scope: Literal["organization", "shared"]
    organization_id: UUID | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class OrganizationPayload(PayloadCore):
    entity_type: Literal["organization"] = "organization"
    document_schema_version: Literal["organization-public-v1"] = "organization-public-v1"
    name: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    home_area_ids: list[UUID] = Field(default_factory=list)
    home_area_names: list[str] = Field(default_factory=list)
    activity_area_ids: list[UUID] = Field(default_factory=list)
    activity_area_names: list[str] = Field(default_factory=list)


Payload = Annotated[
    EventPayload | VenuePayload | OrganizationPayload, Field(discriminator="entity_type")
]


class SemanticDocument(ClosedModel):
    entity_type: EntityType
    entity_id: UUID
    display_name: str
    sections: list[Section] = Field(max_length=5)
    payload: Payload

    @model_validator(mode="after")
    def consistent(self) -> "SemanticDocument":
        if (self.entity_type, self.entity_id, self.display_name) != (
            self.payload.entity_type,
            self.payload.entity_id,
            self.payload.display_name,
        ):
            raise ValueError("inconsistent_document_identity")
        if sum(len(s.text) for s in self.sections) > 200_000:
            raise ValueError("semantic_document_limit")
        return self


def semantic_point_id(document: SemanticDocument, chunk: Chunk) -> str:
    return str(
        uuid5(
            POINT_NAMESPACE,
            f"{document.entity_type}:{document.entity_id}:{chunk.chunk_kind}:{chunk.content_hash}",
        )
    )


class EvidenceChunk(ClosedModel):
    chunk_kind: Kind
    chunk_text: str = Field(min_length=1, max_length=200_000)
    score: float


class SemanticHit(ClosedModel):
    entity_type: EntityType
    entity_id: UUID
    score: float
    display_name: str
    winning_chunk: EvidenceChunk
    supporting_chunks: list[EvidenceChunk] = Field(default_factory=list, max_length=3)
