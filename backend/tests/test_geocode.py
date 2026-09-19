"""Fake Nominatim and disposable PostGIS only. Suggestions never modify source points."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.admin_tables import geocode_candidate as candidate
from app.admin_tables import geocode_request as request
from app.database import create_engine
from app.errors import APIError
from app.geocode_worker import work_once
from app.repositories import geocode
from app.repositories.geocode_sources import source_rows
from app.repositories.quality_sources import load_sources
from app.schemas.finding import FindingFilters
from app.schemas.geocode import GeocodeCandidate, GeocodeFilters
from app.services.checks import persisted_page, run_check
from app.services.geo.geocoding import (
    candidates,
    query_fingerprint,
    query_inputs,
    result_status,
    score,
    source_fingerprint,
)
from app.services.nominatim import NominatimClient
from app.services.notifications.candidates import detect
from app.services.notifications.policy import EXTERNAL_POLICY
from app.services.quality.core import evaluate_core
from app.storage_preflight import RUNTIME_GRANTS, check_grants
from tests.conftest import uid

NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


def source(**changes):
    return dict(
        entity_type="venue",
        entity_key=uid(20),
        name="Public theatre",
        street="Norderstraße",
        house_number="49",
        postal_code="24939",
        city="Flensburg",
        country="DEU",
        state="SH",
        osm_id=123,
        point_missing=True,
        **changes,
    )


def provider_row(**changes):
    return {
        "lat": "54.789123",
        "lon": "9.432123",
        "display_name": "Public theatre",
        "osm_type": "way",
        "osm_id": 123,
        "importance": 0.9,
        "category": "amenity",
        "type": "theatre",
        "addresstype": "amenity",
        "address": {
            "road": "Norderstraße",
            "house_number": "49",
            "postcode": "24939",
            "city": "Flensburg",
            "country_code": "de",
            "private_field": "not stored",
        },
        **changes,
    }


def provider(settings, results=None, handler=None):
    settings.nominatim_base_url = "https://internal-provider.test"
    return NominatimClient(
        settings,
        httpx.MockTransport(
            handler
            or (
                lambda _: httpx.Response(
                    200, json=results if results is not None else [provider_row()]
                )
            )
        ),
    )


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("country_code", "dk", 0.8),
        ("postcode", "24937", 0.75),
        ("city", "Kiel", 0.8),
        ("house_number", "51", 0.85),
        ("road", "Other", 0.8),
    ],
)
def test_scores_address_not_importance(field, value, expected):
    row = provider_row()
    assert score(source(), row["address"])[0] == 1
    row["address"][field] = value
    assert candidates(source(), [row], 5)[0].match_score == expected
    row["importance"] = 1000
    assert candidates(source(), [row], 5)[0].match_score == expected


def test_name_only_country_postal_and_house_normalization():
    row = source()
    row.update(street=None, house_number=None, postal_code=None, country="unknown")
    assert score(row, provider_row()["address"])[0] == 0.2
    assert query_inputs(row) == {}
    row = source()
    row.update(postal_code=" SW1A 1AA ", house_number="12 A", country="germany")
    target = {**provider_row()["address"], "postcode": "sw1a 1aa", "house_number": "12a"}
    assert score(row, target)[0] == 1
    target["house_number"] = "12"
    assert score(row, target)[0] == 0.85
    target["postcode"] = "SW1A1AA"
    assert score(row, target)[0] == 0.6


def test_fingerprints_query_and_generations():
    row = source()
    assert query_fingerprint(row, 1) != query_fingerprint(row, 5)
    initial = source_fingerprint(row)
    row["street"] = " Norderstraße  "
    assert source_fingerprint(row) == initial
    row["house_number"] = "51"
    assert source_fingerprint(row) != initial
    assert query_inputs(row) == {
        "street": "51 Norderstraße",
        "city": "Flensburg",
        "postalcode": "24939",
        "countrycodes": "de",
    }
    row.update(entity_type="organization", address_addition="Hinterhof")
    old_source, old_query = source_fingerprint(row), query_fingerprint(row)
    row["address_addition"] = "Haus B"
    assert source_fingerprint(row) != old_source and query_fingerprint(row) == old_query
    assert not {"name", "state", "osm_id", "address_addition"} & query_inputs(row).keys()


def test_ambiguity_sort_bounded_dedupe_and_osm():
    a, b = provider_row(), provider_row(osm_id=456)
    items = candidates(source(), [a, b], 5)
    assert result_status(items) == "ambiguous"
    assert len(candidates(source(), [a, a], 5)) == 1
    b["address"] = {**b["address"], "postcode": "0"}
    items = candidates(source(), [b, a], 5)
    assert items[0].match_score == 1 and items[0].rank == 1
    assert result_status(items) == "candidate"
    assert result_status(candidates(source(), [b], 5)) == "candidate"  # .75 documented floor
    b["address"]["city"] = "other"
    assert result_status(candidates(source(), [b], 5)) == "ambiguous"
    assert result_status([]) == "not_found"
    assert len(candidates(source(), [provider_row(osm_id=i) for i in range(1, 11)], 5)) == 5
    assert items[0].osm_url == "https://www.openstreetmap.org/way/123"
    item = candidates(source(), [provider_row(osm_id="123?host=evil")], 5)[0]
    assert item.osm_url.startswith("https://www.openstreetmap.org/?mlat=")
    assert "private_field" not in item.address


@pytest.mark.parametrize(
    "field,value",
    [
        ("lat", True),
        ("lat", "NaN"),
        ("lat", "Infinity"),
        ("lat", "91"),
        ("lon", "181"),
        ("importance", "NaN"),
        ("address", []),
        ("display_name", ""),
        ("display_name", {"unexpected": "object"}),
    ],
)
def test_invalid_candidates_rejected(field, value):
    with pytest.raises(APIError):
        candidates(source(), [provider_row(**{field: value})], 5)


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", float("nan")),
        ("longitude", float("inf")),
        ("latitude", -91),
        ("match_score", 1.01),
    ],
)
def test_pydantic_finite_coordinates(field, value):
    item = candidates(source(), [provider_row()], 5)[0].model_dump()
    with pytest.raises(ValidationError):
        GeocodeCandidate.model_validate({**item, field: value})


async def test_provider_contract(settings, caplog, monkeypatch):
    seen = []
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted-proxy.invalid")

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=[provider_row()] * 8)

    caplog.set_level("INFO")
    result = await provider(settings, handler=handler).geocode_address(query_inputs(source()))
    assert len(result) == 5 and len(seen) == 1
    req = seen[0]
    assert req.url.host == "internal-provider.test" and req.url.path == "/search"
    assert req.url.params["format"] == "jsonv2" and req.url.params["limit"] == "5"
    assert req.url.params["addressdetails"] == "1" and req.url.params["namedetails"] == "1"
    assert "polygon_geojson" not in req.url.params and "q" not in req.url.params
    # Application logs carry no address/provider body; HTTPX is suppressed by configure_logging.
    assert not any(
        "Norderstraße" in r.message for r in caplog.records if r.name.startswith("admin")
    )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "https://evil.test"}),
        httpx.Response(503, text="secret"),
        httpx.Response(200, json={}),
        httpx.Response(200, content=b"[", headers={"content-type": "application/json"}),
        httpx.Response(200, json=[{}] * 11),
        httpx.Response(200, content=b" " * 2048, headers={"content-type": "application/json"}),
    ],
)
async def test_provider_failure_security(settings, response):
    settings.nominatim_max_response_bytes = 1024
    seen = []

    def handler(req):
        seen.append(req)
        return response

    with pytest.raises(APIError) as error:
        await provider(settings, handler=handler).geocode_address(query_inputs(source()))
    assert len(seen) == 1 and error.value.message == "Geo provider is unavailable."


async def test_provider_timeout(settings):
    def handler(req):
        raise httpx.ReadTimeout("sensitive query", request=req)

    with pytest.raises(APIError) as error:
        await provider(settings, handler=handler).geocode_address(query_inputs(source()))
    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize("kind,key", [("organization", 10), ("venue", 20)])
@pytest.mark.parametrize(
    "point,missing", [(None, True), ("POINT EMPTY", True), ("POINT(9 54)", False)]
)
async def test_rules_null_empty_valid_and_resolution(
    admin_store, db_connection, settings, now, kind, key, point, missing
):
    await db_connection.execute(
        text(f"UPDATE uranus.{kind} SET point=ST_GeomFromText(:point,4326) WHERE uuid=:id"),
        {"point": point, "id": uid(key)},
    )
    sources = await load_sources(db_connection)
    rule = kind + "_missing_location"
    result = evaluate_core(rule, sources, settings, now)
    found = [f for f in result.findings if f.entity_key == str(uid(key))]
    assert bool(found) == missing
    assert rule not in EXTERNAL_POLICY
    if found:
        assert found[0].field == "point" and found[0].severity == "warning"
        assert found[0].metadata["geocode_supported"] is True
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    await db_connection.execute(
        text(f"UPDATE uranus.{kind} SET point=ST_GeomFromText('POINT(9 54)',4326) WHERE uuid=:id"),
        {"id": uid(key)},
    )
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    page = await persisted_page(
        admin_store, FindingFilters(rule=rule, entity_key=str(uid(key))), now
    )
    if missing:
        assert page.items[0].status == "resolved"


async def test_notification_detector_excludes_missing_locations(
    db_connection, settings, now, monkeypatch
):
    import email_validator

    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)
    from app.schemas.notifications import NotificationConfig
    from tests.test_notifications import CONFIG

    sources = await load_sources(db_connection)
    findings = [
        f
        for kind in ("organization", "venue")
        for f in evaluate_core(kind + "_missing_location", sources, settings, now).findings
    ]
    assert len(findings) == 4
    values = detect(
        sources,
        {uid(10): NotificationConfig.model_validate(CONFIG)},
        {f.id: "open" for f in findings},
        settings,
        now,
    )
    assert all(c.payload.rule not in {f.rule for f in findings} for c in values)


@pytest.mark.parametrize(
    "results,status",
    [
        ([provider_row()], "candidate"),
        ([provider_row(), provider_row(osm_id=124)], "ambiguous"),
        ([], "not_found"),
    ],
)
async def test_persistence_results_and_history(admin_store, settings, results, status):
    row = source()
    assert await geocode.synchronize(admin_store, [row]) == 1
    assert await geocode.synchronize(admin_store, [row]) == 0
    owner = uuid4()
    job = await geocode.claim(admin_store, settings, owner)
    assert job["generation"] == 1
    assert await geocode.begin_attempt(admin_store, job, owner, row, settings)
    items = candidates(row, results, 5)
    assert await geocode.finish(admin_store, settings, job, owner, result_status(items), items)
    async with admin_store.begin():
        stored = (await admin_store.execute(select(request))).mappings().one()
        assert stored["status"] == status and stored["attempt_count"] == 1
        assert (stored["next_check_at"] is not None) == (status == "not_found")
    row["house_number"] = "51"
    assert await geocode.synchronize(admin_store, [row]) == 1
    async with admin_store.begin():
        stored = (await admin_store.execute(select(request))).mappings().one()
        assert (
            stored["generation"] == 2
            and stored["status"] == "pending"
            and stored["attempt_count"] == 0
        )
        old = (await admin_store.execute(select(candidate))).mappings().all()
        assert len(old) == len(items) and all(c["generation"] == 1 for c in old)
        assert all(c["source_fingerprint"] == job["source_fingerprint"] for c in old)
    assert not await geocode.finish(admin_store, settings, job, owner, "candidate", items)


async def test_concurrent_claim_expired_lease_and_fence(admin_store, settings):
    await geocode.synchronize(admin_store, [source()])
    engine = admin_store.engine

    async def worker():
        async with engine.connect() as conn:
            owner = uuid4()
            return owner, await geocode.claim(conn, settings, owner)

    attempts = await asyncio.gather(worker(), worker())
    assert sum(job is not None for _, job in attempts) == 1
    old_owner, old_job = next((owner, job) for owner, job in attempts if job)
    async with admin_store.begin():
        await admin_store.execute(update(request).values(lease_until=NOW - timedelta(days=1)))
    owner, job = await worker()
    assert job is not None
    assert not await geocode.finish(admin_store, settings, old_job, old_owner, "not_found", [])
    assert await geocode.finish(admin_store, settings, job, owner, "not_found", [])


async def test_worker_bound_pacing_failure_and_insufficient(
    database, admin_store, settings, monkeypatch
):
    settings.database_url = SecretStr(database[0])
    settings.geocode_batch_size = 3
    calls, sleeps = [], []

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("app.geocode_worker.asyncio.sleep", sleep)

    def handler(req):
        calls.append(req)
        return httpx.Response(503, text="secret provider body")

    engine = create_engine(settings)
    try:
        counts = await work_once(
            engine, admin_store.engine, settings, provider(settings, handler=handler)
        )
        assert counts["requests_created"] == 4
        assert counts["requests_checked"] == 3
        assert len(calls) <= 2
        assert sleeps == [settings.geocode_request_interval_ms / 1000] * max(0, len(calls) - 1)
        async with admin_store.begin():
            rows = (await admin_store.execute(select(request))).mappings().all()
            assert len(rows) == 4
            assert sum(r["status"] == "pending" for r in rows) == 1
            assert all(
                r["last_error"] == "provider_unavailable" for r in rows if r["status"] == "failed"
            )
            assert all(r["attempt_count"] == 0 for r in rows if r["status"] == "insufficient_input")
        counts = await work_once(
            engine, admin_store.engine, settings, provider(settings, handler=handler)
        )
        assert counts["requests_checked"] == 1
    finally:
        await engine.dispose()


async def test_api_security_retry_stale_and_enrichment(
    admin_store, db_client, db_connection, settings, headers, now
):
    settings.auth_public_origin = "https://admin.example.test"
    rows = await source_rows(db_connection, "venue", ids=[uid(20)])
    await geocode.synchronize(admin_store, rows)
    owner = uuid4()
    job = await geocode.claim(admin_store, settings, owner)
    await geocode.finish(
        admin_store, settings, job, owner, "candidate", candidates(rows[0], [provider_row()], 5)
    )
    path = f"/api/v1/geocode/requests/{job['id']}"
    assert (await db_client.get(path)).status_code == 401
    assert (await db_client.post(path + "/retry")).status_code == 401
    assert (await db_client.get(path, headers=headers)).status_code == 200
    assert (await db_client.post(path + "/retry", headers=headers)).status_code == 403
    valid = {**headers, "Origin": settings.auth_public_origin, "X-Admin-CSRF": "1"}
    for extra in ({"Origin": "https://evil.test"}, {"X-Admin-CSRF": "0"}):
        assert (
            await db_client.post(path + "/retry", headers={**valid, **extra})
        ).status_code == 403
    for body in ({"address": "evil"}, {"lat": 1, "lon": 2}, {}, None):
        assert (
            await db_client.post(path + "/retry", headers=valid, content=json.dumps(body))
        ).status_code == 422
    assert (await db_client.post(path + "/retry?host=evil", headers=valid)).status_code == 422
    assert (
        await db_client.get("/api/v1/geocode/requests?geo_scope_id=" + str(uid(1)), headers=valid)
    ).status_code == 422
    assert (await db_client.get(path + "?q=x", headers=valid)).status_code == 422
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    response = await db_client.get("/api/v1/findings?rule=venue_missing_location", headers=valid)
    assert response.status_code == 200, response.text
    assert any(
        f["location_suggestion_request_id"] == str(job["id"]) for f in response.json()["items"]
    )
    for mode in ("live", "persisted"):
        result = await db_client.get(
            f"/api/v1/findings?rule=venue_missing_location&mode={mode}", headers=valid
        )
        assert any(
            f["location_suggestion_request_id"] == str(job["id"]) for f in result.json()["items"]
        )
    assert (await db_client.post(path + "/retry", headers=valid)).status_code == 202
    assert (await db_client.post(path + "/retry", headers=valid)).status_code == 409
    # In-transaction authoritative change visible to direct service/detail; never API DML.
    await db_connection.execute(
        text("UPDATE uranus.venue SET point=ST_GeomFromText('POINT(9 54)',4326) WHERE uuid=:id"),
        {"id": uid(20)},
    )
    result = await geocode.detail(admin_store, db_connection, job["id"])
    assert result.status == "stale" and result.candidates == []
    with pytest.raises(APIError) as error:
        await geocode.retry(admin_store, db_connection, job["id"])
    assert error.value.code == "geocode_no_longer_needed"
    await check_grants(admin_store, RUNTIME_GRANTS)


@pytest.mark.parametrize(
    "column,value",
    [
        ("latitude", float("nan")),
        ("longitude", float("inf")),
        ("match_score", float("nan")),
        ("provider_importance", float("inf")),
        ("rank", 6),
    ],
)
async def test_database_candidate_constraints(admin_store, settings, column, value):
    await geocode.synchronize(admin_store, [source()])
    owner = uuid4()
    job = await geocode.claim(admin_store, settings, owner)
    item = candidates(source(), [provider_row()], 5)[0]
    values = dict(
        **item.model_dump(exclude={"osm_url"}),
        request_id=job["id"],
        generation=1,
        source_fingerprint=job["source_fingerprint"],
        query_fingerprint=job["query_fingerprint"],
        query_version=1,
        scoring_version=1,
        created_at=NOW,
    )
    values[column] = value
    with pytest.raises(DBAPIError):
        async with admin_store.begin():
            await admin_store.execute(candidate.insert().values(**values))


async def test_migration_upgrade_downgrade_preserves_existing(database, monkeypatch):
    import asyncpg
    from alembic import command
    from alembic.config import Config

    url = database[0]
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    assert not await conn.fetchval("SELECT to_regnamespace('admin')")
    await conn.execute("CREATE SCHEMA admin")
    monkeypatch.setenv("ADMIN_MIGRATION_DATABASE_URL", url)
    cfg = Config("alembic.ini")
    try:
        await asyncio.to_thread(command.upgrade, cfg, "0010")
        await conn.execute(
            "INSERT INTO admin.finding(id,rule,severity,entity_type,entity_id,message,"
            "first_seen_at,last_seen_at) "
            "VALUES ('migration-fixture','test','warning','venue','fixture','Retain',now(),now())"
        )
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='admin' "
            "AND tablename <> 'alembic_version' ORDER BY tablename"
        )

        async def snapshots():
            return {
                r["tablename"]: await conn.fetch(
                    f"SELECT to_jsonb(t) AS value FROM admin.{r['tablename']} t"
                )
                for r in tables
            }

        before = await snapshots()
        await asyncio.to_thread(command.upgrade, cfg, "head")
        assert await conn.fetchval("SELECT version_num FROM admin.alembic_version") == "0011"
        assert await conn.fetchval("SELECT to_regclass('admin.geocode_candidate') IS NOT NULL")
        await asyncio.to_thread(command.check, cfg)
        assert await snapshots() == before
        await asyncio.to_thread(command.downgrade, cfg, "0010")
        assert await snapshots() == before
        assert await conn.fetchval("SELECT to_regclass('admin.geocode_request') IS NULL")
        assert await conn.fetchval("SELECT to_regclass('admin.geocode_candidate') IS NULL")
    finally:
        await conn.execute("DROP SCHEMA admin CASCADE")
        await conn.close()


async def test_worker_point_added_deleted_and_changed_after_provider(
    database, admin_store, settings
):
    import asyncpg

    settings.database_url = SecretStr(database[0])
    writer = await asyncpg.connect(database[0].replace("postgresql+asyncpg://", "postgresql://"))
    engine = create_engine(settings)
    calls = []

    async def handler(req):
        calls.append(req)
        # Only the disposable fixture writer simulates an upstream domain edit.
        await writer.execute(
            "UPDATE uranus.venue SET point=ST_GeomFromText('POINT(9 54)',4326) WHERE uuid=$1",
            uid(20),
        )
        return httpx.Response(200, json=[provider_row()])

    try:
        await work_once(engine, admin_store.engine, settings, provider(settings, handler=handler))
        async with admin_store.begin():
            row = (
                (await admin_store.execute(select(request).where(request.c.entity_key == uid(20))))
                .mappings()
                .one()
            )
            assert row["status"] == "stale"
            assert not (
                await admin_store.execute(
                    select(candidate).where(candidate.c.request_id == row["id"])
                )
            ).first()
        calls.clear()
        await work_once(engine, admin_store.engine, settings, provider(settings, handler=handler))
        assert calls == []
        # Deleted identity is observationally stale and never sent.
        await geocode.synchronize(admin_store, [{**source(), "entity_key": uid(99999)}])
        await work_once(engine, admin_store.engine, settings, provider(settings, handler=handler))
        assert calls == []
        async with admin_store.begin():
            assert (
                await admin_store.execute(
                    select(request.c.status).where(request.c.entity_key == uid(99999))
                )
            ).scalar_one() == "stale"
    finally:
        await writer.execute("UPDATE uranus.venue SET point=NULL WHERE uuid=$1", uid(20))
        await writer.close()
        await engine.dispose()


async def test_api_list_filters_pagination_and_address_change(admin_store, db_connection, settings):
    jobs = []
    for kind in ("organization", "venue"):
        jobs.extend(await source_rows(db_connection, kind))
    await geocode.synchronize(admin_store, jobs)
    data = await geocode.page(
        admin_store, db_connection, GeocodeFilters(entity_type="venue", page_size=1)
    )
    assert data.pagination.total == 2 and data.pagination.pages == 2
    assert len(data.items) == 1 and data.counts["pending"] == 4
    assert data.items[0].source_address
    second = await geocode.page(
        admin_store, db_connection, GeocodeFilters(entity_type="venue", page_size=1, page=2)
    )
    assert data.items[0].id != second.items[0].id
    assert (
        await geocode.page(admin_store, db_connection, GeocodeFilters(status="failed"))
    ).items == []
    row = next(r for r in jobs if r["entity_key"] == uid(20))
    # Choose the request directly to finish a candidate, then change address.
    while True:
        owner = uuid4()
        job = await geocode.claim(admin_store, settings, owner)
        if job["entity_key"] == uid(20):
            break
        await geocode.finish(admin_store, settings, job, owner, "insufficient_input", [])
    await geocode.finish(
        admin_store, settings, job, owner, "candidate", candidates(row, [provider_row()], 5)
    )
    await db_connection.execute(
        text("UPDATE uranus.venue SET house_number='51' WHERE uuid=:id"), {"id": uid(20)}
    )
    detail = await geocode.detail(admin_store, db_connection, job["id"])
    assert detail.status == "stale" and not detail.candidates
    await geocode.retry(admin_store, db_connection, job["id"])
    refreshed = await geocode.detail(admin_store, db_connection, job["id"])
    assert refreshed.status == "pending" and refreshed.generation == 2
    assert refreshed.source_fingerprint != job["source_fingerprint"]


async def test_worker_exact_match_global_lock_and_no_source_mutation(
    database, admin_store, settings
):
    settings.database_url = SecretStr(database[0])
    engine = create_engine(settings)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def handler(req):
        calls.append(req)
        entered.set()
        await release.wait()
        return httpx.Response(
            200,
            json=[
                provider_row(
                    address={
                        "road": "Hafenstraße",
                        "house_number": "3",
                        "postcode": "24937",
                        "city": "Flensburg",
                        "country_code": "de",
                    }
                )
            ],
        )

    async def points():
        async with engine.connect() as reader:
            return (
                await reader.execute(
                    text("SELECT uuid,ST_AsText(point) FROM uranus.venue ORDER BY uuid")
                )
            ).all()

    before = await points()
    first = asyncio.create_task(
        work_once(engine, admin_store.engine, settings, provider(settings, handler=handler))
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=20)
        second = await work_once(
            engine, admin_store.engine, settings, provider(settings, handler=handler)
        )
        assert second["requests_checked"] == 0 and len(calls) == 1
        release.set()
        counts = await first
        assert counts["requests_checked"] == 4 and counts["candidates_found"] == 2
        assert len(calls) == 2
        assert await points() == before
        async with admin_store.begin():
            rows = (await admin_store.execute(select(candidate))).mappings().all()
            assert len(rows) == 2
            assert all(row["match_score"] == 1 and row["rank"] == 1 for row in rows)
            assert all("house_number_exact" in row["match_reasons"] for row in rows)
        again = await work_once(
            engine, admin_store.engine, settings, provider(settings, handler=handler)
        )
        assert again["requests_checked"] == 0 and len(calls) == 2
    finally:
        release.set()
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await engine.dispose()
