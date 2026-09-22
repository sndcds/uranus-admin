from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import event as sql_event
from sqlalchemy import text

from app.repositories.quality_sources import SOURCE_QUERIES, Sources, load_sources
from app.services.notifications.policy import EXTERNAL_POLICY
from app.services.quality.core import CORE_RULES, evaluate_core
from app.services.quality.rules.v2 import RULES, V2_RULES, email_problem, postal_problem
from tests.conftest import uid

NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


@pytest.fixture
def sources():
    data = Sources({kind: [] for kind in SOURCE_QUERIES})
    data.rows["organization"] = [dict(uuid=uid(10), name="Synthetic owner")]
    data.rows["event"] = [
        dict(
            uuid=uid(30),
            name="Synthetic event",
            org_uuid=uid(10),
            release_status="released",
            description="Description",
            categories=[1],
        )
    ]
    data.rows["event_category"] = [dict(category_id=1)]
    data.rows["event_type"] = [dict(type_id=1)]
    data.rows["genre_type"] = [dict(genre_id=2)]
    data.rows["event_type_link"] = [dict(event_uuid=uid(30), type_id=1, genre_id=0)]
    data.rows["language"] = [dict(code_iso_639_1="de")]
    data.rows["link_type"] = [dict(key="website")]
    return data


@pytest.mark.parametrize(
    "end,start_time,end_time,expected",
    [
        (date(2026, 9, 30), None, None, "event_date_end_before_start"),
        (date(2026, 10, 1), time(18), time(17), "event_date_same_day_end_before_start"),
        (None, time(20), time(2), "event_date_overnight_without_end_date"),
        (date(2026, 10, 2), time(20), time(2), None),
        (None, None, time(2), None),
        (date(2026, 10, 1), time(18), time(18), None),
    ],
)
def test_date_order(sources, settings, end, start_time, end_time, expected):
    sources.rows["event_date"] = [
        dict(
            uuid=uid(40),
            event_uuid=uid(30),
            start_date=date(2026, 10, 1),
            start_time=start_time,
            end_date=end,
            end_time=end_time,
            all_day=False,
            release_status="inherited",
            venue_uuid=None,
            space_uuid=None,
        )
    ]
    findings = [
        f
        for rule in V2_RULES
        if rule.startswith("event_date_")
        for f in evaluate_core(rule, sources, settings, NOW).findings
    ]
    assert [f.rule for f in findings] == ([expected] if expected else [])
    if findings:
        assert findings[0].severity == ("info" if end is None else "error")


@pytest.mark.parametrize(
    "rule,kind,changes,expected",
    [
        ("event_price_without_currency", "event", dict(min_price=10, currency=None), True),
        ("event_price_without_currency", "event", dict(min_price=10, currency="EUR"), False),
        ("event_price_without_currency", "event", dict(max_price=0, currency=" "), True),
        ("event_price_range_invalid", "event", dict(min_price=20, max_price=10), True),
        ("event_price_range_invalid", "event", dict(min_price=-1), True),
        ("event_price_range_invalid", "event", dict(max_price=-1), True),
        ("event_price_range_invalid", "event", dict(min_price=0, max_price=10), False),
        ("event_free_with_price", "event", dict(price_type="free", min_price=0), True),
        ("event_free_with_price", "event", dict(price_type="free"), False),
        ("event_link_empty", "event_link", dict(url=" "), True),
        ("event_link_empty", "event_link", dict(url="https://example.test"), False),
        ("event_link_missing_type", "event_link", dict(type=None), True),
        ("event_link_unknown_type", "event_link", dict(type="unknown"), True),
        ("event_link_unknown_type", "event_link", dict(type="website"), False),
        ("event_link_unknown_type", "event_link", dict(type=" "), False),
        (
            "space_capacity_inconsistent",
            "space",
            dict(total_capacity=100, seating_capacity=120),
            True,
        ),
        (
            "space_capacity_inconsistent",
            "space",
            dict(total_capacity=100, seating_capacity=80),
            False,
        ),
        ("space_capacity_invalid", "space", dict(total_capacity=-1), True),
        ("space_capacity_invalid", "space", dict(seating_capacity=-1), True),
        ("space_capacity_invalid", "space", dict(area_sqm=-1), True),
        ("space_capacity_invalid", "space", dict(area_sqm=0), False),
        ("released_event_without_description", "event", dict(description=" "), True),
        (
            "released_event_without_description",
            "event",
            dict(release_status="draft", description=""),
            False,
        ),
        ("released_event_without_categories", "event", dict(categories=[]), True),
        ("released_event_without_categories", "event", dict(categories=[1]), False),
        (
            "released_event_without_categories",
            "event",
            dict(release_status="rescheduled", categories=None),
            True,
        ),
        ("event_unknown_category", "event", dict(categories=[99, 99]), True),
        ("event_unknown_category", "event", dict(categories=[1]), False),
        ("event_unknown_language", "event", dict(languages=["de"]), False),
        ("event_unknown_language", "event", dict(languages=["xx"]), True),
    ],
)
def test_row_checks(sources, settings, rule, kind, changes, expected):
    if not sources.rows[kind]:
        sources.rows[kind] = [dict(uuid=uid(80), id=1, event_uuid=uid(30))]
    sources.rows[kind][0].update(changes)
    result = evaluate_core(rule, sources, settings, NOW)
    assert bool(result.findings) is expected
    assert result.covered
    for finding in result.findings:
        assert finding.severity == RULES[rule][2]
        assert finding.id == evaluate_core(rule, sources, settings, NOW).findings[0].id


