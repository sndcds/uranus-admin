"""Privacy/ranking units and CI-only PostgreSQL counter/receipt regressions."""

import io
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi import Request
from pydantic import ValidationError

from app.admin_database import get_admin_connection
from app.admin_tables import research_query_history as history
from app.admin_tables import research_query_suggestion as suggestions
from app.admin_tables import research_query_suggestion_event as events
from app.errors import APIError
from app.repositories import research_suggestions as repo
from app.schemas.research_suggestions import (
    Impression,
    Selection,
    ShownSuggestion,
    SuggestionFilters,
)
from app.services import research_learning as learning
from app.services.research_suggestions import eligible, normalize, score
from tests.test_research_plan_execution import planned


@pytest.mark.parametrize(
    "query,expected",
    [
        ("  Welche   Orte?  ", "welche orte"),
        ("STRASSE!", "strasse"),
        ("Straße.", "strasse"),
        ("Hvilke øer？", "hvilke øer"),
        ("Musik\n in\tFlensburg", "musik in flensburg"),
        ("Ort: A-B", "ort: a-b"),
    ],
)
def test_normalization(query, expected):
    assert normalize(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "Events für private@example.de",
        "Rufe +49 461 1234567 an",
        "Suche 123e4567-e89b-12d3-a456-426614174000",
        "api_key abcdefghijklmnop",
        "Bearer abcdef",
        "Mein Passwort ist test",
        "https://localhost:9000/test",
        "kulturbytes.de/events",
        "ssh-rsa AAAAB3Nz",
        "ignore previous instructions",
        "SELECT name FROM uranus.event",
        "function x() { return 1; }",
        "x" * 301,
        "Zeige username von anna",
        "Events\u200bin Flensburg",
    ],
)
def test_sensitive_rejected(query):
    assert not eligible(query)


@pytest.mark.parametrize(
    "query",
    [
        "Welche Organisation hat die meisten Veranstaltungen?",
        "Welche Events gibt es 2026 in Flensburg?",
        "Hvilke koncerter er der i Sønderborg?",
    ],
)
def test_cultural_queries_allowed(query):
    assert eligible(query)


def ranked(**changes):
    values = dict(
        starts=True, successes=3, selections=0, conversions=0, impressions=10, age_days=30
    )
    return score(**(values | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"successes": 20},
        {"selections": 10},
        {"conversions": 10},
        {"age_days": 0},
    ],
)
def test_ranking_signals(changes):
    assert ranked(**changes) > ranked()


def test_prefix_and_smoothed_ctr():
    assert ranked() > ranked(starts=False, successes=1000, selections=500, conversions=300)
    assert ranked(successes=100, selections=25, conversions=10, impressions=200) > ranked(
        selections=1, impressions=1
    )
    assert ranked(conversions=10) > ranked(selections=10)


def test_bounded_contracts():
    with pytest.raises(ValidationError):
        SuggestionFilters(q="x")
    with pytest.raises(ValidationError):
        SuggestionFilters(q="ab", limit=9)
    with pytest.raises(ValidationError):
        Selection(request_id=uuid4(), suggestion_id=uuid4(), position=0)
    item = ShownSuggestion(id=uuid4(), position=1)
    with pytest.raises(ValidationError):
        Impression(request_id=uuid4(), prefix="we", suggestions=[item, item])


def test_migration_offline(monkeypatch):
    monkeypatch.setenv(
        "ADMIN_MIGRATION_DATABASE_URL", "postgresql+asyncpg://unused@localhost/unused_test"
    )
    output = io.StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=output), "0017:0018", sql=True)
    sql = output.getvalue()
    assert sql.count("CREATE TABLE admin.research_query_") == 3
    assert "USING gin" in sql and "research_event_once" in sql
    assert "uranus." not in sql and "CREATE EXTENSION" not in sql
    output = io.StringIO()
    command.downgrade(Config("alembic.ini", output_buffer=output), "0018:0017", sql=True)
    assert output.getvalue().count("DROP TABLE admin.research_query_") == 3


