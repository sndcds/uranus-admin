import json

import pytest
from pydantic import SecretStr
from sqlalchemy import event, text

from app.source_schema_verify import run, verify


@pytest.mark.integration
async def test_source_verifier_metadata_only(db_connection, settings):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().upper())

    event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        report = await verify(db_connection, settings)
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)
    assert all(statement.startswith("SELECT") for statement in statements)
    assert report["observed_values"]["venue.scope"]["values"] == ["organization"]
    assert any(
        row["table_name"] == "organization_member_link" and row["kind"] == "u"
        for row in report["constraints"]
    )
    assert any(row["data_type"] == "timestamp without time zone" for row in report["columns"])
    assert report["uranus_timestamp_timezone"] == "UTC"
    assert "fixture@example.invalid" not in json.dumps(report)
    assert "not-a-password-hash" not in json.dumps(report)


@pytest.mark.integration
async def test_source_verifier_readonly_connection(database, settings):
    settings.database_url = SecretStr(database[0])
    report = await run(settings)
    assert report["database"].endswith("_test")
    assert report["transaction_read_only"] is True
    assert "operator confirmation required" in report["timestamp_note"]


def test_source_verifier_sanitizes_failure(monkeypatch, capsys):
    from app import source_schema_verify

    def broken():
        raise ValueError("postgres://operator:SECRET@private.invalid/db")

    monkeypatch.setattr(source_schema_verify, "Settings", broken)
    monkeypatch.setattr("sys.argv", ["verify", "--json"])
    assert source_schema_verify.main() == 1
    assert "SECRET" not in capsys.readouterr().out


@pytest.mark.integration
async def test_source_verifier_flags_incomplete_observed_values(db_connection, settings):
    # Synthetic status metadata only, in the disposable test database.
    await db_connection.execute(
        text("UPDATE uranus.organization_partner_request SET status=:status"), {"status": "x" * 90}
    )
    report = await verify(db_connection, settings)
    status = report["observed_values"]["organization_partner_request.status"]
    assert status["values"] == ["x" * 80]
    assert status["values_truncated"] is True
    assert status["truncated"] is False
    assert report["observed_values"]["venue.scope"]["values_truncated"] is False
    assert "x" * 90 not in json.dumps(report)
