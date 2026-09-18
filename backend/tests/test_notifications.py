"""Synthetic mail addresses and fake transport only; PostgreSQL for durable boundaries."""

import asyncio
import copy
import json
import smtplib
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from html import escape
from uuid import UUID, uuid4
from xml.etree import ElementTree as ET

import email_validator
import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.admin_tables import notification as n
from app.admin_tables import notification_delivery as d
from app.admin_tables import notification_delivery_item as di
from app.config import Settings
from app.notification_worker import work_once
from app.repositories.notifications import claim, local_day, synchronize
from app.repositories.quality_sources import Sources, load_sources
from app.schemas.notifications import NotificationConfig, NotificationPayload
from app.services.notifications import rendering
from app.services.notifications.actions import RecipientActions
from app.services.notifications.batching import batches, content_version
from app.services.notifications.candidates import Candidate, detect
from app.services.notifications.config import source_capability, validate_configs
from app.services.notifications.delivery import SMTPTransport, failure, finish, message
from app.services.notifications.localization import CATALOGUE, catalogue
from app.services.notifications.policy import EXTERNAL_POLICY, next_date
from app.services.notifications.rendering import render

NOW = datetime(2026, 9, 18, 10, tzinfo=UTC)
ORG = UUID(int=10)
CONFIG = {
    "version": 1,
    "recipients": [{"email": "recipient@example.test", "locale": "de", "enabled": True}],
    "events": {
        "unpublished_upcoming_events": {
            "enabled": True,
            "days_before": 14,
            "reminder": {"enabled": True, "days_after": 7},
        },
        "quality_findings": {
            "enabled": True,
            "minimum_severity": "warning",
            "delivery": "daily_digest",
        },
    },
}


@pytest.fixture(autouse=True)
def reserved_test_addresses(monkeypatch):
    # email-validator deliberately rejects .test in production. Enable its documented
    # test mode only in this module; validation itself stays real.
    monkeypatch.setattr(
        email_validator,
        "validate_email",
        partial(email_validator.validate_email, test_environment=True),
    )


@pytest.fixture
def config():
    return NotificationConfig.model_validate(copy.deepcopy(CONFIG))


def payload(**changes):
    return NotificationPayload(
        organization_name="Kulturverein",
        entity_name="Kulturabend",
        entity_type="event",
        entity_key=str(UUID(int=31)),
        internal_action_path=f"/events/{UUID(int=31)}",
        external_action_url=f"https://app.kulturbytes.de/admin/event/{UUID(int=31)}",
        event_status="draft",
        next_date="2026-09-30",
        days_until=12,
        stage=1,
        **changes,
    )


def candidate(key=31, status="active", p=None):
    p = p or payload().model_copy(update={"entity_key": str(UUID(int=key))})
    return Candidate(
        ORG,
        "quality_finding" if p.rule else "unpublished_upcoming_event",
        f"event:{ORG}:{key}",
        status,
        p,
    )


def row(key=31, p=None):
    return {
        "id": UUID(int=key),
        "status": "active",
        "notification_type": "quality_finding" if p and p.rule else "unpublished_upcoming_event",
        "payload": (p or payload()).model_dump(mode="json"),
    }


@pytest.mark.parametrize(
    "path,value",
    [
        (("version",), 2),
        (("version",), True),
        (("version",), "1"),
        (("unknown",), True),
        (("recipients", 0, "email"), "bad\r\nBcc: evil@example.test"),
        (("recipients", 0, "locale"), "fr"),
        (("recipients", 0, "enabled"), "yes"),
        (("events", "unpublished_upcoming_events", "days_before"), -1),
        (("events", "unpublished_upcoming_events", "days_before"), 366),
        (("events", "unpublished_upcoming_events", "reminder", "days_after"), 0),
        (("events", "unpublished_upcoming_events", "reminder", "days_after"), 91),
        (("events", "quality_findings", "delivery"), "immediate"),
    ],
)
def test_strict_config(path, value):
    data = copy.deepcopy(CONFIG)
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        NotificationConfig.model_validate(data)


def test_duplicate_recipient_rejected():
    data = copy.deepcopy(CONFIG)
    data["recipients"].append({"email": "RECIPIENT@example.test", "locale": "da"})
    with pytest.raises(ValidationError):
        NotificationConfig.model_validate(data)


def test_invalid_org_isolated_and_no_pii_log(caplog):
    invalid = copy.deepcopy(CONFIG)
    invalid["recipients"][0]["locale"] = "fr"
    valid, issues = validate_configs(
        [
            {"uuid": ORG, "name": "One", "notifications": invalid},
            {"uuid": UUID(int=11), "name": "Two", "notifications": CONFIG},
        ]
    )
    assert list(valid) == [UUID(int=11)]
    assert len(issues) == 1
    assert "recipient@example.test" not in caplog.text


@pytest.mark.parametrize(
    "locale,subject,day,status",
    [
        ("de", "Deine Veranstaltung", "30. September 2026", "Entwurf"),
        ("da", "Dit arrangement", "30. september 2026", "kladde"),
        ("en", "Your event", "30 September 2026", "Draft"),
    ],
)
def test_localization(locale, subject, day, status, settings):
    preview = render([payload()], locale, settings)
    assert preview.locale == locale
    assert subject in preview.subject
    for value in (
        "Kulturabend",
        "Kulturverein",
        day,
        status,
        "https://app.kulturbytes.de/admin/event/",
    ):
        assert value in preview.text
        assert value in preview.html
    assert "tracking" not in preview.html
    assert "<script" not in preview.html


