from datetime import timedelta

import pytest
from sqlalchemy import text

from app.schemas.queues import QueueFilters
from app.services.queues import get_queue, queue_findings
from tests.conftest import uid


async def test_partner_checks_and_exact_grant_direction(db_connection, settings, now):
    await db_connection.execute(
        text("UPDATE uranus.organization_partner_request SET status='accepted'")
    )
    result = await get_queue(db_connection, settings, "partner_requests", QueueFilters(), now)
    assert result.items[0].checks == ["partner_accepted_without_grant"]
    assert result.items[0].from_organization_id == uid(10)
    assert result.items[0].to_organization_id == uid(11)
    await db_connection.execute(
        text("INSERT INTO uranus.organization_access_grants VALUES (:a,:b,0)"),
        {"a": uid(10), "b": uid(11)},
    )
    assert (
        await get_queue(db_connection, settings, "partner_requests", QueueFilters(), now)
    ).items[0].checks == ["partner_accepted_without_grant"]
    await db_connection.execute(
        text("INSERT INTO uranus.organization_access_grants VALUES (:b,:a,0)"),
        {"a": uid(10), "b": uid(11)},
    )
    assert (
        not (await get_queue(db_connection, settings, "partner_requests", QueueFilters(), now))
        .items[0]
        .checks
    )
    await db_connection.execute(
        text(
            "UPDATE uranus.organization_partner_request SET from_org_uuid=:a,to_org_uuid=:a,"
            "from_user_uuid=:a,status='alien'"
        ),
        {"a": uid(999)},
    )
    checks = (
        (await get_queue(db_connection, settings, "partner_requests", QueueFilters(), now))
        .items[0]
        .checks
    )
    assert set(checks) == {
        "partner_self_request",
        "partner_missing_organization",
        "partner_missing_user",
        "partner_unknown_status",
    }


async def test_invitation_age_and_activation_never_use_modified(db_connection, settings, now):
    old = (now - timedelta(days=60)).replace(tzinfo=None)
    await db_connection.execute(
        text("UPDATE uranus.organization_member_link SET created_at=:old,invited_at=NULL"),
        {"old": old},
    )
    item = (
        await get_queue(db_connection, settings, "team_invitations", QueueFilters(), now)
    ).items[0]
    assert item.age_days is None and item.invited_at is None and not item.checks
    await db_connection.execute(
        text("UPDATE uranus.organization_member_link SET invited_at=:old"), {"old": old}
    )
    assert (
        await get_queue(
            db_connection, settings, "team_invitations", QueueFilters(min_age_days=30), now
        )
    ).items[0].checks == ["team_invitation_old"]
    await db_connection.execute(
        text('UPDATE uranus."user" SET created_at=:old,modified_at=:now'),
        {"old": old, "now": now.replace(tzinfo=None)},
    )
    item = (
        await get_queue(
            db_connection, settings, "user_activation", QueueFilters(organization_id=uid(10)), now
        )
    ).items[0]
    assert item.checks == ["user_activation_old"] and item.age_days == 60
    await db_connection.execute(text('UPDATE uranus."user" SET is_active=true'))
    await db_connection.execute(text("UPDATE uranus.organization_member_link SET has_joined=true"))
    assert not (
        await get_queue(db_connection, settings, "user_activation", QueueFilters(), now)
    ).items
    results = {r.rule: r for r in await queue_findings(db_connection, settings, now)}
    assert not results["user_activation_old"].findings
    assert ("user", str(uid(1))) in results["user_activation_old"].covered
    assert ("team_membership", f"membership:{uid(10)}:{uid(1)}") in results[
        "team_invitation_old"
    ].covered


async def test_long_pending_threshold_and_filters(db_connection, settings, now):
    await db_connection.execute(
        text("UPDATE uranus.organization_partner_request SET created_at=:old"),
        {"old": (now - timedelta(days=15)).replace(tzinfo=None)},
    )
    page = await get_queue(
        db_connection, settings, "partner_requests", QueueFilters(organization_id=uid(11)), now
    )
    assert page.items[0].checks == ["partner_long_pending"]
    assert not (
        await get_queue(
            db_connection, settings, "partner_requests", QueueFilters(status="accepted"), now
        )
    ).items
    assert not (
        await get_queue(
            db_connection, settings, "partner_requests", QueueFilters(page=2, page_size=1), now
        )
    ).items