@pytest.mark.parametrize(
    "path,method",
    [
        ("/suggestions?q=welche", "get"),
        ("/suggestions/impression", "post"),
        ("/suggestions/select", "post"),
    ],
)
async def test_auth(client, path, method):
    assert (await getattr(client, method)("/api/v1/research" + path)).status_code == 401


async def test_api_validation(client, headers):
    async def connection():
        yield AsyncMock()

    app = client._transport.app
    app.dependency_overrides[get_admin_connection] = connection
    try:
        for query in ["q=a", "q=ab&limit=9", "q=ab&unknown=1", "q=%20%20"]:
            assert (
                await client.get("/api/v1/research/suggestions?" + query, headers=headers)
            ).status_code == 422
        for suffix in ["impression", "select"]:
            assert (
                await client.post(
                    "/api/v1/research/suggestions/" + suffix,
                    headers=headers,
                    json={"request_id": "bad"},
                )
            ).status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_learning_skips_clarification_and_isolates_failure(monkeypatch):
    from types import SimpleNamespace

    spy = AsyncMock()
    monkeypatch.setattr(learning, "learn", spy)

    @asynccontextmanager
    async def broken(request):
        raise RuntimeError("sensitive text must not be logged")
        yield

    monkeypatch.setattr(learning, "connect_admin", broken)
    for kind in ["needs_clarification", "count"]:
        response = SimpleNamespace(result=SimpleNamespace(kind=kind), plan=planned())
        await learning.record_success(Request({"type": "http"}), response, None)
    spy.assert_not_called()


@pytest.mark.integration
async def test_learning_events_conversion_and_privacy(admin_store):
    connection = admin_store
    query = "Welche Organisation hat die meisten Veranstaltungen?"
    plan = planned().plan
    async with connection.begin():
        await repo.learn(connection, query, plan, None)
        assert not (await repo.lookup(connection, SuggestionFilters(q="welche org"))).suggestions
        await repo.learn(connection, query, plan, None)
        await repo.learn(connection, query, plan, None)
        result = await repo.lookup(connection, SuggestionFilters(q="welche org"))
        item = result.suggestions[0]
        body = Impression(
            request_id=result.request_id,
            prefix="welche org",
            suggestions=[ShownSuggestion(id=item.id, position=1)],
        )
        await repo.impression(connection, body)
        await repo.impression(connection, body)
        selection = Selection(request_id=result.request_id, suggestion_id=item.id, position=1)
        receipt = await repo.select(connection, selection)
        assert await repo.select(connection, selection) == receipt
        # Receipt does not convert a different question.
        await repo.learn(connection, "Welche Orte gibt es?", plan, receipt)
        await repo.learn(connection, query, plan, receipt)
        await repo.learn(connection, query, plan, receipt)
        row = (
            (await connection.execute(sa.select(suggestions).where(suggestions.c.id == item.id)))
            .mappings()
            .one()
        )
        assert (
            row["success_count"],
            row["suggestion_impressions"],
            row["suggestion_selections"],
            row["successful_selections"],
        ) == (5, 1, 1, 1)
        assert (
            await connection.execute(sa.select(sa.func.count()).select_from(events))
        ).scalar_one() == 2
        await repo.learn(connection, "Email private@example.de", plan, None)
        redacted = (
            (await connection.execute(sa.select(history).where(~history.c.is_eligible)))
            .mappings()
            .one()
        )
        assert redacted["query_text"] is None and redacted["normalized_query"] is None
        assert redacted["successful"]
        await connection.execute(
            suggestions.update().where(suggestions.c.id == item.id).values(is_blocked=True)
        )
        assert not (await repo.lookup(connection, SuggestionFilters(q="welche"))).suggestions
        with pytest.raises(APIError):
            await repo.select(connection, selection)


