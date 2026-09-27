"""Mock provider and disposable PostGIS: no live network or production imports."""

from datetime import date
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin_database import assert_admin_boundary
from app.errors import APIError
from app.repositories.research import research_detail, research_export, research_page
from app.repositories.research_areas import area_page, resolve_area
from app.research.areas import boundary, import_boundaries, provider_policy
from app.research.catalog import CatalogEntry
from app.schemas.research import ResearchFilters
from app.schemas.research_areas import AreaFilters
from app.services.nominatim import NominatimClient
from tests.conftest import uid

POLYGON = {"type": "Polygon", "coordinates": [[[9, 54], [10, 54], [10, 55], [9, 55], [9, 54]]]}


def row(**changes):
    return {
        "osm_type": "relation",
        "osm_id": 101,
        "class": "boundary",
        "type": "administrative",
        "name": "Test Municipality",
        "display_name": "Test Municipality, Schleswig-Holstein",
        "address": {"country_code": "de", "ISO3166-2-lvl4": "DE-SH"},
        "extratags": {"admin_level": "8"},
        "geojson": POLYGON,
        **changes,
    }


def provider(settings, rows=None, handler=None):
    settings.nominatim_base_url = "https://provider.test"
    settings.geocode_request_interval_ms = 1
    records = rows if rows is not None else [row()]
    return NominatimClient(
        settings,
        httpx.MockTransport(
            handler
            or (
                lambda request: httpx.Response(
                    200,
                    json=[
                        r
                        for r in records
                        if request.url.path == "/search"
                        or str(r["osm_id"]) == request.url.params["osm_ids"][1:]
                    ],
                )
            )
        ),
    )


@pytest.mark.parametrize("country,level,region", [("de", 8, "DE-SH"), ("dk", 7, "DK-83")])
@pytest.mark.parametrize("shape", ["Polygon", "MultiPolygon"])
def test_country_geometry_semantics(settings, country, level, region, shape):
    geometry = (
        POLYGON if shape == "Polygon" else {"type": shape, "coordinates": [POLYGON["coordinates"]]}
    )
    result = boundary(
        row(
            address={"country_code": country, "ISO3166-2-lvl4": region},
            extratags={"admin_level": str(level)},
            geojson=geometry,
        ),
        settings,
        region,
    )
    assert result.country_code == country.upper() and result.osm_admin_level == level


@pytest.mark.parametrize(
    "changes",
    [
        {"class": "place"},
        {"type": "city"},
        {"osm_type": "node"},
        {"extratags": {"admin_level": "7"}},
        {"address": {"country_code": "fr", "ISO3166-2-lvl4": "DE-SH"}},
        {"address": {"country_code": "de", "ISO3166-2-lvl4": "DE-BY"}},
        {"address": {"country_code": "de", "state": "Schleswig-Holstein"}},
        {"geojson": None},
        {"geojson": {"type": "Point", "coordinates": [9, 54]}},
        {"geojson": {"type": "Polygon", "coordinates": [[[9, 54], [10, 54], [10, 55], [9, 55]]]}},
        {"osm_id": -1},
    ],
)
def test_rejects_unverified_boundary(settings, changes):
    with pytest.raises(APIError):
        boundary(row(**changes), settings, "DE-SH")


@pytest.mark.parametrize(
    "osm_id,region,level,ags",
    [
        (27020, "DE-SH", 6, "01001000"),
        (27021, "DE-SH", 6, "01002000"),
        (62782, "DE-HH", 4, "02000000"),
        (62559, "DE-HB", 6, "04011000"),
        (62658, "DE-HB", 6, "04012000"),
    ],
)
def test_explicit_city_exceptions(settings, osm_id, region, level, ags):
    data = row(
        osm_id=osm_id,
        address={"country_code": "de", "ISO3166-2-lvl4": region},
        extratags={"admin_level": str(level), "de:amtlicher_gemeindeschluessel": ags},
    )
    assert boundary(data, settings, region).osm_admin_level == level
    data["osm_id"] = 999
    with pytest.raises(APIError):
        boundary(data, settings, region)