@pytest.mark.parametrize("locale", ["de", "da", "en"])
@pytest.mark.parametrize("days,key", [(0, "today"), (1, "tomorrow"), (2, "days")])
def test_relative_text(locale, days, key, settings):
    result = render([payload().model_copy(update={"days_until": days})], locale, settings)
    assert CATALOGUE[locale][key].format(count=days) in result.text


def test_catalogue_complete_and_whole_message_fallback(monkeypatch, settings):
    assert CATALOGUE["de"].keys() == CATALOGUE["da"].keys() == CATALOGUE["en"].keys()
    for rule in EXTERNAL_POLICY:
        for suffix in ("title", "explanation", "recommendation"):
            assert f"{rule}.{suffix}" in CATALOGUE["en"]
    monkeypatch.delitem(CATALOGUE["da"], "publish")
    result = render([payload()], "da", settings)
    assert (
        result.locale == "en"
        and "Your event" in result.text
        and "Dit arrangement" not in result.text
    )
    assert catalogue("invalid")[0] == "en"


def test_escaping_header_and_long_title(settings):
    p = payload().model_copy(
        update={
            "entity_name": '<img src=x onerror="alert(1)">\r\nBcc: evil@example.test' + "a" * 300
        }
    )
    result = render([p], "de", settings)
    assert "<img" not in result.html and "&lt;img" in result.html
    assert "\r" not in result.subject and "\n" not in result.subject
    assert len(result.subject) <= 180
    assert p.entity_name in result.text


@pytest.mark.parametrize("rule", list(EXTERNAL_POLICY))
@pytest.mark.parametrize("locale", ["de", "da", "en"])
def test_quality_presentations(rule, locale, settings):
    kind = sorted(EXTERNAL_POLICY[rule].entities)[0]
    p = payload(rule=rule).model_copy(update={"entity_type": kind, "field": "ticket_link"})
    result = render([p], locale, settings)
    assert CATALOGUE[locale][f"{rule}.recommendation"] in result.text
    for technical in ("entity_key", "UUID", "SQL", "projection", "foreign key", "constraint"):
        assert technical not in result.text
    if rule == "url_syntax":
        assert CATALOGUE[locale]["ticket_link"] in result.text


@pytest.mark.parametrize(
    "rule",
    [
        "postal_code_whitespace",
        "event_date_space_venue_mismatch",
        "image_link_without_image",
        "image_link_unknown_context",
        "image_link_invalid_identifier",
        "image_link_missing_target",
        "image_orphaned_upload",
        "logo_unsupported_format",
        "new_rule",
    ],
)
def test_internal_rules_never_render(rule, settings):
    with pytest.raises(ValueError, match="Internal"):
        render([payload(rule=rule)], "de", settings)


def test_temporal_order_today_null_all_day():
    local = NOW.replace(hour=12)
    values = [
        {"uuid": UUID(int=i), "start_date": date(2026, 9, 18), "start_time": t, "all_day": all_day}
        for i, t, all_day in [
            (3, None, False),
            (2, time(13), False),
            (1, time(13), False),
            (4, time(11), False),
        ]
    ]
    assert next_date(values, local)["uuid"] == UUID(int=1)
    assert next_date([values[0]], local) == values[0]
    assert next_date([values[-1]], local) is None
    values[-1]["all_day"] = True
    assert next_date([values[-1]], local) == values[-1]


def test_reminder_highest_stage_batching(config):
    items = [row(i) for i in range(31, 34)]
    initial = batches(items, [], config.recipients[0], config, NOW)
    assert len(initial) == 1 and len(initial[0]["snapshot"]["ids"]) == 3
    history = [{**initial[0], "id": uuid4(), "status": "sent", "sent_at": NOW}]
    assert batches(items, history, config.recipients[0], config, NOW + timedelta(days=6)) == []
    reminder = batches(items, history, config.recipients[0], config, NOW + timedelta(days=7))
    assert len(reminder) == 1 and reminder[0]["delivery_kind"] == "reminder"
    items[0]["payload"]["stage"] = 3
    escalated = batches([items[0]], history, config.recipients[0], config, NOW + timedelta(days=7))
    assert len(escalated) == 1 and escalated[0]["delivery_kind"] == "escalation"


def test_digest_fingerprint_changes_only_semantics(config):
    items = [row(p=payload(rule="event_without_dates", finding_id="f1", severity="warning"))]
    first = batches(items, [], config.recipients[0], config, NOW)[0]
    history = [{**first, "id": uuid4(), "status": "sent", "sent_at": NOW}]
    items[0]["last_seen_at"] = NOW + timedelta(days=1)
    assert batches(items, history, config.recipients[0], config, NOW + timedelta(days=1)) == []
    for change in ({"severity": "error"}, {"relevance": ["published_soon"]}):
        changed = copy.deepcopy(items)
        changed[0]["payload"].update(change)
        assert len(batches(changed, history, config.recipients[0], config, NOW)) == 1
    assert (
        len(
            batches(
                items + [row(99, payload(rule="url_syntax"))],
                history,
                config.recipients[0],
                config,
                NOW,
            )
        )
        == 1
    )
    assert content_version(items) == content_version(list(reversed(items)))


@pytest.mark.parametrize("attempt,delay", [(1, 300), (2, 1800), (3, 7200), (4, 43200), (5, None)])
def test_retry_schedule(attempt, delay):
    status, next_at, detail = failure(
        smtplib.SMTPDataError(451, b"secret recipient@example.test"), attempt, NOW
    )
    assert next_at == NOW + timedelta(seconds=delay) if delay else next_at is None
    assert status == ("failed" if delay else "permanent_failure")
    assert detail == "smtp_451"


