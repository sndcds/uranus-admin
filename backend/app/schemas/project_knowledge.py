"""Public Knowledge evidence contract; no internal Chunk or assertion payloads.

Mirrors contracts/AnswerResponse.json from sndcds/uranus-research-knowledge
PR #1 at adcb6b917850b2656fd6145181ad47c3c4d3becd. Admin also validates
provenance, response consistency and Fact-to-Evidence references at its boundary.
"""

import re
from hashlib import sha256
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, model_validator

FactKey = Literal[
    "uranus_overview",
    "admin_overview",
    "semantic_search_repository",
    "embedding_component",
    "embedding_model",
    "qdrant_usage",
    "encoder_communication",
    "planner_component",
    "geocoding",
    "architecture",
    "founding_date",
]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True, strict=True)


class Evidence(Closed):
    """Public provenance projection: never serialize internal assertion quotes."""

    id: str
    repository: str
    path: str
    commit_sha: str
    source_url: str
    content_hash: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    license: str
    license_source_url: str | None = None
    evidence_available: Literal[True] = True
    evidence_redistribution_allowed: bool
    excerpt_included: bool
    chunk_text: str | None = Field(default=None, min_length=1, max_length=480)
    graph_edge_ids: list[str] = Field(max_length=100)

    @model_validator(mode="after")
    def excerpt_policy(self) -> "Evidence":
        if self.excerpt_included != (self.chunk_text is not None):
            raise ValueError("invalid_excerpt_status")
        if self.excerpt_included and not self.evidence_redistribution_allowed:
            raise ValueError("excerpt_redistribution_forbidden")
        return self

    @model_validator(mode="after")
    def provenance(self) -> "Evidence":
        if (
            self.repository
            not in {
                "sndcds/uranus",
                "sndcds/uranus-admin",
                "sndcds/uranus-research-planner",
                "sndcds/uranus-research-encoder",
                "sndcds/pluto",
                "sndcds/uranus-dashboard",
                "sndcds/uranus-widget",
                "sndcds/kulturbytes-client",
            }
            or not self.path
            or self.path.startswith("/")
            or ".." in self.path.split("/")
        ):
            raise ValueError("invalid_source")
        if not re.fullmatch(r"[0-9a-f]{40}", self.commit_sha) or not re.fullmatch(
            r"[0-9a-f]{64}", self.content_hash
        ):
            raise ValueError("invalid_provenance_hash")
        expected = (
            f"https://github.com/{self.repository}/blob/{self.commit_sha}/"
            f"{quote(self.path, safe='/')}"
        )
        if self.source_url != expected or self.line_end < self.line_start:
            raise ValueError("invalid_provenance")
        # Withheld text cannot be rehashed; its digest remains provenance metadata.
        if (
            self.chunk_text is not None
            and sha256(self.chunk_text.encode()).hexdigest() != self.content_hash
        ):
            raise ValueError("invalid_content_hash")
        return self


class Fact(Closed):
    key: FactKey
    value: str = Field(max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class AnswerResponse(Closed):
    supported: bool
    authoritative_source: Literal["project_sources"] = "project_sources"
    facts: list[Fact] = Field(max_length=1)
    evidence: list[Evidence] = Field(max_length=20)
    indexed_commits: dict[str, list[str]]
    reason: Literal["supported", "no_explicit_evidence", "conflicting_evidence"]

    @model_validator(mode="after")
    def consistent(self) -> "AnswerResponse":
        if self.supported != bool(self.facts) or (self.reason == "supported") != self.supported:
            raise ValueError("invalid_fact_support")
        evidence = {item.id: item for item in self.evidence}
        if len(evidence) != len(self.evidence):
            raise ValueError("duplicate_evidence_id")
        commits: dict[str, list[str]] = {}
        for item in self.evidence:
            commits.setdefault(item.repository, []).append(item.commit_sha)
        if {key: sorted(set(values)) for key, values in commits.items()} != self.indexed_commits:
            raise ValueError("invalid_indexed_commits")
        for fact in self.facts:
            if any(identity not in evidence for identity in fact.evidence_ids):
                raise ValueError("missing_fact_evidence")
        return self
