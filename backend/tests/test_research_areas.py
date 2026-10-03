"""Mock provider and disposable PostGIS: no live network or production imports."""

import json
import logging
from dataclasses import replace
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin_database import assert_admin_boundary
from app.errors import APIError
from app.logging import JsonFormatter
from app.repositories.research import research_detail, research_export, research_page
from app.repositories.research_areas import area_page, resolve_area
from app.research.areas import (
    CITY_EXCEPTIONS,
    REGIONS,
    boundary,
    classify,
    import_boundaries,
    provider_policy,
)
from app.research.catalog import CatalogEntry
from app.research.danish_catalog import DANISH_MUNICIPALITIES
from app.schemas.research import ResearchFilters
from app.schemas.research_areas import AreaFilters
from app.services.nominatim import NominatimClient
from tests.conftest import uid

POLYGON = {"type": "Polygon", "coordinates": [[[9, 54], [10, 54], [10, 55], [9, 55], [9, 54]]]}

# Measurements supplied by the operator, not synthetic geometry measurements.
VERIFIED_OVERLAP_CASES = [
    (
        "03151040",
        1392804,
        "03151007",
        1392689,
        53898.81205722038,
        0.02386146668532573,
        0.070628273054532,
        60000,
        0.10,
    ),
    (
        "03357019",
        1079013,
        "03357017",
        1079022,
        36856.37779786327,
        0.2709004971879667,
        0.29733202441384327,
        45000,
        0.35,
    ),
]


@pytest.fixture(params=VERIFIED_OVERLAP_CASES, ids=["wittingen", "hamersen"])
def overlap_case(request, settings):
    ags, osm_id, peer_ags, peer_id, area, percent, peer_percent, max_area, max_percent = (
        request.param
    )
    item = boundary(
        row(
            osm_id=osm_id,
            address={"country_code": "de", "ISO3166-2-lvl4": "DE-NI"},
            extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": ags},
        ),
        settings,
        "DE-NI",
        ags,
    )
    overlap = {
        "osm_id": peer_id,
        "municipality_key": peer_ags,
        "overlap_m2": area,
        "candidate_overlap_percent": percent,
        "existing_overlap_percent": peer_percent,
    }
    return item, overlap, max_area, max_percent


def classification_connection(
    overlaps, *, valid=True, overlap=True, existing=False, unchanged=False
):
    summary = MagicMock()
    summary.mappings.return_value.one.return_value = dict(
        valid=valid,
        overlap=overlap,
        existing=existing,
        unchanged=unchanged,
    )
    measured = MagicMock()
    measured.mappings.return_value.all.return_value = overlaps
    return AsyncMock(execute=AsyncMock(side_effect=[summary, measured]))


@pytest.mark.parametrize("reverse", [False, True])
async def test_verified_overlap_accepts_measured_pairs_and_logs(
    overlap_case, reverse, caplog, monkeypatch
):
    item, overlap, _, _ = overlap_case
    if reverse:
        item, overlap = (
            replace(item, osm_id=overlap["osm_id"], municipality_key=overlap["municipality_key"]),
            {
                **overlap,
                "osm_id": item.osm_id,
                "municipality_key": item.municipality_key,
                "candidate_overlap_percent": overlap["existing_overlap_percent"],
                "existing_overlap_percent": overlap["candidate_overlap_percent"],
            },
        )
    monkeypatch.setattr(logging.getLogger("admin"), "propagate", True)
    with caplog.at_level(logging.WARNING, logger="admin.research_areas"):
        status, _ = await classify(classification_connection([overlap]), item)
    assert status == "new"
    records = [r for r in caplog.records if r.getMessage() == "research_area_verified_overlap"]
    assert len(records) == 1
    report = json.loads(JsonFormatter().format(records[0]))
    assert (
        report.items()
        >= {
            "event": "research_area_verified_overlap",
            "level": "WARNING",
            "candidate_ags": item.municipality_key,
            "existing_ags": overlap["municipality_key"],
            "candidate_osm_id": item.osm_id,
            "existing_osm_id": overlap["osm_id"],
            "overlap_m2": overlap["overlap_m2"],
            "candidate_overlap_percent": overlap["candidate_overlap_percent"],
            "existing_overlap_percent": overlap["existing_overlap_percent"],
        }.items()
    )