def test_permanent_recipient_rejection():
    status, next_at, detail = failure(
        smtplib.SMTPRecipientsRefused({"recipient@example.test": (550, b"private")}), 1, NOW
    )
    assert (status, next_at, detail) == ("permanent_failure", None, "smtp_550")


@pytest.mark.parametrize("locale", ["de", "da", "en"])
@pytest.mark.parametrize("rule", [None, "event_without_dates"])
def test_multipart_stable_message_id(locale, rule, settings):
    preview = render([payload(rule=rule)], locale, settings)
    delivery = {
        "id": uuid4(),
        "recipient": "recipient@example.test",
        "snapshot": {"mail": preview.model_dump()},
    }
    mail = message(delivery, settings)
    assert mail["To"] == "recipient@example.test"
    assert mail["From"] == "Kulturbytes <notifications@kulturbytes.de>"
    assert mail["Subject"] == preview.subject
    assert mail.get_content_type() == "multipart/alternative"
    assert mail.get_body(preferencelist=("plain",)).get_content() == preview.text + "\n"
    assert mail.get_body(preferencelist=("html",)).get_content() == preview.html
    assert mail["Message-ID"] == message(delivery, settings)["Message-ID"]


def test_smtp_tls_envelope(monkeypatch, settings):
    calls = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            calls.append("connect")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, context):
            assert context.check_hostname
            calls.append("tls")

        def send_message(self, mail, from_addr, to_addrs):
            calls.append((from_addr, to_addrs))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    settings.notifications_delivery_enabled = True
    settings.notification_smtp_host = "smtp.example.test"
    SMTPTransport(settings).send(
        message(
            {
                "id": uuid4(),
                "recipient": "recipient@example.test",
                "snapshot": {"mail": render([payload()], "de", settings).model_dump()},
            },
            settings,
        ),
        "recipient@example.test",
    )
    assert calls == [
        "connect",
        "ehlo",
        "tls",
        "ehlo",
        ("notifications@kulturbytes.de", ["recipient@example.test"]),
    ]


async def test_source_missing_capability(db_connection):
    assert not await source_capability(db_connection)


async def test_event_and_quality_lifecycle(db_connection, config, settings):
    sources = await load_sources(db_connection)
    events = sources.index("event")
    target = events[str(UUID(int=31))]
    event_date = next(
        r for r in sources.rows["event_date"] if str(r["event_uuid"]) == str(UUID(int=31))
    )
    clock = datetime.combine(event_date["start_date"] - timedelta(days=12), time(10), UTC)
    configs = {UUID(int=11): config}

    def selected():
        return next(
            c
            for c in detect(sources, configs, {}, settings, clock)
            if c.payload.entity_key == str(UUID(int=31))
            and c.notification_type == "unpublished_upcoming_event"
        )

    assert selected().status == "active"
    assert selected().payload.external_action_url == (
        f"https://app.kulturbytes.de/admin/event/{UUID(int=31)}"
    )
    target["release_status"] = "review"
    assert selected().status == "active"
    target["release_status"] = "released"
    assert selected().status == "resolved"
    target["release_status"] = "draft"
    config.events.unpublished_upcoming_events.enabled = False
    assert selected().status == "suppressed"
    config.events.unpublished_upcoming_events.enabled = True
    assert selected().status == "active"
    clock += timedelta(days=100)
    assert selected().status == "expired"


@pytest.mark.parametrize(
    "status,expected",
    [
        ("open", "active"),
        ("in_progress", "suppressed"),
        ("snoozed", "suppressed"),
        ("ignored", "suppressed"),
        ("exception", "suppressed"),
        ("reviewed", "suppressed"),
        ("resolved", "suppressed"),
    ],
)
async def test_finding_status_and_ownership(db_connection, config, settings, status, expected):
    sources = await load_sources(db_connection)
    candidates = detect(sources, {ORG: config}, {}, settings, NOW)
    target = next(
        c
        for c in candidates
        if c.organization_id == ORG and c.payload.rule == "organization_missing_logo"
    )
    result = detect(sources, {ORG: config}, {target.payload.finding_id: status}, settings, NOW)
    assert next(c for c in result if c.dedupe_key == target.dedupe_key).status == expected
    assert all(
        c.payload.rule in EXTERNAL_POLICY
        for c in result
        if c.notification_type == "quality_finding"
    )
    sources.rows["organization"] = []
    assert detect(sources, {ORG: config}, {target.payload.finding_id: "open"}, settings, NOW) == []


async def test_storage_idempotence_batch_and_dry_run(admin_store, config, settings):
    items = [candidate(i) for i in range(31, 34)]
    await synchronize(admin_store, ORG, items, config, settings, NOW)
    async with admin_store.begin():
        assert len((await admin_store.execute(select(n))).all()) == 3
        assert not (await admin_store.execute(select(d))).all()
    settings.notifications_delivery_enabled = True
    for _ in range(2):
        await synchronize(admin_store, ORG, items, config, settings, NOW)
    async with admin_store.begin():
        deliveries = (await admin_store.execute(select(d))).mappings().all()
        assert len(deliveries) == 1
        assert deliveries[0]["delivery_kind"] == "initial"
        assert deliveries[0]["subject"] == "3 deiner Veranstaltungen finden bald statt"
        assert len((await admin_store.execute(select(di))).all()) == 3
    owned = await claim(admin_store, settings, NOW)
    assert owned is not None
    await finish(admin_store, owned, NOW)
    await synchronize(admin_store, ORG, items, config, settings, NOW)
    assert await claim(admin_store, settings, NOW) is None


