"""Real PostgreSQL matching for both HTTP surfaces, using transaction-local fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text

from app.database import get_connection
from app.main import create_app
from app.repositories.entity_search import entity_search, escape_search
from app.schemas.entities import EntitySearchFilters
from tests.conftest import uid


@pytest.fixture
async def search_client(db_connection, settings):
    for index, statement in enumerate(
        (
            """UPDATE uranus."user" SET username='max',display_name='Max Mustermann',
        email='max@example.org',first_name='Maximilian',last_name='Mustermann',
        activate_token='private-activation-secret' WHERE uuid=:id""",
            """UPDATE uranus.organization SET name='OK Lab Flensburg',
        contact_email='lab@org.example',city='Flensburg',postal_code='24939' WHERE uuid=:id""",
            """UPDATE uranus.venue SET name='Aktivitetshuset',contact_email='hello@venue.example',
        street='Norderstraße',house_number='49a',postal_code='24937',city='Flensburg'
        WHERE uuid=:id""",
            "UPDATE uranus.space SET name='Großer Saal',space_type='Auditorium' WHERE uuid=:id",
            """UPDATE uranus.event SET title='hacks on the BEACH',subtitle='Save the Date',
        external_id='external-987',description='not-searchable-description',
        search_text='unverified-search-text' WHERE uuid=:id""",
            """UPDATE uranus.pluto_image SET file_name='beach-photo.jpg',alt_text='Sonnenuntergang',
        creator_name='Photographer',mime_type='image/jpeg',gen_file_name='private-storage-path'
        WHERE uuid=:id""",
        )
    ):
        await db_connection.execute(text(statement), {"id": uid((1, 10, 20, 25, 30, 60)[index])})

    async def connection():
        yield db_connection

    app = create_app(settings)
    app.dependency_overrides[get_connection] = connection
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


CASES = [
    ("user", "users", 1, ["max", "MAX MUSTERMANN", "example.org", "Maximilian", "Mustermann"]),
    ("organization", "organizations", 10, ["OK Lab", "org.example", "Flensburg", "24939"]),
    (
        "venue",
        "venues",
        20,
        ["Aktivitetshuset", "venue.example", "Norder", "49a", "24937", "Flensburg"],
    ),
    ("space", "spaces", 25, ["Großer Saal", "Aktivitetshuset", "Auditorium"]),
    ("event", "events", 30, ["hacks", "Save the Date", "external-987"]),
    ("image", "images", 60, ["beach-photo", "Sonnenuntergang", "Photographer", "image/jpeg"]),
]


@pytest.mark.integration
@pytest.mark.parametrize("kind,section,key,queries", CASES)
async def test_search_fields_on_both_http_surfaces(
    search_client, headers, kind, section, key, queries
):
    for query in [*queries, str(uid(key)), str(uid(key))[:8]]:
        for path, params in (
            ("entity-search", {"entity_type": kind, "q": query}),
            (section, {"q": query}),
        ):
            response = await search_client.get(f"/api/v1/{path}", params=params, headers=headers)
            assert response.status_code == 200, response.text
            assert str(uid(key)) in [item["entity_key"] for item in response.json()["items"]]
            for secret in (
                "password_hash",
                "activate_token",
                "private-activation-secret",
                "not-a-password-hash",
                "gen_file_name",
                "private-storage-path",
            ):
                assert secret not in response.text


@pytest.mark.integration
async def test_compact_labels_subtitles_and_actions(search_client, headers):
    expected = [
        ("user", "max", "Max Mustermann", "@max · max@example.org", "users", 1),
        ("organization", "OK Lab", "OK Lab Flensburg", "Flensburg · 24939", "organizations", 10),
        (
            "venue",
            "Aktivitetshuset",
            "Aktivitetshuset",
            "Norderstraße 49a · 24937 Flensburg",
            "venues",
            20,
        ),
        ("space", "Großer", "Großer Saal", "Aktivitetshuset", "spaces", 25),
        ("event", "hacks", "hacks on the BEACH", "Save the Date", "events", 30),
        ("image", "beach-photo", "Sonnenuntergang", "image/jpeg", "images", 60),
    ]
    for kind, query, label, subtitle, section, key in expected:
        data = (
            await search_client.get(
                "/api/v1/entity-search", params={"q": query, "entity_type": kind}, headers=headers
            )
        ).json()["items"][0]
        assert data["label"] == label
        assert data["subtitle"] == subtitle
        assert data["action"]["href"] == f"/{section}/{uid(key)}"
        assert set(data) == {"entity_type", "entity_key", "label", "subtitle", "status", "action"}
    for query in ("not-searchable-description", "unverified-search-text"):
        for path in ("events", "entity-search"):
            params = {"q": query, **({"entity_type": "event"} if path == "entity-search" else {})}
            assert (
                await search_client.get(f"/api/v1/{path}", params=params, headers=headers)
            ).json()["items"] == []


@pytest.mark.integration
async def test_literal_metacharacters(search_client, db_connection, headers):
    await db_connection.execute(
        text('UPDATE uranus."user" SET display_name=:value WHERE uuid=:id'),
        {"value": r"100% max_ back\slash", "id": uid(1)},
    )
    for query in ("100%", "max_", "back\\", "%%", "__", r"\\"):
        expected = query in r"100% max_ back\slash"
        for path in ("users", "entity-search"):
            params = {"q": query, **({"entity_type": "user"} if path == "entity-search" else {})}
            data = (
                await search_client.get(f"/api/v1/{path}", params=params, headers=headers)
            ).json()
            assert bool(data["items"]) == expected
    for query in ("%", "_"):
        assert (
            await search_client.get("/api/v1/users", params={"q": query}, headers=headers)
        ).json()["pagination"]["total"] == 1


@pytest.mark.integration
@pytest.mark.parametrize("kind,section,key,queries", CASES)
async def test_organization_scope(
    search_client, db_connection, headers, kind, section, key, queries
):
    await db_connection.execute(
        text("""INSERT INTO uranus.pluto_image_link
        (pluto_image_uuid,context,context_uuid,identifier)
        VALUES (:image,'venue',:venue,'main')"""),
        {"image": uid(60), "venue": uid(20)},
    )
    for path in ("entity-search", section):
        for org, found in ((10, True), (999, False)):
            params = {
                "q": queries[0],
                "organization_id": str(uid(org)),
                **({"entity_type": kind} if path == "entity-search" else {}),
            }
            response = await search_client.get(f"/api/v1/{path}", params=params, headers=headers)
            assert response.status_code == 200, response.text
            assert bool(response.json()["items"]) == found


@pytest.mark.integration
async def test_ranking_bounds_stability_and_single_select(db_connection, settings, now):
    for n, name in enumerate(["zzmax", "Maxwell", "max", "amax", "max"], 100):
        await db_connection.execute(
            text(
                'INSERT INTO uranus."user" (uuid,email,password_hash,display_name) '
                "VALUES (:id,:email,'unused',:name)"
            ),
            {"id": uid(n), "email": f"{n}@fixture.invalid", "name": name},
        )
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        result = await entity_search(
            db_connection, EntitySearchFilters(q="max", entity_type="user", limit=4), settings, now
        )
        assert [item.entity_key for item in result.items] == [
            str(uid(n)) for n in (102, 104, 101, 103)
        ]
        assert len(statements) == 1
        assert statements[0].lstrip().startswith("SELECT")
        assert "LIMIT" in statements[0]
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)


@pytest.mark.parametrize(
    "params",
    [
        {"q": "m"},
        {"q": "%"},
        {"q": "_"},
        {"q": "  "},
        {"q": "a" * 201},
        {"limit": 21},
        {"limit": 0},
        {"organization_id": "invalid"},
        {"entity_type": "event_date"},
        {"entity_type": "user;DROP TABLE"},
    ],
)
async def test_search_validation(client, headers, params):
    async def unused_connection():
        yield None

    client._transport.app.dependency_overrides[get_connection] = unused_connection
    response = await client.get(
        "/api/v1/entity-search",
        params={"q": "max", "entity_type": "user", **params},
        headers=headers,
    )
    assert response.status_code == 422


async def test_search_authentication(client):
    assert (await client.get("/api/v1/entity-search?q=max&entity_type=user")).status_code == 401


def test_escape_and_contract_bounds():
    assert escape_search(r" 100%_\ ") == r"100\%\_\\"
    assert EntitySearchFilters(q=" max ", entity_type="user").q == "max"
    assert EntitySearchFilters(q="max", entity_type="user").limit == 10


@pytest.mark.integration
async def test_status_filters_on_search_and_list(search_client, headers):
    for path in ("entity-search", "users"):
        for status, expected in (("inactive", True), ("active", False)):
            response = await search_client.get(
                f"/api/v1/{path}",
                headers=headers,
                params={
                    "q": "max",
                    "status": status,
                    **({"entity_type": "user"} if path == "entity-search" else {}),
                },
            )
            assert response.status_code == 200
            assert bool(response.json()["items"]) == expected


@pytest.mark.integration
async def test_user_and_image_label_fallbacks(search_client, db_connection, headers):
    for assignments, label, subtitle in (
        ("display_name=''", "max", "@max · max@example.org"),
        ("username=NULL", "max@example.org", "max@example.org"),
        ("email=''", str(uid(1)), None),
    ):
        await db_connection.execute(
            text(f'UPDATE uranus."user" SET {assignments} WHERE uuid=:id'), {"id": uid(1)}
        )
        response = await search_client.get(
            "/api/v1/entity-search",
            headers=headers,
            params={"q": str(uid(1)), "entity_type": "user"},
        )
        item = response.json()["items"][0]
        assert (item["label"], item["subtitle"]) == (label, subtitle)
    await db_connection.execute(
        text("UPDATE uranus.pluto_image SET alt_text=NULL WHERE uuid=:id"), {"id": uid(60)}
    )
    response = await search_client.get(
        "/api/v1/entity-search", headers=headers, params={"q": str(uid(60)), "entity_type": "image"}
    )
    assert response.json()["items"][0]["label"] == "beach-photo.jpg"


@pytest.mark.integration
async def test_search_default_and_max_limits(search_client, db_connection, headers):
    await db_connection.execute(
        text("""INSERT INTO uranus.pluto_image (uuid,file_name)
        SELECT md5(n::text)::uuid,'bounded-search.jpg' FROM generate_series(1,25) n""")
    )
    for params, count in (({}, 10), ({"limit": 20}, 20)):
        response = await search_client.get(
            "/api/v1/entity-search",
            headers=headers,
            params={"q": "bounded-search", "entity_type": "image", **params},
        )
        assert len(response.json()["items"]) == count


@pytest.mark.integration
async def test_search_uses_real_read_only_connection(db_client, headers):
    response = await db_client.get(
        "/api/v1/entity-search",
        headers=headers,
        params={"q": "fixture.jpg", "entity_type": "image"},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["entity_key"] == str(uid(60))
