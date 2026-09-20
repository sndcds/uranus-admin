"""All source writes below are guarded disposable fixture setup, never application SQL."""

import json
import logging
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.admin_tables import finding as finding_table
from app.errors import APIError
from app.logging import JsonFormatter
from app.main import create_app
from app.sql_diagnostics.evaluation import evaluate
from app.sql_diagnostics.executor import definition, execute
from app.sql_diagnostics.models import DiagnosticRequest, StoredFinding
from app.sql_diagnostics.registry import PILOT_RULES, RECIPES, URL_RECIPES, parameters_for, resolve
from app.sql_diagnostics.render import copy_sql, json_value
from tests.conftest import uid

STAMP = datetime(2026, 10, 1, tzinfo=UTC)
SECRET = "TOP-SECRET-FIXTURE"


def stored(rule="venue_missing_location", kind="venue", key=None, field="point"):
    return StoredFinding("synthetic-finding", rule, kind, key or str(uid(20)), field, STAMP)


def test_registry_and_parameter_identity():
    assert len(PILOT_RULES) == 8
    items = [*RECIPES, *URL_RECIPES.values()]
    assert len({item.id for item in items}) == len(items)
    for item in items:
        assert item.sql.startswith("SELECT ")
        assert item.sql.endswith("LIMIT :diagnostic_limit")
        assert not {
            "password_hash",
            "accept_token",
            "api_import_token",
            "activate_token",
            "password_reset_token",
        }.intersection(item.result_fields)
    assert parameters_for(stored())["entity_key"] == uid(20)
    assert parameters_for(stored())["diagnostic_limit"] == 50
    member = stored(
        "membership_joined_accept_token_present",
        "team_membership",
        f"membership:{uid(10)}:{uid(1)}",
        "accept_token",
    )
    assert parameters_for(member)["org_uuid"] == uid(10)
    partner = stored(
        "partner_long_pending", "partner_request", f"partner-request:{uid(10)}:{uid(11)}", "status"
    )
    assert parameters_for(partner)["to_org_uuid"] == uid(11)
    for item in (
        replace(member, entity_key="membership:bad:key"),
        replace(member, entity_key=f"wrong:{uid(10)}:{uid(1)}"),
        replace(partner, entity_key=f"partner-request:{uid(10)}"),
        replace(partner, entity_key=f"partner-request:{uid(10)}:{uid(11)}:extra"),
        replace(stored(), entity_key="'; DROP TABLE uranus.venue; --"),
    ):
        with pytest.raises(APIError) as error:
            parameters_for(item)
        assert error.value.code == "diagnostic_invalid_finding"
    with pytest.raises(APIError) as error:
        resolve(replace(stored(), rule="unknown"))
    assert error.value.status == 404
    with pytest.raises(APIError):
        resolve(stored("url_syntax", "venue", field="password_hash"))


@pytest.mark.parametrize(
    "value",
    [
        uid(1),
        3,
        True,
        date(26, 10, 31),
        STAMP,
        "x'; DROP TABLE x; --",
        "back\\slash",
        "100%_name",
        "Grüße\nZeile",
    ],
)
async def test_literal_copy_round_trips_through_postgres(db_connection, value):
    sql = copy_sql("SELECT :value AS value", {"value": value})
    row = (await db_connection.exec_driver_sql(sql)).scalar_one()
    assert str(row).replace("-", "") == str(value).replace("-", "")


def test_unknown_literal_types_and_url_secrets_rejected():
    for value in (None, 1.5, Decimal("1.2"), [], {}, object()):
        with pytest.raises(ValueError):
            copy_sql("SELECT :value", {"value": value})
    for value in (
        f"https://user:{SECRET}@example.org",
        f"https://example.org?token={SECRET}",
        f"https://example.org#{SECRET}",
    ):
        assert SECRET not in str(json_value(value, url=True))
    with pytest.raises(ValueError):
        json_value("x" * 4097)
    with pytest.raises(ValueError):
        DiagnosticRequest.model_validate({"finding_id": "x", "sql": "SELECT 1"})