async def test_cancel_disabled_recipient_and_locale_change(admin_store, config, settings):
    settings.notifications_delivery_enabled = True
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)
    config.recipients[0].enabled = False
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)
    assert await claim(admin_store, settings, NOW) is None
    config.recipients[0].enabled = True
    config.recipients[0].locale = "da"
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)
    claimed = await claim(admin_store, settings, NOW)
    assert claimed["locale"] == "da"
    assert claimed["snapshot"]["mail"]["subject"].startswith("Dit arrangement")


async def test_concurrent_claim_and_expired_lease(admin_store, config, settings):
    settings.notifications_delivery_enabled = True
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)

    async def worker():
        async with admin_store.engine.connect() as connection:
            return await claim(connection, settings, NOW)

    results = await asyncio.gather(worker(), worker())
    owned = next(r for r in results if r)
    assert sum(r is not None for r in results) == 1
    later = NOW + timedelta(seconds=settings.notification_lease_seconds + 1)
    takeover = await claim(admin_store, settings, later)
    assert takeover["id"] == owned["id"]
    assert takeover["worker_id"] != owned["worker_id"]
    assert not await finish(admin_store, owned, later)
    assert await finish(admin_store, takeover, later)


async def test_rate_limit_across_orgs_and_next_day(admin_store, config, settings):
    settings.notifications_delivery_enabled = True
    settings.notification_max_emails_per_recipient_per_day = 1
    for i in (10, 11):
        await synchronize(
            admin_store,
            UUID(int=i),
            [Candidate(UUID(int=i), "unpublished_upcoming_event", f"org:{i}", "active", payload())],
            config,
            settings,
            NOW,
        )
    first = await claim(admin_store, settings, NOW)
    assert first
    # Sending reserves quota, before an SMTP outcome exists.
    assert await claim(admin_store, settings, NOW) is None
    await finish(admin_store, first, NOW)
    async with admin_store.begin():
        queued = (
            (await admin_store.execute(select(d).where(d.c.status == "queued"))).mappings().one()
        )
        assert queued["next_attempt_at"] == local_day(NOW, settings.admin_timezone)[1]
    assert await claim(admin_store, settings, NOW + timedelta(days=1))


async def test_retry_database_state(admin_store, config, settings):
    settings.notifications_delivery_enabled = True
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)
    clock = NOW
    for attempt in range(1, 6):
        delivery = await claim(admin_store, settings, clock)
        assert delivery["attempt_count"] == attempt
        await finish(admin_store, delivery, clock, smtplib.SMTPDataError(451, b"secret"))
        async with admin_store.begin():
            saved = (await admin_store.execute(select(d))).mappings().one()
        if attempt < 5:
            assert saved["status"] == "failed"
            assert await claim(admin_store, settings, clock) is None
            clock = saved["next_attempt_at"]
        else:
            assert saved["status"] == "permanent_failure"
            assert await claim(admin_store, settings, clock + timedelta(days=1)) is None


async def test_worker_dry_run_then_delivery(database, admin_store, settings):
    source = create_async_engine(database[0], poolclass=NullPool)
    clock = datetime.now(UTC)

    class FakeTransport:
        def __init__(self):
            self.messages = []

        def send(self, mail, recipient):
            self.messages.append((mail, recipient))

    transport = FakeTransport()
    try:
        async with source.begin() as connection:
            await connection.execute(
                text("ALTER TABLE uranus.organization ADD COLUMN notifications jsonb")
            )
            await connection.execute(
                text(
                    "UPDATE uranus.organization SET notifications=CAST(:config AS jsonb) "
                    "WHERE uuid=:id"
                ),
                {"config": json.dumps(CONFIG), "id": UUID(int=11)},
            )
        counts = await work_once(source, admin_store.engine, settings, transport, lambda: clock)
        assert counts["candidates_detected"] > 0 and not transport.messages
        async with admin_store.begin():
            assert not (await admin_store.execute(select(d))).all()
        settings.notifications_delivery_enabled = True
        await asyncio.gather(
            work_once(source, admin_store.engine, settings, transport, lambda: clock),
            work_once(source, admin_store.engine, settings, transport, lambda: clock),
        )
        await work_once(source, admin_store.engine, settings, transport, lambda: clock)
        assert len(transport.messages) == 1
        assert transport.messages[0][1] == "recipient@example.test"
    finally:
        async with source.begin() as connection:
            await connection.execute(
                text("ALTER TABLE uranus.organization DROP COLUMN IF EXISTS notifications")
            )
        await source.dispose()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/notifications",
        f"/api/v1/notifications/{UUID(int=1)}",
        f"/api/v1/notifications/{UUID(int=1)}/preview",
        f"/api/v1/notification-deliveries/{UUID(int=1)}",
    ],
)
async def test_api_anonymous_denied(client, path):
    response = await client.get(path)
    assert response.status_code == 401
    assert "recipient" not in response.text


async def test_api_authenticated_preview_filters_and_delivery(
    admin_store, db_client, headers, config, settings
):
    settings.notifications_delivery_enabled = True
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)
    response = await db_client.get("/api/v1/notifications?status=active&days=365", headers=headers)
    assert response.status_code == 200
    page = response.json()
    assert page["summary"]["active"] == 1
    assert page["health"]["source_capability"] is False
    assert "recipient@example.test" not in response.text
    id_ = page["items"][0]["id"]
    detail = (await db_client.get(f"/api/v1/notifications/{id_}", headers=headers)).json()
    assert detail["deliveries"][0]["recipient"] == "recipient@example.test"
    for locale in ("de", "da", "en"):
        preview = await db_client.get(
            f"/api/v1/notifications/{id_}/preview?locale={locale}", headers=headers
        )
        assert preview.status_code == 200 and preview.json()["locale"] == locale
        assert "smtp_password" not in preview.text
    assert (
        await db_client.get(f"/api/v1/notifications/{id_}/preview?locale=fr", headers=headers)
    ).status_code == 422
    delivery = await db_client.get(
        f"/api/v1/notification-deliveries/{detail['deliveries'][0]['id']}", headers=headers
    )
    assert delivery.status_code == 200 and len(delivery.json()["notifications"]) == 1
    assert (await db_client.post("/api/v1/notifications", headers=headers)).status_code == 405


