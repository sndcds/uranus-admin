"""Measured closed-vocabulary calibration. Synthetic test scores are not production evidence."""

import asyncio
import hashlib
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from app.research.taxonomy import (
    MODEL,
    Closed,
    TaxonomyPayload,
    TaxonomyVectorDocument,
    corpus_hash,
    index_payload,
)
from app.research.taxonomy_policy import ConfidencePolicy, confident
from app.research.taxonomy_transport import TaxonomyQdrant, validated_proposals
from app.research.vector_transport import Encoder


class Case(Closed):
    query: str = Field(min_length=1, max_length=200)
    expected: Literal["event_type", "genre", "ambiguous", "unresolved"]
    label: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def target_required(self) -> Self:
        if (self.expected in {"event_type", "genre"}) != (self.label is not None):
            raise ValueError("benchmark_target_required")
        return self


class Benchmark(Closed):
    cases: tuple[Case, ...] = Field(min_length=10, max_length=128)


class Measurement(Closed):
    case: Case
    expected_key: str | None
    hits: tuple[tuple[TaxonomyPayload, float], ...] = Field(max_length=6)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.case.expected in {"event_type", "genre"}) != (self.expected_key is not None):
            raise ValueError("benchmark_target_required")
        if len({p.key for p, _ in self.hits}) != len(self.hits):
            raise ValueError("duplicate_benchmark_candidate")
        if any(not -1 <= score <= 1 for _, score in self.hits):
            raise ValueError("invalid_benchmark_score")
        if self.expected_key:
            matched = [p for p, _ in self.hits if p.key == self.expected_key]
            if any(
                p.kind != self.case.expected or p.canonical_label != self.case.label
                for p in matched
            ):
                raise ValueError("benchmark_target_mismatch")
        return self


class Measurements(Closed):
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    benchmark_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    embedding_version: str
    rows: tuple[Measurement, ...] = Field(min_length=10, max_length=128)


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("benchmark_file_limit")
    return data


async def measure(
    qdrant: TaxonomyQdrant,
    encoder: Encoder,
    docs: list[TaxonomyVectorDocument],
    path: Path,
    output: Path,
) -> None:
    raw = await asyncio.to_thread(read_bounded, path)
    benchmark = Benchmark.model_validate_json(raw)
    digest = corpus_hash(docs)
    if await qdrant.info() is None:
        raise ValueError("taxonomy_index_missing")
    expected = {d.point_id: index_payload(d, digest).model_dump(mode="json") for d in docs}
    if await qdrant.points() != expected:
        raise ValueError("taxonomy_sync_required")
    rows = []
    for case in benchmark.cases:
        keys = [d.key for d in docs if d.kind == case.expected and d.canonical_label == case.label]
        if case.expected in {"event_type", "genre"} and len(keys) != 1:
            raise ValueError("benchmark_target_requires_review")
        vector = (await encoder.embed([case.query], query=True))[0]
        hits = await qdrant.query_taxonomy(vector)
        rows.append(
            Measurement(
                case=case,
                expected_key=keys[0] if keys else None,
                hits=tuple(validated_proposals(hits, digest)),
            )
        )
    values = Measurements(
        corpus_hash=digest,
        benchmark_hash=hashlib.sha256(raw).hexdigest(),
        embedding_version=MODEL.version,
        rows=tuple(rows),
    )
    await asyncio.to_thread(output.write_text, values.model_dump_json(indent=2) + "\n")


def calibrate(values: Measurements) -> ConfidencePolicy:
    if values.embedding_version != MODEL.version:
        raise ValueError("benchmark_model_mismatch")
    rows = [sorted(r.hits, key=lambda h: (-h[1], h[0].key)) for r in values.rows]
    if any(
        p.corpus_hash != values.corpus_hash or not -1 <= score <= 1
        for hits in rows
        for p, score in hits
    ):
        raise ValueError("benchmark_candidate_mismatch")
    # Candidate thresholds derive only from observations. No shipping guessed
    # numeric defaults. Require every reviewed positive AND negative to pass.
    thresholds = sorted({score for hits in rows for _, score in hits}, reverse=True)
    margins = sorted(
        {hits[0][1] - hits[1][1] for hits in rows if len(hits) > 1 and hits[0][1] > hits[1][1]},
        reverse=True,
    )
    if not any(r.expected_key for r in values.rows) or not any(
        r.case.expected == "unresolved" for r in values.rows
    ):
        raise ValueError("benchmark_positive_and_negative_required")
    for threshold in thresholds:
        for margin in margins:
            policy = ConfidencePolicy(
                version="taxonomy-confidence-v1",
                embedding_version=MODEL.version,
                corpus_hash=values.corpus_hash,
                benchmark_hash=values.benchmark_hash,
                minimum_score=threshold,
                minimum_margin=margin,
            )
            success = True
            for row, hits in zip(values.rows, rows, strict=True):
                selected = confident(hits, policy)
                if row.expected_key:
                    passed = len(selected) == 1 and selected[0][0].key == row.expected_key
                elif row.case.expected == "ambiguous":
                    passed = len(selected) > 1
                else:
                    passed = not selected
                if not passed:
                    success = False
                    break
            if success:
                return policy
    raise ValueError("benchmark_has_no_safe_thresholds")


def calibrate_file(path: Path, output: Path) -> None:
    policy = calibrate(Measurements.model_validate_json(read_bounded(path)))
    output.write_text(policy.model_dump_json(indent=2) + "\n")
