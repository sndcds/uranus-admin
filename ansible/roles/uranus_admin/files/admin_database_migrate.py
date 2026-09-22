"""Run only the selected release's Alembic code as its dedicated migration identity."""

import asyncio
import hashlib
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
from app.admin_upgrade_contracts import (  # noqa: E402
    ADMIN_UPGRADE_CONTRACTS,
    ADMIN_UPGRADE_TARGET,
)
from app.auth.diagnostics import OPERATOR_GRANTS  # noqa: E402
from app.storage_preflight import RUNTIME_GRANTS  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


async def identity(conn, expected_head=None):
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


def upgrade_contracts(runtime_grants):
    result = {}
    for origin, contract in ADMIN_UPGRADE_CONTRACTS.items():
        excluded = set(contract["target_only_tables"])
        result[origin] = {
            "schema_fingerprint": contract["schema_fingerprint"],
            "runtime_grants": {
                name: grants for name, grants in runtime_grants.items() if name not in excluded
            },
        }
    return result


async def apply_grants(conn, runtime_grants):
    await conn.execute(
        text(
            "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA admin "
            "FROM PUBLIC,admin_user,admin_auth_operator"
        )
    )
    await conn.execute(
        text("REVOKE ALL PRIVILEGES ON SCHEMA admin FROM PUBLIC,admin_user,admin_auth_operator")
    )
    await conn.execute(text("GRANT USAGE ON SCHEMA admin TO admin_user,admin_auth_operator"))
    for role, grants in (
        ("admin_user", runtime_grants),
        ("admin_auth_operator", {k: list(v) for k, v in OPERATOR_GRANTS.items()}),
    ):
        for name, privileges in grants.items():
            if not name.replace("_", "").isalnum():
                raise ValueError("invalid_grant_contract")
            await conn.execute(text(f'GRANT {",".join(privileges)} ON admin."{name}" TO {role}'))


async def schema_inventory(conn):
    tables = (
        (
            await conn.execute(
                text("""SELECT c.relname FROM pg_class c JOIN pg_namespace n
            ON n.oid=c.relnamespace WHERE n.nspname='admin'
            AND c.relkind IN ('r','p','v','m','f') ORDER BY c.relname""")
            )
        )
        .scalars()
        .all()
    )
    indexes = (
        (
            await conn.execute(
                text("""SELECT c.relname FROM pg_class c JOIN pg_namespace n
            ON n.oid=c.relnamespace WHERE n.nspname='admin' AND c.relkind='i'
            ORDER BY c.relname""")
            )
        )
        .scalars()
        .all()
    )
    column_rows = (
        await conn.execute(
            text("""SELECT c.relname,a.attname FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE n.nspname='admin' AND c.relkind='r'
            AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attname""")
        )
    ).all()
    columns = {}
    for table_name, column_name in column_rows:
        columns.setdefault(table_name, []).append(column_name)
    return tables, indexes, columns