def test_no_public_fallback_and_point_limit(settings):
    for origin in [None, "https://nominatim.openstreetmap.org", "https://evil.test"]:
        settings.nominatim_base_url = origin
        with pytest.raises(APIError):
            provider_policy(settings)
    settings.nominatim_max_geometry_points = 4
    with pytest.raises(APIError):
        boundary(row(), settings, "DE-SH")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"Location": "https://evil.test"}),
        httpx.Response(200, content=b"not-json", headers={"Content-Type": "application/json"}),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json=[row()] * 11),
        httpx.Response(
            200, content=b"[" + b" " * 2048, headers={"Content-Type": "application/json"}
        ),
    ],
)
async def test_transport_limits_and_redirects(settings, response):
    settings.nominatim_max_response_bytes = 1024
    calls = []

    def handler(request):
        calls.append(request)
        return response

    with pytest.raises(APIError) as error:
        await provider(settings, handler=handler).boundary_record("101")
    assert error.value.code == "geo_provider_unavailable" and len(calls) == 1


async def test_timeout_is_safe(settings):
    def handler(request):
        raise httpx.ReadTimeout("secret provider detail")

    with pytest.raises(APIError) as error:
        await provider(settings, handler=handler).boundary_record("101")
    assert error.value.message == "Geo provider is unavailable."


@pytest.fixture
async def area_store(admin_store, database):
    engine = create_async_engine(database[0])
    try:
        async with engine.connect() as connection:
            yield connection
    finally:
        await engine.dispose()


async def test_plan_upsert_rename_geometry_and_missing_do_not_delete(area_store, settings):
    p = provider(settings)
    counts = await import_boundaries(area_store, p, "DE-SH", [], [101])
    assert counts == dict(found=1, new=1, updated=0, unchanged=0, rejected=0)
    assert (
        await area_store.execute(text("SELECT count(*) FROM admin.research_area"))
    ).scalar_one() == 0
    await area_store.rollback()
    assert (await import_boundaries(area_store, p, "DE-SH", [], [101], apply=True))["new"] == 1
    original = (
        await area_store.execute(text("SELECT id,created_at,updated_at FROM admin.research_area"))
    ).one()
    await area_store.rollback()
    assert (await import_boundaries(area_store, p, "DE-SH", [], [101], apply=True))[
        "unchanged"
    ] == 1
    repeated = (
        await area_store.execute(text("SELECT id,created_at,updated_at FROM admin.research_area"))
    ).one()
    assert original == repeated
    await area_store.rollback()
    assert (
        await import_boundaries(
            area_store, provider(settings, [row(name="Renamed")]), "DE-SH", [], [101], apply=True
        )
    )["updated"] == 1
    changed = {
        "type": "Polygon",
        "coordinates": [[[9, 54], [9.8, 54], [9.8, 55], [9, 55], [9, 54]]],
    }
    assert (
        await import_boundaries(
            area_store,
            provider(settings, [row(name="Renamed", geojson=changed)]),
            "DE-SH",
            [],
            [101],
            apply=True,
        )
    )["updated"] == 1
    assert (
        await import_boundaries(area_store, provider(settings, []), "DE-SH", [], [101], apply=True)
    )["rejected"] == 1
    final = (
        await area_store.execute(
            text("SELECT id,created_at,name,ST_Covers(geometry,centroid) FROM admin.research_area")
        )
    ).one()
    assert final[0:2] == original[0:2] and final[2:] == ("Renamed", True)


async def test_overlap_invalid_geometry_and_duplicate_identity(area_store, settings):
    assert (
        await import_boundaries(area_store, provider(settings), "DE-SH", [], [101, 101], apply=True)
    )["found"] == 1
    assert (
        await import_boundaries(
            area_store, provider(settings, [row(osm_id=102)]), "DE-SH", [], [102], apply=True
        )
    )["rejected"] == 1
    invalid = {
        "type": "Polygon",
        "coordinates": [[[12, 54], [13, 55], [13, 54], [12, 55], [12, 54]]],
    }
    assert (
        await import_boundaries(
            area_store,
            provider(settings, [row(osm_id=103, geojson=invalid)]),
            "DE-SH",
            [],
            [103],
            apply=True,
        )
    )["rejected"] == 1
    async with area_store.begin_nested():
        with pytest.raises(IntegrityError):
            await area_store.execute(
                text("INSERT INTO admin.research_area SELECT * FROM admin.research_area")
            )
        await area_store.rollback()


