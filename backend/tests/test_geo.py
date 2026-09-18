"""Synthetic provider and real PostGIS; never call a live Nominatim in tests."""

import json
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.api.geo import get_provider
from app.config import Settings
from app.errors import APIError
from app.repositories.entities import entity_page
from app.repositories.entity_search import entity_search
from app.repositories.geo import import_area
from app.repositories.spatial import spatial_predicate
from app.schemas.entities import EntityFilters, EntitySearchFilters
from app.schemas.geo import GeoAreaImport
from app.services.geo.scopes import resolve_geo_scope
from app.services.nominatim import NominatimClient, normalize_kind, validate_geometry
from app.storage_preflight import RUNTIME_GRANTS, check_grants
from tests.conftest import uid

POLYGON = {"type": "Polygon", "coordinates": [[[9, 54], [10, 54], [10, 55], [9, 55], [9, 54]]]}
IDENTITY = GeoAreaImport(source="osm", source_type="relation", source_id="27020")


def provider_row(**overrides):
    return {
        "osm_type": "relation",
        "osm_id": 27020,
        "category": "boundary",
        "type": "administrative",
        "addresstype": "city",
        "name": "Flensburg",
        "display_name": "Flensburg, Schleswig-Holstein, Deutschland",
        "address": {
            "city": "Flensburg",
            "state": "Schleswig-Holstein",
            "country": "Deutschland",
            "country_code": "de",
        },
        "extratags": {"admin_level": "6"},
        "boundingbox": ["54", "55", "9", "10"],
        "geojson": POLYGON,
        **overrides,
    }


def provider(settings, rows=None, handler=None):
    settings.nominatim_base_url = "https://provider.test"
    return NominatimClient(
        settings,
        httpx.MockTransport(
            handler
            or (lambda _: httpx.Response(200, json=rows if rows is not None else [provider_row()]))
        ),
    )


@pytest.mark.parametrize(
    ("country", "address_type", "level", "kind"),
    [
        ("de", "state", 4, "region"),
        ("de", "county", 6, "county"),
        ("de", "municipality", 8, "municipality"),
        ("de", "city", 6, "city"),
        ("dk", "region", 4, "region"),
        ("dk", None, 7, "municipality"),
        ("xx", None, 8, "other"),
        (None, None, None, "other"),
    ],
)
def test_kind(country, address_type, level, kind):
    assert normalize_kind(country, address_type, level) == kind


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:pass@example.org",
        "https://example.org/",
        "https://example.org?q=1",
        "https://example.org#fragment",
        "https://*.example.org",
        "file:///tmp",
        "https://example.org:bad",
        "https://example.org\n",
        "https://example.org\\evil",
    ],
)
def test_origin_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nominatim_base_url=origin)


async def test_provider_contract_and_safe_projection(settings):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[provider_row(display_name="<script>alert(1)</script>")])

    client = provider(settings, handler=handler)
    items = await client.search_areas("Flensburg &", 10)
    assert items[0].kind == "city"
    assert "geojson" not in items[0].model_dump()
    assert items[0].display_name == "<script>alert(1)</script>"
    assert items[0].bbox == (9, 54, 10, 55)
    await client.lookup_area("27020")
    assert requests[0].url.params["q"] == "Flensburg &"
    assert requests[1].url.params["osm_ids"] == "R27020"
    assert requests[1].url.params["polygon_geojson"] == "1"
    assert all(
        r.url.host == "provider.test" and "geo-service" in r.headers["user-agent"] for r in requests
    )


@pytest.mark.parametrize(
    "row",
    [
        provider_row(osm_type="node"),
        provider_row(type="building"),
        provider_row(osm_id="123?host=evil"),
        provider_row(category="place"),
    ],
)
async def test_ineligible(settings, row):
    client = provider(settings, [row])
    assert await client.search_areas("Foo", 10) == []
    with pytest.raises(APIError, match="administrative"):
        await client.lookup_area("27020")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"Location": "https://evil.test"}),
        httpx.Response(503, text="secret provider error"),
        httpx.Response(
            200, content=b"[" + b" " * 2000, headers={"Content-Type": "application/json"}
        ),
        httpx.Response(200, json={"unexpected": "object"}),
        httpx.Response(200, json=[{}] * 11),
        httpx.Response(200, text="<html>"),
    ],
)
async def test_outage_limits_redirects_and_invalid_responses(settings, response):
    settings.nominatim_max_response_bytes = 1024
    calls = []

    def handler(request):
        calls.append(request)
        return response

    with pytest.raises(APIError) as error:
        await provider(settings, handler=handler).search_areas("Foo", 10)
    assert error.value.code == "geo_provider_unavailable"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "GeometryCollection", "geometries": [POLYGON]},
        {"type": "Point", "coordinates": [9, 54]},
        {"type": "Polygon", "coordinates": []},
        {"type": "MultiPolygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[[9, 54], [9, 55], [10, 55], [11, 54]]]},
        {"type": "Polygon", "coordinates": [[[9, 54], [999, 55], [10, 55], [9, 54]]]},
    ],
)
def test_geometry_rejected(geometry):
    with pytest.raises(APIError) as error:
        validate_geometry(geometry, 250000)
    assert error.value.code == "geo_area_geometry_invalid"


