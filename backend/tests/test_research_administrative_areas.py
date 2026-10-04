"""Persistent operator workflow: mocked Geocoder and disposable PostGIS only."""

import io
import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

from app.clients.research_geocoder import ResearchGeocoderClient
from app.errors import APIError
from app.repositories.research_areas import resolve_area
from app.repositories.research_resolution import candidates
from app.research.administrative_areas import PersistentManifest, boundaries, import_areas
from app.research.areas import import_boundaries
from tests.test_research_areas import area_store as area_store_fixture
from tests.test_research_areas import provider, row

area_store = area_store_fixture


def polygon(west=9, east=10):
    return {
        "type": "Polygon",
        "coordinates": [[[west, 54], [east, 54], [east, 55], [west, 55], [west, 54]]],
    }


def manifest(level="district", ids=(101,), **changes):
    return PersistentManifest.model_validate(
        {
            "level": level,
            "parent_area_id": None,
            "country_codes": ["DE"],
            "region_code": "DE-SH",
            "osm_admin_level": 4 if level == "state" else 6,
            "inventory_source": "Synthetic reviewed test inventory",
            "complete": False,
            "identities": [{"osm_type": "R", "osm_id": i} for i in ids],
            **changes,
        }
    )


def place(level="district", osm_id=101, **changes):
    return {
        "osm_type": "relation",
        "osm_id": osm_id,
        "country_code": "de",
        "name": "Schleswig-Flensburg",
        "display_name": "Schleswig-Flensburg, Schleswig-Holstein",
        "administrative_level": level,
        "administrative_levels": [level],
        "boundary": polygon(),
        **changes,
    }


def geocoder(settings, records):
    settings.research_geocoder_api_key = SecretStr("test-geocoder-key-with-at-least-32-chars")

    def handle(request):
        assert request.url.path == "/lookup"
        body = json.loads(request.content)
        assert body["include_boundary"] is True and body["osm_type"] == "R"
        record = next((r for r in records if r["osm_id"] == body["osm_id"]), None)
        return httpx.Response(200, json=record) if record else httpx.Response(404)

    return ResearchGeocoderClient(settings, transport=httpx.MockTransport(handle))


@pytest.mark.parametrize("level", ["municipality", "region", "country"])
def test_only_district_and_state(level):
    with pytest.raises(ValidationError):
        manifest(level)


@pytest.mark.parametrize(
    "changes",
    [
        {"identities": []},
        {"identities": [{"osm_type": "N", "osm_id": 1}]},
        {"identities": [{"osm_type": "R", "osm_id": 2**63}]},
        {"country_codes": ["DK"]},
        {"region_code": "DE-XX"},
        {"osm_admin_level": True},
        {"identities": [{"osm_type": "R", "osm_id": 1}] * 2},
        {"identities": [{"osm_type": "R", "osm_id": i} for i in range(1, 102)]},
        {"query": "Schleswig-Holstein"},
    ],
)
def test_manifest_closed_bounded_scope(changes):
    with pytest.raises(ValidationError):
        manifest(**changes)


@pytest.mark.parametrize(
    "record",
    [
        None,
        place("state"),
        place(boundary=None),
        place(country_code="dk"),
        place("municipality", administrative_levels=["municipality", "district"]),
        place(boundary={"type": "Polygon", "coordinates": []}),
    ],
)
async def test_invalid_or_municipal_boundary_fails_before_db(settings, record):
    client = geocoder(settings, [] if record is None else [record])
    connection = AsyncMock()
    try:
        with pytest.raises((ValueError, APIError)):
            await import_areas(connection, client, manifest(), apply=True)
        connection.execute.assert_not_called()
        connection.begin.assert_not_called()
    finally:
        await client.close()


async def test_state_official_code_must_match_manifest(settings):
    client = geocoder(
        settings, [place("state", official_code="DE-NI", official_code_type="ISO-3166-2")]
    )
    try:
        with pytest.raises(ValueError, match="State code mismatch"):
            await boundaries(client, manifest("state"))
    finally:
        await client.close()


@pytest.mark.integration
@pytest.mark.parametrize("level", ["district", "state"])
async def test_plan_apply_idempotence_and_resolver(area_store, settings, level):
    client = geocoder(settings, [place(level)])
    try:
        report = await import_areas(area_store, client, manifest(level))
        assert report["counts"] == {"new": 1, "updated": 0, "unchanged": 0}
        assert await area_store.scalar(text("SELECT count(*) FROM admin.research_area")) == 0
        await area_store.rollback()
        assert (await import_areas(area_store, client, manifest(level), apply=True))[
            "counts"
        ] == report["counts"]
        first = (
            await area_store.execute(
                text("""SELECT id,created_at,updated_at FROM admin.research_area""")
            )
        ).one()
        await area_store.rollback()
        assert (await import_areas(area_store, client, manifest(level), apply=True))["counts"] == {
            "new": 0,
            "updated": 0,
            "unchanged": 1,
        }
        assert (
            await area_store.execute(
                text("SELECT id,created_at,updated_at FROM admin.research_area")
            )
        ).one() == first
        match = await candidates(
            area_store, "area", "Schleswig-Flensburg", settings, expected_level=level
        )
        assert len(match) == 1
        area = await resolve_area(area_store, first.id)
        assert area.area.area_type == level and area.area.population is None
        assert (
            await area_store.scalar(text("SELECT municipality_key FROM admin.research_area"))
            is None
        )
    finally:
        await client.close()


