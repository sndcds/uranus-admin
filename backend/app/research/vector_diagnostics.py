"""Bounded, value-redacted diagnostics for metadata-only payload differences."""

import hashlib
from collections.abc import Iterator
from itertools import islice
from typing import Any

from app.research.vector_sync import Plan

_MISSING = object()
MAX_DIAGNOSTIC_POINTS = 20
MAX_DIAGNOSTIC_FIELDS = 40


def _summary(value: Any) -> str:
    if value is _MISSING:
        return "missing"
    if value is None or isinstance(value, (bool, int, float)):
        return repr(value)[:80]
    if isinstance(value, str):
        # Never emit text, URLs, credentials or arbitrary legacy payload values.
        digest = hashlib.sha256(value.encode()).hexdigest()[:16]
        return f"length={len(value)} sha256={digest}"
    if isinstance(value, (list, dict)):
        return f"length={len(value)}"
    return "redacted"


def _differences(desired: Any, stored: Any, path: str = "") -> Iterator[dict[str, str]]:
    if desired == stored:
        return
    if isinstance(desired, dict) and isinstance(stored, dict):
        for key in sorted(desired.keys() | stored.keys()):
            # Only desired keys are application-owned. Old payloads may contain
            # arbitrary keys, so report their presence without leaking their text.
            name = key if key in desired else "<unexpected field>"
            yield from _differences(
                desired.get(key, _MISSING),
                stored.get(key, _MISSING),
                f"{path}.{name}" if path else name,
            )
        return
    if isinstance(desired, list) and isinstance(stored, list) and len(desired) == len(stored):
        for index, (left, right) in enumerate(zip(desired, stored, strict=True)):
            yield from _differences(left, right, f"{path}[{index}]")
        return
    yield {
        "field": path,
        "desired_type": "missing" if desired is _MISSING else type(desired).__name__,
        "qdrant_type": "missing" if stored is _MISSING else type(stored).__name__,
        "desired_summary": _summary(desired),
        "qdrant_summary": _summary(stored),
    }


def metadata_diagnostics(
    plan: Plan, existing: dict[str, dict[str, Any]], *, limit: int = 5
) -> list[dict[str, Any]]:
    """Inspect raw equality failures, including nested fields; never modify either side."""
    if not 1 <= limit <= MAX_DIAGNOSTIC_POINTS:
        raise ValueError("invalid_metadata_diagnostic_limit")
    result = []
    embedded = set(plan.embed)
    for identifier in sorted(plan.desired):
        if (
            identifier in embedded
            or identifier not in existing
            or plan.desired[identifier][1] == existing[identifier]
        ):
            continue
        differences = _differences(plan.desired[identifier][1], existing[identifier])
        fields = list(islice(differences, MAX_DIAGNOSTIC_FIELDS + 1))
        result.append(
            {
                "point_id": identifier,
                "fields": fields[:MAX_DIAGNOSTIC_FIELDS],
                "truncated": len(fields) > MAX_DIAGNOSTIC_FIELDS,
            }
        )
        if len(result) == limit:
            break
    return result