def test_geometry_complexity():
    with pytest.raises(APIError):
        validate_geometry(POLYGON, 4)


@pytest.mark.parametrize(
    "geometry",
    [
        POLYGON,
        {"type": "MultiPolygon", "coordinates": [POLYGON["coordinates"]]},
        {"type": "Polygon", "coordinates": [[[9, 54], [10, 55], [10, 54], [9, 55], [9, 54]]]},
    ],
)
async def test_import_normalize_cache_grants(admin_store, settings, geometry):
    client = provider(settings, [provider_row(geojson=geometry)])
    area = await import_area(admin_store, IDENTITY, client)
    scope = await resolve_geo_scope(admin_store, area.id)
    assert scope.ewkb and scope.area.id == area.id
    assert area.kind == "city"
    details = (
        await admin_store.execute(
            text(
                "SELECT ST_SRID(geometry),GeometryType(geometry),ST_IsValid(geometry),"
                "ST_IsEmpty(geometry) FROM admin.geo_area"
            )
        )
    ).one()
    assert details == (4326, "MULTIPOLYGON", True, False)
    await admin_store.rollback()

    def forbidden(_):
        pytest.fail("A cached scope must not call Nominatim")

    cached = await import_area(admin_store, IDENTITY, provider(settings, handler=forbidden))
    assert cached.id == area.id
    await check_grants(admin_store, RUNTIME_GRANTS)
    assert (
        await admin_store.execute(
            text("SELECT has_table_privilege(current_user,'admin.geo_area','DELETE')")
        )
    ).scalar_one() is False
    assert (
        await admin_store.execute(text("SELECT count(*) FROM admin.geo_area"))
    ).scalar_one() == 1


async def test_collapsed_geometry_rejected(admin_store, settings):
    geometry = {"type": "Polygon", "coordinates": [[[9, 54], [9, 54], [9, 54], [9, 54]]]}
    with pytest.raises(APIError) as error:
        await import_area(
            admin_store, IDENTITY, provider(settings, [provider_row(geojson=geometry)])
        )
    assert error.value.code == "geo_area_geometry_invalid"


async def test_source_membership_and_search(db_connection, settings, now):
    wkb = (
        await db_connection.execute(
            text("SELECT ST_AsEWKB(ST_GeomFromGeoJSON(:geometry))"),
            {"geometry": json.dumps(POLYGON)},
        )
    ).scalar_one()
    for table, ids in (("organization", (10, 11)), ("venue", (20, 21, 22))):
        await db_connection.execute(text(f"UPDATE uranus.{table} SET point=NULL"))
        for position, expected in [
            ("POINT(9.5 54.5)", True),
            ("POINT(9 54)", True),
            ("POINT(11 54)", False),
            ("POINT EMPTY", False),
            (None, False),
        ]:
            await db_connection.execute(
                text(
                    f"UPDATE uranus.{table} SET point=ST_GeomFromText(:point,4326) WHERE uuid=:id"
                ),
                {"point": position, "id": uid(ids[0])},
            )
            section = "organizations" if table == "organization" else "venues"
            page = await entity_page(db_connection, settings, section, EntityFilters(), now, wkb)
            assert page.pagination.total == int(expected)
            search = await entity_search(
                db_connection, EntitySearchFilters(q=table, entity_type=table), settings, now, wkb
            )
            assert len(search.items) == int(expected)
            if table == "venue":
                spaces = await entity_page(
                    db_connection, settings, "spaces", EntityFilters(), now, wkb
                )
                assert spaces.pagination.total == int(expected)


