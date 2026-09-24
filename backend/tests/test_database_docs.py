import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from pglast import parse_sql

from app.admin_tables import metadata
from app.geo_types import Geometry
from scripts import generate_database_docs as docs


def table_block(dbml, name):
    return dbml.split(f"Table admin.{name} {{\n", 1)[1].split("\n}\n", 1)[0]


def test_dbml_all_tables_and_foreign_keys_once():
    dbml = docs.render_dbml(metadata)
    assert re.findall(r"^Table admin\.(\w+) \{", dbml, re.M) == sorted(
        table.name for table in metadata.tables.values()
    )
    references = [line for line in dbml.splitlines() if line.startswith("Ref ")]
    assert len(references) == sum(
        len(table.foreign_key_constraints) for table in metadata.tables.values()
    )
    for table in metadata.tables.values():
        for constraint in table.foreign_key_constraints:
            # Current production metadata has single-column FKs; synthetic composite below.
            assert len(constraint.elements) == 1
            fk = constraint.elements[0]
            relationship = (
                f"admin.{table.name}.{fk.parent.name} > "
                f"admin.{fk.column.table.name}.{fk.column.name}"
            )
            assert sum(relationship in reference for reference in references) == 1
    assert "Table uranus." not in dbml


def test_notification_delivery_retry_regression():
    dbml = docs.render_dbml(metadata)
    assert "retry_of_delivery_id uuid" in dbml
    assert "retry_of_delivery_id uuid" in table_block(dbml, "notification_delivery")
    assert "admin.notification_delivery.retry_of_delivery_id" in dbml
    assert "> admin.notification_delivery.id" in dbml
    assert (
        "admin.notification_delivery.retry_of_delivery_id > admin.notification_delivery.id "
        "[delete: restrict]"
    ) in dbml


def test_composite_primary_unique_keys_and_database_column_names():
    dbml = docs.render_dbml(metadata)
    items = table_block(dbml, "notification_delivery_item")
    assert "delivery_id uuid [not null]" in items
    assert "notification_id uuid [not null]" in items
    assert "(delivery_id, notification_id) [pk]" in items
    assert items.count("[pk]") == 1
    finding = table_block(dbml, "finding")
    assert "entity_id text [not null]" in finding
    assert "(rule, entity_type, entity_id, field) [unique]" in finding
    assert "entity_key" not in finding
    assert "login text [not null, unique]" in table_block(dbml, "auth_account")


def test_defaults_and_postgresql_only_indexes_are_not_misrepresented():
    dbml = docs.render_dbml(metadata)
    account = table_block(dbml, "auth_account")
    assert "is_active boolean [not null, default: false]" in account
    assert "credential_version integer [not null, default: 1]" in account
    assert "created_at timestamptz [not null, default: `now()`]" in account
    assert "default: `'{}'::jsonb`" in dbml
    delivery = table_block(dbml, "notification_delivery")
    assert "retry_of_delivery_id uuid [unique" not in delivery
    assert "Note: 'PostgreSQL indexes:" in delivery
    assert "WHERE status !=" in delivery
    assert "USING gist" in table_block(dbml, "geo_area")


@pytest.mark.parametrize(
    ("type_", "expected"),
    [
        (sa.UUID(), "uuid"),
        (sa.Text(), "text"),
        (sa.Integer(), "integer"),
        (sa.Boolean(), "boolean"),
        (sa.DateTime(timezone=True), "timestamptz"),
        (sa.DateTime(), "timestamp"),
        (sa.dialects.postgresql.JSONB(), "jsonb"),
        (sa.Double(), "double"),
        (Geometry("MultiPolygon"), "geometry(MultiPolygon,4326)"),
        (Geometry("Polygon"), "geometry(Polygon,4326)"),
    ],
)
def test_dbml_type_mapping(type_, expected):
    assert docs.dbml_type(type_) == expected


def test_final_sql_retry_is_defined_inline_and_all_ddl_is_postgresql():
    sql = docs.render_schema_sql(metadata)
    statements = parse_sql(sql)
    assert statements  # Parse the entire document using PostgreSQL's grammar, without a DB.
    delivery = sql.split("CREATE TABLE admin.notification_delivery (", 1)[1].split("\n);", 1)[0]
    assert "retry_of_delivery_id UUID" in delivery
    assert (
        "FOREIGN KEY(retry_of_delivery_id) REFERENCES admin.notification_delivery (id) "
        "ON DELETE RESTRICT"
    ) in delivery
    assert "ALTER TABLE" not in sql
    assert "CREATE SCHEMA admin;" in sql
    assert "geometry(MultiPolygon,4326)" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "JSONB DEFAULT '{}'::jsonb" in sql
    assert "PRIMARY KEY (delivery_id, notification_id)" in sql
    assert "UNIQUE (rule, entity_type, entity_id, field)" in sql
    assert "CHECK (" in sql
    assert "USING gist (geometry)" in sql
    assert "CREATE UNIQUE INDEX notification_delivery_retry_of_idx" in sql
    assert "WHERE status != 'cancelled'" in sql
    assert sql.count("CREATE TABLE ") == len(metadata.tables)
    assert sql.count("CREATE INDEX ") + sql.count("CREATE UNIQUE INDEX ") == sum(
        len(table.indexes) for table in metadata.tables.values()
    )
    assert "alembic_version" not in sql