@pytest.mark.integration
async def test_existing_municipality_never_reclassified(area_store, settings):
    await import_boundaries(area_store, provider(settings), "DE-SH", [], [101], apply=True)
    client = geocoder(settings, [place()])
    try:
        with pytest.raises(ValueError, match="conflicting area_type"):
            await import_areas(area_store, client, manifest(), apply=True)
        assert (
            await area_store.scalar(text("SELECT area_type FROM admin.research_area"))
            == "municipality"
        )
    finally:
        await client.close()


@pytest.mark.integration
@pytest.mark.parametrize("level", ["district", "state"])
@pytest.mark.parametrize("persisted", [False, True])
async def test_same_level_overlap_is_atomic(area_store, settings, level, persisted):
    client = geocoder(settings, [place(level, 101), place(level, 102)])
    try:
        if persisted:
            await import_areas(area_store, client, manifest(level), apply=True)
        for apply in [False, True]:
            with pytest.raises(ValueError, match="overlap"):
                await import_areas(
                    area_store,
                    client,
                    manifest(level, (102,) if persisted else (101, 102)),
                    apply=apply,
                )
            assert await area_store.scalar(text("SELECT count(*) FROM admin.research_area")) == int(
                persisted
            )
            await area_store.rollback()
    finally:
        await client.close()


@pytest.mark.integration
async def test_hierarchy_and_expected_level_filter(area_store, settings):
    await import_boundaries(
        area_store,
        provider(settings, [row(name="Ahneby", display_name="Ahneby, Schleswig-Flensburg")]),
        "DE-SH",
        [],
        [101],
        apply=True,
    )
    client = geocoder(
        settings,
        [
            place("district", 102),
            place("state", 103, boundary=polygon(8, 11), name="Schleswig-Holstein"),
        ],
    )
    try:
        await import_areas(area_store, client, manifest("district", (102,)), apply=True)
        await import_areas(area_store, client, manifest("state", (103,)), apply=True)
        matches = await candidates(
            area_store, "area", "Schleswig-Flensburg", settings, expected_level="district"
        )
        assert len(matches) == 1
        assert (await resolve_area(area_store, UUID(matches[0].id))).area.osm_id == "102"
        assert await area_store.scalar(text("SELECT count(*) FROM admin.research_area")) == 3
    finally:
        await client.close()


@pytest.mark.integration
async def test_invalid_topology_does_not_write(area_store, settings):
    invalid = {"type": "Polygon", "coordinates": [[[9, 54], [10, 55], [9, 55], [10, 54], [9, 54]]]}
    client = geocoder(settings, [place(boundary=invalid)])
    try:
        with pytest.raises(ValueError, match="Invalid boundary geometry"):
            await import_areas(area_store, client, manifest(), apply=True)
        assert await area_store.scalar(text("SELECT count(*) FROM admin.research_area")) == 0
    finally:
        await client.close()


def test_additive_migration_and_lossless_downgrade(monkeypatch):
    monkeypatch.setenv(
        "ADMIN_MIGRATION_DATABASE_URL", "postgresql+asyncpg://unused@localhost/unused_test"
    )
    output = io.StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=output), "0018:0019", sql=True)
    sql = output.getvalue()
    statements = [line for line in sql.splitlines() if line.startswith("ALTER TABLE")]
    assert statements == [
        "ALTER TABLE admin.research_area DROP CONSTRAINT research_area_type;",
        "ALTER TABLE admin.research_area ADD CONSTRAINT research_area_type "
        "CHECK (area_type IN ('region','district','municipality','state'));",
    ]
    migration_sql = sql.split("-- Running upgrade 0018 -> 0019", 1)[1]
    assert all(
        word not in migration_sql for word in ["CREATE TABLE", "CREATE INDEX", "GRANT", "REVOKE"]
    )
    assert all(word not in sql for word in ["DELETE", "UPDATE admin.research_area", "uranus."])
    output = io.StringIO()
    command.downgrade(Config("alembic.ini", output_buffer=output), "0019:0018", sql=True)
    sql = output.getvalue()
    assert sql.index("LOCK TABLE") < sql.index("RAISE EXCEPTION") < sql.index("DROP CONSTRAINT")


def test_import_is_operator_only():
    # No API, startup, worker or deployment hook calls the importer.
    for path in [
        Path("app/main.py"),
        *Path("app/api").glob("*.py"),
        *Path("app").glob("*worker.py"),
        *Path("../ansible").rglob("*.yml"),
        *Path("../ansible").rglob("*.j2"),
    ]:
        assert "research.administrative_areas" not in path.read_text()


@pytest.mark.integration
async def test_adjacent_boundaries_and_metadata_update(area_store, settings):
    client = geocoder(settings, [place(osm_id=101), place(osm_id=102, boundary=polygon(10, 11))])
    try:
        await import_areas(area_store, client, manifest(ids=(101, 102)), apply=True)
    finally:
        await client.close()
    renamed = geocoder(settings, [place(name="Updated label", boundary=polygon(9, 9.5))])
    try:
        planned = await import_areas(area_store, renamed, manifest())
        assert planned["counts"] == {"new": 0, "updated": 1, "unchanged": 0}
        assert (
            await area_store.scalar(text("SELECT name FROM admin.research_area WHERE osm_id=101"))
            == "Schleswig-Flensburg"
        )
        await area_store.rollback()
        await import_areas(area_store, renamed, manifest(), apply=True)
        assert (
            await area_store.scalar(text("SELECT name FROM admin.research_area WHERE osm_id=101"))
            == "Updated label"
        )
        assert await area_store.scalar(text("SELECT count(*) FROM admin.research_area")) == 2
    finally:
        await renamed.close()