async def test_temporal_geo_same_date_and_no_dateless_fallback(
    db_connection, settings, now, tmp_path
):
    # One past inside / future outside. Another event has inside standard venue but no dates.
    await db_connection.execute(text("DELETE FROM uranus.event_date"))
    await db_connection.execute(
        text(
            "UPDATE uranus.venue SET point=CASE WHEN uuid=:inside "
            "THEN ST_SetSRID(ST_Point(9.5,54.5),4326) "
            "ELSE ST_SetSRID(ST_Point(11,54.5),4326) END"
        ),
        {"inside": uid(20)},
    )
    await db_connection.execute(
        text("UPDATE uranus.event SET venue_uuid=:inside"), {"inside": uid(20)}
    )
    for key, days, venue in ((940, -2, None), (941, 2, uid(21))):
        await db_connection.execute(
            text(
                "INSERT INTO uranus.event_date(uuid,event_uuid,venue_uuid,start_date,all_day) "
                "VALUES (:id,:event,:venue,:day,true)"
            ),
            {
                "id": uid(key),
                "event": uid(30),
                "venue": venue,
                "day": (now + timedelta(days=days)).date(),
            },
        )
    for scope_wkt, temporal, expected in [
        ("POLYGON((9 54,10 54,10 55,9 55,9 54))", "past", 1),
        ("POLYGON((9 54,10 54,10 55,9 55,9 54))", "upcoming", 0),
        ("POLYGON((10 54,12 54,12 55,10 55,10 54))", "upcoming", 1),
        ("POLYGON((9 54,10 54,10 55,9 55,9 54))", None, 1),
        ("POLYGON((10 54,12 54,12 55,10 55,10 54))", None, 1),
    ]:
        wkb = (
            await db_connection.execute(
                text("SELECT ST_AsEWKB(ST_GeomFromText(:wkt,4326))"), {"wkt": scope_wkt}
            )
        ).scalar_one()
        result = await entity_page(
            db_connection, settings, "events", EntityFilters(temporal=temporal), now, wkb
        )
        assert result.pagination.total == expected
        assert all(r.entity_key == str(uid(30)) for r in result.items)
        found = await entity_search(
            db_connection,
            EntitySearchFilters(q="event", entity_type="event", temporal=temporal),
            settings,
            now,
            wkb,
        )
        assert len(found.items) == expected
    predicate = spatial_predicate("event_date")
    rows = (
        (
            await db_connection.execute(
                text(
                    "SELECT a.uuid FROM (SELECT uuid,uuid::text entity_key "
                    f"FROM uranus.event_date) a WHERE {predicate}"
                ),
                {"geo_scope_wkb": wkb},
            )
        )
        .scalars()
        .all()
    )
    assert rows == [uid(941)]
    plan = (
        await db_connection.execute(
            text(
                "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT a.uuid "
                "FROM (SELECT uuid,uuid::text entity_key FROM uranus.event) a "
                f"WHERE {spatial_predicate('event')}"
            ),
            {"geo_scope_wkb": wkb},
        )
    ).scalar_one()
    (tmp_path / "geo-explain.json").write_text(json.dumps(plan, indent=2))
    assert plan[0]["Plan"]["Actual Rows"] == 1


async def test_api_scope_auth_validation_and_cached_outage(
    admin_store, db_client, settings, headers
):
    settings.auth_public_origin = "https://admin.example.test"
    headers = {**headers, "Origin": settings.auth_public_origin, "X-Admin-CSRF": "1"}
    app = db_client._transport.app
    app.dependency_overrides[get_provider] = lambda: provider(settings)
    assert (await db_client.get("/api/v1/geo/areas/search?q=Foo")).status_code == 401
    for query in ("q=x", "q=abc%00", "q=" + "a" * 121, "q=abc&limit=11", "q=abc&host=evil"):
        assert (
            await db_client.get("/api/v1/geo/areas/search?" + query, headers=headers)
        ).status_code == 422
    invalid = await db_client.post(
        "/api/v1/geo/areas", headers=headers, json={**IDENTITY.model_dump(), "geometry": POLYGON}
    )
    assert invalid.status_code == 422
    area = await db_client.post("/api/v1/geo/areas", headers=headers, json=IDENTITY.model_dump())
    assert area.status_code == 200, area.text
    key = area.json()["id"]
    assert (await db_client.get(f"/api/v1/geo/areas/{key}", headers=headers)).status_code == 200
    bad = await db_client.get("/api/v1/events?geo_scope_id=bad", headers=headers)
    assert bad.status_code == 422
    unknown = await db_client.get(f"/api/v1/events?geo_scope_id={uid(999)}", headers=headers)
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "geo_scope_not_found"
    app.dependency_overrides[get_provider] = lambda: provider(
        settings, handler=lambda _: httpx.Response(503)
    )
    response = await db_client.get(f"/api/v1/venues?geo_scope_id={key}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["pagination"]["total"] == 1
    assert (
        await db_client.get(f"/api/v1/users?geo_scope_id={key}", headers=headers)
    ).status_code == 422
    assert (
        await db_client.get("/api/v1/geo/areas/search?q=Foo", headers=headers)
    ).status_code == 503
    detail = await db_client.get(f"/api/v1/venues/{uid(20)}", headers=headers)
    assert detail.status_code == 200  # Details remain accessible outside the work scope.


async def test_unknown_scope(admin_store):
    with pytest.raises(APIError) as error:
        await resolve_geo_scope(admin_store, UUID(int=9999))
    assert error.value.code == "geo_scope_not_found"


async def test_source_reader_needs_no_admin_access(admin_store, db_connection, settings, now):
    area = await import_area(admin_store, IDENTITY, provider(settings))
    scope = await resolve_geo_scope(admin_store, area.id)
    await db_connection.execute(text("CREATE ROLE geo_source_test"))
    await db_connection.execute(text("GRANT USAGE ON SCHEMA uranus TO geo_source_test"))
    await db_connection.execute(
        text("GRANT SELECT ON ALL TABLES IN SCHEMA uranus TO geo_source_test")
    )
    await db_connection.execute(text("SET LOCAL ROLE geo_source_test"))
    page = await entity_page(db_connection, settings, "venues", EntityFilters(), now, scope.ewkb)
    assert page.pagination.total == 1
    with pytest.raises(DBAPIError):
        async with db_connection.begin_nested():
            await db_connection.execute(text("SELECT id FROM admin.geo_area"))