def test_composite_fk_uses_database_names_and_preserves_column_pairs():
    sample = sa.MetaData(schema="admin")
    sa.Table(
        "parent",
        sample,
        sa.Column("database_id", sa.Integer, key="python_key", primary_key=True),
        sa.Column("version", sa.Integer, primary_key=True),
    )
    sa.Table(
        "child",
        sample,
        sa.Column("source_id", sa.Integer, key="source_key"),
        sa.Column("source_version", sa.Integer),
        sa.ForeignKeyConstraint(
            ["source_key", "source_version"], ["admin.parent.python_key", "admin.parent.version"]
        ),
    )
    dbml = docs.render_dbml(sample)
    assert "admin.child.(source_id, source_version) > admin.parent.(database_id, version)" in dbml
    assert dbml.count("Ref ") == 1
    assert "python_key" not in dbml and "source_key" not in dbml
    sql = docs.render_schema_sql(sample)
    assert (
        "FOREIGN KEY(source_id, source_version) REFERENCES admin.parent (database_id, version)"
        in sql
    )
    tables = docs.validate_metadata(sample, {})
    dot = docs.render_dot(tables, list(tables), "test")
    assert dot.count(" -> t") == 2
    assert 'label="F1.1"' in dot and 'label="F1.2"' in dot


def test_sql_cycles_defer_constraints_without_mutating_metadata():
    sample = sa.MetaData(schema="admin")
    for name, target in [("first", "second"), ("second", "first")]:
        sa.Table(
            name,
            sample,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("other_id", sa.Integer, sa.ForeignKey(f"admin.{target}.id")),
        )
    before = {table.name: str(sa.schema.CreateTable(table)) for table in sample.tables.values()}
    sql = docs.render_schema_sql(sample)
    assert sql.count("ALTER TABLE") == 2
    assert sql.count("FOREIGN KEY") == 2
    assert sql.index("ALTER TABLE") > sql.rindex("CREATE TABLE")
    assert parse_sql(sql)
    assert docs.render_schema_sql(sample) == sql
    assert {
        table.name: str(sa.schema.CreateTable(table)) for table in sample.tables.values()
    } == before


def test_schema_filter_and_invalid_fk_targets():
    sample = sa.MetaData()
    sa.Table("local", sample, sa.Column("id", sa.Integer, primary_key=True), schema="admin")
    sa.Table("excluded", sample, sa.Column("id", sa.Integer), schema="other")
    assert "excluded" not in docs.render_dbml(sample)
    assert "excluded" not in docs.render_schema_sql(sample)
    sa.Table(
        "invalid",
        sample,
        sa.Column("id", sa.Integer, sa.ForeignKey("other.excluded.id")),
        schema="admin",
    )
    for render in (docs.render_dbml, docs.render_schema_sql):
        with pytest.raises(docs.DocumentationError, match="outside admin"):
            render(sample)


@pytest.mark.parametrize("target", ["admin.missing.id", "admin.target.missing"])
def test_unresolved_foreign_keys_fail(target):
    sample = sa.MetaData(schema="admin")
    sa.Table("target", sample, sa.Column("id", sa.Integer))
    sa.Table("invalid", sample, sa.Column("id", sa.Integer, sa.ForeignKey(target)))
    with pytest.raises(docs.DocumentationError, match="Unresolved foreign key"):
        docs.validate_metadata(sample, {})


def test_groups_and_heads_are_validated(monkeypatch):
    with pytest.raises(docs.DocumentationError, match="missing tables"):
        docs.validate_metadata(metadata, {"bad": ("missing",)})
    monkeypatch.setattr(docs, "run_tool", lambda command: "")
    for heads in ([], ["one", "two"]):
        monkeypatch.setattr(docs.ScriptDirectory, "get_heads", lambda self, heads=heads: heads)
        with pytest.raises(docs.DocumentationError, match="exactly one Alembic head"):
            docs.validate_head()


