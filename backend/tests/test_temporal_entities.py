from datetime import UTC, date, datetime, time

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import event, text

from app.api import entities as api
from app.database import get_connection
from app.main import create_app
from app.repositories.entity_search import entity_search
from app.repositories.temporal import EFFECTIVE_EVENT_DATE_END_SQL
from app.schemas.entities import EntityFilters, EntitySearchFilters
from tests.conftest import uid

NOW = datetime(2026, 3, 29, 10, tzinfo=UTC)  # noon Berlin, DST transition day
TODAY = date(2026, 3, 29)
YESTERDAY = date(2026, 3, 28)
TOMORROW = date(2026, 3, 30)
CASES = {
    "yesterday": ([{"start_date": YESTERDAY, "start_time": time(15)}], {"past"}),
    "tomorrow": ([{"start_date": TOMORROW}], {"upcoming"}),
    "later": ([{"start_time": time(13)}], {"upcoming"}),
    "earlier": ([{"start_time": time(11)}], {"past"}),
    "running": ([{"start_time": time(11), "end_date": TODAY, "end_time": time(13)}], {"upcoming"}),
    "all_day_today": (
        [{"all_day": True, "start_time": time(1), "end_time": time(2)}],
        {"upcoming"},
    ),
    "all_day_yesterday": ([{"all_day": True, "start_date": YESTERDAY}], {"past"}),
    "multi_day": ([{"start_date": YESTERDAY, "end_date": TOMORROW}], {"upcoming"}),
    "mixed": ([{"start_date": YESTERDAY}, {"start_date": TOMORROW}], {"past", "upcoming"}),
    "no_dates": ([], set()),
    "missing_start_time": ([{}], {"past"}),
    "end_date_without_time": ([{"start_date": YESTERDAY, "end_date": TODAY}], {"upcoming"}),
    "end_time_only": ([{"start_time": time(11), "end_time": time(13)}], {"upcoming"}),
    "exact_end": ([{"start_time": time(11), "end_time": time(12)}], {"upcoming"}),
    "just_past": ([{"start_time": time(11), "end_time": time(11, 59, 59, 999999)}], {"past"}),
    "no_events": ([], set()),
}
KINDS = [
    ("event", "events", 3000),
    ("organization", "organizations", 1000),
    ("venue", "venues", 2000),
    ("space", "spaces", 4000),
]


