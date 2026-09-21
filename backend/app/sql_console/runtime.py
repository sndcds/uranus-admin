"""No source/admin engine, pooling, commit, or fallback in this executor."""

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

import asyncpg  # type: ignore[import-untyped]
from sqlalchemy.engine import make_url

from app.config import Settings
from app.sql_console.policy import POLICY, ConsoleError, validate_sql
from app.sql_console.protocol import Execute
from app.sql_console.serialization import BATCH_BYTES, RESULT_BYTES, cell, encode

DEADLINE_SECONDS = 8
BATCH_ROWS = 25
Send = Callable[[dict[str, Any]], Awaitable[None]]


class ConsoleConnection(asyncpg.Connection):  # type: ignore[misc]
    """Keep asyncpg type discovery, without its privileged set_config wrapper.

    asyncpg 0.31 introspection toggles JIT via set_config even when JIT is off.
    The console must never receive that EXECUTE grant. Set jit=off at connection
    startup and run the same catalog-only introspection through the pinned driver.
    Real enum/array/PostGIS tests guard this deliberately narrow private API use.
    """

    async def _introspect_types(self, typeoids: Any, timeout: Any) -> Any:  # noqa: ASYNC109
        return await self._Connection__execute(
            self._intro_query, (list(typeoids),), 0, timeout, ignore_custom_codec=True
        )


async def assert_identity(connection: Any) -> None:
    row = await connection.fetchrow("""
        SELECT current_user AS identity, session_user AS session_identity,
            current_setting('search_path') AS path,
            has_database_privilege(current_user,current_database(),'TEMP') AS temp,
            has_database_privilege(current_user,current_database(),'CREATE') AS create_db,
            EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=current_user
                AND (rolsuper OR rolcreatedb OR rolcreaterole
                    OR rolreplication OR rolbypassrls OR rolinherit))
                AS powerful,
            EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members
                WHERE member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)
                   OR roleid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user))
                AS membership,
            EXISTS (SELECT 1 FROM pg_catalog.pg_namespace
                WHERE has_schema_privilege(current_user,oid,'CREATE')) AS create_schema,
            EXISTS (SELECT 1 FROM pg_catalog.pg_shdepend
                WHERE refclassid='pg_catalog.pg_authid'::regclass AND deptype='o'
                  AND refobjid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user))
                AS owned_objects,
            NOT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n
                JOIN pg_catalog.pg_database d ON d.datname=current_database()
                WHERE n.nspname='uranus' AND n.nspowner=d.datdba
                  AND has_schema_privilege(current_user,n.oid,'USAGE')) AS unsafe_source_schema,
            EXISTS (SELECT 1 FROM pg_catalog.pg_namespace
                WHERE nspname='admin' AND has_schema_privilege(current_user,oid,'USAGE'))
                AS admin_access,
            EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_catalog.pg_database d ON d.datname=current_database()
                WHERE n.nspname='uranus' AND c.relkind IN ('r','v','m','p','f')
                AND (c.relowner<>d.datdba OR c.relkind NOT IN ('r','p')
                    OR c.relrowsecurity OR c.relforcerowsecurity
                    OR NOT has_table_privilege(current_user,c.oid,'SELECT')
                    OR has_table_privilege(current_user,c.oid,
                        'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,SELECT WITH GRANT OPTION')
                    OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE,REFERENCES')
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_attribute att,
                        LATERAL pg_catalog.aclexplode(att.attacl) a WHERE att.attrelid=c.oid
                        AND a.grantee IN (0,(SELECT oid FROM pg_catalog.pg_roles
                            WHERE rolname=current_user)) AND a.is_grantable)
                    OR EXISTS (SELECT 1 FROM pg_catalog.aclexplode(c.relacl) a
                        WHERE a.grantee IN (0,(SELECT oid FROM pg_catalog.pg_roles
                            WHERE rolname=current_user))
                        AND (a.privilege_type<>'SELECT' OR a.is_grantable)))) AS unsafe_tables,
            NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='uranus' AND c.relkind IN ('r','p')) AS missing_tables,
            EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='admin' AND c.relkind IN ('r','v','m','p','f')
                AND (has_table_privilege(current_user,c.oid,
                        'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                    OR has_any_column_privilege(current_user,c.oid,
                        'SELECT,INSERT,UPDATE,REFERENCES')))
                AS admin_table_access,
            EXISTS (SELECT 1 FROM pg_catalog.pg_class WHERE relkind='S'
                AND has_sequence_privilege(current_user,oid,'USAGE,SELECT,UPDATE'))
                AS sequence_access,
            NOT EXISTS (SELECT 1 FROM pg_catalog.pg_default_acl d,
                LATERAL pg_catalog.aclexplode(d.defaclacl) a
                WHERE d.defaclrole=(SELECT datdba FROM pg_catalog.pg_database
                    WHERE datname=current_database())
                  AND d.defaclnamespace=pg_catalog.to_regnamespace('uranus') AND d.defaclobjtype='r'
                  AND a.grantee=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)
                  AND a.privilege_type='SELECT' AND NOT a.is_grantable) AS missing_defaults,
            EXISTS (SELECT 1 FROM pg_catalog.pg_default_acl d,
                LATERAL pg_catalog.aclexplode(d.defaclacl) a
                WHERE (d.defaclrole=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)
                  OR a.grantee IN (0,(SELECT oid FROM pg_catalog.pg_roles
                    WHERE rolname=current_user)))
                AND NOT (d.defaclrole=(SELECT datdba FROM pg_catalog.pg_database
                    WHERE datname=current_database())
                  AND d.defaclnamespace=pg_catalog.to_regnamespace('uranus') AND d.defaclobjtype='r'
                  AND a.grantee=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)
                  AND a.privilege_type='SELECT' AND NOT a.is_grantable)) AS unsafe_defaults
    """)
    if (
        row["identity"] != "uranus_console_reader"
        or row["session_identity"] != "uranus_console_reader"
        or row["path"] != "pg_catalog, uranus"
        or any(
            value
            for key, value in row.items()
            if key not in {"identity", "session_identity", "path"}
        )
    ):
        raise ConsoleError("unsafe_identity")
    unsafe = await connection.fetchval(
        """
        SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
        WHERE (p.prosecdef OR lower(p.proname)=ANY($1::text[])
            OR format('%I.%I(%s)', n.nspname, p.proname, oidvectortypes(p.proargtypes))
                = ANY($3::text[])
            OR EXISTS (SELECT 1 FROM unnest($2::text[]) AS prefix
                WHERE starts_with(lower(p.proname),prefix)))
        AND has_function_privilege(current_user,p.oid,'EXECUTE'))
    """,
        POLICY["denied_names"],
        POLICY["prefixes"],
        POLICY["signatures"],
    )
    if unsafe:
        raise ConsoleError("unsafe_identity")