@pytest.mark.parametrize(
    "links,missing,unknown_type,unknown_genre",
    [
        ([], True, False, False),
        ([(1, 0)], False, False, False),
        ([(1, 2)], False, False, False),
        ([(999, 0)], False, True, False),
        ([(1, 999)], False, False, True),
    ],
)
def test_type_sets(sources, settings, links, missing, unknown_type, unknown_genre):
    sources.rows["event_type_link"] = [
        dict(event_uuid=uid(30), type_id=t, genre_id=g) for t, g in links
    ]
    for rule, expected in [
        ("released_event_without_type", missing),
        ("event_type_link_unknown_type", unknown_type),
        ("event_type_link_unknown_genre", unknown_genre),
    ]:
        assert bool(evaluate_core(rule, sources, settings, NOW).findings) is expected


@pytest.mark.parametrize(
    "value,invalid",
    [
        ("person@example.test", False),
        ("person@@example.test", True),
        ("person", True),
        ("person@-example.test", True),
        (None, False),
        (" ", False),
    ],
)
def test_email(value, invalid):
    assert bool(email_problem(value)) is invalid


@pytest.mark.parametrize(
    "country,value,invalid",
    [
        ("DE", "24937", False),
        ("DEU", "24937^", True),
        ("DK", "6400", False),
        ("DNK", "6400", False),
        ("DK", "24937", True),
        ("GB", "SW1A 1AA", False),
        ("XX", "12-ABC", False),
        ("XX", "12\x00", True),
        ("XX", "12^", True),
        ("DE", " 24937 ", False),
        ("DE", "", False),
    ],
)
def test_postal(country, value, invalid):
    assert bool(postal_problem(value, country)) is invalid


@pytest.mark.parametrize(
    "kind,field",
    [
        ("organization", "contact_email"),
        ("venue", "contact_email"),
        ("event", "registration_email"),
    ],
)
def test_contact_evidence_minimized(sources, settings, kind, field):
    if not sources.rows[kind]:
        sources.rows[kind] = [dict(uuid=uid(20))]
    row = sources.rows[kind][0]
    row[field] = "private@@example.test"
    first = evaluate_core("email_syntax", sources, settings, NOW).findings[0]
    assert row[field] not in first.model_dump_json()
    assert first.metadata["field"] == field
    row[field] = "different@@example.test"
    second = evaluate_core("email_syntax", sources, settings, NOW).findings[0]
    assert first.id == second.id
    assert first.metadata["source_fingerprint"] != second.metadata["source_fingerprint"]


def test_whitespace_deduplication(sources, settings):
    sources.rows["organization"][0].update(
        postal_code=" 24937 ", city=" Example ", description=" Description "
    )
    findings = evaluate_core("text_surrounding_whitespace", sources, settings, NOW).findings
    assert [f.field for f in findings] == ["city"]
    assert not evaluate_core("postal_code_syntax", sources, settings, NOW).findings
    assert len(evaluate_core("postal_code_whitespace", sources, settings, NOW).findings) == 1


