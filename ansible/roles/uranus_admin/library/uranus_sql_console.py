#!/usr/bin/python
"""Plan/reconcile only the reviewed console boundary; never mutate source tables.

Production entrypoint is fixed to local postgres/oklab. Plan and verify use actual
READ ONLY transactions. Provision repeats inspection and verifies before commit.
No catalog exception, DSN, password or SQL is returned to Ansible.
"""

import base64
import hashlib
import hmac
import re
import secrets
from urllib.parse import unquote, urlsplit

import psycopg2
from psycopg2 import sql

OWNER = "uranus_console_owner"
READER = "uranus_console_reader"
SCHEMA = "uranus_console"
SEARCH_PATH = "pg_catalog, uranus_console"
VIEWS = {"event_date", "event", "venue", "organization"}
DANGEROUS = [
    "lo_get",
    "lo_open",
    "loread",
    "lo_close",
    "lo_lseek",
    "lo_lseek64",
    "lo_tell",
    "lo_tell64",
    "lo_create",
    "lo_creat",
    "lo_from_bytea",
    "lo_put",
    "lo_unlink",
    "lo_import",
    "lo_export",
    "lowrite",
    "lo_truncate",
    "lo_truncate64",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_write_file",
    "pg_file_write",
    "pg_file_rename",
    "pg_file_unlink",
    "pg_logdir_ls",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "pg_promote",
    "pg_signal_backend",
]


def require(condition, code):
    if not condition:
        raise ValueError(code)


def console_password(dsn, database="oklab"):
    try:
        u = urlsplit(dsn)
        password = unquote(u.password or "")
        valid = (
            u.scheme == "postgresql+asyncpg"
            and unquote(u.username or "") == READER
            and u.hostname in {"localhost", "127.0.0.1", "::1"}
            and u.port in {None, 5432}
            and u.path == "/" + database
            and not u.query
            and not u.fragment
            and len(password) >= 24
            and password.isascii()
            and all(32 < ord(c) < 127 for c in password)
        )
    except (ValueError, TypeError):
        valid = False
    require(valid, "missing_or_invalid_sql_console_dsn")
    return password


def scram(password, salt=None, iterations=4096):
    salt = salt or secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    stored = hashlib.sha256(hmac.digest(salted, b"Client Key", "sha256")).digest()
    server = hmac.digest(salted, b"Server Key", "sha256")
    salt64, stored64, server64 = (base64.b64encode(b).decode() for b in (salt, stored, server))
    return f"SCRAM-SHA-256${iterations}:{salt64}${stored64}:{server64}"


def password_matches(password, verifier):
    if not verifier or not verifier.startswith("SCRAM-SHA-256$"):
        return False
    try:
        _, parameters, _ = verifier.split("$")
        count, salt = parameters.split(":")
        if not 4096 <= int(count) <= 1000000:
            return False
        return hmac.compare_digest(verifier, scram(password, base64.b64decode(salt), int(count)))
    except (ValueError, TypeError):
        return False


def validate_contract(contract):
    require(
        contract["version"] == 2
        and contract["uranus_sha"] == "7ae87ea7fe39692c1f3dcc3a5621f6c9e7bb574d"
        and contract["schema"] == SCHEMA
        and contract["owner_role"] == OWNER
        and contract["reader_role"] == READER
        and contract["search_path"] == SEARCH_PATH
        and set(contract["views"]) == VIEWS,
        "unsupported_sql_console_contract",
    )
    temp_roles = contract["database_temp_roles"]
    require(
        isinstance(temp_roles, list)
        and bool(temp_roles)
        and all(isinstance(r, str) and re.fullmatch(r"[a-z_]+", r) for r in temp_roles)
        and len(temp_roles) == len(set(temp_roles))
        and not {OWNER, READER, "public"}.intersection(temp_roles),
        "invalid_database_temp_roles",
    )
    for name, view in contract["views"].items():
        require(view["source_table"] == "uranus." + name, "invalid_source_table")
        require(view["reader_grants"] == ["SELECT"], "invalid_reader_grants")
        columns = [c["name"] for c in view["columns"]]
        require(columns == view["owner_select_columns"], "invalid_owner_grants")
        require(len(columns) == len(set(columns)), "duplicate_contract_column")
        require(all(re.fullmatch(r"[a-z_]+", c) for c in columns), "invalid_identifier")


def definition(name, view):
    # Only fixed reviewed identifiers. No expressions/functions or operator input.
    return (
        "SELECT "
        + ", ".join(name + "." + c["name"] for c in view["columns"])
        + " FROM uranus."
        + name
    )