@pytest.fixture
async def temporal_client(db_connection, settings, monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return NOW

    monkeypatch.setattr(api, "datetime", Clock)
    for index, (name, (dates, _)) in enumerate(CASES.items()):
        values = {
            "org": uid(1000 + index),
            "venue": uid(2000 + index),
            "event": uid(3000 + index),
            "space": uid(4000 + index),
            "name": f"Temporal {name}",
        }
        await db_connection.execute(
            text("INSERT INTO uranus.organization (uuid,name) VALUES (:org,:name)"), values
        )
        await db_connection.execute(
            text(
                "INSERT INTO uranus.venue (uuid,org_uuid,name,scope) "
                "VALUES (:venue,:org,:name,'organization')"
            ),
            values,
        )
        await db_connection.execute(
            text("INSERT INTO uranus.space (uuid,venue_uuid,name) VALUES (:space,:venue,:name)"),
            values,
        )
        if name == "no_events":
            continue
        await db_connection.execute(
            text("""INSERT INTO uranus.event
            (uuid,org_uuid,venue_uuid,space_uuid,title,release_status,created_at)
            VALUES (:event,:org,:venue,:space,:name,'released','2000-01-01')"""),
            values,
        )
        for n, row in enumerate(dates):
            await db_connection.execute(
                text("""INSERT INTO uranus.event_date
                (uuid,event_uuid,start_date,start_time,end_date,end_time,all_day)
                VALUES (:id,:event,:start_date,:start_time,:end_date,:end_time,:all_day)"""),
                {
                    "id": uid(10000 + index * 10 + n),
                    "event": values["event"],
                    "start_date": TODAY,
                    "start_time": None,
                    "end_date": None,
                    "end_time": None,
                    "all_day": None,
                    **row,
                },
            )

    async def connection():
        yield db_connection

    app = create_app(settings)
    app.dependency_overrides[get_connection] = connection
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.integration
@pytest.mark.parametrize("kind,section,base", KINDS)
@pytest.mark.parametrize("temporal", ["upcoming", "past", None])
async def test_consistent_end_semantics_on_both_endpoints(
    temporal_client, headers, kind, section, base, temporal
):
    expected = {
        str(uid(base + index))
        for index, (name, (_, matches)) in enumerate(CASES.items())
        if (temporal is None or temporal in matches)
        and not (kind == "event" and name == "no_events")
    }
    for path, extra in (
        (section, {"page_size": 100}),
        ("entity-search", {"entity_type": kind, "limit": 20}),
    ):
        response = await temporal_client.get(
            f"/api/v1/{path}",
            headers=headers,
            params={"q": "Temporal", **extra, **({"temporal": temporal} if temporal else {})},
        )
        assert response.status_code == 200, response.text
        assert {item["entity_key"] for item in response.json()["items"]} == expected
        if path == section:
            assert response.json()["pagination"]["total"] == len(expected)


@pytest.mark.integration
@pytest.mark.parametrize(
    "venue_override,space_override", [(None, None), (2001, None), (2001, 4001), (None, 4001)]
)
async def test_effective_location_inheritance(
    temporal_client, db_connection, headers, venue_override, space_override
):
    # Only the date of this org participates, so no other event can mask an incorrect inheritance.
    await db_connection.execute(
        text("""UPDATE uranus.event_date SET venue_uuid=:venue,space_uuid=:space,
        start_date=:tomorrow WHERE event_uuid=:event"""),
        {
            "venue": uid(venue_override) if venue_override else None,
            "space": uid(space_override) if space_override else None,
            "event": uid(3000),
            "tomorrow": TOMORROW,
        },
    )
    expected_venue = venue_override or 2000
    expected_space = space_override if venue_override else (space_override or 4000)
    for kind, section, expected in [
        ("venue", "venues", expected_venue),
        ("space", "spaces", expected_space),
    ]:
        # All candidate entities must belong to org1000 for organization_id's entity scope.
        await db_connection.execute(
            text("UPDATE uranus.venue SET org_uuid=:org WHERE uuid=:venue"),
            {"org": uid(1000), "venue": uid(2001)},
        )
        # Remove dates of the second event to isolate the overridden date.
        await db_connection.execute(
            text("DELETE FROM uranus.event_date WHERE event_uuid=:event"), {"event": uid(3001)}
        )
        for path in (section, "entity-search"):
            for temporal, ids in [
                ("upcoming", {str(uid(expected))} if expected else set()),
                ("past", set()),
            ]:
                response = await temporal_client.get(
                    f"/api/v1/{path}",
                    headers=headers,
                    params={
                        "q": "Temporal",
                        "temporal": temporal,
                        "organization_id": str(uid(1000)),
                        **({"entity_type": kind} if path == "entity-search" else {}),
                    },
                )
                assert response.status_code == 200, response.text
                assert {item["entity_key"] for item in response.json()["items"]} == ids


@pytest.mark.integration
async def test_combined_filters_and_pagination(temporal_client, db_connection, headers):
    query = {"q": "Temporal", "temporal": "upcoming", "status": "released", "page_size": 1}
    pages = []
    for page in (1, 2):
        result = await temporal_client.get(
            "/api/v1/events", headers=headers, params={**query, "page": page}
        )
        assert result.status_code == 200
        pages.append(result.json())
    assert pages[0]["pagination"]["total"] == pages[1]["pagination"]["total"] > 1
    assert pages[0]["items"][0]["entity_key"] != pages[1]["items"][0]["entity_key"]
    org = str(uid(1001))  # tomorrow only
    for path in ("events", "entity-search"):
        params = {
            "q": "tomorrow",
            "temporal": "upcoming",
            "organization_id": org,
            **({"entity_type": "event"} if path == "entity-search" else {}),
        }
        for status, count in [("released", 1), ("draft", 0)]:
            response = await temporal_client.get(
                f"/api/v1/{path}", headers=headers, params={**params, "status": status}
            )
            assert len(response.json()["items"]) == count
        for override in (
            {"temporal": "past"},
            {"q": "not-found"},
            {"organization_id": str(uid(9999))},
        ):
            response = await temporal_client.get(
                f"/api/v1/{path}", headers=headers, params={**params, **override}
            )
            assert response.json()["items"] == []


@pytest.mark.parametrize("value", ["all", "", "future", "past' OR true --"])
@pytest.mark.parametrize(
    "model,extra", [(EntityFilters, {}), (EntitySearchFilters, {"q": "Te", "entity_type": "event"})]
)
async def test_temporal_validation(value, model, extra):
    with pytest.raises(ValidationError):
        model(temporal=value, **extra)
    assert model(**extra).temporal is None
    assert model(temporal="upcoming", **extra).temporal == "upcoming"


@pytest.mark.integration
@pytest.mark.parametrize("kind,section", [("user", "users"), ("image", "images")])
async def test_unsupported_types_reject_temporal(temporal_client, headers, kind, section):
    for path in (section, "entity-search"):
        for value in ("past", "upcoming", "invalid"):
            response = await temporal_client.get(
                f"/api/v1/{path}",
                headers=headers,
                params={
                    "q": "fixture",
                    "temporal": value,
                    **({"entity_type": kind} if path == "entity-search" else {}),
                },
            )
            assert response.status_code == 422
        response = await temporal_client.get(
            f"/api/v1/{path}",
            headers=headers,
            params={
                "q": "fixture",
                **({"entity_type": kind} if path == "entity-search" else {}),
            },
        )
        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize(
    "local_day,utc_end",
    [
        (date(2026, 3, 29), datetime(2026, 3, 29, 21, 59, 59, 999999, tzinfo=UTC)),
        (date(2026, 10, 25), datetime(2026, 10, 25, 22, 59, 59, 999999, tzinfo=UTC)),
    ],
)
async def test_day_end_on_dst_transitions(db_connection, local_day, utc_end):
    await db_connection.execute(
        text("""UPDATE uranus.event_date SET start_date=:day,end_date=NULL,
        all_day=true,start_time=NULL,end_time=NULL WHERE uuid=:id"""),
        {"day": local_day, "id": uid(40)},
    )
    actual = (
        await db_connection.execute(
            text(f"""SELECT {EFFECTIVE_EVENT_DATE_END_SQL}
        FROM uranus.event_date d WHERE d.uuid=:id"""),
            {"event_tz": "Europe/Berlin", "id": uid(40)},
        )
    ).scalar_one()
    assert actual == utc_end


@pytest.mark.integration
async def test_timezone_and_boundary_use_aware_instants(
    temporal_client, db_connection, settings, headers
):
    # 12:00 Berlin equals NOW, whereas 12:00 Tokyo is already past.
    for zone, expected in [("Europe/Berlin", "upcoming"), ("Asia/Tokyo", "past")]:
        settings.event_timezone = zone
        for path in ("events", "entity-search"):
            for temporal in ("upcoming", "past"):
                response = await temporal_client.get(
                    f"/api/v1/{path}",
                    headers=headers,
                    params={
                        "q": "exact_end",
                        "temporal": temporal,
                        **({"entity_type": "event"} if path == "entity-search" else {}),
                    },
                )
                assert bool(response.json()["items"]) == (temporal == expected)
    # Database/session timezone must not affect the configured event timezone.
    await db_connection.execute(text("SET LOCAL TIME ZONE 'Pacific/Honolulu'"))
    settings.event_timezone = "Europe/Berlin"
    result = await entity_search(
        db_connection,
        EntitySearchFilters(q="exact_end", entity_type="event", temporal="upcoming"),
        settings,
        NOW,
    )
    assert len(result.items) == 1


@pytest.mark.integration
async def test_temporal_search_is_one_bounded_select(temporal_client, db_connection, settings):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        result = await entity_search(
            db_connection,
            EntitySearchFilters(q="Temporal", entity_type="venue", temporal="upcoming", limit=1),
            settings,
            NOW,
        )
        assert len(result.items) == 1
        assert len(statements) == 1
        assert statements[0].lstrip().startswith("SELECT")
        assert "EXISTS" in statements[0] and "LIMIT" in statements[0]
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)