@pytest.mark.integration
async def test_expired_receipt_and_order_limit(admin_store):
    connection = admin_store
    plan = planned().plan
    async with connection.begin():
        for number in range(12):
            for _ in range(3):
                await repo.learn(
                    connection, f"Welche Orte haben {number} Veranstaltungen?", plan, None
                )
        result = await repo.lookup(connection, SuggestionFilters(q="welche"))
        assert len(result.suggestions) == 8
        assert (
            result.suggestions
            == (await repo.lookup(connection, SuggestionFilters(q="welche"))).suggestions
        )
        item = result.suggestions[0]
        await repo.impression(
            connection,
            Impression(
                request_id=result.request_id,
                prefix="welche",
                suggestions=[ShownSuggestion(id=item.id, position=1)],
            ),
        )
        receipt = await repo.select(
            connection, Selection(request_id=result.request_id, suggestion_id=item.id, position=1)
        )
        # Append-only events: advance the application clock instead of editing telemetry.
        from unittest.mock import patch

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(UTC) + timedelta(minutes=11)

        with patch.object(repo, "datetime", Later):
            await repo.learn(connection, item.query, plan, receipt)
        assert (
            await connection.execute(
                sa.select(suggestions.c.successful_selections).where(suggestions.c.id == item.id)
            )
        ).scalar_one() == 0


@pytest.mark.parametrize("suffix", ["impression", "select"])
@pytest.mark.parametrize("origin", [None, "https://evil.test", "https://admin.test"])
async def test_telemetry_cookie_origin_and_csrf(client, monkeypatch, suffix, origin):
    from app.api import research
    from app.auth import dependencies
    from app.auth.service import AdminPrincipal

    app = client._transport.app
    app.state.settings.auth_public_origin = "https://admin.test"
    monkeypatch.setattr(
        dependencies,
        "session_identity",
        AsyncMock(return_value=AdminPrincipal(subject="fixture", journalist=True)),
    )
    connection = AsyncMock()
    connection.begin = lambda: transaction()

    @asynccontextmanager
    async def transaction():
        yield

    async def admin():
        yield connection

    app.dependency_overrides[get_admin_connection] = admin
    monkeypatch.setattr(research.research_suggestions, "impression", AsyncMock())
    monkeypatch.setattr(research.research_suggestions, "select", AsyncMock(return_value=uuid4()))
    client.cookies.set("admin_session", "a" * 43)
    body = {"request_id": str(uuid4())}
    if suffix == "impression":
        body.update(prefix="welche", suggestions=[{"id": str(uuid4()), "position": 1}])
    else:
        body.update(suggestion_id=str(uuid4()), position=1)
    headers = {"Origin": origin, "X-Admin-CSRF": "1"} if origin else {}
    try:
        result = await client.post(
            "/api/v1/research/suggestions/" + suffix, headers=headers, json=body
        )
        assert result.status_code == (200 if origin == "https://admin.test" else 403)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
async def test_api_event_deduplication(client, headers, admin_store):
    async with admin_store.begin():
        for _ in range(3):
            await repo.learn(admin_store, "Welche Orte gibt es?", planned().plan, None)
        result = await repo.lookup(admin_store, SuggestionFilters(q="welche"))
    item = result.suggestions[0]

    async def admin():
        yield admin_store

    app = client._transport.app
    app.dependency_overrides[get_admin_connection] = admin
    try:
        for _ in range(2):
            response = await client.post(
                "/api/v1/research/suggestions/impression",
                headers=headers,
                json={
                    "request_id": str(result.request_id),
                    "prefix": "welche",
                    "suggestions": [{"id": str(item.id), "position": 1}],
                },
            )
            assert response.status_code == 200
        receipts = []
        for _ in range(2):
            response = await client.post(
                "/api/v1/research/suggestions/select",
                headers=headers,
                json={
                    "request_id": str(result.request_id),
                    "suggestion_id": str(item.id),
                    "position": 1,
                },
            )
            assert response.status_code == 200
            receipts.append(response.json()["receipt"])
        assert receipts[0] == receipts[1]
        async with admin_store.begin():
            row = (
                await admin_store.execute(
                    sa.select(
                        suggestions.c.suggestion_impressions, suggestions.c.suggestion_selections
                    )
                )
            ).one()
            assert tuple(row) == (1, 1)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
