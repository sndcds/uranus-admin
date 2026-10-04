"""Recompute reviewed inventories from frozen migrations without a database."""

import io
import runpy
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pglast import ast, parse_sql
from pglast.enums import AlterTableType, ConstrType

from app.admin_upgrade_contracts import ADMIN_UPGRADE_CONTRACTS, ADMIN_UPGRADE_TARGET
from app.storage_preflight import RUNTIME_GRANTS

ROOT = Path(__file__).resolve().parents[2]
AdminDatabase = runpy.run_path(
    str(ROOT / "ansible/roles/uranus_admin/library/uranus_admin_database.py")
)["AdminDatabase"]
packager = runpy.run_path(str(ROOT / "ansible/scripts/package_release.py"))


def migration_inventory(revision, monkeypatch):
    """Read the inventory covered by schema_fingerprint, not a live schema dump.

    Only the DDL forms used by these frozen migrations are supported. Unexpected
    forms fail rather than silently inventing an inventory for a future revision.
    """
    monkeypatch.setenv(
        "ADMIN_MIGRATION_DATABASE_URL", "postgresql+asyncpg://unused@localhost/unused_test"
    )
    output = io.StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=output), revision, sql=True)
    columns, indexes = {}, set()
    for raw in parse_sql(output.getvalue()):
        node = raw.stmt
        if isinstance(node, ast.CreateStmt):
            assert node.relation.schemaname == "admin"
            table = node.relation.relname
            columns[table] = []
            for item in node.tableElts:
                if isinstance(item, ast.ColumnDef):
                    columns[table].append(item.colname)
                    continue
                assert isinstance(item, ast.Constraint)
                if item.contype == ConstrType.CONSTR_PRIMARY:
                    indexes.add(item.conname or f"{table}_pkey")
                elif item.contype == ConstrType.CONSTR_UNIQUE:
                    keys = "_".join(key.sval for key in item.keys)
                    indexes.add(item.conname or f"{table}_{keys}_key")
                else:
                    assert item.contype in (ConstrType.CONSTR_CHECK, ConstrType.CONSTR_FOREIGN)
        elif isinstance(node, ast.IndexStmt):
            assert node.relation.schemaname == "admin"
            indexes.add(node.idxname)
        elif isinstance(node, ast.AlterTableStmt):
            assert node.relation.schemaname == "admin"
            for alteration in node.cmds:
                if alteration.subtype == AlterTableType.AT_AddColumn:
                    columns[node.relation.relname].append(alteration.def_.colname)
                elif alteration.subtype == AlterTableType.AT_AddConstraint:
                    assert alteration.def_.contype in (
                        ConstrType.CONSTR_CHECK,
                        ConstrType.CONSTR_FOREIGN,
                    )
                else:
                    assert alteration.subtype == AlterTableType.AT_DropConstraint
                    assert alteration.name in (
                        "finding_status",
                        "check_run_status",
                        "research_area_region",
                        "research_area_type",
                    )
        else:
            assert isinstance(
                node, (ast.TransactionStmt, ast.DoStmt, ast.InsertStmt, ast.UpdateStmt)
            )
    return sorted(columns), sorted(indexes), {k: sorted(v) for k, v in columns.items()}


@pytest.mark.parametrize("origin", ADMIN_UPGRADE_CONTRACTS)
def test_reviewed_origin_fingerprint_and_target_only_tables(origin, monkeypatch):
    tables, indexes, columns = migration_inventory(origin, monkeypatch)
    contract = ADMIN_UPGRADE_CONTRACTS[origin]
    assert (
        AdminDatabase.schema_fingerprint(tables, indexes, columns) == contract["schema_fingerprint"]
    )
    target_tables, _, _ = migration_inventory(ADMIN_UPGRADE_TARGET, monkeypatch)
    assert set(contract["target_only_tables"]) == set(target_tables) - set(tables)
    assert set(target_tables) == set(RUNTIME_GRANTS)


def test_0018_inventory_matches_0019_release_without_new_grants(monkeypatch):
    origin = migration_inventory("0018", monkeypatch)
    assert origin == migration_inventory("0019", monkeypatch)
    tables, indexes, columns = origin
    source = (ROOT / "backend/app/admin_tables.py").read_bytes()
    assert indexes == packager["admin_indexes"](source)
    assert columns == packager["admin_columns"](source)
    assert set(tables) == set(RUNTIME_GRANTS)