def schema_fingerprint(tables, indexes, columns):
    value = json.dumps(
        {"tables": tables, "indexes": indexes, "columns": columns},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(value).hexdigest()


async def verify_grants(conn, runtime_grants):
    privileges = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
    unexpected_acl = (
        await conn.execute(
            text("""SELECT EXISTS(
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace,
                LATERAL aclexplode(c.relacl) acl
                WHERE n.nspname='admin' AND acl.grantee NOT IN (
                    SELECT oid FROM pg_roles WHERE rolname IN
                    ('admin_migrator','admin_user','admin_auth_operator'))
                UNION ALL
                SELECT 1 FROM pg_namespace n,
                LATERAL aclexplode(n.nspacl) acl
                WHERE n.nspname='admin' AND acl.grantee NOT IN (
                    SELECT oid FROM pg_roles WHERE rolname IN
                    ('admin_migrator','admin_user','admin_auth_operator'))
                UNION ALL
                SELECT 1 FROM pg_attribute a
                JOIN pg_class c ON c.oid=a.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace,
                LATERAL aclexplode(a.attacl) acl
                WHERE n.nspname='admin')""")
        )
    ).scalar_one()
    if unexpected_acl:
        raise ValueError("source_grant_contract_mismatch")
    for role, expected in (
        ("admin_user", runtime_grants),
        ("admin_auth_operator", {k: list(v) for k, v in OPERATOR_GRANTS.items()}),
    ):
        schema_rights = (
            await conn.execute(
                text("""SELECT has_schema_privilege(:role,'admin','USAGE'),
                has_schema_privilege(:role,'admin','CREATE')"""),
                {"role": role},
            )
        ).one()
        if tuple(schema_rights) != (True, False):
            raise ValueError("source_grant_contract_mismatch")
        explicit_column_grants = (
            await conn.execute(
                text("""SELECT EXISTS(SELECT 1 FROM pg_attribute a
                JOIN pg_class c ON c.oid=a.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace,
                LATERAL aclexplode(a.attacl) acl
                WHERE n.nspname='admin' AND acl.grantee=(
                    SELECT oid FROM pg_roles WHERE rolname=:role))"""),
                {"role": role},
            )
        ).scalar_one()
        if explicit_column_grants:
            raise ValueError("source_grant_contract_mismatch")
        for table_name in runtime_grants:
            actual = {
                privilege
                for privilege in privileges
                if (
                    await conn.execute(
                        text("SELECT has_table_privilege(:role,:table,:privilege)"),
                        {
                            "role": role,
                            "table": f"admin.{table_name}",
                            "privilege": privilege,
                        },
                    )
                ).scalar_one()
            }
            grant_options = False
            for privilege in privileges:
                if (
                    await conn.execute(
                        text("SELECT has_table_privilege(:role,:table,:privilege)"),
                        {
                            "role": role,
                            "table": f"admin.{table_name}",
                            "privilege": privilege + " WITH GRANT OPTION",
                        },
                    )
                ).scalar_one():
                    grant_options = True
                    break
            if actual != set(expected.get(table_name, [])) or grant_options:
                raise ValueError("source_grant_contract_mismatch")
    public_rights = (
        await conn.execute(
            text("""SELECT EXISTS(SELECT 1 FROM pg_namespace n,
            LATERAL aclexplode(n.nspacl) acl WHERE n.nspname='admin'
            AND acl.grantee=0 AND acl.privilege_type IN ('USAGE','CREATE'))""")
        )
    ).scalar_one()
    if public_rights:
        raise ValueError("source_grant_contract_mismatch")


async def verify_origin(conn, manifest):
    if not (await conn.execute(text("SELECT to_regnamespace('admin') IS NOT NULL"))).scalar_one():
        return
    heads = (
        (await conn.execute(text("SELECT version_num FROM admin.alembic_version"))).scalars().all()
    )
    if heads == [manifest["head"]]:
        return
    if len(heads) != 1 or heads[0] not in manifest["admin_upgrade_contracts"]:
        raise ValueError("unsupported_migration_origin")
    contract = manifest["admin_upgrade_contracts"][heads[0]]
    tables, indexes, columns = await schema_inventory(conn)
    if schema_fingerprint(tables, indexes, columns) != contract["schema_fingerprint"]:
        raise ValueError("source_schema_contract_mismatch")
    await verify_grants(conn, contract["runtime_grants"])


async def verify_target(conn, manifest):
    await identity(conn, manifest["head"])
    tables, indexes, columns = await schema_inventory(conn)
    unsafe_objects = (
        await conn.execute(
            text("""SELECT count(*) FROM pg_class c JOIN pg_namespace n
            ON n.oid=c.relnamespace WHERE n.nspname='admin' AND
            (c.relkind NOT IN ('r','i') OR c.relowner<>(SELECT oid FROM pg_roles
            WHERE rolname='admin_migrator') OR c.relrowsecurity OR c.relforcerowsecurity)""")
        )
    ).scalar_one()
    if (
        tables != sorted(manifest["runtime_grants"])
        or indexes != sorted(manifest["admin_indexes"])
        or columns != manifest["admin_columns"]
        or unsafe_objects
    ):
        raise ValueError("post_migration_contract_mismatch")
    await verify_grants(conn, manifest["runtime_grants"])


def run_alembic(sync_connection, config, operation):
    config.attributes["connection"] = sync_connection
    operation(config)


async def migrate(manifest, config):
    engine = create_async_engine(
        os.environ["ADMIN_MIGRATION_DATABASE_URL"],
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"timeout": 10, "command_timeout": 60},
    )
    try:
        async with engine.begin() as conn:
            await identity(conn)
            await verify_origin(conn, manifest)
            await conn.run_sync(run_alembic, config, lambda c: command.upgrade(c, "head"))
            await apply_grants(conn, manifest["runtime_grants"])
            await conn.run_sync(run_alembic, config, command.current)
            await conn.run_sync(run_alembic, config, command.check)
            await verify_target(conn, manifest)
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
    if (
        ADMIN_UPGRADE_TARGET != manifest["head"]
        or upgrade_contracts(manifest["runtime_grants"]) != manifest["admin_upgrade_contracts"]
    ):
        raise ValueError("release_upgrade_registry_mismatch")
    ancestors = set()
    revision = scripts.get_revision(manifest["head"])
    while revision is not None:
        ancestors.add(revision.revision)
        revision = scripts.get_revision(revision.down_revision)
    if not set(manifest["admin_upgrade_contracts"]) <= ancestors:
        raise ValueError("release_upgrade_path_mismatch")
    columns = {
        table.name: sorted(column.name for column in table.columns)
        for table in metadata.tables.values()
    }
    columns["alembic_version"] = ["version_num"]
    if columns != manifest["admin_columns"]:
        raise ValueError("release_column_registry_mismatch")
    asyncio.run(migrate(manifest, config))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No raw exception, DSN, SQL, password or traceback can enter Ansible output.
        raise SystemExit(1) from None
