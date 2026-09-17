import pytest
from sqlalchemy import event

from app.repositories.entities import entity_page
from app.schemas.entities import EntityFilters
from tests.conftest import uid

CASES = [
    ("organizations", 10),
    ("venues", 20),
    ("spaces", 25),
    ("events", 30),
    ("users", 1),
    ("images", 60),
]


@pytest.mark.integration
@pytest.mark.parametrize("section,key", CASES)
async def test_entity_list_detail_and_boundaries(db_client, headers, section, key):
    response = await db_client.get(f"/api/v1/{section}?page_size=1", headers=headers)
    assert response.status_code == 200, response.text
    page = response.json()
    assert len(page["items"]) == 1
    item = page["items"][0]
    key = item["entity_key"]
    detail = await db_client.get(f"/api/v1/{section}/{key}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["item"]["entity_key"] == key
    assert len(detail.json()["related"]["items"]) <= 25
    serialized = detail.text + response.text
    for secret in (
        "password_hash",
        "activation_token",
        "invitation_token",
        "import_token",
        "not-a-password-hash",
    ):
        assert secret not in serialized
    assert (
        await db_client.get(f"/api/v1/{section}/{uid(99999)}", headers=headers)
    ).status_code == 404
    assert (await db_client.get(f"/api/v1/{section}/invalid", headers=headers)).status_code == 422
    assert (await db_client.get(f"/api/v1/{section}")).status_code == 401
    assert (await db_client.post(f"/api/v1/{section}", headers=headers, json={})).status_code == 405
    search = await db_client.get(f"/api/v1/{section}", params={"q": key}, headers=headers)
    assert search.status_code == 200
    assert search.json()["pagination"]["total"] == 1
    empty = await db_client.get(
        f"/api/v1/{section}", params={"q": "%_' OR true --"}, headers=headers
    )
    assert empty.json()["items"] == []
    org = await db_client.get(
        f"/api/v1/{section}", params={"organization_id": str(uid(99999))}, headers=headers
    )
    assert org.json()["items"] == []
    status = await db_client.get(f"/api/v1/{section}?status=nonexistent", headers=headers)
    assert status.json()["items"] == []


@pytest.mark.integration
async def test_entity_pagination_deterministic_batch_queries(db_connection, settings, now):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().upper())

    event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        first = await entity_page(
            db_connection, settings, "venues", EntityFilters(page_size=1), now
        )
        queries_per_page = len(statements)
        statements.clear()
        second = await entity_page(
            db_connection, settings, "venues", EntityFilters(page=2, page_size=1), now
        )
        assert first.items[0].entity_key != second.items[0].entity_key
        statements.clear()
        all_items = await entity_page(
            db_connection, settings, "venues", EntityFilters(page_size=100), now
        )
        assert len(statements) == queries_per_page
        assert all(s.startswith("SELECT") or s.startswith("WITH") for s in statements)
        assert [i.entity_key for i in all_items.items][:2] == [
            first.items[0].entity_key,
            second.items[0].entity_key,
        ]
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)


@pytest.mark.integration
async def test_detail_relations_and_unknown_image_date(db_client, headers, settings):
    settings.uranus_api_url = "https://api.kulturbytes.de"
    user = (await db_client.get(f"/api/v1/users/{uid(1)}", headers=headers)).json()
    assert any(i["entity_type"] == "team_membership" for i in user["related"]["items"])
    org = (await db_client.get(f"/api/v1/organizations/{uid(10)}", headers=headers)).json()
    assert {"event", "venue", "user", "team_membership"} <= {
        i["entity_type"] for i in org["related"]["items"]
    }
    images = (await db_client.get("/api/v1/images", headers=headers)).json()
    assert any(i["created_at"] is None for i in images["items"])
    assert all(i["image_url"] for i in images["items"])


@pytest.mark.integration
async def test_domain_workflow_counts_and_exact_finding_filter(admin_store, db_client, headers):
    response = await db_client.get("/api/v1/venues", headers=headers)
    assert response.status_code == 200, response.text
    assert all(
        item["finding_count"] == 0 and item["mark_count"] == 0 for item in response.json()["items"]
    )
    detail = await db_client.get(f"/api/v1/venues/{uid(20)}", headers=headers)
    assert detail.json()["item"]["finding_count"] == 0
    assert detail.json()["item"]["action"]["href"] == f"/venues/{uid(20)}"
    findings = await db_client.get(
        f"/api/v1/findings?mode=live&entity_type=venue&entity_key={uid(20)}", headers=headers
    )
    assert findings.status_code == 200
    assert findings.json()["items"]
    assert all(item["entity_key"] == str(uid(20)) for item in findings.json()["items"])
