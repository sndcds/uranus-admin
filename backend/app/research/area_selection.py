"""Shared bounded selection for semantic area filters."""

from uuid import UUID

MAX_AREA_IDS = 50


def normalize_area_ids(
    area_id: UUID | None = None, area_ids: list[UUID] | None = None
) -> list[UUID] | None:
    if area_id is not None and area_ids is not None:
        raise ValueError("conflicting_area_filters")
    if area_ids is not None:
        if not 1 <= len(area_ids) <= MAX_AREA_IDS:
            raise ValueError("invalid_area_count")
        return list(dict.fromkeys(area_ids))
    return [area_id] if area_id is not None else None