@pytest.mark.parametrize(
    "joined,present,expected", [(True, True, True), (False, True, False), (True, False, False)]
)
def test_membership(sources, settings, joined, present, expected):
    sources.rows["team_membership"] = [
        dict(org_uuid=uid(10), user_uuid=uid(1), has_joined=joined, accept_token_present=present)
    ]
    result = evaluate_core("membership_joined_accept_token_present", sources, settings, NOW)
    assert bool(result.findings) is expected
    assert result.covered == {("team_membership", f"membership:{uid(10)}:{uid(1)}")}
    if expected:
        item = result.findings[0]
        assert item.metadata["token_present"] is True
        assert item.action.href == f"/organizations/{uid(10)}"
        assert item.severity == "error"


def test_closed_external_policy():
    assert set(V2_RULES) <= set(CORE_RULES)
    assert set(V2_RULES).isdisjoint(EXTERNAL_POLICY)
    assert {
        "source_schema_drift",
        "expired_password_reset_token",
        "social_post_stuck_pending",
    }.isdisjoint(EXTERNAL_POLICY)


@pytest.mark.integration
async def test_secret_projection_and_scoped_snapshot(
    db_connection, db_client, headers, settings, caplog, monkeypatch
):
    secret = "synthetic-invite-secret-never-output"
    await db_connection.execute(
        text("UPDATE uranus.organization_member_link SET has_joined=true,accept_token=:token"),
        {"token": secret},
    )
    await db_connection.execute(
        text("UPDATE uranus.organization SET api_import_token=:token"),
        {"token": "synthetic-import-secret-never-output"},
    )
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sql_event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        data = await load_sources(db_connection)
    finally:
        sql_event.remove(db_connection.sync_connection, "before_cursor_execute", capture)
    assert len(statements) == len(SOURCE_QUERIES)
    assert all(s.startswith("SELECT ") for s in statements)
    assert all(
        "password_hash" not in s and "api_import_token" not in s and "activate_token" not in s
        for s in statements
    )
    assert set(data.rows["team_membership"][0]) == {
        "org_uuid",
        "user_uuid",
        "has_joined",
        "accept_token_present",
        "name",
    }
    output = "".join(
        f.model_dump_json()
        for rule in V2_RULES
        for f in evaluate_core(rule, data, settings, NOW).findings
    )
    assert secret not in output + repr(data.rows) + caplog.text
    assert "synthetic-import-secret-never-output" not in output + repr(data.rows) + caplog.text

    async def projected_snapshot(*args):
        return data

    monkeypatch.setattr("app.services.quality.engine.load_sources", projected_snapshot)
    response = await db_client.get("/api/v1/findings?mode=live", headers=headers)
    assert response.status_code == 200
    assert secret not in response.text + caplog.text
    assert "synthetic-import-secret-never-output" not in response.text + caplog.text
    assert any(
        item["rule"] == "membership_joined_accept_token_present"
        for item in response.json()["items"]
    )
    scoped = await load_sources(db_connection, uid(11))
    assert not scoped.rows["team_membership"]


