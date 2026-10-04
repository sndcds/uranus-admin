"""Measured exact-first, kind-aware calibration; synthetic scores are not live evidence."""

import asyncio
import hashlib
import math
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from app.repositories.research_resolution import taxonomy_match_indices
from app.research.taxonomy import (
    MODEL,
    Closed,
    Kind,
    TaxonomyPayload,
    TaxonomyVectorDocument,
    corpus_hash,
    index_payload,
)
from app.research.taxonomy_policy import ConfidencePolicy, ConfidenceThresholds, confident
from app.research.taxonomy_transport import TaxonomyQdrant, validated_proposals
from app.research.vector_transport import Encoder


class Case(Closed):
    query: str = Field(min_length=1, max_length=200)
    requested_kind: Kind
    expected: Literal["event_type", "genre", "ambiguous", "unresolved", "exact_or_ambiguous"]
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
    cross_hits: tuple[tuple[TaxonomyPayload, float], ...] = Field(max_length=6)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.case.expected in {"event_type", "genre"}) != (self.expected_key is not None):
            raise ValueError("benchmark_target_required")
        for hits, same_kind in ((self.hits, True), (self.cross_hits, False)):
            if len({p.key for p, _ in hits}) != len(hits):
                raise ValueError("duplicate_benchmark_candidate")
            if any(
                not -1 <= score <= 1 or (p.kind == self.case.requested_kind) != same_kind
                for p, score in hits
            ):
                raise ValueError("invalid_benchmark_candidate")
        return self


class Measurements(Closed):
    version: Literal["taxonomy-measurements-v2"]
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    benchmark_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    embedding_version: str
    documents: tuple[TaxonomyVectorDocument, ...] = Field(max_length=4096)
    rows: tuple[Measurement, ...] = Field(min_length=10, max_length=128)


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("benchmark_file_limit")
    return data


def exact_matches(case: Case, docs: list[TaxonomyVectorDocument]) -> list[str]:
    other: Kind = "genre" if case.requested_kind == "event_type" else "event_type"
    for kind in (case.requested_kind, other):
        choices = sorted(
            (d for d in docs if d.kind == kind),
            key=lambda d: (d.canonical_label.lower(), d.identity),
        )
        matches = taxonomy_match_indices(case.query, [d.canonical_label for d in choices])
        if matches:
            return [choices[i].key for i in matches]
    return []


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
        same, cross = [], []
        if not exact_matches(case, docs):
            vector = (await encoder.embed([case.query], query=True))[0]
            other: Kind = "genre" if case.requested_kind == "event_type" else "event_type"
            same = validated_proposals(
                await qdrant.query_taxonomy(vector, expected_kind=case.requested_kind),
                digest,
                expected_kind=case.requested_kind,
            )
            cross = validated_proposals(
                await qdrant.query_taxonomy(vector, expected_kind=other),
                digest,
                expected_kind=other,
            )
        rows.append(
            Measurement(
                case=case,
                expected_key=keys[0] if keys else None,
                hits=tuple(same),
                cross_hits=tuple(cross),
            )
        )
    values = Measurements(
        version="taxonomy-measurements-v2",
        corpus_hash=digest,
        benchmark_hash=hashlib.sha256(raw).hexdigest(),
        embedding_version=MODEL.version,
        documents=tuple(docs),
        rows=tuple(rows),
    )
    await asyncio.to_thread(output.write_text, values.model_dump_json(indent=2) + "\n")


def passes(row: Measurement, keys: tuple[str, ...] | list[str], *, exact: bool = False) -> bool:
    if row.expected_key:
        return list(keys) == [row.expected_key]
    if row.case.expected == "exact_or_ambiguous":
        return bool(keys) if exact else len(keys) > 1
    if row.case.expected == "ambiguous":
        return len(keys) > 1
    return not keys


