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
        assert set(data) == {
            "entity_type",
            "entity_key",
            "label",
            "subtitle",
            "status",
            "action",
            "venue_scope",
        }
        assert data["venue_scope"] == ("organization" if kind == "venue" else None)
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
        {"entity_type": "partner_request"},
        {"entity_type": "team_membership"},
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
        ("display_name=''", "max", "max@example.org"),
        ("username=NULL", "max@example.org", None),
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


@pytest.mark.integration
@pytest.mark.parametrize("kind,section,key,queries", CASES)
async def test_global_and_graph_share_canonical_fields(
    search_client, headers, kind, section, key, queries
):
    for query in [*queries, str(uid(key)), str(uid(key))[:8]]:
        response = await search_client.get(
            "/api/v1/search", params={"q": query, "types": kind}, headers=headers
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query"] == query
        assert len(data["groups"]) == 1
        group = data["groups"][0]
        assert group["entity_type"] == kind
        item = next(item for item in group["items"] if item["entity_key"] == str(uid(key)))
        assert item["action"]["href"] == f"/{section}/{uid(key)}"
        assert item["venue_scope"] == ("organization" if kind == "venue" else None)
        assert item["matched_fields"]
        assert set(item) == {
            "entity_type",
            "entity_key",
            "label",
            "subtitle",
            "matched_fields",
            "action",
            "venue_scope",
        }
        if kind != "image":
            graph_response = await search_client.get(
                "/api/v1/graph/search", params={"q": query, "entity_type": kind}, headers=headers
            )
            assert graph_response.status_code == 200, graph_response.text
            graph_item = next(
                i for i in graph_response.json()["items"] if i["key"] == str(uid(key))
            )
            assert (graph_item["label"], graph_item["subtitle"]) == (
                item["label"],
                item["subtitle"],
            )


@pytest.mark.parametrize(
    "params",
    [
        {"q": ""},
        {"q": "x"},
        {"q": "  "},
        {"q": "x" * 121},
        {"limit_per_type": 0},
        {"limit_per_type": 11},
        {"limit_per_type": "x"},
        {"types": ""},
        {"types": "user,user"},
        {"types": "user,unknown"},
        {"types": "admin_account"},
        {"types": "user;DROP TABLE"},
        {"geo_scope_id": str(uid(1))},
    ],
)
async def test_global_validation(client, headers, params):
    async def unused_connection():
        yield None

    client._transport.app.dependency_overrides[get_connection] = unused_connection
    result = await client.get("/api/v1/search", params={"q": "max", **params}, headers=headers)
    assert result.status_code == 422


async def test_global_authentication(client):
    assert (await client.get("/api/v1/search?q=person@example.org")).status_code == 401


@pytest.mark.integration
async def test_global_email_and_fallbacks(search_client, db_connection, headers):
    for query in ("max@example.org", "@example.org"):
        result = await search_client.get("/api/v1/search", params={"q": query}, headers=headers)
        user = result.json()["groups"][0]["items"][0]
        assert user["label"] == "Max Mustermann"
        assert user["matched_fields"] == ["email"]
    for assignment, expected in (
        ("display_name=''", "max"),
        ("username=NULL", "max@example.org"),
        ("email=''", str(uid(1))),
    ):
        await db_connection.execute(
            text(f'UPDATE uranus."user" SET {assignment} WHERE uuid=:id'), {"id": uid(1)}
        )
        data = (
            await search_client.get(
                "/api/v1/search", params={"q": str(uid(1)), "types": "user"}, headers=headers
            )
        ).json()
        assert data["groups"][0]["items"][0]["label"] == expected


@pytest.mark.integration
async def test_global_literal_and_no_secret_search(search_client, db_connection, headers):
    value = r"100% max_ back\slash"
    await db_connection.execute(
        text('UPDATE uranus."user" SET display_name=:name WHERE uuid=:id'),
        {"id": uid(1), "name": value},
    )
    for query in (
        "100%",
        "max_",
        "back\\",
        "%%",
        "__",
        r"\\",
        "private-activation-secret",
        "not-a-password-hash",
        "private-storage-path",
        "not-searchable-description",
    ):
        response = await search_client.get("/api/v1/search", params={"q": query}, headers=headers)
        assert response.status_code == 200
        assert bool(response.json()["groups"]) == (query in value)
        for secret in ("activate_token", "password_hash", "gen_file_name", "matched_values"):
            assert secret not in response.text


@pytest.mark.integration
async def test_global_ranking_limits_single_query_and_explain(db_connection):
    from app.repositories.entity_search import global_search, global_search_query
    from app.schemas.search import GlobalSearchFilters

    # Exact UUID must outrank a different user's exact display-name match.
    for n, name in enumerate(["zzmax", "Maxwell", "max", "amax", "max", str(uid(102))], 100):
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
        result = await global_search(db_connection, GlobalSearchFilters(q="max", limit_per_type=4))
        assert [i.entity_key for i in result.groups[0].items] == [
            str(uid(n)) for n in (102, 104, 101, 103)
        ]
        assert len(statements) == 1
        assert statements[0].count("LIMIT") == 9
        assert "SELECT *" not in statements[0]
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)
    result = await global_search(db_connection, GlobalSearchFilters(q=str(uid(102))))
    assert [i.entity_key for i in result.groups[0].items] == [str(uid(102)), str(uid(105))]
    for limit in (5, 10):
        filters = GlobalSearchFilters(
            q="00", limit_per_type=limit, types="image,event,space,venue,organization,user"
        )
        result = await global_search(db_connection, filters)
        assert [g.entity_type for g in result.groups] == list(filters.selected_types)
        assert all(len(g.items) <= limit for g in result.groups)
        assert sum(len(g.items) for g in result.groups) <= 6 * limit
    query = global_search_query(GlobalSearchFilters(q="max"))
    plan = (
        await db_connection.execute(
            text("EXPLAIN (ANALYZE, FORMAT JSON) " + str(query.statement)), query.parameters
        )
    ).scalar_one()

    def nodes(node):
        yield node
        for child in node.get("Plans", []):
            yield from nodes(child)

    assert sum(n["Node Type"] == "Limit" for n in nodes(plan[0]["Plan"])) == 9