def test_dot_composite_keys_self_reference_and_escaping():
    tables = docs.validate_metadata(metadata, docs.DIAGRAM_GROUPS)
    dot = docs.render_dot(tables, list(tables), "full")
    assert "PK2, FK" in dot
    assert "NOT NULL" in dot and "TIMESTAMP WITH TIME ZONE" in dot
    assert "notification_delivery.retry_of_delivery_id -> admin.notification_delivery.id" in dot
    assert dot.count(" -> t") == sum(len(table.foreign_keys) for table in tables.values())
    sample = sa.MetaData(schema="admin")
    sa.Table('a<&"', sample, sa.Column("x<&", sa.Text))
    tables = docs.validate_metadata(sample, {})
    escaped = docs.render_dot(tables, list(tables), "quoted")
    assert "a&lt;&amp;&quot;" in escaped
    assert "x&lt;&amp;" in escaped


def test_tool_environment_excludes_secrets_and_propagates_failure(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "must-not-be-inherited")
    monkeypatch.setenv("ADMIN_MIGRATION_DATABASE_URL", "must-not-be-inherited")
    monkeypatch.setenv("PRIVATE_SECRET", "must-not-be-inherited")
    environment = docs.subprocess_environment()
    assert "DATABASE_URL" not in environment
    assert "PRIVATE_SECRET" not in environment
    assert environment["ADMIN_MIGRATION_DATABASE_URL"] == docs.DUMMY_URL
    with pytest.raises(docs.DocumentationError, match="exit 7"):
        docs.run_tool([sys.executable, "-c", "import sys; print('diagnostic'); sys.exit(7)"])
    assert "diagnostic" in capsys.readouterr().out


def test_missing_graphviz_is_actionable(monkeypatch, capsys):
    monkeypatch.setattr(docs.shutil, "which", lambda command: None)
    assert docs.main([]) == 1
    assert "sudo apt install graphviz" in capsys.readouterr().err


def test_failed_migration_keeps_previous_outputs(tmp_path, monkeypatch):
    target = tmp_path / "admin-schema.sql"
    target.write_text("previous output")
    monkeypatch.setattr(docs.shutil, "which", lambda command: "/unused/dot")
    monkeypatch.setattr(docs, "validate_head", lambda: "test-head")

    def fail(command):
        assert command[-3:] == ["upgrade", "head", "--sql"]
        raise docs.DocumentationError("migration failed")

    monkeypatch.setattr(docs, "run_tool", fail)
    with pytest.raises(docs.DocumentationError, match="migration failed"):
        docs.generate(tmp_path)
    assert target.read_text() == "previous output"
    assert list(tmp_path.iterdir()) == [target]


def test_text_artifacts_are_deterministic_across_processes():
    command = [
        sys.executable,
        "-c",
        (
            "from app.admin_tables import metadata; "
            "from scripts.generate_database_docs import render_schema_sql, render_dbml; "
            "print(render_schema_sql(metadata)); print(render_dbml(metadata))"
        ),
    ]
    outputs = [
        subprocess.check_output(
            command,
            cwd=docs.BACKEND_ROOT,
            env={**docs.subprocess_environment(), "PYTHONHASHSEED": seed},
        )
        for seed in ("1", "42")
    ]
    assert outputs[0] == outputs[1]


def test_generator_creates_all_artifacts_offline(tmp_path):
    if not shutil.which("dot"):
        pytest.skip("Graphviz is required for the rendering smoke test")
    docs.generate(tmp_path)
    expected = {"admin-migrations.sql", "admin-schema.sql", "admin-schema.dbml"} | {
        f"admin-er-{group}.{extension}"
        for group in ("full", *docs.DIAGRAM_GROUPS)
        for extension in ("dot", "svg", "pdf")
    }
    assert {path.name for path in tmp_path.iterdir()} == expected
    assert all(path.stat().st_size for path in tmp_path.iterdir())
    assert "ALTER TABLE" in (tmp_path / "admin-migrations.sql").read_text()
    assert "ALTER TABLE" not in (tmp_path / "admin-schema.sql").read_text()


@pytest.mark.parametrize("migration_flag", ["--skip-migrations", "--skip-ddl"])
def test_cli_selection_and_skip_options(tmp_path, migration_flag):
    if not shutil.which("dot"):
        pytest.skip("Graphviz is required for the rendering smoke test")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(docs.__file__)),
            "--output-dir",
            str(tmp_path),
            "--only",
            "auth",
            migration_flag,
            "--skip-schema-sql",
            "--skip-dbml",
            "--skip-pdf",
        ],
        cwd=tmp_path,
        env=docs.subprocess_environment(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert {path.name for path in tmp_path.iterdir()} == {"admin-er-auth.dot", "admin-er-auth.svg"}
