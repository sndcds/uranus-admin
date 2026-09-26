from datetime import date

import pytest
from sqlalchemy import text

from app.repositories.research import research_detail, research_export, research_page, source_url
from app.schemas.research import ResearchFilters
from tests.conftest import uid


@pytest.mark.parametrize("section,key", [("events", 30), ("venues", 20), ("organizations", 10)])
async def test_research_safe_contract(db_client, headers, section, key):
    response = await db_client.get(f"/api/v1/research/{section}/{uid(key)}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["item"]["entity_key"] == str(uid(key))
    for forbidden in (
        "email",
        "password",
        "actor",
        "created_by",
        "modified_by",
        "finding",
        "assignment",
        "notification",
        "contact_phone",
        "custom",
        "admin_url",
    ):
        assert forbidden not in response.text
    assert (await db_client.get(f"/api/v1/research/{section}/{uid(key)}")).status_code == 401
    assert (await db_client.post(f"/api/v1/research/{section}", headers=headers)).status_code == 405


async def test_private_events_and_search_fields_are_not_disclosed(db_client, headers):
    assert (
        await db_client.get(f"/api/v1/research/events/{uid(31)}", headers=headers)
    ).status_code == 404
    for query in ("fixture@example.invalid", "%' OR true --"):
        response = await db_client.get(
            "/api/v1/research/search", params={"q": query}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["items"] == []
    assert (
        await db_client.get("/api/v1/research/search?status=draft", headers=headers)
    ).status_code == 422


async def test_dates_filters_pagination_and_complete_export(db_connection, settings, now):
    await db_connection.execute(
        text(
            "UPDATE uranus.event_date SET start_date='2026-03-01',start_time='19:00' "
            "WHERE event_uuid=:id"
        ),
        {"id": uid(30)},
    )
    filters = ResearchFilters(
        entity_type="event",
        city="Flensburg",
        from_date=date(2026, 3, 1),
        to_date=date(2026, 3, 1),
        page_size=1,
    )
    page = await research_page(db_connection, settings, filters, now)
    assert page.pagination.total == 1
    assert page.items[0].entity_key == uid(30)
    assert page.items[0].start_date == date(2026, 3, 1)
    exported = await research_export(
        db_connection, settings, filters.model_copy(update={"page": 999}), now
    )
    assert exported.total == 1
    assert exported.rows[0]["event_uuid"] == str(uid(30))
    empty = await research_page(
        db_connection, settings, filters.model_copy(update={"city": "Missing"}), now
    )
    assert empty.pagination.total == 0


async def test_effective_venue_override_stops_space_inheritance(db_connection, settings, now):
    await db_connection.execute(
        text("UPDATE uranus.event SET space_uuid=:space WHERE uuid=:id"),
        {"space": uid(25), "id": uid(30)},
    )
    await db_connection.execute(
        text("UPDATE uranus.event_date SET venue_uuid=:venue,space_uuid=NULL WHERE event_uuid=:id"),
        {"venue": uid(21), "id": uid(30)},
    )
    page = await research_page(
        db_connection, settings, ResearchFilters(entity_type="event", venue_id=uid(21)), now
    )
    event = next(i for i in page.items if i.entity_key == uid(30))
    assert event.venue_id == uid(21)
    assert event.space_id is None
    assert event.location is not None


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "https://user:secret@example.test",
        "https://example.test?token=secret",
        "https://example.test/#secret",
    ],
)
def test_source_links_never_expose_credentials(value):
    assert source_url(value) is None


async def test_research_rejects_unknown_and_inverted_filters(db_client, headers):
    for query in (
        "from_date=2026-12-01&to_date=2026-01-01",
        "page_size=101",
        "status=draft",
        "sql=SELECT",
        "category=-1",
    ):
        assert (
            await db_client.get("/api/v1/research/search?" + query, headers=headers)
        ).status_code == 422


async def test_research_dossier_months(db_connection, settings, now):
    detail = await research_detail(
        db_connection, settings, "venue", uid(20), ResearchFilters(), now
    )
    assert detail.months


async def test_research_categories_public_dates_and_usage(db_connection, settings, now):
    await db_connection.execute(
        text("UPDATE uranus.event SET categories=ARRAY[772,772] WHERE uuid=:id"), {"id": uid(30)}
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event_category(category_id,iso_639_1,name) "
            "VALUES (772,'de','Forschungskonzert'),(772,'en','Research concert')"
        )
    )
    filters = ResearchFilters(entity_type="event", category=772)
    result = await research_page(db_connection, settings, filters, now)
    assert result.pagination.total == 1
    assert [c.name for c in result.items[0].categories] == ["Forschungskonzert"]
    detail = await research_detail(db_connection, settings, "organization", uid(10), filters, now)
    category = next(item for item in detail.usage if item.kind == "category")
    assert category.name == "Forschungskonzert" and category.event_count == 1
    await db_connection.execute(
        text("UPDATE uranus.event_date SET release_status='draft' WHERE event_uuid=:id"),
        {"id": uid(30)},
    )
    assert (await research_page(db_connection, settings, filters, now)).items == []


async def test_export_never_silently_truncates(db_connection, settings, now):
    from app.errors import APIError

    await db_connection.execute(
        text("""INSERT INTO uranus.event(uuid,org_uuid,title,release_status)
        SELECT md5('research-export-'||i)::uuid,:org,'Export fixture '||i,'released'
        FROM generate_series(1,10001) i"""),
        {"org": uid(10)},
    )
    with pytest.raises(APIError) as error:
        await research_export(db_connection, settings, ResearchFilters(entity_type="event"), now)
    assert error.value.code == "research_export_limit"
