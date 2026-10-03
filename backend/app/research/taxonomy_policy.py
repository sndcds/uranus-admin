"""Thresholds are an operator-reviewed benchmark artifact, never guessed defaults."""

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator

from app.research.taxonomy import MODEL, Closed, TaxonomyPayload


class ConfidencePolicy(Closed):
    version: str = Field(pattern=r"^taxonomy-confidence-v1$")
    embedding_version: str
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    benchmark_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    minimum_score: float = Field(ge=-1, le=1)
    minimum_margin: float = Field(gt=0, le=2)

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if self.embedding_version != MODEL.version:
            raise ValueError("taxonomy_policy_model_mismatch")
        return self


def load_policy(path: Path) -> ConfidencePolicy:
    with path.open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError("taxonomy_policy_limit")
    return ConfidencePolicy.model_validate_json(raw)


def confident(
    hits: list[tuple[TaxonomyPayload, float]],
    policy: ConfidencePolicy,
) -> list[tuple[TaxonomyPayload, float]]:
    """Retain uncertainty; a stale or weak runner-up must never manufacture uniqueness."""
    if not hits or hits[0][1] < policy.minimum_score:
        return []
    if len(hits) == 1 or hits[0][1] - hits[1][1] >= policy.minimum_margin:
        return hits[:1]
    plausible = [
        h
        for h in hits
        if h[1] >= policy.minimum_score and hits[0][1] - h[1] < policy.minimum_margin
    ]
    return plausible[:5] if len(plausible) > 1 else []