CASES = [
    (
        stored("event_date_end_before_start", "event_date", field="end_date"),
        {
            "start_date": date(2026, 10, 1),
            "end_date": date(26, 10, 31),
            "start_time": None,
            "end_time": None,
        },
        {"end_date": None},
    ),
    (
        stored("event_date_same_day_end_before_start", "event_date", field="end_time"),
        {
            "start_date": date(2026, 10, 1),
            "end_date": date(2026, 10, 1),
            "start_time": time(18),
            "end_time": time(17),
        },
        {"end_time": time(21)},
    ),
    (
        stored("event_date_without_location", "event_date", field="venue_uuid"),
        {
            "date_venue_uuid": None,
            "date_space_uuid": None,
            "event_venue_uuid": None,
            "event_space_uuid": uid(25),
            "online_link": "example.org",
        },
        {"online_link": "https://example.org"},
    ),
    (
        stored("event_price_without_currency", "event", field="currency"),
        {"min_price": Decimal("0"), "max_price": None, "currency": "\t\u2003"},
        {"currency": "EUR"},
    ),
    (stored(), {"point_missing": True}, {"point_missing": False}),
    (
        stored("url_syntax", "event", field="source_link"),
        {"source_link": "example.org/foo"},
        {"source_link": "https://example.org/foo"},
    ),
    (
        stored("membership_joined_accept_token_present", "team_membership", field="accept_token"),
        {"has_joined": True, "accept_token_present": True},
        {"has_joined": False},
    ),
    (
        stored("partner_long_pending", "partner_request", field="status"),
        {"status": "pending", "created_at": (STAMP - timedelta(days=1000)).replace(tzinfo=None)},
        {"status": "accepted"},
    ),
]


@pytest.mark.parametrize("finding,row,correction", CASES, ids=[item[0].rule for item in CASES])
def test_matching_and_current_nonmatching_evaluation(settings, finding, row, correction):
    assert evaluate(finding, [row], settings, STAMP).matched is True
    current = evaluate(finding, [{**row, **correction}], settings, STAMP)
    assert current.matched is False
    assert "nicht mehr" in current.message
    assert evaluate(finding, [], settings, STAMP).matched is None


def test_shared_python_semantics(settings):
    finding, row, _ = CASES[5]
    with patch(
        "app.sql_diagnostics.evaluation.url_problem", return_value="missing_scheme"
    ) as helper:
        assert evaluate(finding, [row], settings, STAMP).matched
        helper.assert_called_once_with("example.org/foo")
    finding, row, _ = CASES[2]
    assert not evaluate(finding, [{**row, "event_venue_uuid": uid(20)}], settings, STAMP).matched
    assert not evaluate(finding, [{**row, "date_venue_uuid": uid(21)}], settings, STAMP).matched
    settings.uranus_timestamp_timezone = "Europe/Berlin"
    settings.pending_age_days = 10
    # Strict threshold, source timestamp interpreted in the configured timezone.
    row = {"status": "pending", "created_at": datetime(2026, 9, 21, 2)}
    assert not evaluate(CASES[7][0], [row], settings, STAMP).matched
    assert evaluate(
        CASES[7][0],
        [{**row, "created_at": row["created_at"] - timedelta(seconds=1)}],
        settings,
        STAMP,
    ).matched


@pytest.mark.parametrize("item", [*RECIPES, *URL_RECIPES.values()], ids=lambda item: item.id)
async def test_every_registered_query_matches_fixture_contract(db_connection, settings, now, item):
    kind = item.entity_type
    key = {
        "event_date": str(uid(40)),
        "event": str(uid(30)),
        "venue": str(uid(20)),
        "organization": str(uid(10)),
        "team_membership": f"membership:{uid(10)}:{uid(1)}",
        "partner_request": f"partner-request:{uid(10)}:{uid(11)}",
    }[kind]
    finding = stored(item.rule, kind, key, item.fields[0])
    rows = [
        dict(row)
        for row in (await db_connection.execute(text(item.sql), parameters_for(finding))).mappings()
    ]
    assert len(rows) == 1
    assert set(rows[0]) == set(item.result_fields)
    evaluate(finding, rows, settings, now)
    assert definition(finding).readonly


