from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.repositories.activity import activity_page
from app.schemas.activity import ActivityFilters
from tests.conftest import uid


def test_time_filters_require_aware_instants_and_honest_unknowns():
    for values in [
        {"from_at": "2026-09-01T00:00:00"},
        {"timestamp_state": "unknown", "period": "7d"},
        {"period": "today", "from_at": "2026-09-01T00:00:00Z"},
        {"from_at": "2026-09-02T00:00:00Z", "to_at": "2026-09-01T00:00:00Z"},
    ]:
        with pytest.raises(ValidationError):
            ActivityFilters(**values)


async def test_activity_all_sources_pagination_and_unknown(db_connection, settings, now):
    filters = ActivityFilters(from_at=now - timedelta(days=60), to_at=now, page_size=100)
    result = await activity_page(db_connection, settings, filters, now)
    assert result.pagination.total == 23
    assert {x.entity_type for x in result.items} == {
        "organization",
        "venue",
        "space",
        "event",
        "event_date",
        "user",
        "partner_request",
        "team_membership",
        "image",
    }
    assert all(x.created_at is not None for x in result.items)
    assert result.unknown_timestamp_count == 1
    assert len({(x.entity_type, x.entity_key) for x in result.items}) == 23
    first = await activity_page(
        db_connection, settings, filters.model_copy(update={"page_size": 1}), now
    )
    second = await activity_page(
        db_connection, settings, filters.model_copy(update={"page_size": 1, "page": 2}), now
    )
    assert first.items[0] == result.items[0] and second.items[0] == result.items[1]
    unknown = await activity_page(
        db_connection, settings, ActivityFilters(timestamp_state="unknown"), now
    )
    assert len(unknown.items) == 1 and unknown.items[0].created_at is None
    membership = next(x for x in result.items if x.entity_type == "team_membership")
    assert membership.entity_key == f"membership:{uid(10)}:{uid(1)}"
    assert "joined_at" not in membership.model_dump()
    assert "last_login" not in str(result.model_dump())


async def test_activity_filters(db_connection, settings, now):
    result = await activity_page(
        db_connection, settings, ActivityFilters(entity_type="user", organization_id=uid(10)), now
    )
    assert len(result.items) == 1 and result.items[0].organization_id is None
    result = await activity_page(
        db_connection,
        settings,
        ActivityFilters(entity_type="partner_request", organization_id=uid(11)),
        now,
    )
    assert len(result.items) == 1
    result = await activity_page(
        db_connection, settings, ActivityFilters(entity_key=str(uid(30))), now
    )
    assert result.items[0].entity_type == "event"  # Old event remains directly navigable.