class ConsoleRuntime:
    """Single API process owns the global fail-fast slots (deployment uses one worker)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tasks: set[asyncio.Task[None]] = set()
        self.closed = False

    def start(
        self,
        message: Execute,
        actor: str,
        send: Send,
        acknowledge: Callable[[int], Awaitable[None]],
    ) -> asyncio.Task[None]:
        if self.closed or len(self.tasks) >= self.settings.sql_console_max_connections:
            raise ConsoleError("busy")
        task = asyncio.create_task(
            self.execute(message, actor, send, acknowledge, submitted_at=perf_counter())
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def close(self) -> None:
        self.closed = True
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def execute(
        self,
        message: Execute,
        actor: str,
        send: Send,
        acknowledge: Callable[[int], Awaitable[None]],
        *,
        submitted_at: float | None = None,
    ) -> None:
        started = submitted_at if submitted_at is not None else perf_counter()
        connection = None
        transaction = None
        count, size, batch_id = 0, 0, 0
        status = "error"
        truncated = False
        terminal: dict[str, Any] = {"type": "error", "code": "unavailable"}

        async def emit(payload: dict[str, Any]) -> None:
            await send({"v": 1, "request_id": str(message.request_id), **payload})

        try:
            async with asyncio.timeout(max(0, DEADLINE_SECONDS - (perf_counter() - started))):
                secret = self.settings.sql_console_database_url
                if secret is None:
                    raise ConsoleError("unavailable")
                url = make_url(secret.get_secret_value())
                if url.username != "uranus_console_reader" or url.drivername not in {
                    "postgresql",
                    "postgresql+asyncpg",
                }:
                    raise ConsoleError("unsafe_identity")
                validate_sql(message.sql)
                await emit({"type": "started"})
                connection = await asyncpg.connect(
                    secret.get_secret_value().replace("postgresql+asyncpg://", "postgresql://", 1),
                    timeout=3,
                    statement_cache_size=0,
                    connection_class=ConsoleConnection,
                    server_settings={
                        "application_name": "uranus-admin-sql-console",
                        "timezone": "UTC",
                        "jit": "off",
                    },
                )
                transaction = connection.transaction(isolation="repeatable_read", readonly=True)
                await transaction.start()
                await connection.execute("SET LOCAL statement_timeout = '5s'")
                await connection.execute("SET LOCAL lock_timeout = '1s'")
                await connection.execute("SET LOCAL idle_in_transaction_session_timeout = '8s'")
                await assert_identity(connection)
                # A fixed named protocol statement survives asyncpg's anonymous
                # type-introspection statements; this connection runs one query.
                statement = await connection.prepare(message.sql, name="console_query")
                attributes = statement.get_attributes()
                if len(attributes) > 128:
                    raise ConsoleError("result_too_large")
                columns: list[str] = []
                for index, attribute in enumerate(attributes):
                    name = attribute.name
                    if name in columns:
                        name = f"{name} [{index + 1}]"
                    while name in columns:
                        name += "_"
                    columns.append(name)
                await emit({"type": "columns", "columns": columns})
                size = len(encode(columns).encode())
                cursor = await statement.cursor()
                batch: list[dict[str, object]] = []
                batch_size = 0

                async def flush() -> None:
                    nonlocal batch_id, batch, batch_size
                    if not batch:
                        return
                    batch_id += 1
                    await emit({"type": "rows", "batch": batch_id, "rows": batch})
                    # Exactly one outstanding batch, including at the proxy/browser.
                    await acknowledge(batch_id)
                    batch, batch_size = [], 0

                # Fetch one DB row at a time: even 128 maximally sized cells cannot
                # multiply through a 25-row prefetch buffer. Wire batches remain bounded.
                for _ in range(message.row_limit + 1):
                    records = await cursor.fetch(1)
                    if not records:
                        break
                    if count == message.row_limit:
                        truncated = True
                        break
                    row = {key: cell(value) for key, value in zip(columns, records[0], strict=True)}
                    row_size = len(encode(row).encode()) + 1
                    if row_size > BATCH_BYTES or size + row_size + 256 > RESULT_BYTES:
                        truncated = True
                        break
                    if batch and (len(batch) == BATCH_ROWS or batch_size + row_size > BATCH_BYTES):
                        await flush()
                    batch.append(row)
                    batch_size += row_size
                    size += row_size + 128  # Conservative allowance for framing/metadata.
                    count += 1
                await flush()
                status = "completed"
                terminal = {"type": "complete", "row_count": count, "truncated": truncated}
        except asyncio.CancelledError:
            status = "cancelled"
            terminal = {"type": "cancelled"}
        except Exception as exc:
            code = getattr(exc, "sqlstate", None)
            status = (
                "timeout"
                if isinstance(exc, TimeoutError) or code in {"57014", "55P03"}
                else "error"
            )
            category = (
                exc.code
                if isinstance(exc, ConsoleError)
                else "timeout"
                if status == "timeout"
                else "permission_denied"
                if code == "42501"
                else "syntax_error"
                if code and code.startswith("42")
                else "unavailable"
            )
            position = getattr(exc, "position", None)
            terminal = {"type": "error", "code": category}
            if position and str(position).isdigit() and 0 < int(position) <= len(message.sql) + 1:
                terminal["position"] = int(position)
        finally:
            # asyncpg task cancellation sends PostgreSQL CancelRequest. Rollback waits
            # for cancellation completion. Never return this connection to a pool.
            if connection is not None:
                try:
                    async with asyncio.timeout(1):
                        if transaction is not None:
                            await transaction.rollback()
                        await connection.close(timeout=0.5)
                except (Exception, asyncio.CancelledError):
                    connection.terminate()
            duration = round((perf_counter() - started) * 1000, 2)
            logging.getLogger("admin.sql_console").info(
                "sql_console_query",
                extra={
                    "actor_subject": actor,
                    "request_id": str(message.request_id),
                    "duration_ms": duration,
                    "row_count": count,
                    "error_type": status,
                    "query_hash": hashlib.sha256(message.sql.encode(errors="replace")).hexdigest(),
                },
            )
        # A terminal event is emitted only after rollback/close, with no late rows.
        try:
            async with asyncio.timeout(0.5):
                await emit({**terminal, "duration_ms": duration})
        except (Exception, asyncio.CancelledError):
            pass