async def test_token_fixture_never_leaves_projection(db_connection, settings, now, caplog):
    await db_connection.execute(
        text("UPDATE uranus.organization_member_link SET has_joined=true, accept_token=:token"),
        {"token": SECRET},
    )
    finding = stored(
        "membership_joined_accept_token_present",
        "team_membership",
        f"membership:{uid(10)}:{uid(1)}",
        "accept_token",
    )
    item = resolve(finding)
    rows = [
        dict(row)
        for row in (await db_connection.execute(text(item.sql), parameters_for(finding))).mappings()
    ]
    assert rows[0]["accept_token_present"] is True
    assert evaluate(finding, rows, settings, now).matched
    public = (
        definition(finding).model_dump_json()
        + repr(rows)
        + evaluate(finding, rows, settings, now).model_dump_json()
    )
    assert SECRET not in public + caplog.text
    assert '"accept_token"' not in json.dumps(rows, default=str)


async def test_executor_readonly_timeouts_bound_limit_rollback(database, settings, caplog):
    engine = create_async_engine(database[0], poolclass=NullPool, hide_parameters=True)
    commands = []
    rollbacks = []
    event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, params, context, many: commands.append((statement, params)),
    )
    event.listen(engine.sync_engine, "rollback", lambda conn: rollbacks.append(True))
    caplog.set_level(logging.INFO, logger="admin.sql_diagnostics")
    try:
        result = await execute(engine, stored(), settings, "admin:fixture")
        assert result.row_count == 1
        assert result.evaluation.matched
        assert commands[0][0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        assert "5000ms" in commands[1][0]
        assert "1000ms" in commands[2][0]
        assert "10000ms" in commands[3][0]
        assert "LIMIT" in commands[4][0] and 50 in commands[4][1]
        assert rollbacks == [True]
        record = next(record for record in caplog.records if record.name == "admin.sql_diagnostics")
        audit = json.loads(JsonFormatter(debug=True).format(record))
        assert audit["actor_subject"] == "admin:fixture"
        assert audit["row_count"] == 1 and "rows" not in audit
        assert audit["finding_id_hash"] != stored().id
    finally:
        await engine.dispose()


async def test_db_exception_is_safe_even_in_debug_logs(settings, caplog):
    engine = AsyncMock()
    engine.connect = lambda: (_ for _ in ()).throw(RuntimeError(SECRET))
    with pytest.raises(APIError) as error:
        await execute(engine, stored(), settings, "admin:fixture")
    import traceback

    rendered = "".join(traceback.format_exception(error.value))
    assert SECRET not in rendered + repr(error.value) + caplog.text
    assert error.value.code == "diagnostic_failed"


async def test_api_loads_persisted_resolved_finding_and_rejects_sql(
    database, admin_store, settings, headers
):
    from pydantic import SecretStr

    settings.database_url = SecretStr(database[0])
    await admin_store.execute(
        finding_table.insert().values(
            id="diagnostic-test",
            rule="venue_missing_location",
            entity_type="venue",
            entity_key=str(uid(21)),
            field="point",
            status="resolved",
            severity="warning",
            message="Historical",
            first_seen_at=STAMP,
            last_seen_at=STAMP,
            metadata={},
        )
    )
    await admin_store.commit()
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        url = "/api/v1/findings/sql-diagnostic"
        assert (await client.get(url, params={"finding_id": "diagnostic-test"})).status_code == 401
        with patch("app.api.sql_diagnostics.execute", new_callable=AsyncMock) as executor:
            response = await client.get(
                url, headers=headers, params={"finding_id": "diagnostic-test"}
            )
            assert response.status_code == 200
            executor.assert_not_called()
            bad = await client.post(
                url + "/execute",
                headers=headers,
                json={"finding_id": "diagnostic-test", "sql": "SELECT 1"},
            )
            assert bad.status_code == 422
            executor.assert_not_called()
            bad_query = await client.post(
                url + "/execute?sql=SELECT+1",
                headers=headers,
                json={"finding_id": "diagnostic-test"},
            )
            assert bad_query.status_code == 422
            executor.assert_not_called()
        response = await client.post(
            url + "/execute", headers=headers, json={"finding_id": "diagnostic-test"}
        )
        assert response.status_code == 200
        assert response.json()["evaluation"]["matched"] is False
        assert (
            await client.get(url, headers=headers, params={"finding_id": "missing"})
        ).status_code == 404
        assert (
            await client.get(
                url, headers=headers, params={"finding_id": "diagnostic-test", "sql": "SELECT 1"}
            )
        ).status_code == 422


async def test_actual_postgres_transaction_settings_and_timeout(database, settings):
    engine = create_async_engine(database[0], poolclass=NullPool, hide_parameters=True)
    registered = resolve(stored())
    inspection = replace(
        registered,
        sql="""SELECT
current_setting('transaction_read_only') = 'on'
AND current_setting('transaction_isolation') = 'repeatable read'
AND current_setting('statement_timeout') = '5s'
AND current_setting('lock_timeout') = '1s'
AND current_setting('idle_in_transaction_session_timeout') = '10s' AS point_missing
WHERE CAST(:entity_key AS uuid) IS NOT NULL LIMIT :diagnostic_limit""",
        result_fields=("point_missing",),
    )
    try:
        with patch("app.sql_diagnostics.executor.resolve", return_value=inspection):
            assert (await execute(engine, stored(), settings, "admin:fixture")).rows == [
                {"point_missing": True}
            ]
        slow = replace(
            registered,
            sql=(
                "SELECT pg_sleep(6) WHERE CAST(:entity_key AS uuid) IS NOT NULL "
                "LIMIT :diagnostic_limit"
            ),
        )
        with patch("app.sql_diagnostics.executor.resolve", return_value=slow):
            with pytest.raises(APIError) as error:
                await execute(engine, stored(), settings, "admin:fixture")
            assert error.value.code == "diagnostic_timeout"
        async with engine.connect() as connection:
            assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


async def test_membership_token_api_and_least_privilege_reader(
    database, admin_store, settings, headers, capsys
):
    from pydantic import SecretStr
    from sqlalchemy.engine import make_url

    setup = create_async_engine(database[0], poolclass=NullPool)
    async with setup.begin() as connection:
        await connection.execute(
            text("CREATE ROLE diagnostic_reader_test LOGIN PASSWORD 'fixture-reader-only'")
        )
        await connection.execute(text("GRANT USAGE ON SCHEMA uranus TO diagnostic_reader_test"))
        await connection.execute(
            text("GRANT SELECT ON ALL TABLES IN SCHEMA uranus TO diagnostic_reader_test")
        )
        await connection.execute(
            text("UPDATE uranus.organization_member_link SET has_joined=true, accept_token=:token"),
            {"token": SECRET},
        )
    settings.database_url = SecretStr(
        make_url(database[0])
        .set(username="diagnostic_reader_test", password="fixture-reader-only")
        .render_as_string(hide_password=False)
    )
    await admin_store.execute(
        finding_table.insert().values(
            id="token-test",
            rule="membership_joined_accept_token_present",
            entity_type="team_membership",
            entity_key=f"membership:{uid(10)}:{uid(1)}",
            field="accept_token",
            status="open",
            severity="error",
            message="Synthetic",
            first_seen_at=STAMP,
            last_seen_at=STAMP,
            metadata={},
        )
    )
    await admin_store.commit()
    try:
        app = create_app(settings)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            url = "/api/v1/findings/sql-diagnostic"
            response = await client.get(url, headers=headers, params={"finding_id": "token-test"})
            assert response.status_code == 200
            assert SECRET not in response.text
            response = await client.post(
                url + "/execute", headers=headers, json={"finding_id": "token-test"}
            )
            assert response.status_code == 200
            assert response.json()["evaluation"]["matched"] is True
            assert response.json()["rows"][0]["accept_token_present"] is True
            assert SECRET not in response.text + repr(response.json())
        output = capsys.readouterr()
        assert SECRET not in output.out + output.err
    finally:
        async with setup.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE uranus.organization_member_link SET has_joined=false, accept_token=NULL"
                )
            )
            await connection.execute(text("DROP OWNED BY diagnostic_reader_test"))
            await connection.execute(text("DROP ROLE diagnostic_reader_test"))
        await setup.dispose()