def normalized(value):
    return " ".join(value.rstrip("; \n").split())


class Boundary:
    def __init__(self, connection, contract):
        validate_contract(contract)
        self.conn, self.contract = connection, contract
        self.actions, self.blockers = [], []

    def rows(self, query, args=()):
        with self.conn.cursor() as cursor:
            cursor.execute(query, args)
            return cursor.fetchall()

    def execute(self, query, args=()):
        with self.conn.cursor() as cursor:
            cursor.execute(query, args)

    def issue(self, code):
        self.blockers.append(code)

    def action(self, label, query, args=()):
        self.actions.append((label, query, args))

    def inspect(self, password=None):
        self.actions, self.blockers = [], []
        if self.conn.server_version // 10000 not in (16, 17):
            self.issue("unsupported_postgresql_major")
        db_oid = self.inspect_temp()
        roles = self.rows(
            """
            SELECT oid,rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,
                   rolreplication,rolbypassrls,rolinherit,rolconfig,rolvaliduntil
            FROM pg_roles WHERE rolname IN (%s,%s)
        """,
            (OWNER, READER),
        )
        ids = {row[1]: row[0] for row in roles}
        for row in roles:
            oid, name, login, *rest = row
            if login != (name == READER) or any(rest[:5]) or rest[6] or rest[7]:
                self.issue("unsafe_role_attributes_or_settings:" + name)
            if rest[5]:
                self.issue("unsafe_role_inherit:" + name)
            if self.rows("SELECT 1 FROM pg_auth_members WHERE member=%s OR roleid=%s", (oid, oid)):
                self.issue("role_membership:" + name)
            if self.rows("SELECT 1 FROM pg_database WHERE datdba=%s", (oid,)):
                self.issue("database_owned:" + name)
        for name in (OWNER, READER):
            if name not in ids:
                self.action(
                    "would create role " + name,
                    sql.SQL(
                        "CREATE ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "NOREPLICATION NOBYPASSRLS NOINHERIT"
                    ).format(
                        sql.Identifier(name), sql.SQL("LOGIN" if name == READER else "NOLOGIN")
                    ),
                )
        if READER in ids and password is not None:
            verifier = self.rows("SELECT rolpassword FROM pg_authid WHERE rolname=%s", (READER,))[
                0
            ][0]
            if not password_matches(password, verifier):
                self.issue("console_password_mismatch_no_automatic_rotation")
        self.ids = ids
        for name in (OWNER, READER):
            oid = ids.get(name, 0)
            for privilege, grantable, grantee in self.rows(
                """
                SELECT privilege_type,is_grantable,a.grantee FROM pg_database,
                  LATERAL aclexplode(coalesce(datacl,acldefault('d',datdba))) a
                WHERE oid=%s AND a.grantee IN (0,%s)
            """,
                (db_oid, oid),
            ):
                # PUBLIC TEMP is handled exclusively by the audited atomic plan.
                # Direct console TEMP and every other shared privilege still fail.
                if privilege == "TEMPORARY" and grantee == 0 and self.temp_reconcile["allowed"]:
                    continue
                if privilege != "CONNECT" or grantable:
                    self.issue("database_privilege:" + name + ":" + privilege)
            if (
                oid
                and self.rows("SELECT has_database_privilege(%s,%s,'CREATE')", (oid, db_oid))[0][0]
            ):
                self.issue("effective_database_create:" + name)
            if name == READER and (
                not oid
                or not self.rows(
                    """SELECT 1 FROM pg_database, LATERAL aclexplode(datacl) a
                WHERE oid=%s AND a.grantee=%s AND a.privilege_type='CONNECT'""",
                    (db_oid, oid),
                )
            ):
                self.action(
                    "would reconcile CONNECT " + name,
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(self.conn.info.dbname), sql.Identifier(name)
                    ),
                )

        schemas = self.rows("SELECT oid,nspname,nspowner FROM pg_namespace")
        for ns_oid, ns, owner in schemas:
            if ns == SCHEMA and self.rows(
                """SELECT 1 FROM pg_namespace, LATERAL aclexplode(nspacl) a
                WHERE oid=%s AND a.grantee NOT IN (%s,%s)""",
                (ns_oid, ids.get(OWNER, -1), ids.get(READER, -1)),
            ):
                self.issue("unexpected_console_schema_grantee")
            if owner in ids.values() and not (ns == SCHEMA and owner == ids.get(OWNER)):
                self.issue("unexpected_schema_owner:" + ns)
            for role in (OWNER, READER):
                oid = ids.get(role, 0)
                acl = self.rows(
                    """SELECT privilege_type,is_grantable FROM pg_namespace,
                    LATERAL aclexplode(coalesce(nspacl,acldefault('n',nspowner))) a
                    WHERE oid=%s AND a.grantee IN (0,%s)""",
                    (ns_oid, oid),
                )
                for privilege, grantable in acl:
                    if ns == SCHEMA and role == OWNER and owner == oid:
                        continue  # Ownership inherently includes grant options here only.
                    if (
                        privilege == "CREATE"
                        or grantable
                        or (
                            privilege == "USAGE"
                            and ns in {"uranus", "admin"}
                            and not (role == OWNER and ns == "uranus")
                        )
                    ):
                        self.issue("schema_privilege:" + role + ":" + ns)
        console = next((s for s in schemas if s[1] == SCHEMA), None)
        if console is None:
            self.action(
                "would create schema " + SCHEMA,
                sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                    sql.Identifier(SCHEMA), sql.Identifier(OWNER)
                ),
            )
        elif console[2] != ids.get(OWNER):
            self.issue("sql_console_schema_owner")
        for role, ns in ((OWNER, "uranus"), (READER, SCHEMA)):
            oid = ids.get(role)
            exists = any(s[1] == ns for s in schemas)
            if (
                not oid
                or not exists
                or not self.rows("SELECT has_schema_privilege(%s,%s,'USAGE')", (oid, ns))[0][0]
            ):
                self.action(
                    "would reconcile USAGE " + role + " " + ns,
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                        sql.Identifier(ns), sql.Identifier(role)
                    ),
                )

        relations = self.rows("""SELECT c.oid,n.nspname,c.relname,c.relkind,c.relowner,
            c.relrowsecurity,c.relforcerowsecurity,c.reloptions
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
            AND n.nspname NOT LIKE 'pg_toast%%' AND n.nspname NOT LIKE 'pg_temp%%'""")
        source = {}
        existing = {}
        for oid, ns, name, kind, owner, rls, force_rls, options in relations:
            approved = ns == SCHEMA and name in VIEWS and kind == "v"
            if ns == SCHEMA:
                if self.rows(
                    """SELECT 1 FROM pg_class, LATERAL aclexplode(relacl) a
                    WHERE oid=%s AND a.grantee NOT IN (%s,%s)""",
                    (oid, ids.get(OWNER, -1), ids.get(READER, -1)),
                ):
                    self.issue("unexpected_console_view_grantee")
                if not approved:
                    self.issue("unexpected_sql_console_object")
                else:
                    existing[name] = (oid, owner, options)
            if owner in ids.values() and not (approved and owner == ids.get(OWNER)):
                self.issue("unexpected_relation_owner:" + ns + "." + name)
            if ns == "uranus" and name in VIEWS:
                source[name] = oid
                if kind != "r" or rls or force_rls:
                    self.issue("unsupported_source_kind_or_rls:" + name)
            if kind not in {"r", "p", "v", "m", "f", "S"}:
                continue
            for role in (OWNER, READER):
                role_oid = ids.get(role, 0)
                if approved and role == OWNER and owner == role_oid:
                    continue
                grants = self.rows(
                    """SELECT privilege_type,is_grantable FROM pg_class,
                    LATERAL aclexplode(coalesce(relacl,acldefault(
                      CASE WHEN relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,relowner))) a
                    WHERE oid=%s AND a.grantee IN (0,%s)""",
                    (oid, role_oid),
                )
                for privilege, grantable in grants:
                    if not (
                        approved and role == READER and privilege == "SELECT" and not grantable
                    ):
                        self.issue(
                            "unexpected_relation_grant:"
                            + role
                            + ":"
                            + ns
                            + "."
                            + name
                            + ":"
                            + privilege
                        )
                columns = self.rows(
                    """SELECT attname,privilege_type,is_grantable FROM pg_attribute,
                    LATERAL aclexplode(attacl) a WHERE attrelid=%s AND attnum>0
                    AND NOT attisdropped AND a.grantee IN (0,%s)""",
                    (oid, role_oid),
                )
                for column, privilege, grantable in columns:
                    allowed = (
                        role == OWNER
                        and ns == "uranus"
                        and name in VIEWS
                        and column in self.contract["views"][name]["owner_select_columns"]
                        and privilege == "SELECT"
                        and not grantable
                    )
                    if not allowed:
                        self.issue(
                            "unexpected_column_grant:" + role + ":" + ns + "." + name + ":" + column
                        )
        for name, view in self.contract["views"].items():
            expected = [(c["name"], c["type"]) for c in view["columns"]]
            if name not in source:
                self.issue("source_table_missing:" + name)
                continue
            columns = dict(self.columns(source[name]))
            for col, typ in expected:
                if columns.get(col) != typ:
                    self.issue("source_column_type_mismatch:" + name + "." + col)
            # Reject user-defined executable type I/O, domains and casts in this contract.
            if self.rows(
                """SELECT 1 FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
                JOIN pg_namespace n ON n.oid=t.typnamespace WHERE a.attrelid=%s
                AND a.attname=ANY(%s) AND NOT (n.nspname='pg_catalog' OR
                  (n.nspname='uranus' AND t.typname='event_release_status' AND t.typtype='e'
                   AND t.typinput='enum_in'::regproc AND t.typoutput='enum_out'::regproc))""",
                (source[name], view["owner_select_columns"]),
            ):
                self.issue("unreviewed_source_type:" + name)
            for col, _ in expected:
                if (
                    OWNER not in ids
                    or not self.rows(
                        "SELECT has_column_privilege(%s,%s,%s,'SELECT')",
                        (ids[OWNER], source[name], col),
                    )[0][0]
                ):
                    self.action(
                        "would reconcile owner SELECT " + name + "." + col,
                        sql.SQL("GRANT SELECT ({}) ON uranus.{} TO {}").format(
                            sql.Identifier(col), sql.Identifier(name), sql.Identifier(OWNER)
                        ),
                    )
            if name not in existing:
                self.action(
                    "would create view " + name,
                    sql.SQL(
                        "CREATE VIEW {}.{} WITH (security_barrier=true, security_invoker=false) AS "
                        + definition(name, view)
                    ).format(sql.Identifier(SCHEMA), sql.Identifier(name)),
                )
            else:
                oid, owner, options = existing[name]
                if owner != ids.get(OWNER):
                    self.issue("sql_console_view_owner:" + name)
                if self.columns(oid) != expected:
                    self.issue("sql_console_view_column_contract:" + name)
                current = self.rows("SELECT pg_get_viewdef(%s,true)", (oid,))[0][0]
                if normalized(current) not in {
                    normalized(definition(name, view)),
                    normalized(
                        "SELECT "
                        + ", ".join(c["name"] for c in view["columns"])
                        + " FROM uranus."
                        + name
                    ),
                } or set(options or []) != {"security_barrier=true", "security_invoker=false"}:
                    self.action(
                        "would update view " + name,
                        sql.SQL(
                            "CREATE OR REPLACE VIEW {}.{} WITH (security_barrier=true, "
                            "security_invoker=false) AS " + definition(name, view)
                        ).format(sql.Identifier(SCHEMA), sql.Identifier(name)),
                    )
                if self.rows(
                    "SELECT 1 FROM pg_rewrite WHERE ev_class=%s AND rulename<>'_RETURN'", (oid,)
                ) or self.rows(
                    "SELECT 1 FROM pg_trigger WHERE tgrelid=%s AND NOT tgisinternal", (oid,)
                ):
                    self.issue("unexpected_sql_console_rule_or_trigger")
            if (
                name not in existing
                or READER not in ids
                or not self.rows(
                    "SELECT has_table_privilege(%s,%s,'SELECT')", (ids[READER], existing[name][0])
                )[0][0]
            ):
                self.action(
                    "would reconcile reader SELECT " + name,
                    sql.SQL("GRANT SELECT ON {}.{} TO {}").format(
                        sql.Identifier(SCHEMA), sql.Identifier(name), sql.Identifier(READER)
                    ),
                )
        self.inspect_paths(ids)
        for table, columns in self.contract["sensitive_columns"].items():
            for column in columns:
                relation = 'uranus."' + table + '"'
                exists = self.rows(
                    "SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass(%s) "
                    "AND attname=%s AND NOT attisdropped",
                    (relation, column),
                )
                if not exists:
                    self.issue("sensitive_source_column_missing:" + table + "." + column)
                elif (
                    READER in ids
                    and self.rows(
                        "SELECT has_column_privilege(%s,%s,%s,'SELECT')",
                        (ids[READER], relation, column),
                    )[0][0]
                ):
                    self.issue("sensitive_column_access:" + table + "." + column)
        settings = (
            self.rows(
                "SELECT setconfig FROM pg_db_role_setting WHERE setdatabase=%s AND setrole=%s",
                (db_oid, ids.get(READER, 0)),
            )
            if READER in ids
            else []
        )
        if settings != [(["search_path=" + SEARCH_PATH],)]:
            if settings and any(not s.startswith("search_path=") for s in settings[0][0]):
                self.issue("unexpected_console_database_role_settings")
            else:
                self.action(
                    "would set role search_path",
                    sql.SQL(
                        "ALTER ROLE {} IN DATABASE {} SET search_path = pg_catalog, uranus_console"
                    ).format(sql.Identifier(READER), sql.Identifier(self.conn.info.dbname)),
                )
        if OWNER in ids and self.rows(
            "SELECT 1 FROM pg_db_role_setting WHERE setrole=%s", (ids[OWNER],)
        ):
            self.issue("unexpected_owner_database_role_settings")
        return self.report()

    def inspect_temp(self):
        """Inventory effective TEMP and its sources before scheduling any mutations.

        Superusers and the database owner's own ACL are not PUBLIC dependants.
        Console identities are explicit removal targets, never preservation targets.
        All other LOGIN consumers must belong to the repository's reviewed contract.
        """
        db_oid, db_owner, self.public_temp = self.rows("""
            SELECT oid,datdba,EXISTS(SELECT 1 FROM aclexplode(coalesce(datacl,
              acldefault('d',datdba))) a WHERE a.grantee=0 AND a.privilege_type='TEMPORARY')
            FROM pg_database WHERE datname=current_database()
        """)[0]
        approved = self.contract["database_temp_roles"]
        roles = self.rows(
            """SELECT oid,rolname,rolcanlogin,rolsuper,
                has_database_privilege(oid,%s,'TEMPORARY') FROM pg_roles ORDER BY rolname""",
            (db_oid,),
        )
        direct = self.rows(
            """SELECT r.rolname,a.is_grantable FROM pg_database d,
                LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a
                JOIN pg_roles r ON r.oid=a.grantee
                WHERE d.oid=%s AND a.privilege_type='TEMPORARY' ORDER BY r.rolname""",
            (db_oid,),
        )
        direct_names = {name for name, _ in direct}
        by_name = {r[1]: r for r in roles}
        issues = []
        for name in approved:
            if name not in by_name or not by_name[name][2]:
                issues.append("missing_temp_contract_login_role:" + name)
        for name, grantable in direct:
            if by_name[name][0] == db_owner:
                continue  # Preserve the owner's existing ACL, never grant or revoke it.
            if name not in approved:
                issues.append("unexpected_direct_temp_grantee:" + name)
            elif grantable:
                issues.append("unexpected_temp_grant_option:" + name)
        paths = self.rows(
            """SELECT r.rolname,s.rolname,pg_has_role(r.oid,s.oid,'USAGE'),
                pg_has_role(r.oid,s.oid,'SET') FROM pg_roles r CROSS JOIN pg_roles s
                WHERE NOT r.rolsuper AND r.oid<>s.oid
                AND pg_has_role(r.oid,s.oid,'MEMBER')
                AND (s.rolname=ANY(%s) OR s.oid=%s OR s.rolsuper)
                ORDER BY r.rolname,s.rolname""",
            (sorted(direct_names | set(approved)), db_owner),
        )
        for member, source, _, _ in paths:
            issues.append("unexpected_temp_membership_path:" + member + ":" + source)
        self.temp_roles = [name for _, name, login, _, effective in roles if login and effective]
        self.temp_inventory = {
            "direct_grants": [dict(role=n, grant_option=g) for n, g in direct],
            "membership_paths": [
                dict(role=m, source=s, inherited=i, set_role=t) for m, s, i, t in paths
            ],
            "public_consumers": [],
            "privileged_roles": [
                dict(
                    role=n,
                    superuser=superuser,
                    database_owner=oid == db_owner,
                    effective_temp=effective,
                )
                for oid, n, _, superuser, effective in roles
                if superuser or oid == db_owner
            ],
        }
        for oid, name, login, superuser, effective in roles:
            if name in (OWNER, READER):
                # With no PUBLIC TEMP, any effective TEMP is necessarily unapproved.
                if effective and not self.public_temp:
                    issues.append("effective_console_temp:" + name)
                continue
            if superuser or oid == db_owner:
                # An owner lacking its own TEMP ACL would lose PUBLIC-derived TEMP.
                if (
                    oid == db_owner
                    and not superuser
                    and self.public_temp
                    and name not in direct_names
                ):
                    issues.append("database_owner_temp_depends_on_public:" + name)
                continue
            if login and effective and self.public_temp:
                self.temp_inventory["public_consumers"].append(name)
                if name not in approved:
                    issues.append("unexpected_public_temp_consumer:" + name)
            elif effective and not self.public_temp and name not in approved:
                issues.append("unexpected_effective_temp:" + name)
        missing = [name for name in approved if name not in direct_names]
        self.temp_reconcile = {
            "allowed": not issues,
            "would_grant_explicit": missing if not issues else [],
            "would_revoke_public_temp": self.public_temp and not issues,
        }
        for issue in issues:
            self.issue(issue)
        if not issues:
            for name in missing:
                self.action(
                    "would grant explicit TEMPORARY " + name,
                    sql.SQL("GRANT TEMPORARY ON DATABASE {} TO {}").format(
                        sql.Identifier(self.conn.info.dbname), sql.Identifier(name)
                    ),
                )
            if self.public_temp:
                self.action(
                    "would revoke PUBLIC TEMPORARY",
                    sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                        sql.Identifier(self.conn.info.dbname)
                    ),
                )
        return db_oid

    def columns(self, oid):
        return self.rows(
            "SELECT attname,format_type(atttypid,atttypmod) FROM "
            "pg_attribute WHERE attrelid=%s AND attnum>0 AND NOT "
            "attisdropped ORDER BY attnum",
            (oid,),
        )

    def inspect_paths(self, ids):
        for role in (OWNER, READER):
            oid = ids.get(role, 0)
            # Core catalogs are otherwise readable under PostgreSQL's normal masking.
            # Direct extra grants must never expose password verifiers or statistics.
            if oid and self.rows(
                """SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
                LATERAL aclexplode(c.relacl) a
                WHERE n.nspname IN ('pg_catalog','information_schema')
                AND a.grantee=%s UNION ALL
                SELECT 1 FROM pg_attribute t JOIN pg_class c ON c.oid=t.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace, LATERAL aclexplode(t.attacl) a
                WHERE n.nspname IN ('pg_catalog','information_schema') AND a.grantee=%s""",
                (oid, oid),
            ):
                self.issue("unexpected_catalog_grant:" + role)
            for relation, column in (
                ("pg_authid", "rolpassword"),
                ("pg_shadow", "passwd"),
                ("pg_subscription", "subconninfo"),
                ("pg_user_mapping", "umoptions"),
                ("pg_statistic", "stavalues1"),
                ("pg_statistic", "stavalues2"),
                ("pg_statistic", "stavalues3"),
                ("pg_statistic", "stavalues4"),
                ("pg_statistic", "stavalues5"),
                ("pg_statistic_ext_data", "stxdmcv"),
            ):
                if self.rows(
                    """SELECT 1 FROM pg_class c, LATERAL aclexplode(c.relacl) a
                    WHERE c.oid=to_regclass(%s) AND a.grantee IN (0,%s)
                    AND a.privilege_type='SELECT' UNION ALL
                    SELECT 1 FROM pg_attribute t, LATERAL aclexplode(t.attacl) a
                    WHERE t.attrelid=to_regclass(%s) AND t.attname=%s
                    AND a.grantee IN (0,%s) AND a.privilege_type='SELECT'""",
                    ("pg_catalog." + relation, oid, "pg_catalog." + relation, column, oid),
                ):
                    self.issue("sensitive_catalog_access:" + role + ":" + relation)
            for catalog, acl in (
                ("pg_proc", "proacl"),
                ("pg_type", "typacl"),
                ("pg_language", "lanacl"),
            ):
                if self.rows(
                    sql.SQL(
                        "SELECT 1 FROM {}, LATERAL aclexplode({}) a "
                        "WHERE a.grantee IN (0,%s) AND a.is_grantable"
                    ).format(sql.Identifier(catalog), sql.Identifier(acl)),
                    (oid,),
                ):
                    self.issue("unexpected_grant_option:" + role + ":" + catalog)
            if self.rows(
                """SELECT 1 FROM pg_foreign_data_wrapper, LATERAL aclexplode(fdwacl) a
                WHERE a.grantee IN (0,%s) UNION ALL
                SELECT 1 FROM pg_parameter_acl, LATERAL aclexplode(paracl) a
                WHERE a.grantee IN (0,%s)""",
                (oid, oid),
            ):
                self.issue("foreign_wrapper_or_parameter_grant:" + role)
            # All overloads; absent roles are evaluated against PUBLIC grants.
            paths = self.rows(
                """SELECT n.nspname,p.proname FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE (p.proowner=%s OR EXISTS(SELECT 1 FROM aclexplode(coalesce(
                    p.proacl,acldefault('f',p.proowner))) a WHERE a.grantee IN (0,%s)
                    AND a.privilege_type='EXECUTE'))
                AND (p.prosecdef OR p.proname=ANY(%s) OR p.proname LIKE 'dblink%%'
                    OR p.oid>=16384 OR (n.nspname NOT IN ('pg_catalog','information_schema')))
                AND (n.nspname IN ('pg_catalog','uranus_console') OR (%s=%s AND n.nspname='uranus')
                    OR EXISTS(SELECT 1 FROM
                      aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a
                      WHERE a.grantee IN (0,%s) AND a.privilege_type='USAGE'))
            """,
                (oid, oid, DANGEROUS, role, OWNER, oid),
            )
            for ns, name in paths:
                self.issue("unreviewed_function_path:" + role + ":" + ns + "." + name)
            if self.rows(
                """SELECT 1 FROM pg_foreign_server s WHERE srvowner=%s OR EXISTS(
                SELECT 1 FROM aclexplode(srvacl) a WHERE a.grantee IN (0,%s))""",
                (oid, oid),
            ) or self.rows("SELECT 1 FROM pg_user_mapping WHERE umuser IN (0,%s)", (oid,)):
                self.issue("foreign_server_or_user_mapping:" + role)
            if self.rows(
                """SELECT 1 FROM pg_largeobject_metadata l WHERE lomowner=%s OR EXISTS(
                SELECT 1 FROM aclexplode(lomacl) a WHERE a.grantee IN (0,%s))""",
                (oid, oid),
            ):
                self.issue("large_object_access:" + role)
            if self.rows(
                """SELECT 1 FROM pg_default_acl d WHERE defaclrole=%s OR EXISTS(
                SELECT 1 FROM aclexplode(defaclacl) a WHERE a.grantee IN (0,%s))""",
                (oid, oid),
            ):
                self.issue("unreviewed_default_privileges:" + role)
            if self.rows("SELECT 1 FROM pg_proc WHERE proowner=%s", (oid,)) or self.rows(
                "SELECT 1 FROM pg_extension WHERE extowner=%s", (oid,)
            ):
                self.issue("unexpected_function_or_extension_owner:" + role)
            if self.rows(
                """SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                WHERE t.typowner=%s AND NOT (n.nspname=%s AND (
                    EXISTS(SELECT 1 FROM pg_class c WHERE c.oid=t.typrelid
                      AND c.relkind='v' AND c.relname=ANY(%s))
                    OR EXISTS(SELECT 1 FROM pg_type b JOIN pg_class c ON c.oid=b.typrelid
                      WHERE b.oid=t.typelem AND c.relkind='v' AND c.relname=ANY(%s))))""",
                (oid, SCHEMA, list(VIEWS), list(VIEWS)),
            ):
                self.issue("unexpected_type_owner:" + role)
            # pg_shdepend also covers ownership kinds not represented by pg_class,
            # including objects in other databases. Only this schema and view types
            # may be owned by the NOLOGIN owner; reader ownership is always refused.
            if self.rows(
                """SELECT 1 FROM pg_shdepend d WHERE d.refclassid='pg_authid'::regclass
                AND d.refobjid=%s AND d.deptype='o' AND NOT (
                  %s=%s AND d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
                  AND ((d.classid='pg_namespace'::regclass AND d.objid=to_regnamespace(%s))
                  OR (d.classid='pg_class'::regclass AND EXISTS(SELECT 1 FROM pg_class c
                      WHERE c.oid=d.objid AND c.relnamespace=to_regnamespace(%s)
                      AND c.relkind='v' AND c.relname=ANY(%s)))
                  OR (d.classid='pg_type'::regclass AND EXISTS(SELECT 1 FROM pg_type t
                      WHERE t.oid=d.objid AND t.typnamespace=to_regnamespace(%s)))))""",
                (oid, role, OWNER, SCHEMA, SCHEMA, list(VIEWS), SCHEMA),
            ):
                self.issue("unexpected_owned_object:" + role)
        for catalog, namespace in (
            ("pg_operator", "oprnamespace"),
            ("pg_collation", "collnamespace"),
            ("pg_conversion", "connamespace"),
            ("pg_opclass", "opcnamespace"),
            ("pg_opfamily", "opfnamespace"),
            ("pg_ts_config", "cfgnamespace"),
            ("pg_ts_dict", "dictnamespace"),
            ("pg_ts_parser", "prsnamespace"),
            ("pg_ts_template", "tmplnamespace"),
        ):
            if self.rows(
                sql.SQL("SELECT 1 FROM {} WHERE {}=to_regnamespace(%s)").format(
                    sql.Identifier(catalog), sql.Identifier(namespace)
                ),
                (SCHEMA,),
            ):
                self.issue("unexpected_sql_console_object")
        if self.rows("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'"):
            self.issue("unreviewed_event_trigger")
        if self.rows("SELECT 1 FROM pg_extension WHERE extname NOT IN ('plpgsql','postgis')"):
            self.issue("unreviewed_extension")
        if self.rows("SELECT 1 FROM pg_proc WHERE pronamespace=to_regnamespace(%s)", (SCHEMA,)):
            self.issue("unexpected_sql_console_object")
        if self.rows(
            """SELECT 1 FROM pg_type t WHERE typnamespace=to_regnamespace(%s)
            AND typrelid=0 AND NOT EXISTS(SELECT 1 FROM pg_type b WHERE b.oid=t.typelem
                AND b.typrelid<>0)""",
            (SCHEMA,),
        ):
            self.issue("unexpected_sql_console_object")

    def report(self):
        return {
            "required": True,
            "role": READER,
            "schema": SCHEMA,
            "owner_role": OWNER,
            "contract_version": self.contract["version"],
            "changes_planned": list(dict.fromkeys(a[0] for a in self.actions)),
            "blockers": sorted(set(self.blockers)),
            "public_temp": self.public_temp,
            "temp_login_roles": self.temp_roles,
            "temp_inventory": self.temp_inventory,
            "temp_reconcile": self.temp_reconcile,
            "fallback": False,
            "postgresql_version": self.conn.server_version,
            "extensions": [
                dict(name=n, version=v)
                for n, v in self.rows(
                    "SELECT extname,extversion FROM pg_extension ORDER BY extname"
                )
            ],
        }

    def provision(self, password):
        self.inspect(password)
        require(not self.blockers, "sql_console_blocked")
        changes = list(self.actions)
        for label, query, args in changes:
            if label.startswith(("would create view", "would update view")):
                self.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(OWNER)))
                self.execute(query, args)
                self.execute("RESET ROLE")
            else:
                self.execute(query, args)
        if READER not in self.ids:
            self.execute(
                sql.SQL("ALTER ROLE {} PASSWORD %s").format(sql.Identifier(READER)),
                (scram(password),),
            )
        self.inspect(password)
        require(
            not self.blockers and not self.actions, "sql_console_post_apply_verification_failed"
        )
        return bool(changes)


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "contract": {"type": "dict", "required": True},
            "state": {"choices": ["plan", "provision", "verify"], "required": True},
            "dsn": {"type": "str", "no_log": True},
        },
        supports_check_mode=True,
    )
    conn = None
    try:
        state = module.params["state"]
        writing = state == "provision" and not module.check_mode
        password = console_password(module.params["dsn"]) if writing else None
        conn = psycopg2.connect(
            dbname="oklab",
            user="postgres",
            host="/var/run/postgresql",
            port=5432,
            connect_timeout=10,
            options="-c search_path=pg_catalog -c statement_timeout=10000 -c lock_timeout=2000",
        )
        conn.set_session(readonly=not writing, isolation_level="REPEATABLE READ")
        boundary = Boundary(conn, module.params["contract"])
        if writing:
            # Do not persist credential statements/parameters in server statement logs.
            boundary.execute("SET LOCAL log_statement='none'")
            boundary.execute("SET LOCAL log_min_duration_statement=-1")
            boundary.execute("SET LOCAL log_min_duration_sample=-1")
            boundary.execute("SET LOCAL log_transaction_sample_rate=0")
            boundary.execute("SET LOCAL log_min_error_statement='panic'")
            boundary.execute("SET LOCAL log_parameter_max_length_on_error=0")
            boundary.execute("SET LOCAL log_parameter_max_length=0")
            boundary.execute("SELECT pg_advisory_xact_lock(762076)")
        report = boundary.inspect(password)
        if writing or state == "verify":
            require(not report["blockers"], "sql_console_blocked")
        if state == "verify":
            require(not report["changes_planned"], "sql_console_drift")
        changed = boundary.provision(password) if writing else False
        if writing:
            conn.commit()
        else:
            conn.rollback()
        module.exit_json(changed=changed, sql_console=report)
    except (ValueError, KeyError, TypeError):
        module.fail_json(
            msg="SQL console contract, credentials or boundary rejected; review the read-only plan."
        )
    except psycopg2.Error:
        module.fail_json(msg="SQL console database operation failed; no activation permitted.")
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