async def test_sql_queue_pagination_matches_domain_mapping(db_connection, settings, now):
    from app.repositories.queues import queue_rows
    from app.services.queues import map_queue

    # Many rows, equal ages, unknown/future invitation dates and closed states.
    for n in range(2, 32):
        stamp = (now - timedelta(days=n % 4, hours=1)).replace(tzinfo=None)
        invited = None if n % 5 == 0 else stamp
        if n % 7 == 0:
            invited = (now + timedelta(days=1)).replace(tzinfo=None)
        await db_connection.execute(
            text(
                'INSERT INTO uranus."user" (uuid,created_at,is_active,email,password_hash) '
                "VALUES (:id,:stamp,:active,:email,'not-a-password-hash')"
            ),
            {
                "id": uid(n + 100),
                "stamp": stamp,
                "active": n % 6 == 0,
                "email": f"fixture-{n}@example.invalid",
            },
        )
        await db_connection.execute(
            text(
                "INSERT INTO uranus.organization_member_link "
                "(org_uuid,user_uuid,created_at,invited_at,has_joined) "
                "VALUES (:org,:id,:stamp,:invited,:joined)"
            ),
            {
                "org": uid(10 if n % 2 else 11),
                "id": uid(n + 100),
                "stamp": stamp,
                "invited": invited,
                "joined": n % 6 == 0,
            },
        )
    for kind in ("partner_requests", "team_invitations", "user_activation"):
        rows = await queue_rows(db_connection, kind)
        candidates = [(map_queue(kind, row, settings, now), row) for row in rows]
        for extra in (
            {},
            {"organization_id": uid(10)},
            {"min_age_days": 0},
            {"min_age_days": 2},
            {"status": "joined"},
            {"status": "active"},
            {"status": "invited"},
            {"entity_key": candidates[0][0].entity_key},
            {"entity_key": "' OR 1=1 --"},
        ):
            if kind == "team_invitations" and "status" in extra:
                continue  # Memberships use the separate typed filter.
            filters = QueueFilters(page_size=3, **extra)
            expected = []
            for item, row in candidates:
                if item.status == "active" or (item.status == "joined" and not filters.entity_key):
                    continue
                if filters.organization_id and filters.organization_id not in {
                    item.organization_id,
                    item.to_organization_id,
                    *row.get("organizations", []),
                }:
                    continue
                if filters.status and item.status != filters.status:
                    continue
                if filters.entity_key and item.entity_key != filters.entity_key:
                    continue
                if filters.min_age_days is not None and (
                    item.age_days is None or item.age_days < filters.min_age_days
                ):
                    continue
                expected.append(item)
            expected.sort(key=lambda x: (x.age_days is None, -(x.age_days or 0), x.entity_key))
            for page in (1, 2, 100):
                filters.page = page
                result = await get_queue(db_connection, settings, kind, filters, now)
                assert result.pagination.total == len(expected)
                assert result.items == expected[(page - 1) * 3 : page * 3]


async def test_email_label_preserves_existing_review_fingerprint(db_connection, settings, now):
    """A presentation-only deployment must not invalidate old queue exceptions."""
    import hashlib
    import json

    old = (now - timedelta(days=60)).replace(tzinfo=None)
    for name in (None, ""):
        await db_connection.execute(
            text(
                'UPDATE uranus."user" SET display_name=:name,username=NULL,'
                "email='no-name@example.org',created_at=:old WHERE uuid=:id"
            ),
            {"name": name, "old": old, "id": uid(1)},
        )
        # Exact pre-change queue evidence shape (including its NULL/blank name).
        historical_row = {
            "user_id": uid(1),
            "user_name": name,
            "created_at": old,
            "is_active": False,
            "organizations": [uid(10)],
        }
        expected = hashlib.sha256(
            json.dumps(historical_row, sort_keys=True, default=str).encode()
        ).hexdigest()
        results = {r.rule: r for r in await queue_findings(db_connection, settings, now)}
        finding = results["user_activation_old"].findings[0]
        assert finding.entity_name == "no-name@example.org"
        assert finding.metadata["source_fingerprint"] == expected
        assert "review_user_name" not in finding.model_dump_json()


