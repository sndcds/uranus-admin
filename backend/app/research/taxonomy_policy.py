"""Thresholds are an operator-reviewed benchmark artifact, never guessed defaults."""

import hashlib
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator

from app.research.taxonomy import MODEL, Closed, Kind, TaxonomyPayload


class ConfidenceThresholds(Closed):
    minimum_score: float = Field(ge=-1, le=1)
    minimum_margin: float = Field(gt=0, le=2)


class ConfidencePolicy(Closed):
    version: str = Field(pattern=r"^taxonomy-confidence-v2$")
    embedding_version: str
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    benchmark_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    benchmark_path: str = Field(min_length=1, max_length=4096)
    # Null disables an uncalibrated stage; it never supplies guessed thresholds.
    event_type: ConfidenceThresholds | None
    genre: ConfidenceThresholds | None
    cross_level: ConfidenceThresholds | None

    def requested(self, kind: Kind) -> ConfidenceThresholds | None:
        return self.event_type if kind == "event_type" else self.genre

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
    policy = ConfidencePolicy.model_validate_json(raw)
    benchmark = Path(policy.benchmark_path)
    if not benchmark.is_absolute():
        benchmark = path.parent / benchmark
    with benchmark.open("rb") as stream:
        reviewed = stream.read(2_000_001)
    if len(reviewed) > 2_000_000 or hashlib.sha256(reviewed).hexdigest() != policy.benchmark_hash:
        raise ValueError("taxonomy_policy_benchmark_mismatch")
    return policy


def confident(
    hits: list[tuple[TaxonomyPayload, float]],
    policy: ConfidenceThresholds | None,
) -> list[tuple[TaxonomyPayload, float]]:
    """Retain uncertainty; a stale or weak runner-up must never manufacture uniqueness."""
    if policy is None or not hits or hits[0][1] < policy.minimum_score:
        return []
    if len(hits) == 1 or hits[0][1] - hits[1][1] >= policy.minimum_margin:
        return hits[:1]
    plausible = [
        h
        for h in hits
        if h[1] >= policy.minimum_score and hits[0][1] - h[1] < policy.minimum_margin
    ]
    return plausible[:5] if len(plausible) > 1 else []
