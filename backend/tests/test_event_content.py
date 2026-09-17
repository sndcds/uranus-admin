from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import event, text

from app.schemas.event_content import EventContentFilters
from app.services.event_content import get_event_content
from app.services.periods import period_window
from tests.conftest import uid

NOW = datetime(2026, 9, 17, 12, tzinfo=UTC)


@pytest.fixture
async def content_source(db_connection):
    await db_connection.execute(text("TRUNCATE uranus.event CASCADE"))
    for i in range(10):
        await db_connection.execute(
            text(
                "INSERT INTO uranus.event "
                "(uuid,title,org_uuid,created_at,release_status,categories) "
                "VALUES (:id,'Content fixture',:org,:stamp,"
                "CAST(:status AS uranus.event_release_status),:categories)"
            ),
            {
                "id": uid(10000 + i),
                "org": uid(10),
                "stamp": (NOW - timedelta(hours=1)).replace(tzinfo=None),
                "status": "released" if i < 8 else "draft" if i == 8 else "review",
                "categories": [1, 1, 2, None]
                if i == 0
                else [1]
                if i == 1
                else [3]
                if i < 8
                else []
                if i == 8
                else None,
            },
        )
        if i < 9:
            await db_connection.execute(
                text("INSERT INTO uranus.event_type_link VALUES (:id,1,:genre)"),
                {"id": uid(10000 + i), "genre": 4 if i < 6 else 0},
            )
    await db_connection.execute(
        text("INSERT INTO uranus.event_type_link VALUES (:id,1,5),(:id,2,4),(:id,2,0)"),
        {"id": uid(10000)},
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event_category VALUES "
            "(1,'en','Music',NULL),(1,'de','Musik',NULL),(1,'de','Musik',NULL),"
            "(2,'en','Family',NULL),(3,'fr','Culture',NULL),(3,'da','Kultur',NULL)"
        )
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event_type VALUES "
            "(1,'en','Concert',NULL),(1,'de','Konzert',NULL),(2,'de','Workshop',NULL)"
        )
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.genre_type VALUES "
            "('Rock',4,1,'de'),('Rock English',4,1,'en'),('Rock',4,1,'de'),"
            "('Anderes Rock',4,2,'de'),('Should not count',0,1,'de')"
        )
    )
    return db_connection


async def test_distinct_multi_assignments_coverage_language_and_genre_identity(
    content_source, settings
):
    result = await get_event_content(
        content_source, settings, EventContentFilters(period="all"), NOW
    )
    assert result.event_count == 10
    assert result.coverage.categories.model_dump() == {
        "events_with_assignment": 8,
        "events_without_assignment": 2,
        "coverage_percent": 80.0,
    }
    assert result.coverage.genres.coverage_percent == 60
    assert result.coverage.genres.events_without_assignment == 4
    assert result.coverage.event_types.coverage_percent == 90
    categories = {r.id: r for r in result.categories.items}
    assert categories["1"].event_count == 2 and categories["1"].name == "Musik"
    assert categories["1"].event_share_percent == 20
    assert categories["2"].name == "Family" and categories["2"].event_count == 1
    assert categories["3"].name == "Kultur"
    types = {r.id: r for r in result.event_types.items}
    assert types["1"].event_count == 9 and types["2"].event_count == 1
    genres = {r.id: r for r in result.genres.items}
    assert set(genres) == {"1:4", "1:5", "2:4"}
    assert genres["1:4"].event_count == 6 and genres["1:4"].name == "Konzert · Rock"
    assert genres["2:4"].event_count == 1 and genres["2:4"].name == "Workshop · Anderes Rock"
    assert genres["1:5"].name == "Konzert · Genre 5"
    assert result.from_at is None and result.to_at is None and result.comparison is None