def test_global_bound_parameters_and_definition_fields():
    from app.repositories.entity_search import SEARCH_DEFINITIONS, global_search_query
    from app.schemas.search import GlobalSearchFilters

    value = "private@example.org' OR TRUE --"
    query = global_search_query(GlobalSearchFilters(q=value))
    assert value not in str(query.statement)
    assert query.parameters["exact"] == value
    assert GlobalSearchFilters(q=" max ").q == "max"
    assert GlobalSearchFilters(q="max").limit_per_type == 5
    for definition in SEARCH_DEFINITIONS.values():
        assert len(definition.fields) == len(definition.field_names)
        assert definition.field_names[0] == "uuid"
        assert not {"password_hash", "activate_token", "api_import_token"} & set(
            definition.field_names
        )


@pytest.mark.integration
async def test_global_real_readonly_and_privacy(db_client, headers, caplog):
    import logging
    from unittest.mock import patch

    with patch("app.logging.logging.getLogger", return_value=logging.getLogger("search-test")):
        with caplog.at_level(logging.INFO, logger="search-test"):
            result = await db_client.get(
                "/api/v1/search", params={"q": "fixture@example.invalid"}, headers=headers
            )
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    assert result.json()["groups"][0]["items"][0]["label"] == "fixture@example.invalid"
    assert "fixture@example.invalid" not in caplog.text
    assert all(not hasattr(record, "q") for record in caplog.records)


@pytest.mark.integration
async def test_global_default_and_max_group_limit(search_client, db_connection, headers):
    await db_connection.execute(
        text("""INSERT INTO uranus.pluto_image (uuid,file_name)
        SELECT md5(n::text)::uuid,'global-bounded-search.jpg' FROM generate_series(1,25) n""")
    )
    for params, count in (({}, 5), ({"limit_per_type": 10}, 10)):
        response = await search_client.get(
            "/api/v1/search", headers=headers, params={"q": "global-bounded-search", **params}
        )
        assert response.status_code == 200
        groups = response.json()["groups"]
        assert len(groups) == 1
        assert groups[0]["entity_type"] == "image"
        assert len(groups[0]["items"]) == count