async def test_digest_daily_limit_and_unchanged_does_not_nag(admin_store, config, settings):
    settings.notifications_delivery_enabled = True
    p = payload(rule="event_without_dates", finding_id="first", severity="warning")
    initial = candidate(p=p)
    await synchronize(admin_store, ORG, [initial], config, settings, NOW)
    first = await claim(admin_store, settings, NOW)
    assert first["delivery_kind"] == "digest"
    await finish(admin_store, first, NOW)
    await synchronize(admin_store, ORG, [initial], config, settings, NOW + timedelta(days=7))
    assert await claim(admin_store, settings, NOW + timedelta(days=7)) is None
    extra = candidate(
        99, p=p.model_copy(update={"finding_id": "second", "entity_key": str(UUID(int=99))})
    )
    await synchronize(admin_store, ORG, [initial, extra], config, settings, NOW)
    assert await claim(admin_store, settings, NOW) is None
    next_morning = NOW + timedelta(days=1)
    second = await claim(admin_store, settings, next_morning)
    assert len(second["snapshot"]["ids"]) == 2
    await finish(admin_store, second, next_morning)
    # Removing one finding meaningfully changes a nonempty digest.
    await synchronize(admin_store, ORG, [initial], config, settings, next_morning)
    assert await claim(admin_store, settings, next_morning) is None
    changed = await claim(admin_store, settings, next_morning + timedelta(days=1))
    assert len(changed["snapshot"]["ids"]) == 1


async def test_resolved_expired_suppressed_timestamps(admin_store, config, settings):
    for status in ("active", "suppressed", "active", "resolved", "active", "expired"):
        await synchronize(admin_store, ORG, [candidate(status=status)], config, settings, NOW)
        async with admin_store.begin():
            saved = (await admin_store.execute(select(n))).mappings().one()
            assert saved["status"] == status
            assert (saved["resolved_at"] is not None) == (status == "resolved")
            assert (saved["expired_at"] is not None) == (status == "expired")


async def test_scoped_source_snapshot_matches_bulk(db_connection, config, settings):
    all_sources = await load_sources(db_connection)
    scoped = await load_sources(db_connection, ORG)
    all_candidates = detect(all_sources, {ORG: config}, {}, settings, NOW)
    scoped_candidates = detect(scoped, {ORG: config}, {}, settings, NOW)
    assert [c for c in all_candidates if c.organization_id == ORG] == scoped_candidates


@pytest.mark.parametrize(
    "timezone,day,hours",
    [
        ("Europe/Berlin", "2026-03-29T10:00:00+00:00", 23),
        ("Europe/Berlin", "2026-10-25T10:00:00+00:00", 25),
    ],
)
def test_admin_day_uses_local_dst_boundaries(timezone, day, hours):
    start, end = local_day(datetime.fromisoformat(day), timezone)
    assert (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() == hours * 3600


async def test_recurring_issue_is_new_episode_but_config_toggle_is_not(
    admin_store, config, settings
):
    settings.notifications_delivery_enabled = True
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)
    first = await claim(admin_store, settings, NOW)
    await finish(admin_store, first, NOW)
    for state in ("suppressed", "active"):
        await synchronize(admin_store, ORG, [candidate(status=state)], config, settings, NOW)
    assert await claim(admin_store, settings, NOW) is None
    for state in ("resolved", "active"):
        await synchronize(admin_store, ORG, [candidate(status=state)], config, settings, NOW)
    second = await claim(admin_store, settings, NOW)
    assert second["delivery_kind"] == "initial"
    assert second["snapshot"]["payloads"][0]["episode"] == 2


async def test_wrong_source_column_type_is_unavailable(db_connection):
    await db_connection.execute(
        text("ALTER TABLE uranus.organization ADD COLUMN notifications text")
    )
    assert not await source_capability(db_connection)


async def test_resolved_issue_recurring_while_disabled_keeps_new_episode(
    admin_store, config, settings
):
    settings.notifications_delivery_enabled = True
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)
    delivery = await claim(admin_store, settings, NOW)
    await finish(admin_store, delivery, NOW)
    later = NOW + timedelta(days=1)
    await synchronize(admin_store, ORG, [candidate(status="resolved")], config, settings, later)
    async with admin_store.begin():
        saved = (await admin_store.execute(select(n))).mappings().one()
        assert saved["last_detected_at"] == NOW
    for state in ("suppressed", "active"):
        await synchronize(admin_store, ORG, [candidate(status=state)], config, settings, later)
    delivery = await claim(admin_store, settings, later)
    assert delivery["snapshot"]["payloads"][0]["episode"] == 2
    assert delivery["delivery_kind"] == "initial"


async def test_expired_event_preview_is_unavailable_not_server_error(
    admin_store, db_client, headers, config, settings
):
    await synchronize(admin_store, ORG, [candidate()], config, settings, NOW)
    expired = payload().model_copy(update={"next_date": None, "days_until": None})
    await synchronize(
        admin_store, ORG, [candidate(status="expired", p=expired)], config, settings, NOW
    )
    async with admin_store.begin():
        id_ = (await admin_store.execute(select(n.c.id))).scalar_one()
    assert (
        await db_client.get(f"/api/v1/notifications/{id_}/preview", headers=headers)
    ).status_code == 422