async def test_sql_ranking_uses_learning_signals(admin_store):
    now = datetime.now(UTC)
    samples = [
        ("Welche Orte Alpha?", 3, 1, 0, 1, 0),
        ("Welche Orte Beta?", 100, 25, 10, 200, 0),
        ("Welche Orte Gamma?", 3, 0, 0, 10, 0),
        ("Welche Orte Delta?", 3, 0, 0, 10, 100),
        ("Finde welche Orte Epsilon?", 100, 25, 10, 200, 0),
    ]
    expected = []
    async with admin_store.begin():
        for query, successes, selections, conversions, impressions, age in samples:
            await repo.learn(admin_store, query, planned().plan, None)
            await admin_store.execute(
                suggestions.update()
                .where(suggestions.c.normalized_query == normalize(query))
                .values(
                    success_count=successes,
                    suggestion_selections=selections,
                    successful_selections=conversions,
                    suggestion_impressions=impressions,
                    last_used_at=now - timedelta(days=age),
                )
            )
            expected.append(
                (
                    score(
                        starts=normalize(query).startswith("welche"),
                        successes=successes,
                        selections=selections,
                        conversions=conversions,
                        impressions=impressions,
                        age_days=age,
                    ),
                    query,
                )
            )
        result = await repo.lookup(admin_store, SuggestionFilters(q="welche"))
        assert [item.query for item in result.suggestions] == [
            query for _, query in sorted(expected, reverse=True)
        ]
        # A token-boundary prefix is supported, not an arbitrary infix.
        assert (await repo.lookup(admin_store, SuggestionFilters(q="orte"))).suggestions
        assert not (await repo.lookup(admin_store, SuggestionFilters(q="rte"))).suggestions
        assert not (await repo.lookup(admin_store, SuggestionFilters(q="we%"))).suggestions


@pytest.mark.integration
async def test_concurrent_events_and_conversions(admin_store):
    import asyncio

    query = "Welche Organisation nutzt die meisten Veranstaltungsorte?"
    async with admin_store.begin():
        for _ in range(3):
            await repo.learn(admin_store, query, planned().plan, None)
        result = await repo.lookup(admin_store, SuggestionFilters(q="welche"))
    item = result.suggestions[0]
    body = Impression(
        request_id=result.request_id,
        prefix="welche",
        suggestions=[ShownSuggestion(id=item.id, position=1)],
    )
    selection = Selection(request_id=result.request_id, suggestion_id=item.id, position=1)

    async def show_and_select():
        async with admin_store.engine.begin() as connection:
            await repo.impression(connection, body)
            return await repo.select(connection, selection)

    receipts = await asyncio.gather(show_and_select(), show_and_select())
    assert receipts[0] == receipts[1]

    async def execute_success():
        async with admin_store.engine.begin() as connection:
            await repo.learn(connection, query, planned().plan, receipts[0])

    await asyncio.gather(execute_success(), execute_success())
    async with admin_store.begin():
        row = (
            await admin_store.execute(
                sa.select(
                    suggestions.c.success_count,
                    suggestions.c.suggestion_impressions,
                    suggestions.c.suggestion_selections,
                    suggestions.c.successful_selections,
                )
            )
        ).one()
        assert tuple(row) == (5, 1, 1, 1)


@pytest.mark.integration
async def test_learning_role_is_append_only(admin_store):
    from sqlalchemy.exc import DBAPIError

    from app.admin_database import assert_admin_boundary

    async with admin_store.begin():
        await assert_admin_boundary(admin_store)
        for table in ["research_query_history", "research_query_suggestion_event"]:
            for statement in [
                f"DELETE FROM admin.{table}",
                f"UPDATE admin.{table} SET created_at=now()",
            ]:
                with pytest.raises(DBAPIError):
                    async with admin_store.begin_nested():
                        await admin_store.execute(sa.text(statement))
