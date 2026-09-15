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


async def test_activity_rich_previews_are_batched_and_safe(db_connection, settings, now):
    from sqlalchemy import event, text

    settings.uranus_api_url = "https://api.kulturbytes.de"
    await db_connection.execute(
        text("UPDATE uranus.venue SET slug='hafenbuehne' WHERE uuid=:id"), {"id": uid(20)}
    )
    await db_connection.execute(text("UPDATE uranus.organization SET city='Flensburg'"))
    await db_connection.execute(
        text(
            "UPDATE uranus.event SET subtitle='Kultur am Hafen', space_uuid=:space WHERE uuid=:id"
        ),
        {"id": uid(30), "space": uid(25)},
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.pluto_image_link"
            "(context,context_uuid,identifier,pluto_image_uuid) VALUES "
            "('event',:event,'main',:image),('organization',:org,'main_logo',:image),"
            "('venue',:venue,'main_photo',:image)"
        ),
        {"event": uid(30), "org": uid(10), "venue": uid(20), "image": uid(60)},
    )
    calls = []

    def capture(*args):
        calls.append(args[2])

    event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        filters = ActivityFilters(from_at=now - timedelta(days=60), to_at=now, page_size=100)
        result = await activity_page(db_connection, settings, filters, now)
        assert len(calls) == 4  # unknown count, total, page, one preview batch
        calls.clear()
        await activity_page(
            db_connection, settings, filters.model_copy(update={"page_size": 1}), now
        )
        assert len(calls) == 4
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)
    rows = {(x.entity_type, x.entity_key): x for x in result.items}
    image_url = f"https://api.kulturbytes.de/api/image/{uid(60)}?width=160&ratio=1%3A1"
    assert rows["organization", str(uid(10))].subtitle == "Flensburg"
    assert rows["organization", str(uid(10))].image_url == image_url
    assert rows["organization", str(uid(10))].public_url is None
    venue = rows["venue", str(uid(20))]
    assert venue.address == "Hafenstraße 3, 24937 Flensburg"
    assert venue.public_url == "https://kulturbytes.de/de/ort/hafenbuehne"
    assert venue.image_url == image_url
    assert rows["space", str(uid(25))].subtitle == "Venue 20"
    assert rows["space", str(uid(25))].image_url is None
    assert "Kultur am Hafen" in rows["event", str(uid(30))].subtitle
    assert rows["event_date", str(uid(42))].image_url == image_url
    assert "Venue 21" in rows["event_date", str(uid(42))].subtitle
    assert "Saal" not in rows["event_date", str(uid(42))].subtitle  # own venue clears event space
    assert "Saal" in rows["event_date", str(uid(40))].subtitle
    assert rows["image", str(uid(60))].subtitle is None  # ambiguous relationship
    serialized = result.model_dump_json()
    for field in (
        "password_hash",
        "activate_token",
        "accept_token",
        "api_import_token",
        "file_name",
        "exif",
        "fixture@example.invalid",
    ):
        assert field not in serialized


async def test_activity_public_routes_require_public_status_and_supported_identifiers(
    db_connection, settings, now
):
    from uuid import UUID

    from sqlalchemy import text

    settings.uranus_api_url = "https://api.kulturbytes.de"
    date_id = UUID("019954ea-0000-7000-8000-000000000042")
    await db_connection.execute(
        text("UPDATE uranus.event_date SET uuid=:new WHERE uuid=:old"),
        {"new": date_id, "old": uid(40)},
    )
    filters = ActivityFilters(entity_type="event_date", entity_key=str(date_id))
    page = await activity_page(db_connection, settings, filters, now)
    assert (
        page.items[0].public_url == f"https://kulturbytes.de/de/veranstaltung/{uid(30)}/{date_id}"
    )
    event_filters = ActivityFilters(entity_type="event", entity_key=str(uid(30)))
    event_page = await activity_page(db_connection, settings, event_filters, now)
    assert event_page.items[0].public_url == page.items[0].public_url
    assert "Nächster öffentlicher Termin" in event_page.items[0].subtitle
    await db_connection.execute(
        text("UPDATE uranus.event_date SET release_status='draft' WHERE uuid=:id"), {"id": date_id}
    )
    assert (await activity_page(db_connection, settings, filters, now)).items[0].public_url is None
    await db_connection.execute(
        text("UPDATE uranus.event SET release_status='draft' WHERE uuid=:id"), {"id": uid(30)}
    )
    assert (await activity_page(db_connection, settings, filters, now)).items[0].public_url is None
    draft_event = (await activity_page(db_connection, settings, event_filters, now)).items[0]
    assert draft_event.public_url is None
    assert not draft_event.subtitle or "Nächster öffentlicher Termin" not in draft_event.subtitle
    settings.uranus_api_url = "http://localhost:8080"
    result = await activity_page(
        db_connection,
        settings,
        ActivityFilters(entity_type="image", timestamp_state="unknown"),
        now,
    )
    assert result.items[0].image_url is None
    assert result.items[0].created_at is None


async def test_activity_unknown_image_with_unique_target_and_invitation_time(
    db_connection, settings, now
):
    from sqlalchemy import text

    settings.uranus_api_url = "https://api.kulturbytes.de/"
    await db_connection.execute(
        text(
            "INSERT INTO uranus.pluto_image_link"
            "(context,context_uuid,identifier,pluto_image_uuid) VALUES "
            "('organization',:org,'main_logo',:image)"
        ),
        {"org": uid(10), "image": uid(61)},
    )
    page = await activity_page(
        db_connection,
        settings,
        ActivityFilters(entity_type="image", organization_id=uid(10), timestamp_state="unknown"),
        now,
    )
    item = page.items[0]
    assert page.pagination.total == 1
    assert item.subtitle == "Organization 10"
    assert item.image_url == f"https://api.kulturbytes.de/api/image/{uid(61)}?width=160&ratio=1%3A1"
    assert item.created_at is None and item.public_url is None
    invited = await activity_page(
        db_connection, settings, ActivityFilters(entity_type="team_membership"), now
    )
    assert invited.items[0].subtitle.startswith("Eingeladen: ")
    assert invited.items[0].status == "invited"
    await db_connection.execute(
        text("UPDATE uranus.organization_member_link SET invited_at=NULL, has_joined=true")
    )
    joined = await activity_page(
        db_connection, settings, ActivityFilters(entity_type="team_membership"), now
    )
    assert joined.items[0].subtitle is None
    assert joined.items[0].status == "joined"