def test_mixed_initial_and_reminder_share_compatible_event_batch(config):
    old = row(31)
    initial = batches([old], [], config.recipients[0], config, NOW)[0]
    history = [{**initial, "id": uuid4(), "status": "sent", "sent_at": NOW - timedelta(days=7)}]
    planned = batches([old, row(32)], history, config.recipients[0], config, NOW)
    assert len(planned) == 1
    assert planned[0]["delivery_kind"] == "reminder"
    assert len(planned[0]["snapshot"]["ids"]) == 2


@pytest.fixture
def action_sources():
    return Sources(
        {
            "organization": [{"uuid": ORG}],
            "event": [{"uuid": UUID(int=31), "org_uuid": ORG}],
            "venue": [{"uuid": UUID(int=21), "org_uuid": ORG}],
            "space": [{"uuid": UUID(int=51), "venue_uuid": UUID(int=21)}],
            "event_date": [{"uuid": UUID(int=41), "event_uuid": UUID(int=31)}],
            "event_link": [{"id": 7, "event_uuid": UUID(int=31)}],
        }
    )


@pytest.mark.parametrize("locale", ["de", "da", "en"])
@pytest.mark.parametrize(
    "rule,entity,key,path,target",
    [
        (None, "event", str(UUID(int=31)), f"/admin/event/{UUID(int=31)}", "event"),
        (
            "event_without_dates",
            "event",
            str(UUID(int=31)),
            f"/admin/event/{UUID(int=31)}",
            "event",
        ),
        (
            "event_without_location",
            "event",
            str(UUID(int=31)),
            f"/admin/event/{UUID(int=31)}",
            "event",
        ),
        (
            "event_date_without_location",
            "event_date",
            str(UUID(int=41)),
            f"/admin/event/{UUID(int=31)}",
            "event",
        ),
        (
            "venue_missing_logo",
            "venue",
            str(UUID(int=21)),
            f"/admin/org/{ORG}/venue/{UUID(int=21)}/edit",
            "venue",
        ),
        (
            "organization_missing_logo",
            "organization",
            str(ORG),
            f"/admin/org/{ORG}/edit",
            "organization",
        ),
        ("url_syntax", "event_link", "7", f"/admin/event/{UUID(int=31)}", "event"),
        ("url_syntax", "event_date", str(UUID(int=41)), f"/admin/event/{UUID(int=31)}", "event"),
        ("url_syntax", "event", str(UUID(int=31)), f"/admin/event/{UUID(int=31)}", "event"),
        (
            "url_syntax",
            "venue",
            str(UUID(int=21)),
            f"/admin/org/{ORG}/venue/{UUID(int=21)}/edit",
            "venue",
        ),
        ("url_syntax", "organization", str(ORG), f"/admin/org/{ORG}/edit", "organization"),
        (
            "url_syntax",
            "space",
            str(UUID(int=51)),
            f"/admin/org/{ORG}/venue/{UUID(int=21)}/space/{UUID(int=51)}/edit",
            "space",
        ),
    ],
)
def test_verified_recipient_routes(
    locale, rule, entity, key, path, target, action_sources, settings
):
    url = RecipientActions(action_sources, settings).url(entity, key, ORG)
    assert url == "https://app.kulturbytes.de" + path
    p = payload().model_copy(
        update={
            "rule": rule,
            "entity_type": entity,
            "entity_key": key,
            "external_action_url": url,
            "internal_action_path": "/findings?mode=persisted",
        }
    )
    preview = render([p], locale, settings)
    for body in (preview.text, preview.html):
        assert url in body
        assert CATALOGUE[locale][f"{target}_action"] in body
        assert "https://admin.kulturbytes.de" not in body
        assert "/findings" not in body
        for jargon in ("UUID", "entity_key", "SQL", "constraint", "foreign key"):
            assert jargon not in body
    assert f'href="{url}"' in preview.html


@pytest.mark.parametrize("locale", ["de", "da", "en"])
@pytest.mark.parametrize(
    "url",
    [
        None,
        "https://admin.kulturbytes.de/events/" + str(UUID(int=31)),
        "https://app.kulturbytes.de/findings",
        "https://evil.example.test/admin/event/" + str(UUID(int=31)),
        "https://app.kulturbytes.de@evil.example.test/admin/event/" + str(UUID(int=31)),
        "https://app.kulturbytes.de/admin/event/../../findings",
        "https://app.kulturbytes.de/admin/event/"
        + str(UUID(int=31))
        + "?next=https://admin.kulturbytes.de",
        "https://app.kulturbytes.de/admin/event/" + str(UUID(int=31)) + "#section",
        "https://app.kulturbytes.de/admin/event/" + str(UUID(int=31)) + "\n",
        "javascript:alert(1)",
        "https://[invalid",
        "//app.kulturbytes.de/admin/event/" + str(UUID(int=31)),
        "https://app.kulturbytes.de/admin/org/" + str(ORG) + "/edit",
    ],
)
def test_unsafe_or_missing_recipient_route_degrades(locale, url, settings):
    p = payload().model_copy(update={"external_action_url": url})
    for rule in (None, "event_without_dates"):
        p.rule = rule
        preview = render([p], locale, settings)
        assert 'class="button"' not in preview.html
        assert 'class="button-container"' not in preview.html
        assert 'style="word-break:break-all;"' not in preview.html
        assert 'href=""' not in preview.html
        assert CATALOGUE[locale]["action_guidance"] in preview.text
        assert CATALOGUE[locale]["action_guidance"] in preview.html
        assert "https://admin.kulturbytes.de" not in preview.text + preview.html
        assert "/findings" not in preview.text + preview.html