@pytest.mark.parametrize(
    "point,expected",
    [("POINT(9.5 54.5)", True), ("POINT(10 54.5)", True), ("POINT(11 54.5)", False)],
)
async def test_covers_and_index(area_store, settings, point, expected):
    await import_boundaries(area_store, provider(settings), "DE-SH", [], [101], apply=True)
    assert (
        await area_store.execute(
            text(
                "SELECT ST_Covers(geometry,ST_GeomFromText(:point,4326)) FROM admin.research_area"
            ),
            {"point": point},
        )
    ).scalar_one() is expected
    await area_store.execute(text("SET LOCAL enable_seqscan=off"))
    plan = (
        (
            await area_store.execute(
                text(
                    "EXPLAIN SELECT id FROM admin.research_area WHERE "
                    "ST_Covers(geometry,ST_GeomFromText(:point,4326))"
                ),
                {"point": point},
            )
        )
        .scalars()
        .all()
    )
    assert "research_area_geometry_idx" in "\n".join(plan)


async def test_runtime_is_readonly(area_store, admin_store, settings):
    await import_boundaries(area_store, provider(settings), "DE-SH", [], [101], apply=True)
    privileges = (
        await admin_store.execute(
            text(
                "SELECT "
                "has_table_privilege(current_user,'admin.research_area','SELECT'),has_table_privilege(current_user,'admin.research_area','INSERT,UPDATE,DELETE')"
            )
        )
    ).one()
    assert privileges == (True, False)
    await admin_store.rollback()
    async with area_store.begin():
        await area_store.execute(text("GRANT UPDATE ON admin.research_area TO admin_history_test"))
    with pytest.raises(APIError):
        await assert_admin_boundary(admin_store)


async def prepared(area_store, settings):
    await import_boundaries(area_store, provider(settings), "DE-SH", [], [101], apply=True)
    identifier = (await area_store.execute(text("SELECT id FROM admin.research_area"))).scalar_one()
    return await resolve_area(area_store, identifier, boundary=True)


@pytest.mark.parametrize(
    "case,expected_space",
    [
        ("event_venue", None),
        ("date_venue", None),
        ("date_space", 26),
        ("event_space", 25),
        ("venue_stops_space", None),
    ],
)
async def test_effective_location_and_area_filter(
    area_store, db_connection, settings, now, case, expected_space
):
    area = await prepared(area_store, settings)
    await db_connection.execute(
        text(
            "UPDATE uranus.venue SET point=ST_GeomFromText('POINT(9.5 54.5)',4326) WHERE "
            "uuid IN (:a,:b)"
        ),
        {"a": uid(20), "b": uid(21)},
    )
    await db_connection.execute(
        text("INSERT INTO uranus.space(uuid,venue_uuid,name) VALUES (:id,:venue,'Date space')"),
        {"id": uid(26), "venue": uid(20)},
    )
    event_space = uid(25) if case in {"event_space", "venue_stops_space"} else None
    date_space = uid(26) if case == "date_space" else None
    date_venue = uid(21) if case in {"date_venue", "venue_stops_space"} else None
    await db_connection.execute(
        text("UPDATE uranus.event SET venue_uuid=:venue,space_uuid=:space WHERE uuid=:id"),
        {"venue": uid(20), "space": event_space, "id": uid(30)},
    )
    await db_connection.execute(
        text(
            "UPDATE uranus.event_date SET "
            "venue_uuid=:venue,space_uuid=:space,start_date='2026-09-01' WHERE event_uuid=:id"
        ),
        {"venue": date_venue, "space": date_space, "id": uid(30)},
    )
    filters = ResearchFilters(
        area_id=area.area.id,
        entity_type="event",
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 1),
        city="Flensburg",
    )
    result = await research_page(db_connection, settings, filters, now, area)
    event = next(i for i in result.items if i.entity_key == uid(30))
    assert event.space_id == (uid(expected_space) if expected_space else None)
    exported = await research_export(db_connection, settings, filters, now, area)
    assert str(uid(30)) in [r["event_uuid"] for r in exported.rows]
    detail = await research_detail(db_connection, settings, "event", uid(30), filters, now, area)
    assert all(d.start_date == date(2026, 9, 1) for d in detail.dates.items)
    excluded = await research_page(
        db_connection, settings, filters.model_copy(update={"city": "Neighbor"}), now, area
    )
    assert excluded.pagination.total == 0


