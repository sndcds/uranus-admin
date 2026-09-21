"""Bound every JSON cell, including its truncation marker. Never use arbitrary repr."""

import json
import math
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

CELL_BYTES = 16 * 1024
RESULT_BYTES = 1024 * 1024
BATCH_BYTES = 64 * 1024


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def cell(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        # Preserve exact PostgreSQL bigint values beyond JavaScript's safe integer range.
        return value if abs(value) <= 9007199254740991 else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        value = str(value)
    if not isinstance(value, str):
        # asyncpg arrays/composites/binary/geometric objects aren't arbitrary repr'd.
        value = "[unsupported result type]"
    # Slice before encoding to bound work even for multi-megabyte source values.
    candidate = value[:CELL_BYTES]
    if len(value) <= CELL_BYTES and len(encode(candidate).encode()) <= CELL_BYTES:
        return candidate
    low, high = 0, len(candidate)
    while low < high:
        mid = (low + high + 1) // 2
        if len(encode({"value": candidate[:mid], "truncated": True}).encode()) <= CELL_BYTES:
            low = mid
        else:
            high = mid - 1
    return {"value": candidate[:low], "truncated": True}