def test_recipient_parent_requires_proven_ownership(action_sources, settings):
    actions = RecipientActions(action_sources, settings)
    for entity, rows in action_sources.rows.items():
        key = str(rows[0]["id" if entity == "event_link" else "uuid"])
        assert actions.url(entity, key, UUID(int=999)) is None
        assert actions.url(entity, "missing", ORG) is None
    assert actions.url("unknown", "anything", ORG) is None
    action_sources.rows["event"] = []
    action_sources.rows["venue"] = []
    actions = RecipientActions(action_sources, settings)
    assert actions.url("event_date", str(UUID(int=41)), ORG) is None
    assert actions.url("event_link", "7", ORG) is None
    assert actions.url("space", str(UUID(int=51)), ORG) is None


@pytest.mark.parametrize(
    "origin",
    [
        "https://admin.kulturbytes.de",
        "https://admin%2ekulturbytes.de",
        "https://admin.kulturbytes.de.",
        "https://app.kulturbytes.de.",
        "https://app.kulturbytes.de/",
        "https://app.kulturbytes.de/x",
        "https://user:password@app.kulturbytes.de",
        "https://@app.kulturbytes.de",
        "https://*.kulturbytes.de",
        "https://app.kulturbytes.de?x=y",
        "https://app.kulturbytes.de#x",
        "https://app.kulturbytes.de?",
        "https://app.kulturbytes.de#",
        "ftp://app.kulturbytes.de",
        "https://app.kulturbytes.de:bad",
        "https://app.kulturbytes.de:99999",
        "https://app.kulturbytes.de\n",
        "https://app.kulturbytes.de\\evil",
        "http://app.kulturbytes.de",
    ],
)
def test_recipient_origin_validation(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, kulturbytes_app_public_base_url=origin)


def test_recipient_origin_is_separate_and_supports_local_preview():
    with pytest.raises(ValidationError, match="separate"):
        Settings(_env_file=None, admin_public_base_url="https://app.kulturbytes.de")
    with pytest.raises(ValidationError, match="separate"):
        Settings(_env_file=None, auth_public_origin="https://app.kulturbytes.de.")
    assert Settings(
        _env_file=None, app_env="test", kulturbytes_app_public_base_url="http://localhost:3000"
    )


async def test_detected_quality_actions_use_source_parents(db_connection, config, settings):
    sources = await load_sources(db_connection)
    sources.rows["event_link"].append({"id": 901, "event_uuid": UUID(int=31), "url": "broken"})
    # Exercise detection's wiring, not just the route helper: all existing source IDs
    # stay unchanged, while synthetic invalid URLs ensure the relevant rules appear.
    for entity in ("event", "event_date", "event_link", "venue", "space", "organization"):
        for row in sources.rows[entity]:
            row[
                "url"
                if entity == "event_link"
                else "ticket_link"
                if entity == "event_date"
                else "web_link"
                if entity in {"organization", "venue", "space"}
                else "online_link"
            ] = "broken"
    candidates = detect(sources, {ORG: config}, {}, settings, NOW)
    actions = RecipientActions(sources, settings)
    seen = set()
    for candidate in candidates:
        p = candidate.payload
        if p.rule:
            seen.add(p.entity_type)
            assert p.external_action_url == actions.url(
                p.entity_type, p.entity_key, candidate.organization_id
            )
            assert p.external_action_url is not None
            assert p.internal_action_path.startswith("/findings?")
    assert {"event", "event_date", "event_link", "organization", "venue", "space"} <= seen


def email_tree(html):
    # The renderer emits HTML void meta tags; normalize only those for XML inspection.
    import re

    return ET.fromstring(re.sub(r"(<meta\b[^>]*)(>)", r"\1/>", html).replace("&nbsp;", "\u00a0"))