async def test_multidate_earliest_matching_date_and_activity(
    area_store, db_connection, settings, now
):
    area = await prepared(area_store, settings)
    await db_connection.execute(
        text("UPDATE uranus.venue SET point=ST_GeomFromText('POINT(11 54.5)',4326) WHERE uuid=:id"),
        {"id": uid(20)},
    )
    await db_connection.execute(
        text(
            "UPDATE uranus.event_date SET venue_uuid=:venue,start_date='2026-09-01' WHERE "
            "event_uuid=:id"
        ),
        {"venue": uid(20), "id": uid(30)},
    )
    await db_connection.execute(
        text(
            "INSERT INTO "
            "uranus.event_date(uuid,event_uuid,venue_uuid,start_date,release_status) "
            "VALUES (:date,:event,:venue,'2026-09-05','released')"
        ),
        {"date": uuid4(), "event": uid(30), "venue": uid(21)},
    )
    filters = ResearchFilters(area_id=area.area.id, status="released", entity_type="event")
    events = await research_page(db_connection, settings, filters, now, area)
    assert next(i for i in events.items if i.entity_key == uid(30)).start_date == date(2026, 9, 5)
    for kind, key in [("venue", 21), ("organization", 10)]:
        page = await research_page(
            db_connection, settings, filters.model_copy(update={"entity_type": kind}), now, area
        )
        assert uid(key) in [i.entity_key for i in page.items]
    excluded = await research_page(
        db_connection, settings, filters.model_copy(update={"to_date": date(2026, 9, 2)}), now, area
    )
    assert uid(30) not in [i.entity_key for i in excluded.items]