async def test_diagnostics_enforce_admin_and_cookie_csrf(settings):
    from app.auth.service import AdminPrincipal

    settings.auth_public_origin = "http://test"
    app = create_app(settings)
    url = "/api/v1/findings/sql-diagnostic/execute"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(url, json={"finding_id": "x"})).status_code == 401
        client.cookies.set(settings.session_cookie, "x" * 43)
        with (
            patch("app.auth.dependencies.session_identity", new_callable=AsyncMock) as identity,
            patch("app.api.sql_diagnostics.load_finding", new_callable=AsyncMock) as loader,
        ):
            identity.return_value = AdminPrincipal(subject="admin:fixture", system_admin=True)
            for extra in (
                {},
                {"Origin": "http://evil.invalid", "X-Admin-CSRF": "1"},
                {"Origin": "http://test"},
            ):
                response = await client.post(url, headers=extra, json={"finding_id": "x"})
                assert response.status_code == 403
                assert response.json()["error"]["code"] == "csrf_rejected"
            identity.return_value = AdminPrincipal(subject="admin:fixture", system_admin=False)
            response = await client.post(
                url,
                headers={"Origin": "http://test", "X-Admin-CSRF": "1"},
                json={"finding_id": "x"},
            )
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "admin_access_denied"
            loader.assert_not_called()