@pytest.mark.integration
async def test_evidence_review_failure_and_geo(
    admin_store, db_connection, settings, now, monkeypatch
):
    from app.schemas.checks import ReviewUpdate
    from app.schemas.finding import FindingFilters
    from app.services.checks import persisted_page, review, run_check
    from app.services.geo.membership import filter_live_findings
    from app.services.quality.engine import scan

    rule = "event_price_without_currency"
    await db_connection.execute(
        text("UPDATE uranus.event SET min_price=10,currency=NULL WHERE uuid=:id"), {"id": uid(30)}
    )
    filters = FindingFilters(rule=rule)
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    original = (await persisted_page(admin_store, filters, now)).items[0]
    assert "published_soon" in original.priority_reasons
    await review(
        admin_store,
        db_connection,
        ReviewUpdate(
            finding_id=original.id, status="exception", exception_reason="Synthetic review"
        ),
        "admin:test",
        now,
    )
    await db_connection.execute(
        text("UPDATE uranus.event SET min_price=20 WHERE uuid=:id"), {"id": uid(30)}
    )
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    changed = (await persisted_page(admin_store, filters, now)).items[0]
    assert changed.status == "open" and changed.id == original.id
    assert changed.metadata["source_fingerprint"] != original.metadata["source_fingerprint"]
    await db_connection.execute(
        text("UPDATE uranus.event SET currency='EUR' WHERE uuid=:id"), {"id": uid(30)}
    )

    async def incomplete(*args):
        results = await scan(*args)
        next(r for r in results if r.rule == rule).success = False
        return results

    with monkeypatch.context() as patch:
        patch.setattr("app.services.checks.scan", incomplete)
        assert (await run_check(db_connection, admin_store, settings)).status == "failed"
    assert (await persisted_page(admin_store, filters, now)).items[0].status == "open"
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    assert (await persisted_page(admin_store, filters, now)).items[0].status == "resolved"
    await db_connection.execute(
        text("UPDATE uranus.event SET currency=NULL WHERE uuid=:id"), {"id": uid(30)}
    )
    await db_connection.execute(
        text(
            "UPDATE uranus.organization_member_link "
            "SET has_joined=true,accept_token='fake-invite-v2'"
        )
    )
    all_items = [f for r in await scan(db_connection, settings, now) for f in r.findings]
    bounds = (
        await db_connection.execute(text("SELECT ST_AsEWKB(ST_MakeEnvelope(9,54,10,55,4326))"))
    ).scalar_one()
    scoped = await filter_live_findings(db_connection, all_items, bounds)
    assert original.id in {f.id for f in scoped}  # event date overrides to venue21 inside
    assert any(f.entity_type == "team_membership" for f in all_items)
    assert not any(f.entity_type == "team_membership" for f in scoped)
    assert not any(f.rule.endswith("missing_location") for f in scoped)
    outside = (
        await db_connection.execute(text("SELECT ST_AsEWKB(ST_MakeEnvelope(0,0,1,1,4326))"))
    ).scalar_one()
    assert not await filter_live_findings(db_connection, all_items, outside)


@pytest.mark.integration
@pytest.mark.parametrize(
    "token,present", [(None, False), ("", False), ("   ", False), ("synthetic", True)]
)
async def test_membership_projection_handles_optional_token(db_connection, token, present):
    await db_connection.execute(
        text("UPDATE uranus.organization_member_link SET has_joined=true,accept_token=:token"),
        {"token": token},
    )
    data = await load_sources(db_connection)
    row = data.rows["team_membership"][0]
    assert row["accept_token_present"] is present
    assert "accept_token" not in row


def test_price_variants_have_distinct_stable_fields(sources, settings):
    sources.rows["event"][0].update(min_price=-1, max_price=-2)
    result = evaluate_core("event_price_range_invalid", sources, settings, NOW)
    assert {f.field for f in result.findings} == {"min_price", "max_price", "price"}
    assert len({f.id for f in result.findings}) == 3
    assert {f.metadata["reason"] for f in result.findings} == {
        "negative_min_price",
        "negative_max_price",
        "min_greater_than_max",
    }


def test_v2_projection_preserves_existing_rule_fingerprints(sources, settings):
    import hashlib
    import json

    sources.rows["organization"][0]["web_link"] = None
    row = sources.rows["event"][0]
    row.update(
        venue_uuid=None,
        space_uuid=None,
        source_link=None,
        online_link="broken.example",
        ticket_link=None,
        registration_link=None,
    )
    previous_projection = {
        key: row[key]
        for key in (
            "uuid",
            "name",
            "org_uuid",
            "venue_uuid",
            "space_uuid",
            "release_status",
            "source_link",
            "online_link",
            "ticket_link",
            "registration_link",
        )
    }
    expected = hashlib.sha256(
        json.dumps(previous_projection, sort_keys=True, default=str).encode()
    ).hexdigest()
    first = evaluate_core("url_syntax", sources, settings, NOW).findings[0]
    assert first.metadata["source_fingerprint"] == expected
    row.update(
        description="Changed content", min_price=10, registration_email="person@example.test"
    )
    second = evaluate_core("url_syntax", sources, settings, NOW).findings[0]
    assert second.metadata["source_fingerprint"] == expected
    row["online_link"] = "different-broken.example"
    third = evaluate_core("url_syntax", sources, settings, NOW).findings[0]
    assert third.id == first.id
    assert third.metadata["source_fingerprint"] != expected