def options(
    rows: list[list[tuple[TaxonomyPayload, float]]],
) -> list[tuple[ConfidenceThresholds | None, tuple[tuple[str, ...], ...]]]:
    # Exact boundaries and their next representable values cover strict versus
    # inclusive decisions. Every candidate derives from actual observed scores.
    scores = {s for hits in rows for _, s in hits}
    gaps = {hits[0][1] - s for hits in rows for _, s in hits[1:] if hits[0][1] > s}
    thresholds = sorted(
        scores | {math.nextafter(s, math.inf) for s in scores if s < 1}, reverse=True
    )
    margins = sorted(gaps | {math.nextafter(g, math.inf) for g in gaps if g < 2}, reverse=True)
    result: list[tuple[ConfidenceThresholds | None, tuple[tuple[str, ...], ...]]] = []
    seen = set()
    for threshold in thresholds:
        for margin in margins:
            policy = ConfidenceThresholds(minimum_score=threshold, minimum_margin=margin)
            signature = tuple(tuple(p.key for p, _ in confident(h, policy)) for h in rows)
            if signature not in seen:
                seen.add(signature)
                result.append((policy, signature))
    # An uncalibrated stage is explicitly disabled, never assigned defaults.
    result.append((None, tuple(() for _ in rows)))
    return result


def calibrate(values: Measurements, benchmark_path: Path) -> ConfidencePolicy:
    raw = read_bounded(benchmark_path)
    reviewed = Benchmark.model_validate_json(raw)
    if hashlib.sha256(raw).hexdigest() != values.benchmark_hash or reviewed.cases != tuple(
        r.case for r in values.rows
    ):
        raise ValueError("benchmark_review_mismatch")
    if values.embedding_version != MODEL.version:
        raise ValueError("benchmark_model_mismatch")
    docs = list(values.documents)
    if corpus_hash(docs) != values.corpus_hash or len({d.key for d in docs}) != len(docs):
        raise ValueError("benchmark_corpus_mismatch")
    canonical = {d.key: index_payload(d, values.corpus_hash) for d in docs}
    pending = []
    for row in values.rows:
        targets = [
            d.key
            for d in docs
            if d.kind == row.case.expected and d.canonical_label == row.case.label
        ]
        if row.expected_key and targets != [row.expected_key]:
            raise ValueError("benchmark_target_mismatch")
        for payload, _ in (*row.hits, *row.cross_hits):
            if canonical.get(payload.key) != payload:
                raise ValueError("benchmark_candidate_mismatch")
        exact = exact_matches(row.case, docs)
        if exact:
            if row.hits or row.cross_hits or not passes(row, exact, exact=True):
                raise ValueError("benchmark_exact_requires_review")
        else:
            pending.append(row)
    if not any(r.expected_key for r in pending) or not any(
        r.case.expected == "unresolved" for r in pending
    ):
        raise ValueError("benchmark_positive_and_negative_required")
    same = [sorted(r.hits, key=lambda h: (-h[1], h[0].key)) for r in pending]
    cross = [sorted(r.cross_hits, key=lambda h: (-h[1], h[0].key)) for r in pending]
    kinds: tuple[Kind, ...] = ("event_type", "genre")
    indices = {
        kind: [i for i, r in enumerate(pending) if r.case.requested_kind == kind] for kind in kinds
    }
    candidates = {kind: options([same[i] for i in indices[kind]]) for kind in kinds}
    # Prefer no cross-level authorization when it has no reviewed positive evidence.
    cross_options = options(cross)
    for cross_policy, cross_selected in [cross_options[-1], *cross_options[:-1]]:
        chosen: dict[Kind, ConfidenceThresholds | None] = {}
        used_cross = False
        for kind in kinds:
            for policy, selected in candidates[kind]:
                if policy is not None and not any(
                    len(keys) == 1 and pending[i].expected_key == keys[0]
                    for i, keys in zip(indices[kind], selected, strict=True)
                ):
                    continue
                if all(
                    passes(pending[i], keys or cross_selected[i])
                    for i, keys in zip(indices[kind], selected, strict=True)
                ):
                    chosen[kind] = policy
                    used_cross |= any(
                        not keys and len(cross_selected[i]) == 1 and pending[i].expected_key
                        for i, keys in zip(indices[kind], selected, strict=True)
                    )
                    break
            else:
                break
        if len(chosen) == 2 and (cross_policy is None or used_cross):
            return ConfidencePolicy(
                version="taxonomy-confidence-v2",
                embedding_version=MODEL.version,
                corpus_hash=values.corpus_hash,
                benchmark_hash=values.benchmark_hash,
                benchmark_path=str(benchmark_path.resolve()),
                event_type=chosen["event_type"],
                genre=chosen["genre"],
                cross_level=cross_policy,
            )
    raise ValueError("benchmark_has_no_safe_thresholds")


def calibrate_file(path: Path, output: Path, benchmark_path: Path) -> None:
    policy = calibrate(Measurements.model_validate_json(read_bounded(path)), benchmark_path)
    output.write_text(policy.model_dump_json(indent=2) + "\n")
