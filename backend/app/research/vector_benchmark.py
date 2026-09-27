"""Reproducible, unlabelled retrieval exports; quality metrics require real judgments."""

import asyncio
import csv
import json
import math
import os
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.research.vector_documents import EventDocument, content_hash
from app.research.vector_sync import deduplicate
from app.research.vector_transport import Encoder, Qdrant


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9-]{1,50}$")
    query: str = Field(min_length=2, max_length=500)
    language: str = Field(pattern=r"^(de|da|en)$")
    notes: str = Field(max_length=1000)


def questions(path: Path) -> list[Question]:
    if path.stat().st_size > 128_000:
        raise ValueError("benchmark_file_limit")
    items = [Question.model_validate(q) for q in json.loads(path.read_text())]
    if not 1 <= len(items) <= 100 or len({q.id for q in items}) != len(items):
        raise ValueError("invalid_benchmark_questions")
    return items


def save_json(path: Path, value: object) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


def csv_cell(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


async def benchmark(
    qdrant: Qdrant,
    encoder: Encoder,
    documents: list[EventDocument],
    items: list[Question],
    output: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    titles = {str(d.entity_id): d.title for d in documents}
    rows = []
    latencies = []
    for item in items:
        start = perf_counter()
        vector = (await encoder.embed([item.query], query=True))[0]
        limit = 100
        while True:
            hits = await qdrant.search(vector, limit)
            ranked = deduplicate(hits, set(titles), encoder.model)
            if len(ranked) >= 10 or len(hits) < limit or limit == 10000:
                break
            limit = min(limit * 2, 10000)
        elapsed = perf_counter() - start
        latencies.append(elapsed)
        for rank, hit in enumerate(ranked, 1):
            payload = hit["payload"]
            rows.append(
                {
                    "query_id": item.id,
                    "query": item.query,
                    "language": item.language,
                    "model": encoder.model.name,
                    "rank": rank,
                    "entity_id": payload["entity_id"],
                    "event_title": titles[payload["entity_id"]],
                    "score": hit["score"],
                    "chunk_kind": payload["chunk_kind"],
                    "manual_relevance": "",
                    "query_latency_seconds": elapsed,
                }
            )
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True, mode=0o700)
    report = {
        **manifest,
        "query_set_hash": content_hash(
            json.dumps([q.model_dump() for q in items], sort_keys=True, ensure_ascii=False)
        ),
        "query_count": len(items),
        "results_count": len(rows),
        "latency_mean_seconds": mean(latencies),
        "latency_p95_seconds": sorted(latencies)[math.ceil(len(latencies) * 0.95) - 1],
        "quality_metrics": None,
        "quality_note": "Manual relevance is not yet judged.",
        "collection": await qdrant.info(),
    }
    save_json(output / "results.json", rows)
    save_json(output / "report.json", report)
    with os.fdopen(
        os.open(output / "results.csv", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
        "w",
        newline="",
    ) as file:
        columns = [
            "query_id",
            "query",
            "language",
            "model",
            "rank",
            "entity_id",
            "event_title",
            "score",
            "chunk_kind",
            "manual_relevance",
            "query_latency_seconds",
        ]
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: csv_cell(value) for key, value in row.items()} for row in rows)
    return report


def quality_metrics(rows: list[dict[str, Any]]) -> dict[str, float] | None:
    """Evaluate a completely judged top-10 run; never turn unjudged results into zeroes.

    nDCG uses the pooled judged events supplied by the operator. MRR is truncated
    at rank 10. The benchmark docs state this evaluation/coverage limitation.
    """
    if not rows or any(r.get("manual_relevance") in (None, "") for r in rows):
        return None
    qrels: dict[str, dict[str, int]] = {}
    runs: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        raw = row["manual_relevance"]
        if (
            isinstance(raw, bool)
            or not isinstance(raw, (str, int))
            or str(raw) not in {"0", "1", "2"}
        ):
            raise ValueError("invalid_relevance_grade")
        grade = int(raw)
        if grade not in {0, 1, 2}:
            raise ValueError("invalid_relevance_grade")
        previous = qrels.setdefault(row["query_id"], {}).setdefault(row["entity_id"], grade)
        if previous != grade:
            raise ValueError("conflicting_relevance_grade")
        runs.setdefault((row["model"], row["query_id"]), []).append(row)
    metrics: dict[str, list[float]] = {}
    for (model, query), items in runs.items():
        ordered = sorted(items, key=lambda r: int(r["rank"]))
        if (
            len(ordered) > 10
            or [int(r["rank"]) for r in ordered] != list(range(1, len(ordered) + 1))
            or len({r["entity_id"] for r in ordered}) != len(ordered)
        ):
            raise ValueError("invalid_judged_ranking")
        grades = [qrels[query][r["entity_id"]] for r in ordered]
        ideal = sorted(qrels[query].values(), reverse=True)[:10]
        dcg = sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades))
        idcg = sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(ideal))
        for name, value in {
            "precision_at_5": sum(g > 0 for g in grades[:5]) / 5,
            "precision_at_10": sum(g > 0 for g in grades) / 10,
            "mrr_at_10": next((1 / (rank + 1) for rank, g in enumerate(grades) if g > 0), 0),
            "ndcg_at_10": dcg / idcg if idcg else 0,
        }.items():
            metrics.setdefault(model + ":" + name, []).append(value)
    return {key: mean(values) for key, values in metrics.items()}