@pytest.mark.parametrize(
    "field", ["overlap_m2", "candidate_overlap_percent", "existing_overlap_percent"]
)
async def test_verified_overlap_rejects_exceeded_limit(overlap_case, field):
    item, overlap, max_area, max_percent = overlap_case
    overlap[field] = (max_area if field == "overlap_m2" else max_percent) + 0.000001
    assert (await classify(classification_connection([overlap]), item))[0] == "rejected"


async def test_verified_overlap_accepts_exact_limits(overlap_case):
    item, overlap, max_area, max_percent = overlap_case
    overlap.update(
        overlap_m2=max_area,
        candidate_overlap_percent=max_percent,
        existing_overlap_percent=max_percent,
    )
    assert (await classify(classification_connection([overlap]), item))[0] == "new"


@pytest.mark.parametrize("missing", ["candidate", "existing", "both", "unlisted"])
async def test_verified_overlap_requires_exact_keys_even_for_tiny_overlap(overlap_case, missing):
    item, overlap, _, _ = overlap_case
    overlap.update(
        overlap_m2=1, candidate_overlap_percent=0.00001, existing_overlap_percent=0.00001
    )
    if missing in {"candidate", "both"}:
        item = replace(item, municipality_key=None)
    if missing in {"existing", "both"}:
        overlap["municipality_key"] = None
    if missing == "unlisted":
        overlap["municipality_key"] = "03999999"
    assert (await classify(classification_connection([overlap]), item))[0] == "rejected"


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), 0, -1])
@pytest.mark.parametrize(
    "field", ["overlap_m2", "candidate_overlap_percent", "existing_overlap_percent"]
)
async def test_verified_overlap_rejects_unusable_measurements(overlap_case, field, value):
    item, overlap, _, _ = overlap_case
    overlap[field] = value
    assert (await classify(classification_connection([overlap]), item))[0] == "rejected"


async def test_verified_overlap_does_not_allow_another_unlisted_peer(overlap_case):
    item, overlap, _, _ = overlap_case
    other = {**overlap, "osm_id": 999999, "municipality_key": "03999999"}
    assert (await classify(classification_connection([overlap, other]), item))[0] == "rejected"


@pytest.mark.parametrize(
    "existing,unchanged,expected",
    [(False, False, "new"), (True, False, "updated"), (True, True, "unchanged")],
)
async def test_zero_overlap_retains_classification(overlap_case, existing, unchanged, expected):
    item, _, _, _ = overlap_case
    connection = classification_connection(
        [], overlap=False, existing=existing, unchanged=unchanged
    )
    assert (await classify(connection, item))[0] == expected
    connection.execute.assert_awaited_once()


async def test_verified_overlap_never_accepts_invalid_candidate(overlap_case):
    item, overlap, _, _ = overlap_case
    connection = classification_connection([overlap], valid=False)
    assert (await classify(connection, item))[0] == "rejected"
    connection.execute.assert_awaited_once()


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
            osm_id=2178063 if country == "dk" else 101,
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
        (27027, "DE-SH", 6, "01003000"),
        (62528, "DE-SH", 6, "01004000"),
        (62531, "DE-NI", 6, "03101000"),
        (62659, "DE-NI", 6, "03102000"),
        (62418, "DE-NI", 6, "03103000"),
        (62414, "DE-NI", 6, "03401000"),
        (62562, "DE-NI", 6, "03402000"),
        (62409, "DE-NI", 6, "03403000"),
        (62631, "DE-NI", 6, "03404000"),
        (62444, "DE-NI", 6, "03405000"),
        (62405, "DE-MV", 6, "13003000"),
        (62685, "DE-MV", 6, "13004000"),
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