@pytest.mark.parametrize("rule", [None, "event_without_dates"])
@pytest.mark.parametrize(
    "locale,country,privacy,label,legal,imprint,signoff,team,fallback",
    [
        (
            "de",
            "",
            "datenschutz",
            "Datenschutzerklärung",
            "impressum",
            "Impressum",
            "Viele Grüße,",
            "Dein kulturbytes-Team",
            "Falls der Button nicht funktioniert, kopiere diesen Link in deinen Browser:",
        ),
        (
            "da",
            ", Tyskland",
            "privatlivspolitik",
            "Privatlivspolitik",
            "impressum",
            "Impressum",
            "Mange hilsner,",
            "Dit kulturbytes-team",
            "Hvis knappen ikke virker, kan du kopiere dette link til din browser:",
        ),
        (
            "en",
            ", Germany",
            "privacy",
            "Privacy policy",
            "legal",
            "Imprint",
            "Best regards,",
            "Your kulturbytes team",
            "If the button does not work, copy this link into your browser:",
        ),
    ],
)
def test_kulturbytes_reference_layout(
    locale, country, privacy, label, legal, imprint, signoff, team, fallback, rule, settings
):
    p = payload(rule=rule, priority="urgent")
    result = render([p], locale, settings)
    assert result.html.startswith(f'<!DOCTYPE html>\n<html lang="{locale}">')
    tree = email_tree(result.html)
    assert tree.find('./head/meta[@name="viewport"]').get("content") == (
        "width=device-width, initial-scale=1.0"
    )
    css = tree.find("./head/style").text
    for declaration in (
        "margin: 0;",
        "padding: 0;",
        "background-color: #f9fafb;",
        "color: #374151;",
        "font-family: Arial, Helvetica, sans-serif;",
        "line-height: 1.5;",
        "max-width: 600px;",
        "margin: 0 auto;",
        "padding: 40px 24px;",
        "background-color: #ffffff;",
        "padding: 32px;",
        "border-radius: 12px;",
        "font-size: 20px;",
        "color: #111827;",
        "margin: 0 0 12px 0;",
        "margin: 0 0 18px 0;",
        "margin: 0 0 20px 0;",
        "display: inline-block;",
        "background-color: #3f2dd2;",
        "color: #ffffff !important;",
        "padding: 12px 24px;",
        "text-decoration: none;",
        "border-radius: 999px;",
        "font-weight: 500;",
        "margin: 0 0 16px 0;",
        "color: #6b7280;",
        "font-size: 14px;",
        "color: #3f2dd2;",
        "margin: 20px 0 0 0;",
        "padding-top: 20px;",
        "border-top: 1px solid #eef2f6;",
        "font-size: 12px;",
        "color: #9ca3af;",
        "text-decoration: underline;",
        "margin: 12px 0 0 0;",
        "text-align: center;",
    ):
        assert declaration in css
    responsive = css.split("@media only screen and (max-width: 600px)")[1]
    assert ".email-container {\n        padding: 24px 12px;\n    }" in responsive
    assert ".email-content {\n        padding: 24px;\n    }" in responsive
    container = tree.find('./body/div[@class="email-container"]')
    content = container.find('./div[@class="email-content"]')
    assert content.find('./h1[@class="heading"]').text == CATALOGUE[locale]["hello"]
    assert (
        content.find('./h2[@class="heading"]').text == f"Kulturabend · {CATALOGUE[locale]['event']}"
    )
    assert content.find('./p[@class="text"]/strong').text == CATALOGUE[locale]["urgent"]
    button = content.find('./p[@class="button-container"]/a[@class="button"]')
    assert button.attrib == {
        "href": p.external_action_url,
        "class": "button",
        "target": "_blank",
        "rel": "noopener noreferrer",
    }
    fallback_link = content.find('./p[@class="muted"]/a[@class="link"]')
    assert fallback_link.text == fallback_link.get("href") == p.external_action_url
    assert fallback_link.get("style") == "word-break:break-all;"
    assert fallback in result.html
    assert result.html.index('class="button-container"') < result.html.index(fallback)
    footer = content.find('./p[@class="footer"]')
    assert footer.text.strip() == signoff
    assert footer.find("strong").text == team
    assert footer.find("a").get("href") == "https://kulturbytes.de"
    legal_box = content.find('./div[@class="legal"]')
    address = "DatenSindDaten e. V., Friesische Straße 41, 24937 Flensburg" + country
    assert legal_box.find("p").text == address
    links = legal_box.findall('./p/a[@class="legal-link"]')
    assert [(a.get("href"), a.text.strip()) for a in links] == [
        (f"https://kulturbytes.de/{locale}/{privacy}", label),
        (f"https://kulturbytes.de/{locale}/{legal}", imprint),
    ]
    assert list(content)[-2:] == [footer, legal_box]
    assert container.find('./p[@class="copyright"]').text == "© DatenSindDaten e. V."
    assert len(list(container)) == 2
    for value in (signoff, team, address, "© DatenSindDaten e. V.", p.external_action_url):
        assert value in result.text
    assert tree.findall(".//script") == tree.findall(".//link") == []
    assert render([p], locale, settings) == result


def test_digest_grouping_and_escaped_recommendations(monkeypatch, settings):
    attack = '<img src=x onerror="alert(1)"> & <script>alert(1)</script>'
    monkeypatch.setitem(CATALOGUE["de"], "venue_missing_logo.recommendation", attack)
    venue = payload(rule="venue_missing_logo").model_copy(
        update={
            "entity_type": "venue",
            "entity_name": attack,
            "entity_key": "venue",
            "organization_name": attack,
            "external_action_url": None,
        }
    )
    items = [payload(rule="url_syntax"), venue, payload(rule="event_without_dates")]
    result = render(items, "de", settings)
    tree = email_tree(result.html)
    assert len(tree.findall('.//h2[@class="heading"]')) == 2
    assert tree.findall(".//img") == tree.findall(".//script") == []
    assert escape(attack) in result.html and attack in result.text
    assert render(list(reversed(items)), "de", settings) == result


def test_design_update_does_not_resend_sent_digest(monkeypatch, config, settings):
    p = payload(rule="event_without_dates", finding_id="f1", severity="warning")
    items = [row(p=p)]
    intent = batches(items, [], config.recipients[0], config, NOW)[0]
    # Simulate a successful pre-design delivery. Its rendered body is not semantic input.
    intent["snapshot"]["mail"] = {"html": "<html><body>Previous design</body></html>"}
    history = [{**intent, "id": uuid4(), "status": "sent", "sent_at": NOW}]
    before = render([p], "de", settings)
    monkeypatch.setattr(rendering, "EMAIL_CSS", rendering.EMAIL_CSS + "\n/* cosmetic change */")
    assert render([p], "de", settings).html != before.html
    assert intent["snapshot"]["version"] == content_version(items)
    assert (
        batches(items, [], config.recipients[0], config, NOW)[0]["message_fingerprint"]
        == (intent["message_fingerprint"])
    )
    assert batches(items, history, config.recipients[0], config, NOW + timedelta(days=1)) == []