@pytest.mark.parametrize(
    "status,total,category_coverage",
    [(None, 10, 80), ("released", 8, 100), ("draft", 1, 0), ("review", 1, 0)],
)
async def test_status_uses_same_base_for_totals_and_rankings(
    content_source, settings, status, total, category_coverage
):
    result = await get_event_content(
        content_source, settings, EventContentFilters(period="7d", status=status), NOW
    )
    assert result.event_count == total
    assert result.coverage.categories.coverage_percent == category_coverage
    assert all(item.event_count <= total for item in result.categories.items)


@pytest.mark.parametrize("period", ["today", "24h", "7d", "30d", "90d", "all"])
@pytest.mark.parametrize("month", [1, 7])
@pytest.mark.parametrize("zone", ["UTC", "Europe/Berlin"])
async def test_period_boundaries_and_source_timezone(content_source, settings, period, month, zone):
    settings.uranus_timestamp_timezone = zone
    now = NOW.replace(month=month)
    window = period_window(period if period != "all" else "90d", now, "Europe/Berlin")
    stamps = [
        now - timedelta(hours=1),
        now - timedelta(hours=12),
        now - timedelta(days=3),
        now - timedelta(days=20),
        now - timedelta(days=60),
        now - timedelta(days=120),
        window.start,
        window.start - timedelta(microseconds=1),
        now,
        now + timedelta(days=1),
    ]
    for i, stamp in enumerate(stamps):
        await content_source.execute(
            text(
                "UPDATE uranus.event SET created_at=:stamp,modified_at=:modified,"
                "release_date=:day WHERE uuid=:id"
            ),
            {
                "stamp": stamp.astimezone(ZoneInfo(zone)).replace(tzinfo=None),
                "id": uid(10000 + i),
                "modified": now.replace(tzinfo=None),
                "day": now.date(),
            },
        )
    result = await get_event_content(
        content_source, settings, EventContentFilters(period=period), now
    )
    assert result.event_count == sum(
        period == "all" or window.start <= stamp < now for stamp in stamps
    )
    assert all(r.event_count <= result.event_count for r in result.genres.items)


@pytest.mark.parametrize("higher", [2, 11])
async def test_compare_uses_all_previous_ranks_and_deterministic_ties(
    content_source, settings, higher
):
    # New ranking id 1 is behind eleven old assignments, outside the prior top ten.
    await content_source.execute(text("UPDATE uranus.event SET categories=ARRAY[1]"))
    for i in range(higher + 1):
        await content_source.execute(
            text(
                "INSERT INTO uranus.event (uuid,title,org_uuid,created_at,categories) "
                "VALUES (:id,'Previous',:org,:stamp,:categories)"
            ),
            {
                "id": uid(11000 + i),
                "org": uid(10),
                "stamp": (NOW - timedelta(days=8)).replace(tzinfo=None),
                "categories": [1] if i == higher else list(range(20, 20 + higher)),
            },
        )
    result = await get_event_content(
        content_source, settings, EventContentFilters(period="7d", compare="previous"), NOW
    )
    item = result.categories.items[0]
    assert item.id == "1" and item.rank == 1 and item.previous_rank == higher + 1
    assert item.rank_delta == higher and item.count_delta == 9
    assert item.previous_event_count == 1 and item.event_count == 10
    assert item.previous_share_percent == round(100 / (higher + 1), 2)
    assert item.share_delta_percentage_points == round(100 - round(100 / (higher + 1), 2), 2)
    assert result.comparison.event_count == higher + 1
    assert result.comparison.to_at == result.from_at
    assert result.comparison.to_at - result.comparison.from_at == result.to_at - result.from_at
    for ranking in (result.categories, result.genres, result.event_types):
        assert len(ranking.items) <= 10
    # Full range has 12 identities, but just ten ordered rows are returned.
    all_data = await get_event_content(
        content_source, settings, EventContentFilters(period="all"), NOW
    )
    assert all_data.categories.distinct_assignment_count == higher + 1
    assert len(all_data.categories.items) == min(10, higher + 1)
    assert (
        all_data.categories.items
        == (
            await get_event_content(
                content_source, settings, EventContentFilters(period="all"), NOW
            )
        ).categories.items
    )