@pytest.fixture
async def memberships(db_connection, now):
    await db_connection.execute(
        text(
            "INSERT INTO uranus.organization_member_link "
            "(org_uuid,user_uuid,created_at,invited_at,has_joined) "
            "VALUES (:org,:user,:stamp,:stamp,true)"
        ),
        {"org": uid(11), "user": uid(1), "stamp": now.replace(tzinfo=None)},
    )
    return {"invited": f"membership:{uid(10)}:{uid(1)}", "joined": f"membership:{uid(11)}:{uid(1)}"}


@pytest.mark.parametrize(
    "status,expected",
    [
        (None, ["invited"]),
        ("invited", ["invited"]),
        ("joined", ["joined"]),
        ("all", ["invited", "joined"]),
    ],
)
async def test_membership_status_counts_and_pages(
    memberships, db_connection, settings, now, status, expected
):
    filters = QueueFilters(**({"membership_status": status} if status else {}), page_size=1)
    found = []
    for page_number in range(1, len(expected) + 2):
        filters.page = page_number
        result = await get_queue(db_connection, settings, "team_invitations", filters, now)
        assert result.pagination.total == len(expected)
        assert result.pagination.pages == len(expected)
        assert len(result.items) == (1 if page_number <= len(expected) else 0)
        found.extend(item.status for item in result.items)
    assert sorted(found) == sorted(expected)


@pytest.mark.parametrize("state", ["joined", "invited"])
@pytest.mark.parametrize("status", ["invited", "joined", "all"])
async def test_exact_membership_overrides_filters(
    memberships, db_connection, settings, now, state, status
):
    filters = QueueFilters(
        entity_key=memberships[state],
        membership_status=status,
        organization_id=uid(999),
        min_age_days=36500,
    )
    result = await get_queue(db_connection, settings, "team_invitations", filters, now)
    assert result.pagination.total == result.pagination.pages == 1
    assert len(result.items) == 1
    item = result.items[0]
    assert item.entity_key == memberships[state]
    assert item.status == state
    assert item.has_joined == (state == "joined")
    assert not item.checks
    from urllib.parse import parse_qs, urlsplit

    assert parse_qs(urlsplit(item.action.href).query) == {"entity_key": [memberships[state]]}


@pytest.mark.parametrize("key", [f"membership:{uid(999)}:{uid(1)}", "' OR 1=1 --"])
async def test_missing_membership_and_bound_key(memberships, db_connection, settings, now, key):
    from app.repositories.queues import queue_page_queries

    filters = QueueFilters(entity_key=key)
    result = await get_queue(db_connection, settings, "team_invitations", filters, now)
    assert result.items == []
    assert result.pagination.total == result.pagination.pages == 0
    for query in queue_page_queries("team_invitations", filters, now, "UTC").values():
        assert key not in str(query.statement)
        assert query.parameters["entity_key"] == key


@pytest.mark.parametrize(
    "params", [{"membership_status": "active"}, {"membership_status": ""}, {"status": "joined"}]
)
async def test_membership_api_rejects_ambiguous_status(db_client, headers, params):
    response = await db_client.get(
        "/api/v1/work-queues/team_invitations", headers=headers, params=params
    )
    assert response.status_code == 422


async def test_membership_api_uses_readonly_source(db_client, headers):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        response = await db_client.get(
            "/api/v1/work-queues/team_invitations",
            headers=headers,
            params={"membership_status": "all"},
        )
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert response.json()["items"][0]["status"] == "invited"
    assert any("READ ONLY" in statement for statement in statements)
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
    )


async def test_user_timeline_membership_link_opens_joined_record(
    memberships, admin_store, db_connection, settings, now, headers
):
    from urllib.parse import urlsplit

    from httpx import ASGITransport, AsyncClient

    from app.database import get_connection
    from app.main import create_app
    from app.repositories.timeline import timeline_page
    from app.schemas.timeline import TimelineFilters

    timeline = await timeline_page(
        db_connection, admin_store, settings, "user", uid(1), TimelineFilters(), now
    )
    invitation = next(
        item
        for item in timeline.items
        if item.kind == "team_invitation" and item.metadata.status == "joined"
    )
    assert invitation.href is not None
    query = urlsplit(invitation.href).query

    async def source():
        yield db_connection

    app = create_app(settings)
    app.dependency_overrides[get_connection] = source
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/work-queues/team_invitations?{query}", headers=headers
        )
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] == 1
    assert data["items"][0]["entity_key"] == memberships["joined"]
    assert data["items"][0]["status"] == "joined"