@pytest.mark.parametrize("same_batch", [False, True], ids=["persisted-peer", "batch-peer"])
@pytest.mark.parametrize(
    "size,intrusion,unlisted,expected",
    [
        (10000, 4, False, "new"),
        (10000, 7, False, "rejected"),  # Above both area limits.
        (1000, 4, False, "rejected"),  # About 0.4% of each, below both area limits.
        (10000, 1, True, "rejected"),
        (10000, 0, True, "new"),  # Shared edge remains valid, including unlisted pairs.
    ],
)
async def test_verified_overlap_postgis_plan_and_apply(
    area_store, settings, overlap_case, same_batch, size, intrusion, unlisted, expected
):
    item, overlap, _, _ = overlap_case
    # Synthetic rectangles in metric CRS, converted to WGS84. The production query
    # measures the intersection and both complete geometries as spheroidal geography.
    shapes = []
    for shift in (0, size - intrusion):
        raw = await area_store.scalar(
            text("""SELECT ST_AsGeoJSON(ST_Transform(ST_MakeEnvelope(
                500000 + :shift, 5900000, 500000 + :shift + :size,
                5900000 + :size, 25832),4326))"""),
            {"shift": shift, "size": size},
        )
        shapes.append(json.loads(raw))
    await area_store.rollback()
    candidate = row(
        osm_id=item.osm_id,
        address={"country_code": "de", "ISO3166-2-lvl4": "DE-NI"},
        extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": item.municipality_key},
        geojson=shapes[0],
    )
    peer = row(
        osm_id=overlap["osm_id"],
        address={"country_code": "de", "ISO3166-2-lvl4": "DE-NI"},
        extratags={
            "admin_level": "8",
            "de:amtlicher_gemeindeschluessel": "03999999"
            if unlisted
            else overlap["municipality_key"],
        },
        geojson=shapes[1],
    )
    records = [candidate, peer] if same_batch else [candidate]
    if not same_batch:
        assert (
            await import_boundaries(
                area_store,
                provider(settings, [peer]),
                "DE-NI",
                [],
                [peer["osm_id"]],
                apply=True,
            )
        )["new"] == 1
    identities = [r["osm_id"] for r in records]
    plan = await import_boundaries(area_store, provider(settings, records), "DE-NI", [], identities)
    assert plan["rejected"] == (1 if expected == "rejected" else 0)
    assert plan["new"] == len(records) - plan["rejected"]
    assert await area_store.scalar(text("SELECT count(*) FROM admin.research_area")) == (
        0 if same_batch else 1
    )
    await area_store.rollback()
    applied = await import_boundaries(
        area_store,
        provider(settings, records),
        "DE-NI",
        [],
        identities,
        apply=True,
    )
    assert applied == plan
    if expected == "new":
        repeated = await import_boundaries(
            area_store,
            provider(settings, records),
            "DE-NI",
            [],
            identities,
            apply=True,
        )
        assert repeated["unchanged"] == len(records)
        assert repeated["rejected"] == 0


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


async def test_catalog_city_uses_verified_relation_and_rechecks_ags(settings, area_store):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.url.params["osm_ids"] == "R62782"
        return httpx.Response(
            200,
            json=[
                row(
                    osm_id=62782,
                    address={"country_code": "de", "ISO3166-2-lvl4": "DE-HH"},
                    extratags={"admin_level": "4", "de:amtlicher_gemeindeschluessel": "02000001"},
                )
            ],
        )

    counts = await import_boundaries(
        area_store,
        provider(settings, handler=handler),
        "DE-HH",
        [],
        [],
        catalog=[CatalogEntry("DE-HH", "02000000", "Hamburg")],
        apply=True,
    )
    assert counts["rejected"] == 1 and counts["new"] == 0
    assert calls == ["/lookup"]


async def test_catalog_search_retry_requires_exact_ags(settings, area_store):
    calls = []
    record = row(extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": "01999000"})

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=[] if len(calls) == 1 else [record])

    counts = await import_boundaries(
        area_store,
        provider(settings, handler=handler),
        "DE-SH",
        [],
        [],
        catalog=[CatalogEntry("DE-SH", "01999000", "Test Municipality")],
    )
    assert counts["new"] == 1
    assert len(calls) == 3
    assert calls[1]["q"] == "Test Municipality"
    assert calls[1]["countrycodes"] == "de"