async def test_zero_events_finite_results_and_one_select(content_source, settings):
    statements = []

    def capture(conn, cursor, statement, params, context, many):
        statements.append(statement.strip())

    event.listen(content_source.sync_connection, "before_cursor_execute", capture)
    try:
        result = await get_event_content(
            content_source,
            settings,
            EventContentFilters(period="today", status="cancelled", compare="previous"),
            NOW,
        )
    finally:
        event.remove(content_source.sync_connection, "before_cursor_execute", capture)
    assert len(statements) == 1 and statements[0].startswith("WITH")
    assert result.event_count == 0 and result.comparison.event_count == 0
    assert result.categories.items == [] and result.genres.items == []
    assert result.coverage.categories.coverage_percent == 0
    assert result.coverage.categories.events_without_assignment == 0


@pytest.mark.parametrize(
    "query",
    [
        {"period": "custom"},
        {"period": "unknown"},
        {"period": "all", "compare": "previous"},
        {"status": "inherited"},
        {"status": "bad"},
        {"compare": "true"},
        {"from_at": NOW},
    ],
)
def test_strict_filters(query):
    with pytest.raises(ValidationError):
        EventContentFilters.model_validate(query)


async def test_endpoint_auth_validation_and_read_only(db_client, headers, settings):
    path = "/api/v1/statistics/events/content"
    assert (await db_client.get(path)).status_code == 401
    for query in ["period=7d&compare=previous", "period=today&compare=previous", "period=all"]:
        response = await db_client.get(path + "?" + query, headers=headers)
        assert response.status_code == 200, response.text
        assert "password" not in response.text and "email" not in response.text
    for query in [
        "period=bad",
        "period=all&compare=previous",
        "status=inherited",
        "from_at=2026-01-01",
    ]:
        assert (await db_client.get(path + "?" + query, headers=headers)).status_code == 422
    settings.uranus_timestamp_timezone = None
    assert (await db_client.get(path, headers=headers)).status_code == 503


async def test_event_shares_can_exceed_one_hundred_percent(content_source, settings):
    await content_source.execute(text("UPDATE uranus.event SET categories=ARRAY[1,1,2]"))
    result = await get_event_content(
        content_source, settings, EventContentFilters(period="7d"), NOW
    )
    assert [item.event_count for item in result.categories.items] == [10, 10]
    assert sum(item.event_share_percent for item in result.categories.items) == 200
    assert result.coverage.categories.coverage_percent == 100
    assert result.categories.distinct_assignment_count == 2


async def test_missing_and_multilingual_type_genre_labels(content_source, settings):
    await content_source.execute(
        text(
            "INSERT INTO uranus.event_type VALUES "
            "(3,'en','English type',NULL),(4,'fr','French type',NULL),(4,'da','Danish type',NULL)"
        )
    )
    await content_source.execute(
        text(
            "INSERT INTO uranus.genre_type VALUES "
            "('English genre',9,3,'en'),('French genre',9,4,'fr'),('Danish genre',9,4,'da')"
        )
    )
    await content_source.execute(
        text("INSERT INTO uranus.event_type_link VALUES (:id,3,9),(:id,4,9),(:id,999,9)"),
        {"id": uid(10000)},
    )
    await content_source.execute(
        text("UPDATE uranus.event SET categories=ARRAY[999] WHERE uuid=:id"), {"id": uid(10000)}
    )
    result = await get_event_content(
        content_source, settings, EventContentFilters(period="7d"), NOW
    )
    genres = {item.id: item.name for item in result.genres.items}
    assert genres["3:9"] == "English type · English genre"
    assert genres["4:9"] == "Danish type · Danish genre"
    assert genres["999:9"] == "Event-Typ 999 · Genre 9"
    assert (
        next(item for item in result.categories.items if item.id == "999").name == "Kategorie 999"
    )