@pytest.mark.integration
async def test_global_event_dates(search_client, db_connection, headers):
    await db_connection.execute(
        text(
            "UPDATE uranus.event_date SET start_date='2026-10-12',start_time='19:00' WHERE uuid=:id"
        ),
        {"id": uid(40)},
    )
    for query, matched in (
        ("hacks on the BEACH", "title"),
        (str(uid(40)), "uuid"),
        (str(uid(30)), "uuid"),
        ("2026-10-12", "start_date"),
        ("12.10.2026", "start_date"),
        ("19:00", "start_time"),
    ):
        response = await search_client.get(
            "/api/v1/search",
            params={"q": query, "types": "event_date", "limit_per_type": 10},
            headers=headers,
        )
        assert response.status_code == 200
        item = next(
            i for i in response.json()["groups"][0]["items"] if i["entity_key"] == str(uid(40))
        )
        assert item["label"] == "hacks on the BEACH"
        assert item["subtitle"] == "12.10.2026 · 19:00"
        assert item["matched_fields"] == [matched]
        assert item["action"]["entity_type"] == "event"
        assert item["action"]["href"] == f"/events/{uid(30)}"
    await db_connection.execute(
        text("UPDATE uranus.event_date SET event_uuid=NULL,all_day=true WHERE uuid=:id"),
        {"id": uid(40)},
    )
    data = (
        await search_client.get(
            "/api/v1/search",
            params={"q": str(uid(40)), "types": "event_date"},
            headers=headers,
        )
    ).json()["groups"][0]["items"][0]
    assert data["label"] == "Termin ohne Veranstaltungstitel"
    assert data["subtitle"] == "12.10.2026 · Ganztägig"
    assert data["action"]["href"] == f"/activity?entity_key={uid(40)}&entity_type=event_date"


@pytest.mark.integration
@pytest.mark.parametrize("joined", [False, True])
async def test_global_memberships_search_and_queue_action(
    search_client, db_connection, headers, joined
):
    from urllib.parse import urlsplit

    await db_connection.execute(
        text("UPDATE uranus.organization_member_link SET has_joined=:joined,invited_at=NULL"),
        {"joined": joined},
    )
    key = f"membership:{uid(10)}:{uid(1)}"
    for query, field in (
        ("Max Mustermann", "display_name"),
        ("max@example.org", "email"),
        ("OK Lab", "name"),
        (str(uid(10)), "uuid"),
        (str(uid(1)), "uuid"),
        ("max", "username"),
    ):
        response = await search_client.get(
            "/api/v1/search",
            params={"q": query, "types": "team_membership"},
            headers=headers,
        )
        assert response.status_code == 200
        item = response.json()["groups"][0]["items"][0]
        assert item["entity_key"] == key
        assert item["label"] == "Max Mustermann"
        assert item["subtitle"] == f"OK Lab Flensburg · {'Beigetreten' if joined else 'Eingeladen'}"
        assert field in item["matched_fields"]
        assert "joined_at" not in response.text
        action = item["action"]
        assert action["route"] == "team_invitations"
        queue = await search_client.get(
            "/api/v1/work-queues/team_invitations?" + urlsplit(action["href"]).query,
            headers=headers,
        )
        assert queue.status_code == 200
        assert queue.json()["items"][0]["entity_key"] == key
        assert queue.json()["items"][0]["has_joined"] is joined
        assert queue.json()["items"][0]["invited_at"] is None


@pytest.mark.integration
async def test_global_partner_search_fallback_and_queue_action(
    search_client, db_connection, headers
):
    from urllib.parse import urlsplit

    for query in ("OK Lab", "Organization 11", str(uid(10)), str(uid(11))):
        response = await search_client.get(
            "/api/v1/search",
            params={"q": query, "types": "partner_request"},
            headers=headers,
        )
        assert response.status_code == 200
        item = response.json()["groups"][0]["items"][0]
        assert item["entity_key"] == f"partner-request:{uid(10)}:{uid(11)}"
        assert item["label"] == "OK Lab Flensburg → Organization 11"
        assert item["subtitle"] == "Ausstehend"
        assert item["matched_fields"] == ["uuid" if query.startswith("0000") else "name"]
        queue = await search_client.get(
            "/api/v1/work-queues/partner_requests?" + urlsplit(item["action"]["href"]).query,
            headers=headers,
        )
        assert queue.status_code == 200
        assert queue.json()["items"][0]["entity_key"] == item["entity_key"]
    await db_connection.execute(
        text("UPDATE uranus.organization SET name='  ' WHERE uuid=:id"), {"id": uid(10)}
    )
    await db_connection.execute(
        text("UPDATE uranus.organization_partner_request SET to_org_uuid=:id,status='accepted'"),
        {"id": uid(999)},
    )
    item = (
        await search_client.get(
            "/api/v1/search",
            params={"q": str(uid(999)), "types": "partner_request"},
            headers=headers,
        )
    ).json()["groups"][0]["items"][0]
    assert item["label"] == "Organisation ohne Namen → Organisation ohne Namen"
    assert item["subtitle"] == "Angenommen"


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["event_date", "partner_request", "team_membership"])
async def test_new_global_literal_metacharacters(search_client, db_connection, headers, kind):
    value = r"100% max_ back\slash"
    if kind == "event_date":
        statement = "UPDATE uranus.event SET title=:value"
    elif kind == "partner_request":
        statement = "UPDATE uranus.organization SET name=:value"
    else:
        statement = 'UPDATE uranus."user" SET display_name=:value'
    await db_connection.execute(text(statement), {"value": value})
    for query in ("100%", "max_", "back\\", "%%", "__", r"\\"):
        response = await search_client.get(
            "/api/v1/search",
            params={"q": query, "types": kind},
            headers=headers,
        )
        assert response.status_code == 200
        assert bool(response.json()["groups"]) == (query in value)