async def test_catalog_ignores_district_with_same_ags_but_rejects_two_municipalities(
    settings, area_store
):
    municipality = row(
        osm_id=101,
        extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": "01999000"},
    )
    district = row(
        osm_id=102,
        extratags={"admin_level": "9", "de:amtlicher_gemeindeschluessel": "01999000"},
    )
    catalog = [CatalogEntry("DE-SH", "01999000", "Test Municipality")]
    counts = await import_boundaries(
        area_store, provider(settings, [municipality, district]), "DE-SH", [], [], catalog=catalog
    )
    assert counts["new"] == 1 and counts["rejected"] == 0
    district["extratags"]["admin_level"] = "8"
    counts = await import_boundaries(
        area_store, provider(settings, [municipality, district]), "DE-SH", [], [], catalog=catalog
    )
    assert counts["new"] == 0 and counts["rejected"] == 1


async def test_operations_reuses_identity_geometry_and_legacy_import(
    area_store, admin_store, settings
):
    from app.repositories.geo import import_area
    from app.services.geo.scopes import resolve_geo_scope
    from tests.test_geo import IDENTITY, provider_row
    from tests.test_geo import provider as geo_provider

    old_polygon = {
        "type": "Polygon",
        "coordinates": [[[11, 54], [12, 54], [12, 55], [11, 55], [11, 54]]],
    }
    old = await import_area(
        admin_store, IDENTITY, geo_provider(settings, [provider_row(geojson=old_polygon)])
    )
    await import_boundaries(
        area_store, provider(settings, [row(osm_id=27020)]), "DE-SH", [], [27020], apply=True
    )
    identifier = (await area_store.execute(text("SELECT id FROM admin.research_area"))).scalar_one()
    for key in (identifier, old.id):
        resolved = await resolve_geo_scope(admin_store, key)
        assert resolved.area.id == resolved.area.area_id == identifier
        assert (
            await area_store.execute(
                text("SELECT ST_Covers(ST_GeomFromEWKB(:g),ST_SetSRID(ST_Point(9,54),4326))"),
                {"g": resolved.ewkb},
            )
        ).scalar_one()
    await admin_store.rollback()

    def forbidden(_):
        pytest.fail("Canonical municipalities must never call Nominatim")

    reused = await import_area(admin_store, IDENTITY, geo_provider(settings, handler=forbidden))
    assert reused.id == identifier
    assert (
        await admin_store.execute(text("SELECT count(*) FROM admin.geo_area"))
    ).scalar_one() == 1


@pytest.mark.parametrize(
    "endpoint",
    [
        "events",
        "venues",
        "spaces",
        "organizations",
        "dashboard/activity",
        "findings",
        "dashboard/summary",
        "statistics/entities",
        "statistics/events/content",
        "graph/search?q=Venue",
    ],
)
async def test_operations_canonical_area_during_provider_outage(
    area_store, settings, db_client, headers, endpoint
):
    area = await prepared(area_store, settings)
    await area_store.rollback()
    settings.nominatim_base_url = None
    path = (
        "/api/v1/"
        + endpoint
        + ("&" if "?" in endpoint else "?")
        + "geo_scope_id="
        + str(area.area.id)
    )
    response = await db_client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert (await db_client.get(path)).status_code == 401
    assert (await area_store.execute(text("SELECT count(*) FROM admin.geo_area"))).scalar_one() == 0


async def test_selected_area_metadata_is_small_read_only_and_provider_independent(
    area_store, settings, db_client, headers
):
    area = await prepared(area_store, settings)
    await area_store.rollback()
    settings.nominatim_base_url = None
    path = f"/api/v1/research/areas/{area.area.id}/metadata"
    response = await db_client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(area.area.id)
    assert not {"geometry", "ewkb", "events", "venues", "organizations"} & response.json().keys()
    assert (await db_client.get(path)).status_code == 401
    assert (await db_client.post(path, headers=headers)).status_code == 405
    assert (
        await db_client.get(f"/api/v1/research/areas/{uuid4()}/metadata", headers=headers)
    ).status_code == 404


