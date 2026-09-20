"""Bounded Source-only membership evaluation; no admin joins or provider requests."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repositories.query import ReadQuery
from app.repositories.spatial import SPATIAL_TYPES, spatial_predicate
from app.schemas.finding import Finding

MEMBERSHIP_BATCH_SIZE = 500


def membership_query(kind: str, ids: list[UUID], geo_scope_wkb: bytes) -> ReadQuery:
    if kind not in SPATIAL_TYPES:
        raise ValueError("Unknown spatial entity kind")
    return ReadQuery(
        text(
            "SELECT a.entity_key FROM unnest(CAST(:ids AS uuid[])) a(entity_key) WHERE "
            + spatial_predicate(kind, key_expression="a.entity_key")
        ),
        {"ids": ids, "geo_scope_wkb": geo_scope_wkb},
    )


async def spatial_membership(
    source: AsyncConnection, identities: Iterable[tuple[str, str]], geo_scope_wkb: bytes
) -> set[tuple[str, str]]:
    """Caller supplies a bounded batch. Preserve original keys, reject technical keys safely."""
    grouped: dict[str, dict[UUID, set[str]]] = {}
    for kind, key in identities:
        if kind not in SPATIAL_TYPES:
            continue
        try:
            identity = UUID(key)
        except ValueError:
            continue
        grouped.setdefault(kind, {}).setdefault(identity, set()).add(key)
    eligible: set[tuple[str, str]] = set()
    for kind, keys in grouped.items():
        ids = list(keys)
        for start in range(0, len(ids), MEMBERSHIP_BATCH_SIZE):
            rows = await source.execute(
                membership_query(
                    kind, ids[start : start + MEMBERSHIP_BATCH_SIZE], geo_scope_wkb
                ).statement,
                membership_query(
                    kind, ids[start : start + MEMBERSHIP_BATCH_SIZE], geo_scope_wkb
                ).parameters,
            )
            for identity in rows.scalars():
                eligible.update((kind, key) for key in keys[identity])
    return eligible


async def filter_live_findings(
    source: AsyncConnection, items: list[Finding], geo_scope_wkb: bytes | None
) -> list[Finding]:
    if geo_scope_wkb is None:
        return items
    result: list[Finding] = []
    for start in range(0, len(items), MEMBERSHIP_BATCH_SIZE):
        batch = items[start : start + MEMBERSHIP_BATCH_SIZE]
        eligible = await spatial_membership(
            source, ((item.entity_type, item.entity_key) for item in batch), geo_scope_wkb
        )
        result.extend(item for item in batch if (item.entity_type, item.entity_key) in eligible)
    return result
