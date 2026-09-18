"""Manual retry against fresh synthetic source data and real PostgreSQL locks."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from functools import partial
from uuid import UUID, uuid4

import email_validator
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.admin_tables import finding
from app.admin_tables import notification as n
from app.admin_tables import notification_delivery as d
from app.admin_tables import notification_delivery_item as di
from app.database import create_engine
from app.errors import APIError
from app.notification_worker import work_once
from app.repositories.notifications import claim, synchronize, valid_intent
from app.services.notifications.delivery import message
from app.services.notifications.retry import enqueue_retry
from app.services.notifications.state import collect
from tests.test_notifications import CONFIG

ORG = UUID(int=11)
WRITE = {"Origin": "http://test", "X-Admin-CSRF": "1"}


@pytest.fixture(autouse=True)
def addresses(monkeypatch):
    monkeypatch.setattr(
        email_validator,
        "validate_email",
        partial(email_validator.validate_email, test_environment=True),
    )


@pytest.fixture
async def retry_case(database, admin_store, settings, request):
    settings.database_url = SecretStr(database[0])
    settings.auth_public_origin = "http://test"
    settings.notification_quality_start_hour = 0
    setup = create_async_engine(database[0], poolclass=NullPool)
    source = create_engine(settings)
    now = datetime.now(UTC)
    config = copy.deepcopy(CONFIG)
    config["recipients"][0]["email"] = "pippa@example.test"
    event = getattr(request, "param", "digest") == "event"
    config["events"]["unpublished_upcoming_events"]["enabled"] = event
    config["events"]["quality_findings"]["enabled"] = not event
    config["events"]["quality_findings"]["minimum_severity"] = "info"

    async def save_config():
        async with setup.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE uranus.organization SET notifications=CAST(:c AS jsonb) WHERE uuid=:id"
                ),
                {"c": json.dumps(config), "id": ORG},
            )

    async def sync():
        _, configs, candidates = await collect(source, admin_store.engine, settings, now, ORG)
        await synchronize(admin_store, ORG, candidates, configs[ORG], settings, now)

    try:
        async with setup.begin() as connection:
            await connection.execute(
                text("ALTER TABLE uranus.organization ADD COLUMN notifications jsonb")
            )
        await save_config()
        _, _, candidates = await collect(source, admin_store.engine, settings, now, ORG)
        async with admin_store.begin():
            for c in candidates:
                p = c.payload
                if p.rule:
                    await admin_store.execute(
                        insert(finding).values(
                            id=p.finding_id,
                            rule=p.rule,
                            severity=p.severity,
                            entity_type=p.entity_type,
                            entity_key=p.entity_key,
                            field=p.field or "",
                            message="Internal detail",
                            first_seen_at=now,
                            last_seen_at=now,
                            status="open",
                            metadata={"finding": {"organization_id": str(ORG)}},
                        )
                    )
        settings.notifications_delivery_enabled = True
        await sync()
        async with admin_store.begin():
            old_id = (await admin_store.execute(select(d.c.id))).scalar_one()
            await admin_store.execute(
                update(d)
                .where(d.c.id == old_id)
                .values(
                    status="permanent_failure",
                    attempt_count=2,
                    last_error="smtp_553",
                    next_attempt_at=None,
                )
            )
            old = dict((await admin_store.execute(select(d))).mappings().one())
        yield {
            "source": source,
            "setup": setup,
            "now": now,
            "config": config,
            "save": save_config,
            "sync": sync,
            "old": old,
        }
    finally:
        async with setup.begin() as connection:
            await connection.execute(
                text("ALTER TABLE uranus.organization DROP COLUMN IF EXISTS notifications")
            )
        await source.dispose()
        await setup.dispose()


async def retry(case, admin, settings, id_=None):
    return await enqueue_retry(
        admin, case["source"], id_ or case["old"]["id"], settings, case["now"]
    )


async def delivery(admin, id_):
    async with admin.begin():
        return dict((await admin.execute(select(d).where(d.c.id == id_))).mappings().one())


async def test_production_553_case_immutable_new_locale_body_and_chain(
    retry_case, admin_store, settings
):
    c = retry_case
    c["config"]["recipients"][0]["locale"] = "da"
    await c["save"]()
    async with c["setup"].begin() as conn:
        await conn.execute(
            text("UPDATE uranus.organization SET name='Updated culture club' WHERE uuid=:id"),
            {"id": ORG},
        )
    try:
        result = await retry(c, admin_store, settings)
        new = await delivery(admin_store, result.delivery_id)
        assert new["status"] == "queued" and new["attempt_count"] == 0
        assert new["queued_at"] == new["next_attempt_at"] == c["now"]
        assert new["locale"] == "da" and new["delivery_kind"] == "digest"
        assert new["retry_of_delivery_id"] == c["old"]["id"]
        assert "Updated culture club" in new["snapshot"]["mail"]["text"]
        assert new["message_fingerprint"] != c["old"]["message_fingerprint"]
        assert message(new, settings)["Message-ID"] != message(c["old"], settings)["Message-ID"]
        assert await delivery(admin_store, c["old"]["id"]) == c["old"]
        async with admin_store.begin():
            await admin_store.execute(
                update(d).where(d.c.id == new["id"]).values(status="permanent_failure")
            )
        again = await retry(c, admin_store, settings, new["id"])
        assert again.retry_of_delivery_id == new["id"]
        with pytest.raises(APIError) as error:
            await retry(c, admin_store, settings)
        assert error.value.code == "notification_retry_not_allowed"
    finally:
        async with c["setup"].begin() as conn:
            await conn.execute(
                text("UPDATE uranus.organization SET name='Organization 11' WHERE uuid=:id"),
                {"id": ORG},
            )


@pytest.mark.parametrize("status", ["failed", "queued", "sending", "sent", "cancelled"])
async def test_nonterminal_states_not_manually_retryable(retry_case, admin_store, settings, status):
    async with admin_store.begin():
        await admin_store.execute(update(d).values(status=status))
    with pytest.raises(APIError) as error:
        await retry(retry_case, admin_store, settings)
    assert (error.value.status, error.value.code) == (409, "notification_retry_not_allowed")


@pytest.mark.parametrize(
    "change", ["removed", "disabled", "invalid", "config_disabled", "absent", "capability"]
)
async def test_recipient_config_capability_revalidated(retry_case, admin_store, settings, change):
    c = retry_case
    if change == "removed":
        c["config"]["recipients"] = []
    if change == "disabled":
        c["config"]["recipients"][0]["enabled"] = False
    if change == "invalid":
        c["config"]["recipients"][0]["locale"] = "fr"
    if change == "config_disabled":
        c["config"]["events"]["quality_findings"]["enabled"] = False
    await c["save"]()
    async with c["setup"].begin() as conn:
        if change == "absent":
            await conn.execute(text("UPDATE uranus.organization SET notifications=NULL"))
        if change == "capability":
            await conn.execute(text("ALTER TABLE uranus.organization DROP COLUMN notifications"))
    with pytest.raises(APIError) as error:
        await retry(c, admin_store, settings)
    assert error.value.code == "notification_retry_obsolete"
    assert await delivery(admin_store, c["old"]["id"]) == c["old"]


@pytest.mark.parametrize(
    "status", ["resolved", "snoozed", "ignored", "exception", "reviewed", "in_progress"]
)
async def test_finding_reviews_revalidated(retry_case, admin_store, settings, status):
    async with admin_store.begin():
        await admin_store.execute(update(finding).values(status=status))
    with pytest.raises(APIError) as error:
        await retry(retry_case, admin_store, settings)
    assert error.value.code == "notification_retry_obsolete"


@pytest.mark.parametrize("state", ["resolved", "expired", "suppressed"])
async def test_inactive_notification_not_retried(retry_case, admin_store, settings, state):
    async with admin_store.begin():
        await admin_store.execute(update(n).values(status=state))
    with pytest.raises(APIError) as error:
        await retry(retry_case, admin_store, settings)
    assert error.value.code == "notification_retry_obsolete"


async def test_digest_prunes_old_items_and_excludes_new_findings(retry_case, admin_store, settings):
    c = retry_case
    old_ids = c["old"]["snapshot"]["ids"]
    assert len(old_ids) >= 2
    async with admin_store.begin():
        first = (
            await admin_store.execute(select(n.c.finding_id).where(n.c.id == UUID(old_ids[0])))
        ).scalar_one()
        await admin_store.execute(
            update(finding).where(finding.c.id == first).values(status="resolved")
        )
        # An unrelated later notification, absent from the original delivery items.
        other = dict(
            (await admin_store.execute(select(n).where(n.c.id == UUID(old_ids[1]))))
            .mappings()
            .one()
        )
        other.update(id=uuid4(), dedupe_key="unrelated-new-finding")
        await admin_store.execute(insert(n).values(**other))
    result = await retry(c, admin_store, settings)
    new = await delivery(admin_store, result.delivery_id)
    assert new["snapshot"]["ids"] == old_ids[1:]
    async with admin_store.begin():
        ids = list(
            (
                await admin_store.execute(
                    select(di.c.notification_id).where(di.c.delivery_id == new["id"])
                )
            ).scalars()
        )
        rows = [dict(r) for r in (await admin_store.execute(select(n))).mappings()]
    assert set(map(str, ids)) == set(old_ids[1:])
    _, configs, _ = await collect(c["source"], admin_store.engine, settings, c["now"], ORG)
    assert valid_intent(new, rows, configs[ORG])


async def test_parallel_retry_requests_have_one_successor(retry_case, admin_store, settings):
    async def request():
        async with admin_store.engine.connect() as conn:
            try:
                return await retry(retry_case, conn, settings)
            except APIError as error:
                return error

    results = await asyncio.gather(request(), request())
    assert sum(not isinstance(r, APIError) for r in results) == 1
    assert (
        next(r for r in results if isinstance(r, APIError)).code
        == "notification_retry_already_queued"
    )
    async with admin_store.begin():
        assert len((await admin_store.execute(select(d))).all()) == 2


@pytest.mark.parametrize("status", ["queued", "sending", "failed"])
async def test_active_successor_blocks_another_retry(retry_case, admin_store, settings, status):
    new = await retry(retry_case, admin_store, settings)
    async with admin_store.begin():
        await admin_store.execute(update(d).where(d.c.id == new.delivery_id).values(status=status))
    with pytest.raises(APIError) as error:
        await retry(retry_case, admin_store, settings)
    assert error.value.code == "notification_retry_already_queued"


@pytest.mark.parametrize("retry_case", ["event"], indirect=True)
async def test_current_event_title_countdown_worker_and_stable_message_id(
    retry_case, admin_store, settings
):
    c = retry_case
    async with c["setup"].begin() as conn:
        await conn.execute(
            text("UPDATE uranus.event SET title='Fresh event title' WHERE uuid=:id"),
            {"id": UUID(int=31)},
        )
    try:
        c["now"] += timedelta(days=1)
        result = await retry(c, admin_store, settings)
        new = await delivery(admin_store, result.delivery_id)
        assert (
            new["snapshot"]["payloads"][0]["days_until"]
            == c["old"]["snapshot"]["payloads"][0]["days_until"] - 1
        )
        assert "Fresh event title" in new["subject"]
        mails = []

        class FakeTransport:
            def send(self, mail, recipient):
                mails.append((mail, recipient))

        await work_once(
            c["source"], admin_store.engine, settings, FakeTransport(), lambda: c["now"]
        )
        sent = await delivery(admin_store, result.delivery_id)
        assert sent["status"] == "sent" and sent["attempt_count"] == 1
        assert len(mails) == 1 and mails[0][1] == "pippa@example.test"
        assert mails[0][0]["Message-ID"] == message(new, settings)["Message-ID"]
        assert await delivery(admin_store, c["old"]["id"]) == c["old"]
    finally:
        async with c["setup"].begin() as conn:
            await conn.execute(
                text("UPDATE uranus.event SET title='Event 31' WHERE uuid=:id"),
                {"id": UUID(int=31)},
            )


@pytest.mark.parametrize("retry_case", ["event"], indirect=True)
@pytest.mark.parametrize("change", ["released", "past", "ownership"])
async def test_event_source_revalidation(retry_case, admin_store, settings, change):
    c = retry_case
    if change == "past":
        c["now"] += timedelta(days=100)
    async with c["setup"].begin() as conn:
        if change == "released":
            await conn.execute(
                text("UPDATE uranus.event SET release_status='released' WHERE uuid=:id"),
                {"id": UUID(int=31)},
            )
        if change == "ownership":
            await conn.execute(
                text("UPDATE uranus.event SET org_uuid=:org WHERE uuid=:id"),
                {"org": UUID(int=10), "id": UUID(int=31)},
            )
    try:
        with pytest.raises(APIError) as error:
            await retry(c, admin_store, settings)
        assert error.value.code == "notification_retry_obsolete"
    finally:
        async with c["setup"].begin() as conn:
            await conn.execute(
                text("UPDATE uranus.event SET release_status='draft',org_uuid=:org WHERE uuid=:id"),
                {"org": ORG, "id": UUID(int=31)},
            )


@pytest.mark.parametrize("limit", ["recipient", "digest"])
async def test_retry_obeys_quotas_but_failed_original_does_not_count(
    retry_case, admin_store, settings, limit
):
    c = retry_case
    new = await retry(c, admin_store, settings)
    async with admin_store.begin():
        other = {
            **c["old"],
            "id": uuid4(),
            "status": "sent",
            "sent_at": c["now"],
            "message_fingerprint": "other-success",
            "delivery_kind": "digest" if limit == "digest" else "initial",
        }
        await admin_store.execute(insert(d).values(**other))
    if limit == "recipient":
        settings.notification_max_emails_per_recipient_per_day = 1
    assert await claim(admin_store, settings, c["now"]) is None
    queued = await delivery(admin_store, new.delivery_id)
    assert queued["status"] == "queued" and queued["next_attempt_at"] > c["now"]
    assert await claim(admin_store, settings, c["now"] + timedelta(days=1))


async def test_api_list_auth_origin_body_conflicts_and_retry(
    retry_case, admin_store, db_client, headers
):
    c = retry_case
    url = f"/api/v1/notification-deliveries/{c['old']['id']}/retry"
    assert (await db_client.post(url)).status_code == 401
    assert (await db_client.post(url, headers=headers)).status_code == 403
    assert (
        await db_client.post(url, headers={**headers, **WRITE, "Origin": "http://evil.test"})
    ).status_code == 403
    for body in [{"recipient": "other@example.test"}, {}, None]:
        assert (
            await db_client.post(url, headers={**headers, **WRITE}, content=json.dumps(body))
        ).status_code == 422
    assert (
        await db_client.post(url + "?locale=da", headers={**headers, **WRITE})
    ).status_code == 422
    assert (await db_client.get("/api/v1/notification-deliveries")).status_code == 401
    page = await db_client.get(
        "/api/v1/notification-deliveries?status=permanent_failure", headers=headers
    )
    assert page.status_code == 200
    assert page.json()["items"][0]["recipient"] == "pippa@example.test"
    assert page.json()["items"][0]["organization_name"] == "Organization 11"
    assert (
        await db_client.get("/api/v1/notification-deliveries?status=sent", headers=headers)
    ).json()["items"] == []
    unknown = await db_client.post(
        f"/api/v1/notification-deliveries/{uuid4()}/retry", headers={**headers, **WRITE}
    )
    assert (
        unknown.status_code == 404
        and unknown.json()["error"]["code"] == "notification_delivery_not_found"
    )
    result = await db_client.post(url, headers={**headers, **WRITE})
    assert result.status_code == 201, result.text
    new_id = result.json()["delivery_id"]
    detail = (
        await db_client.get(f"/api/v1/notification-deliveries/{new_id}", headers=headers)
    ).json()
    assert detail["retry_of_delivery_id"] == str(c["old"]["id"])
    old = (await db_client.get(url.removesuffix("/retry"), headers=headers)).json()
    assert old["retries"][0]["id"] == new_id
    conflict = await db_client.post(url, headers={**headers, **WRITE})
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "notification_retry_already_queued"
    )


async def test_migration_0008_to_0009_preserves_history_and_downgrade(database, monkeypatch):
    setup = create_async_engine(database[0], poolclass=NullPool)
    monkeypatch.setenv("ADMIN_MIGRATION_DATABASE_URL", database[0])
    try:
        async with setup.begin() as conn:
            await conn.execute(text("CREATE SCHEMA admin"))
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "0008")
        old_id, new_id = uuid4(), uuid4()
        async with setup.begin() as conn:
            await conn.execute(
                text("""INSERT INTO admin.notification_delivery
                (id,organization_id,recipient,locale,delivery_kind,status,message_fingerprint,snapshot,attempt_count,last_error,created_at,updated_at)
                VALUES (:id,:org,'pippa@example.test','de','digest','permanent_failure',
                'old','{}',2,'smtp_553',now(),now())"""),
                {"id": old_id, "org": ORG},
            )
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
        async with setup.begin() as conn:
            old = dict((await conn.execute(select(d))).mappings().one())
            assert old["retry_of_delivery_id"] is None
            new = {
                **old,
                "id": new_id,
                "retry_of_delivery_id": old_id,
                "message_fingerprint": "new",
            }
            await conn.execute(insert(d).values(**new))
        with pytest.raises(IntegrityError):
            async with setup.begin() as conn:
                await conn.execute(
                    text("DELETE FROM admin.notification_delivery WHERE id=:id"), {"id": old_id}
                )
        with pytest.raises(IntegrityError):
            async with setup.begin() as conn:
                await conn.execute(
                    insert(d).values(**{**new, "id": uuid4(), "message_fingerprint": "duplicate"})
                )
        await asyncio.to_thread(command.downgrade, Config("alembic.ini"), "0008")
        async with setup.begin() as conn:
            rows = (
                (await conn.execute(text("SELECT * FROM admin.notification_delivery")))
                .mappings()
                .all()
            )
            assert len(rows) == 2
            assert all("retry_of_delivery_id" not in row for row in rows)
            assert next(row for row in rows if row["id"] == old_id)["last_error"] == "smtp_553"
    finally:
        async with setup.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS admin CASCADE"))
        await setup.dispose()


async def test_parallel_api_posts_create_one_retry(retry_case, db_client, headers):
    url = f"/api/v1/notification-deliveries/{retry_case['old']['id']}/retry"
    responses = await asyncio.gather(
        *(db_client.post(url, headers={**headers, **WRITE}) for _ in range(2))
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["error"]["code"]
        == "notification_retry_already_queued"
    )


async def test_api_obsolete_and_ordinary_account_denied(
    retry_case, admin_store, db_client, headers
):
    from app.auth.dependencies import get_identity
    from app.auth.service import AdminPrincipal

    app = db_client._transport.app
    app.dependency_overrides[get_identity] = lambda: AdminPrincipal(
        subject="ordinary", system_admin=False
    )
    url = f"/api/v1/notification-deliveries/{retry_case['old']['id']}/retry"
    try:
        denied = await db_client.post(url, headers={**headers, **WRITE})
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "admin_access_denied"
    finally:
        app.dependency_overrides.pop(get_identity)
    async with admin_store.begin():
        await admin_store.execute(update(finding).values(status="resolved"))
    obsolete = await db_client.post(url, headers={**headers, **WRITE})
    assert (
        obsolete.status_code == 409
        and obsolete.json()["error"]["code"] == "notification_retry_obsolete"
    )
    assert "no-store" in obsolete.headers["cache-control"]


async def test_dry_run_keeps_retry_queued_and_recipient_removed_before_worker_cancels(
    retry_case, admin_store, settings
):
    c = retry_case
    settings.notifications_delivery_enabled = False
    result = await retry(c, admin_store, settings)

    class NoSMTP:
        def send(self, *args):
            pytest.fail("Must not send in Dry Run or to a removed recipient")

    await work_once(c["source"], admin_store.engine, settings, NoSMTP(), lambda: c["now"])
    assert (await delivery(admin_store, result.delivery_id))["status"] == "queued"
    c["config"]["recipients"] = []
    await c["save"]()
    settings.notifications_delivery_enabled = True
    await work_once(c["source"], admin_store.engine, settings, NoSMTP(), lambda: c["now"])
    assert (await delivery(admin_store, result.delivery_id))["status"] == "cancelled"


async def test_manual_digest_survives_new_unrelated_eligible_finding(
    retry_case, admin_store, settings
):
    c = retry_case
    new_event = uuid4()
    try:
        async with c["setup"].begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO uranus.event (uuid,org_uuid,title,release_status) "
                    "VALUES (:id,:org,'Later unrelated event','draft')"
                ),
                {"id": new_event, "org": ORG},
            )
        _, _, fresh = await collect(c["source"], admin_store.engine, settings, c["now"], ORG)
        p = next(
            item.payload
            for item in fresh
            if item.payload.rule == "event_without_dates"
            and item.payload.entity_key == str(new_event)
        )
        async with admin_store.begin():
            await admin_store.execute(
                insert(finding).values(
                    id=p.finding_id,
                    rule=p.rule,
                    severity=p.severity,
                    entity_type=p.entity_type,
                    entity_key=p.entity_key,
                    message="Internal",
                    field=p.field or "",
                    first_seen_at=c["now"],
                    last_seen_at=c["now"],
                    status="open",
                    metadata={"finding": {"organization_id": str(ORG)}},
                )
            )
        settings.notifications_delivery_enabled = False
        await c["sync"]()
        settings.notifications_delivery_enabled = True
        result = await retry(c, admin_store, settings)
        mails = []

        class FakeTransport:
            def send(self, mail, recipient):
                mails.append(mail)

        await work_once(
            c["source"], admin_store.engine, settings, FakeTransport(), lambda: c["now"]
        )
        saved = await delivery(admin_store, result.delivery_id)
        assert saved["status"] == "sent"
        assert saved["snapshot"]["ids"] == c["old"]["snapshot"]["ids"]
        assert len(mails) == 1
        assert (
            "Later unrelated event"
            not in mails[0].get_body(preferencelist=("plain",)).get_content()
        )
    finally:
        async with c["setup"].begin() as conn:
            await conn.execute(text("DELETE FROM uranus.event WHERE uuid=:id"), {"id": new_event})


async def test_cancelled_successor_allows_fresh_parent_intent(retry_case, admin_store, settings):
    first = await retry(retry_case, admin_store, settings)
    async with admin_store.begin():
        await admin_store.execute(
            update(d).where(d.c.id == first.delivery_id).values(status="cancelled")
        )
    second = await retry(retry_case, admin_store, settings)
    assert second.delivery_id != first.delivery_id
    assert second.retry_of_delivery_id == first.retry_of_delivery_id
    assert (await delivery(admin_store, first.delivery_id))["status"] == "cancelled"
    assert await delivery(admin_store, retry_case["old"]["id"]) == retry_case["old"]