@pytest.fixture
async def all_search_types(db_connection):
    # One common identity across nine independent synthetic types, with enough rows
    # to exercise real per-branch limits. These are not deployed schema evidence.
    for n, label in enumerate(
        ["zzneedle", "Needlework", "needle", "aneedle", "needle", str(uid(102))]
        + ["needlezz bounded"] * 12,
        100,
    ):
        params = {
            "id": uid(n),
            "label": label,
            "email": f"{n}@fixture.invalid",
            "org": uid(10),
            "target": uid(11),
            "venue": uid(20),
        }
        for sql in (
            'INSERT INTO uranus."user" (uuid,email,password_hash,display_name) '
            "VALUES (:id,:email,'unused',:label)",
            "INSERT INTO uranus.organization (uuid,name) VALUES (:id,:label)",
            "INSERT INTO uranus.venue (uuid,org_uuid,name,scope) "
            "VALUES (:id,:org,:label,'organization')",
            "INSERT INTO uranus.space (uuid,venue_uuid,name) VALUES (:id,:venue,:label)",
            "INSERT INTO uranus.event (uuid,org_uuid,title) VALUES (:id,:org,:label)",
            "INSERT INTO uranus.event_date (uuid,event_uuid,start_date) "
            "VALUES (:id,:id,'2026-10-12')",
            "INSERT INTO uranus.pluto_image (uuid,file_name) VALUES (:id,:label)",
            "INSERT INTO uranus.organization_member_link (org_uuid,user_uuid) VALUES (:org,:id)",
            "INSERT INTO uranus.organization_partner_request "
            "(from_org_uuid,to_org_uuid,from_user_uuid) "
            "VALUES (:id,:target,:id)",
        ):
            await db_connection.execute(text(sql), params)


@pytest.mark.integration
async def test_all_nine_ranking_grouping_and_full_bounds(all_search_types, db_connection):
    from app.repositories.entity_search import global_search
    from app.schemas.search import SEARCH_TYPES, GlobalSearchFilters

    def key(kind, n):
        if kind == "partner_request":
            return f"partner-request:{uid(n)}:{uid(11)}"
        if kind == "team_membership":
            return f"membership:{uid(10)}:{uid(n)}"
        return str(uid(n))

    result = await global_search(db_connection, GlobalSearchFilters(q="needle", limit_per_type=3))
    assert tuple(g.entity_type for g in result.groups) == SEARCH_TYPES
    for group in result.groups:
        assert [i.entity_key for i in group.items] == [
            key(group.entity_type, n) for n in (102, 104, 101)
        ]
    result = await global_search(db_connection, GlobalSearchFilters(q="needle", limit_per_type=10))
    for group in result.groups:
        assert [i.entity_key for i in group.items][-1] == key(group.entity_type, 112)
    # Isolate the substring tier after all prefixes by selecting an exact suffix.
    result = await global_search(db_connection, GlobalSearchFilters(q="dle", limit_per_type=10))
    for group in result.groups:
        assert group.items[0].entity_key == key(group.entity_type, 103)

    result = await global_search(db_connection, GlobalSearchFilters(q=str(uid(102))))
    for group in result.groups:
        assert [i.entity_key for i in group.items] == [
            key(group.entity_type, n) for n in (102, 105)
        ]
    for limit in (None, 10):
        filters = GlobalSearchFilters(q="needle", **({"limit_per_type": limit} if limit else {}))
        result = await global_search(db_connection, filters)
        assert len(result.groups) == 9
        assert all(len(g.items) == (limit or 5) for g in result.groups)
        assert sum(len(g.items) for g in result.groups) == (90 if limit else 45)
    filters = GlobalSearchFilters(q="needle", types=",".join(reversed(SEARCH_TYPES)))
    assert (
        tuple(g.entity_type for g in (await global_search(db_connection, filters)).groups)
        == SEARCH_TYPES
    )
