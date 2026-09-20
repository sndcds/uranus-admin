"""Active worklists filter in PostgreSQL; historical findings remain stored."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.admin_tables import finding
from app.errors import APIError
from app.schemas.finding import FindingFilters
from app.services import checks
from tests.conftest import uid


async def seed(admin, now, statuses):
    async with admin.begin():
        await admin.execute(
            finding.insert(),
            [
                {
                    "id": f"active-test-{i:03}",
                    "rule": "active_test",
                    "severity": "error" if status == "resolved" else "warning",
                    "entity_type": "venue",
                    "entity_key": str(uid(21)),
                    "field": f"field-{i}",
                    "message": "Synthetic finding",
                    "status": status,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "metadata": {"finding": {"priority_score": 10000 - i}},
                }
                for i, status in enumerate(statuses)
            ],
        )


@pytest.fixture(params=[False, True], ids=["global", "spatial"])
async def read_page(request, admin_store, db_connection, now):
    geometry = None
    if request.param:
        geometry = bytes(
            (
                await db_connection.execute(
                    text("SELECT ST_AsEWKB(ST_MakeEnvelope(9,54,10,55,4326))")
                )
            ).scalar_one()
        )

    async def read(**kwargs):
        filters = FindingFilters(**kwargs)
        return await checks.persisted_page(admin_store, filters, now, db_connection, geometry)

    return read


async def test_active_keeps_every_nonresolved_status_and_matches_counts(
    admin_store, now, read_page
):
    statuses = ["resolved", "open", "in_progress", "snoozed", "exception", "reviewed", "ignored"]
    await seed(admin_store, now, statuses)
    page = await read_page(active_only=True)
    assert [item.status for item in page.items] == statuses[1:]
    counts, _ = await checks.persisted_counts(admin_store)
    assert page.pagination.total == counts.total == 6
    history = await read_page(active_only=False)
    assert history.pagination.total == 7
    assert history.items[0].status == "resolved"
    assert (await read_page()).pagination.total == 7
    assert (await read_page(active_only=True, status="resolved")).pagination.total == 0
    assert (await read_page(active_only=True, status="exception")).pagination.total == 1


async def test_active_filters_before_limit_offset_and_spatial_membership(
    admin_store, now, read_page
):
    await seed(admin_store, now, ["resolved"] * 10 + ["open"] * 4)
    original_membership = checks.spatial_membership

    async def checked_membership(source, identities, polygon):
        batch = list(identities)
        assert len(batch) == 4  # Resolved rows must never reach the membership scan.
        return await original_membership(source, batch, polygon)

    membership = AsyncMock(side_effect=checked_membership)
    with patch.object(checks, "spatial_membership", membership):
        page = await read_page(active_only=True, page_size=4)
    assert len(page.items) == page.pagination.total == 4
    assert page.pagination.pages == 1
    assert all(item.status == "open" for item in page.items)
    # Every in-scope fixture uses the same venue; only four rows may reach the scan.
    if membership.await_count:
        assert membership.await_count == 1
    second = await read_page(active_only=True, page_size=2, page=2)
    assert [item.id for item in second.items] == [item.id for item in page.items[2:]]
    assert second.pagination.total == 4
    assert all(item.status == "resolved" for item in (await read_page(page_size=4)).items)


@pytest.mark.parametrize("initial_active", [False, True])
async def test_cursor_scope_rejects_active_filter_changes(
    admin_store, now, read_page, initial_active
):
    await seed(admin_store, now, ["resolved", "open", "exception", "reviewed"])
    first = await read_page(active_only=initial_active, cursor="start", page_size=1)
    cursor = first.cursor_pagination.next_cursor
    assert cursor
    second = await read_page(active_only=initial_active, cursor=cursor, page_size=1)
    assert second.items[0].id != first.items[0].id
    assert second.pagination.total == (3 if initial_active else 4)
    with pytest.raises(APIError, match="Invalid cursor"):
        await read_page(active_only=not initial_active, cursor=cursor, page_size=1)
