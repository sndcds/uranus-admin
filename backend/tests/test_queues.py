from datetime import timedelta

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
            filters = QueueFilters(page_size=3, **extra)
            expected = []
            for item, row in candidates:
                if item.status in {"joined", "active"}:
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
