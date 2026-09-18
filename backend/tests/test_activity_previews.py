"""Admin next-date selection against the source enum and real PostgreSQL ordering."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.repositories.entities import entity_page
from app.schemas.entities import EntityFilters
from tests.conftest import uid

NOW = datetime(2026, 9, 18, 10, tzinfo=UTC)  # noon in Europe/Berlin
TODAY = date(2026, 9, 18)
EVENT_ID = uid(9000)
STATUSES = ["inherited", "draft", "review", "released", "cancelled", "deferred", "rescheduled"]


def date_id(number):
    return UUID(f"019954ea-0000-7000-8000-{number:012d}")


@pytest.fixture
async def preview(db_connection, settings):
    settings.uranus_api_url = "https://api.kulturbytes.de"
    await db_connection.execute(
        text("""INSERT INTO uranus.event
        (uuid,org_uuid,title,release_status,created_at)
        VALUES (:id,:org,'Next date fixture','draft',:created)"""),
        {"id": EVENT_ID, "org": uid(10), "created": NOW.replace(tzinfo=None) - timedelta(days=1)},
    )

    async def fetch(status, dates, *, now=NOW, upcoming=True):
        await db_connection.execute(
            text("UPDATE uranus.event SET release_status=:status WHERE uuid=:id"),
            {"id": EVENT_ID, "status": status},
        )
        for index, values in enumerate(dates, start=1):
            await db_connection.execute(
                text("""INSERT INTO uranus.event_date
                (uuid,event_uuid,start_date,start_time,all_day,release_status)
                VALUES (:id,:event,:day,:time,:all_day,:status)"""),
                {
                    "id": date_id(index),
                    "event": EVENT_ID,
                    "day": TODAY + timedelta(days=1),
                    "time": time(18),
                    "all_day": False,
                    "status": "inherited",
                    **values,
                },
            )
        page = await entity_page(
            db_connection,
            settings,
            "events",
            EntityFilters(
                q="Next date fixture",
                status=status,
                period="90d",
                temporal="upcoming" if upcoming else None,
            ),
            now,
        )
        assert page.observed_at == now
        assert page.pagination.total == 1
        item = page.items[0]
        assert item.facts.event_dates == len(dates)
        assert item.status == status
        assert item.created_at == NOW - timedelta(days=1)
        return item

    return fetch


@pytest.mark.parametrize("status", ["draft", "review"])
async def test_unpublished_events_select_only_the_nearest_future_date(preview, status):
    days = [-1, 4, 10] if status == "draft" else [-1, 1, 10]
    item = await preview(status, [{"day": TODAY + timedelta(days=day)} for day in days])
    expected_day = TODAY + timedelta(days=days[1])
    assert item.subtitle == f"Nächster Termin: {expected_day:%d.%m.%Y} · 18:00 (Europe/Berlin)"
    assert item.public_url is None


@pytest.mark.parametrize("event_status", STATUSES)
@pytest.mark.parametrize("date_status", STATUSES)
async def test_admin_selection_and_public_link_have_separate_status_boundaries(
    preview, event_status, date_status
):
    item = await preview(event_status, [{"status": date_status, "day": TODAY + timedelta(days=3)}])
    effective_status = event_status if date_status == "inherited" else date_status
    assert item.notice == (
        "Dieser noch unveröffentlichte Event findet schon in 3 Tagen statt."
        if event_status in {"draft", "review"}
        else None
    )
    public_statuses = {"released", "cancelled", "deferred", "rescheduled"}
    public = event_status in public_statuses and effective_status in public_statuses
    prefix = "Nächster öffentlicher Termin" if public else "Nächster Termin"
    assert item.subtitle == f"{prefix}: 21.09.2026 · 18:00 (Europe/Berlin)"
    assert item.public_url == (
        f"https://kulturbytes.de/de/veranstaltung/{EVENT_ID}/{date_id(1)}" if public else None
    )


@pytest.mark.parametrize("status", ["draft", "review", "released"])
@pytest.mark.parametrize(
    ("start_time", "all_day", "expected"),
    [
        (time(18), False, "18.09.2026 · 18:00"),
        (time(11, 59, 59), False, "19.09.2026 · 18:00"),
        (time(12), False, "18.09.2026 · 12:00"),
        (time(1), True, "18.09.2026 · ganztägig"),
        (None, False, "18.09.2026 · Uhrzeit unbekannt"),
    ],
)
async def test_today_uses_existing_local_start_semantics(
    preview, status, start_time, all_day, expected
):
    item = await preview(
        status,
        [{"day": TODAY, "time": start_time, "all_day": all_day}, {}],
    )
    prefix = "Nächster öffentlicher Termin" if status == "released" else "Nächster Termin"
    assert item.subtitle == f"{prefix}: {expected} (Europe/Berlin)"


@pytest.mark.parametrize("status", ["draft", "review"])
@pytest.mark.parametrize("dates", [[], [{"day": TODAY - timedelta(days=1)}]])
async def test_no_future_date_keeps_count_without_date_subtitle(preview, status, dates):
    item = await preview(status, dates, upcoming=False)
    assert item.subtitle is None
    assert item.notice is None
    assert item.public_url is None


async def test_next_date_order_is_date_then_time_nulls_last_then_uuid(preview):
    item = await preview(
        "released",
        [
            {"day": TODAY + timedelta(days=10)},
            {"time": None},
            {"time": time(19)},
            {"id": date_id(50), "time": time(18)},
            {"id": date_id(40), "time": time(18)},
        ],
    )
    assert item.subtitle == "Nächster öffentlicher Termin: 19.09.2026 · 18:00 (Europe/Berlin)"
    assert item.public_url == f"https://kulturbytes.de/de/veranstaltung/{EVENT_ID}/{date_id(40)}"


@pytest.mark.parametrize(
    ("zone", "now"),
    [
        ("Europe/Berlin", datetime(2026, 9, 18, 22, 30, tzinfo=UTC)),
        ("America/New_York", datetime(2026, 9, 19, 3, 30, tzinfo=UTC)),
        ("Europe/Berlin", datetime(2026, 10, 25, 1, 30, tzinfo=UTC)),
    ],
)
async def test_preview_uses_configured_timezone_at_midnight_and_dst(preview, settings, zone, now):
    settings.event_timezone = zone
    local = now.astimezone(ZoneInfo(zone))
    early = local.replace(minute=0).time().replace(tzinfo=None)
    later = local.replace(minute=45).time().replace(tzinfo=None)
    item = await preview(
        "review",
        [{"day": local.date(), "time": early}, {"day": local.date(), "time": later}],
        now=now,
    )
    assert item.subtitle == f"Nächster Termin: {local:%d.%m.%Y} · {later:%H:%M} ({zone})"
    assert item.notice == "Dieser noch unveröffentlichte Event findet heute statt."
    assert item.public_url is None


async def test_released_event_does_not_skip_an_earlier_unpublished_date(preview):
    item = await preview(
        "released",
        [{"status": "review"}, {"day": TODAY + timedelta(days=3), "status": "released"}],
    )
    assert item.subtitle == "Nächster Termin: 19.09.2026 · 18:00 (Europe/Berlin)"
    assert item.public_url is None


async def test_existing_event_subtitle_is_preserved(preview, db_connection):
    await db_connection.execute(
        text("UPDATE uranus.event SET subtitle='Kultur am Hafen' WHERE uuid=:id"),
        {"id": EVENT_ID},
    )
    item = await preview("draft", [{}])
    assert item.subtitle == (
        "Kultur am Hafen · Nächster Termin: 19.09.2026 · 18:00 (Europe/Berlin)"
    )


@pytest.mark.parametrize("status", ["draft", "review"])
@pytest.mark.parametrize(
    ("days", "notice"),
    [
        (0, "Dieser noch unveröffentlichte Event findet heute statt."),
        (1, "Dieser noch unveröffentlichte Event findet bereits morgen statt."),
        (2, "Dieser noch unveröffentlichte Event findet schon in 2 Tagen statt."),
        (3, "Dieser noch unveröffentlichte Event findet schon in 3 Tagen statt."),
        (4, "Dieser noch unveröffentlichte Event findet schon in 4 Tagen statt."),
        (5, "Dieser noch unveröffentlichte Event findet schon in 5 Tagen statt."),
        (6, "Dieser noch unveröffentlichte Event findet schon in 6 Tagen statt."),
        (7, "Dieser noch unveröffentlichte Event findet schon in 7 Tagen statt."),
        (8, None),
        (30, None),
    ],
)
async def test_unpublished_event_notice_uses_seven_calendar_day_window(
    preview, status, days, notice
):
    start = TODAY + timedelta(days=days)
    item = await preview(status, [{"day": start}, {"day": start + timedelta(days=10)}])
    assert item.subtitle == f"Nächster Termin: {start:%d.%m.%Y} · 18:00 (Europe/Berlin)"
    assert item.notice == notice
    assert item.public_url is None


@pytest.mark.parametrize(
    "status", ["released", "cancelled", "deferred", "rescheduled", "inherited"]
)
async def test_other_event_statuses_have_no_unpublished_notice(preview, status):
    item = await preview(status, [{"day": TODAY + timedelta(days=2)}])
    assert item.notice is None
    if status != "inherited":
        assert item.subtitle == "Nächster öffentlicher Termin: 20.09.2026 · 18:00 (Europe/Berlin)"
        assert item.public_url is not None


@pytest.mark.parametrize("status", ["draft", "review"])
@pytest.mark.parametrize(
    ("days", "notice"),
    [
        (0, "Dieser noch unveröffentlichte Event findet heute statt."),
        (1, "Dieser noch unveröffentlichte Event findet bereits morgen statt."),
        (7, "Dieser noch unveröffentlichte Event findet schon in 7 Tagen statt."),
        (8, None),
    ],
)
async def test_notice_day_and_threshold_use_berlin_calendar_at_utc_midnight(
    preview, status, days, notice
):
    now = datetime(2026, 9, 18, 22, 30, tzinfo=UTC)  # Berlin: 19 September, 00:30
    start = date(2026, 9, 19) + timedelta(days=days)
    item = await preview(status, [{"day": start}], now=now)
    assert item.subtitle == f"Nächster Termin: {start:%d.%m.%Y} · 18:00 (Europe/Berlin)"
    assert item.notice == notice
    assert item.public_url is None


async def test_event_date_rows_do_not_receive_parent_event_notice(preview, db_connection, settings):
    from app.repositories.activity_previews import activity_previews

    parent = await preview("draft", [{}])
    assert parent.notice is not None
    key = ("event_date", str(date_id(1)))
    result = await activity_previews(
        db_connection,
        settings,
        [{"entity_type": key[0], "entity_key": key[1]}],
        NOW,
    )
    assert result[key]["notice"] is None