@pytest.mark.parametrize(
    "point, expected", [("POINT(9.5 54.5)", True), ("POINT(9 54)", True), ("POINT(11 54)", False)]
)
async def test_operations_venue_membership_uses_canonical_polygon(
    area_store, db_connection, settings, now, point, expected
):
    from app.repositories.entities import entity_page
    from app.schemas.entities import EntityFilters
    from app.services.geo.scopes import resolve_geo_scope

    area = await prepared(area_store, settings)
    scope = await resolve_geo_scope(area_store, area.area.id)
    await db_connection.execute(
        text("UPDATE uranus.venue SET point=ST_GeomFromText(:point,4326) WHERE uuid=:id"),
        {"point": point, "id": uid(20)},
    )
    page = await entity_page(db_connection, settings, "venues", EntityFilters(), now, scope.ewkb)
    assert any(item.entity_key == str(uid(20)) for item in page.items) is expected


@pytest.mark.parametrize("region", [r for r in REGIONS if r.startswith("DE-")])
def test_all_german_regions(settings, region):
    from app.research.catalog import REGION_PREFIX

    prefix = next(p for p, r in REGION_PREFIX.items() if r == region)
    ags = prefix + "999999"
    data = row(
        address={"country_code": "de", "ISO3166-2-lvl4": region},
        extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": ags},
    )
    assert boundary(data, settings, region, ags).region_code == region
    with pytest.raises(APIError):
        boundary(data, settings, region, prefix + "999998")


@pytest.mark.parametrize("region,code,name,identity", DANISH_MUNICIPALITIES)
def test_danish_explicit_id_required(settings, region, code, name, identity):
    data = row(
        osm_id=identity,
        name=name,
        address={"country_code": "dk", "ISO3166-2-lvl4": region},
        extratags={"admin_level": "7"},
    )
    assert boundary(data, settings, region).osm_id == identity
    for changes in (
        {"osm_id": 999999},
        {"osm_type": "way"},
        {"type": "city"},
        {"geojson": None},
        {"extratags": {"admin_level": "8"}},
        {"address": {"country_code": "de", "ISO3166-2-lvl4": region}},
    ):
        with pytest.raises(APIError):
            boundary({**data, **changes}, settings, region)
    wrong_region = "DK-82" if region == "DK-81" else "DK-81"
    with pytest.raises(APIError):
        boundary(
            {**data, "address": {"country_code": "dk", "ISO3166-2-lvl4": wrong_region}},
            settings,
            wrong_region,
        )


@pytest.mark.parametrize("identity,exception", CITY_EXCEPTIONS.items())
def test_all_verified_city_exceptions_are_identity_bound(settings, identity, exception):
    region, level, ags = exception
    data = row(
        osm_id=identity,
        address={"country_code": "de", "ISO3166-2-lvl4": region},
        extratags={"admin_level": str(level), "de:amtlicher_gemeindeschluessel": ags},
    )
    assert boundary(data, settings, region, ags).municipality_key == ags
    with pytest.raises(APIError):
        boundary({**data, "osm_id": 999999}, settings, region, ags)
    with pytest.raises(APIError):
        boundary(
            {
                **data,
                "extratags": {
                    "admin_level": str(level),
                    "de:amtlicher_gemeindeschluessel": ags[:-1] + "1",
                },
            },
            settings,
            region,
            ags,
        )


@pytest.mark.parametrize(
    "ags,region", [("1234567", "DE-BB"), ("123456789", "DE-BB"), ("09999999", "DE-BW")]
)
def test_expected_ags_cannot_bypass_catalog_checks(settings, ags, region):
    data = row(
        address={"country_code": "de", "ISO3166-2-lvl4": region},
        extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": ags},
    )
    with pytest.raises(APIError):
        boundary(data, settings, region, ags)