@pytest.mark.parametrize(
    "rule,kind,key,field,available",
    [
        ("venue_missing_location", "venue", str(uid(20)), "point", True),
        ("url_syntax", "venue", str(uid(20)), "web_link", True),
        ("unsupported", "venue", str(uid(20)), "point", False),
        ("venue_missing_location", "event", str(uid(20)), "point", False),
        ("venue_missing_location", "venue", str(uid(20)), "wrong", False),
        ("venue_missing_location", "venue", "invalid", "point", False),
        (
            "membership_joined_accept_token_present",
            "team_membership",
            f"membership:{uid(10)}:{uid(1)}",
            "accept_token",
            True,
        ),
    ],
)
@pytest.mark.parametrize("status", ["open", "resolved"])
def test_finding_diagnostic_capability_uses_registry(rule, kind, key, field, available, status):
    from app.schemas.finding import Finding
    from app.services.checks import stored_finding

    live = Finding(
        id="fixture",
        rule=rule,
        entity_type=kind,
        entity_key=key,
        field=field,
        entity_name="Fixture",
        message="Fixture",
        severity="warning",
        priority=4,
        priority_score=1,
        priority_reasons=[],
        organization_id=None,
        organization_name=None,
        last_seen_at=STAMP,
    )
    assert live.sql_diagnostic_available is False
    row = {**live.model_dump(), "status": status, "first_seen_at": STAMP}
    # Stale or fabricated capability in persisted display metadata is never trusted.
    row["metadata"] = {"finding": {"sql_diagnostic_available": not available}}
    assert stored_finding(row).sql_diagnostic_available is available
