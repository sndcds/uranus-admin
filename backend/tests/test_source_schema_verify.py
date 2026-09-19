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


def contract_columns():
    from app.source_contract import QUALITY_SOURCE_CONTRACT

    return [
        {
            "table_name": table,
            "column_name": column,
            "udt_name": kind,
            "formatted_type": "geometry(Point,4326)" if kind == "geometry" else kind,
        }
        for table, fields in QUALITY_SOURCE_CONTRACT.items()
        for column, kind in fields.items()
    ]


def test_contract_missing_column_and_extra_table():
    from app.source_contract import compare_contract

    columns = contract_columns()
    columns.append({"table_name": "legacy_portal", "column_name": "old", "udt_name": "text"})
    assert compare_contract(columns)["compatible"] is True
    columns = [
        r for r in columns if (r["table_name"], r["column_name"]) != ("event_date", "end_date")
    ]
    report = compare_contract(columns)
    assert report["compatible"] is False
    assert report["missing_columns"] == [
        {"table": "event_date", "column": "end_date", "category": "missing_required_source_column"}
    ]


@pytest.mark.parametrize(
    "table,column,kind,formatted",
    [
        ("event", "uuid", "text", "text"),
        ("event", "categories", "text", "text"),
        ("event_date", "start_date", "timestamp", "timestamp without time zone"),
        ("organization", "point", "geometry", "geometry(Point,3857)"),
        ("venue", "point", "geometry", "geometry(Polygon,4326)"),
        ("event", "release_status", "text", "text"),
    ],
)
def test_contract_type_drift(table, column, kind, formatted):
    from app.source_contract import compare_contract

    columns = contract_columns()
    row = next(r for r in columns if r["table_name"] == table and r["column_name"] == column)
    row.update(udt_name=kind, formatted_type=formatted)
    report = compare_contract(columns)
    assert report["compatible"] is False
    assert report["type_mismatches"][0]["category"] == "source_type_mismatch"


@pytest.mark.integration
async def test_catalog_detects_required_column_missing_and_ignores_extra(db_connection, settings):
    await db_connection.execute(text("CREATE TABLE uranus.legacy_portal (id integer)"))
    assert (await verify(db_connection, settings))["source_contract"]["compatible"] is True
    await db_connection.execute(text("ALTER TABLE uranus.event_date DROP COLUMN end_date"))
    report = await verify(db_connection, settings)
    assert report["source_contract"]["missing_columns"] == [
        {"table": "event_date", "column": "end_date", "category": "missing_required_source_column"}
    ]


@pytest.mark.parametrize("compatible,exit_code", [(True, 0), (False, 1)])
def test_operator_exit_code_on_drift(monkeypatch, capsys, settings, compatible, exit_code):
    from app import source_schema_verify

    async def report(_settings):
        return {"source_contract": {"compatible": compatible}}

    monkeypatch.setattr(source_schema_verify, "Settings", lambda: settings)
    monkeypatch.setattr(source_schema_verify, "run", report)
    monkeypatch.setattr("sys.argv", ["verify", "--json"])
    assert source_schema_verify.main() == exit_code
    assert json.loads(capsys.readouterr().out)["source_contract"]["compatible"] is compatible
