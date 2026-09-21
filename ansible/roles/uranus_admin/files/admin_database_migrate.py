"""Run only the selected release's Alembic code as its dedicated migration identity."""

import asyncio
import json
import os
import sys
from pathlib import Path

RELEASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RELEASE / "backend"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from app.admin_tables import metadata  # noqa: E402
from app.auth.diagnostics import OPERATOR_GRANTS  # noqa: E402
from app.storage_preflight import RUNTIME_GRANTS  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


async def identity(expected_head=None):
    engine = create_async_engine(
        os.environ["ADMIN_MIGRATION_DATABASE_URL"],
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"timeout": 10, "command_timeout": 60},
    )
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("""SELECT current_user,session_user,rolsuper,
                rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles
                WHERE rolname=current_user""")
                )
            ).one()
            if tuple(row) != (
                "admin_migrator",
                "admin_migrator",
                False,
                False,
                False,
                False,
                False,
            ):
                raise ValueError("migration_identity_rejected")
            if expected_head is not None:
                heads = (
                    (await conn.execute(text("SELECT version_num FROM admin.alembic_version")))
                    .scalars()
                    .all()
                )
                if heads != [expected_head]:
                    raise ValueError("migration_head_mismatch")
    finally:
        await engine.dispose()


def main():
    manifest = json.loads((RELEASE / "release.json").read_text())
    config = Config(str(RELEASE / "backend/alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    if scripts.get_heads() != [manifest["head"]]:
        raise ValueError("release_migration_tree_mismatch")
    if {k: list(v) for k, v in RUNTIME_GRANTS.items()} != manifest["runtime_grants"]:
        raise ValueError("release_grant_registry_mismatch")
    if {k: list(v) for k, v in OPERATOR_GRANTS.items()} != manifest["operator_grants"]:
        raise ValueError("release_operator_registry_mismatch")
    columns = {
        table.name: sorted(column.name for column in table.columns)
        for table in metadata.tables.values()
    }
    columns["alembic_version"] = ["version_num"]
    if columns != manifest["admin_columns"]:
        raise ValueError("release_column_registry_mismatch")
    asyncio.run(identity())
    command.upgrade(config, "head")
    command.current(config)
    command.check(config)
    asyncio.run(identity(manifest["head"]))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No raw exception, DSN, SQL, password or traceback can enter Ansible output.
        raise SystemExit(1) from None