async def test_area_api_dossier_and_no_import_endpoint(area_store, settings, db_client, headers):
    area = await prepared(area_store, settings)
    await area_store.rollback()
    response = await db_client.get("/api/v1/research/areas?q=Test&country_code=DE", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["id"] == str(area.area.id)
    assert "geometry" not in response.json()["items"][0]
    response = await db_client.get(f"/api/v1/research/areas/{area.area.id}", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["geometry"]["type"] == "MultiPolygon"
    assert data["area"]["centroid"] and data["area"]["source"] == "osm"
    assert all(k in data for k in ["months", "usage", "events", "venues", "organizations"])
    assert (await db_client.get("/api/v1/research/areas")).status_code == 401
    assert (await db_client.post("/api/v1/research/areas", headers=headers)).status_code == 405
    assert (
        await db_client.get(f"/api/v1/research/areas/{uuid4()}", headers=headers)
    ).status_code == 404
    assert (
        await db_client.get("/api/v1/research/areas?country_code=FR", headers=headers)
    ).status_code == 422
    listed = await area_page(area_store, AreaFilters(q=str(area.area.id)))
    assert len(listed.items) == 1


async def test_outage_cannot_partially_apply_or_remove(area_store, settings):
    await import_boundaries(area_store, provider(settings), "DE-SH", [], [101], apply=True)

    def handler(request):
        if request.url.params["osm_ids"] == "R102":
            return httpx.Response(200, json=[row(osm_id=102)])
        raise httpx.ReadTimeout("private provider detail")

    with pytest.raises(APIError):
        await import_boundaries(
            area_store, provider(settings, handler=handler), "DE-SH", [], [102, 103], apply=True
        )
    assert (
        await area_store.execute(text("SELECT osm_id FROM admin.research_area"))
    ).scalars().all() == [101]


async def test_unresolved_area_cannot_silently_disable_filter(db_connection, settings, now):
    with pytest.raises(APIError) as error:
        await research_page(db_connection, settings, ResearchFilters(area_id=uuid4()), now)
    assert error.value.code == "research_area_unavailable"


async def test_venues_without_events_and_source_index(area_store, db_connection, settings, now):
    area = await prepared(area_store, settings)
    await db_connection.execute(
        text(
            "INSERT INTO uranus.venue(uuid,org_uuid,name,scope,point) VALUES "
            "(:id,:org,'Quiet venue','organization',ST_GeomFromText('POINT(9.5 54.5)',4326))"
        ),
        {"id": uid(999), "org": uid(10)},
    )
    filters = ResearchFilters(area_id=area.area.id, entity_type="venue")
    result = await research_page(db_connection, settings, filters, now, area)
    assert uid(999) in [item.entity_key for item in result.items]
    detail = await research_detail(db_connection, settings, "venue", uid(999), filters, now, area)
    assert detail.events.pagination.total == 0
    result = await research_page(
        db_connection, settings, filters.model_copy(update={"category": 1}), now, area
    )
    assert uid(999) not in [item.entity_key for item in result.items]
    await db_connection.execute(text("SET LOCAL enable_seqscan=off"))
    plan = (
        (
            await db_connection.execute(
                text(
                    "EXPLAIN SELECT uuid FROM uranus.venue WHERE point && ST_GeomFromEWKB(:g) "
                    "AND ST_Covers(ST_GeomFromEWKB(:g),point)"
                ),
                {"g": area.ewkb},
            )
        )
        .scalars()
        .all()
    )
    assert "idx_venue_point" in "\n".join(plan)


async def test_area_and_category_combine_on_same_event(area_store, db_connection, settings, now):
    area = await prepared(area_store, settings)
    await db_connection.execute(
        text("UPDATE uranus.event SET categories=ARRAY[772] WHERE uuid=:id"), {"id": uid(30)}
    )
    await db_connection.execute(
        text("UPDATE uranus.event_date SET venue_uuid=:venue WHERE event_uuid=:id"),
        {"venue": uid(21), "id": uid(30)},
    )
    filters = ResearchFilters(area_id=area.area.id, entity_type="event", category=772)
    assert uid(30) in [
        r.entity_key
        for r in (await research_page(db_connection, settings, filters, now, area)).items
    ]
    assert not (
        await research_page(
            db_connection, settings, filters.model_copy(update={"category": 773}), now, area
        )
    ).items


async def test_catalog_discovery_requires_exact_ags(area_store, settings):
    entries = [CatalogEntry("DE-SH", "01999000", "Test Municipality")]
    matching = row(extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": "01999000"})
    counts = await import_boundaries(
        area_store, provider(settings, [matching]), "DE-SH", [], [], catalog=entries
    )
    assert counts["new"] == 1 and counts["rejected"] == 0
    counts = await import_boundaries(
        area_store, provider(settings), "DE-SH", [], [], catalog=entries
    )
    assert counts["new"] == 0 and counts["rejected"] == 1


async def test_population_plan_idempotence_and_boundary_identity(area_store, settings):
    from dataclasses import replace

    from app.research.population import PopulationEntry, import_population

    boundary_row = row(
        extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": "01999000"}
    )
    await import_boundaries(
        area_store, provider(settings, [boundary_row]), "DE-SH", [], [101], apply=True
    )
    entry = PopulationEntry("01999000", "Test Municipality", 123, date(2024, 12, 31), "a" * 64)
    assert (await import_population(area_store, [entry], "DE-SH"))["new"] == 1
    assert (
        await area_store.execute(text("SELECT population_count FROM admin.research_area"))
    ).scalar_one() is None
    await area_store.rollback()
    assert (await import_population(area_store, [entry], "DE-SH", apply=True))["new"] == 1
    assert (await import_population(area_store, [entry], "DE-SH", apply=True))["unchanged"] == 1
    assert (await import_population(area_store, [replace(entry, value=124)], "DE-SH", apply=True))[
        "updated"
    ] == 1
    assert (
        await import_population(
            area_store, [replace(entry, as_of=date(2023, 12, 31))], "DE-SH", apply=True
        )
    )["rejected"] == 1
    assert (
        await import_population(area_store, [replace(entry, ags="01999001")], "DE-SH", apply=True)
    )["rejected"] == 1
    await import_boundaries(
        area_store, provider(settings, [boundary_row]), "DE-SH", [], [101], apply=True
    )
    identifier = (await area_store.execute(text("SELECT id FROM admin.research_area"))).scalar_one()
    result = await resolve_area(area_store, identifier)
    assert result.area.population.value == 124
    assert result.area.population.as_of == date(2024, 12, 31)
    await area_store.rollback()
    boundary_row["extratags"]["de:amtlicher_gemeindeschluessel"] = "01999001"
    await import_boundaries(
        area_store, provider(settings, [boundary_row]), "DE-SH", [], [101], apply=True
    )
    assert (await resolve_area(area_store, identifier)).area.population is None
    await area_store.rollback()
