#!/usr/bin/python
"""Admin first installation only. No source DDL/DML, drift repair or secret output."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import encrypt_password

RELEASE_ROOT = Path("/var/lib/uranus-admin/releases")
OWNER_UID = 0
ROLES = {
    "uranus_reader": "DATABASE_URL",
    "admin_user": "ADMIN_DATABASE_URL",
    "admin_migrator": "ADMIN_MIGRATION_DATABASE_URL",
    "admin_auth_operator": "ADMIN_AUTH_MANAGEMENT_DATABASE_URL",
}
OPERATOR_GRANTS = {
    "alembic_version": ["SELECT"],
    "auth_account": ["SELECT", "INSERT", "UPDATE"],
    "auth_system_admin": ["SELECT", "INSERT", "DELETE"],
    "auth_session": ["SELECT", "UPDATE"],
}


def require(condition, category):
    if not condition:
        raise ValueError(category)


class AdminDatabase:
    def __init__(self, connection, manifest, boundary, diagnostic=None):
        self.diagnostic = diagnostic if diagnostic is not None else {}
        self.mark("release_contract")
        self.conn, self.manifest, self.boundary = connection, manifest, boundary
        require(re.fullmatch(r"[0-9a-f]{40}", manifest["commit"]), "invalid_release")
        require(re.fullmatch(r"[0-9]{4}", manifest["head"]), "invalid_release_head")
        require(
            manifest["runtime_grants"]
            and all(
                re.fullmatch(r"[a-z_]+", name)
                and isinstance(grants, list)
                and grants
                and set(grants) <= {"SELECT", "INSERT", "UPDATE"}
                for name, grants in manifest["runtime_grants"].items()
            ),
            "invalid_release_grants",
        )
        # The existing versioned source boundary remains the reader's grant contract.
        self.mark("source_contract")
        _, start, remainder = boundary.partition("source_tables(name) AS (")
        source_contract, end, _ = remainder.partition("), problems")
        require(bool(start and end), "invalid_source_contract")
        self.source_tables = re.findall(r"\('([a-z_]+)'\)", source_contract)
        require(bool(self.source_tables), "invalid_source_contract")
        self.mark("operator_contract")
        require(
            manifest.get("operator_grants") == OPERATOR_GRANTS,
            "unsupported_operator_contract",
        )
        self.mark("admin_object_contract")
        require(
            isinstance(manifest.get("admin_indexes"), list),
            "missing_admin_object_contract",
        )
        self.mark("admin_column_contract")
        require(
            isinstance(manifest.get("admin_columns"), dict),
            "missing_admin_column_contract",
        )

    def mark(self, check):
        # Callers supply only fixed code-owned labels, never SQL or database values.
        self.diagnostic["check"] = check

    def rows(self, query, params=()):
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall() if cur.description else []

    def inspect(self, environment, approved=False):
        self.mark("environment")
        require(environment in {"production", "staging", "test"}, "invalid_environment")
        self.mark("inspection_session")
        self.rows("SET LOCAL search_path=pg_catalog")
        problems = []
        self.mark("database_identity")
        db, owner = self.rows(
            "SELECT datname,datdba FROM pg_database WHERE datname=current_database()"
        )[0]
        self.mark("schema_inventory")
        schema = self.rows("SELECT oid,nspowner FROM pg_namespace WHERE nspname='admin'")
        source = self.rows("SELECT oid,nspowner FROM pg_namespace WHERE nspname='uranus'")
        self.mark("public_create")
        if self.rows("""SELECT 1 FROM pg_database d,
            LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a
            WHERE d.datname=current_database() AND a.grantee=0 AND a.privilege_type='CREATE'
            UNION ALL SELECT 1 FROM pg_namespace n,LATERAL aclexplode(n.nspacl) a
            WHERE a.grantee=0 AND a.privilege_type='CREATE'"""):
            problems.append("public_create")
        if not source or source[0][1] != owner:
            problems.append("source_schema_owner")
        self.mark("source_public_acl")
        if self.rows("""SELECT 1 FROM pg_namespace n,LATERAL aclexplode(n.nspacl) a
            WHERE n.nspname='uranus' AND a.grantee=0
            UNION ALL SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
            LATERAL aclexplode(c.relacl) a WHERE n.nspname='uranus' AND a.grantee=0
            AND (a.privilege_type<>'SELECT' OR a.is_grantable)"""):
            problems.append("public_source_privileges")
        self.mark("postgis")
        if not self.rows("SELECT 1 FROM pg_extension WHERE extname='postgis'"):
            problems.append("postgis_missing")
        self.mark("relation_inventory")
        relations = self.rows("""SELECT c.oid,n.nspname,c.relname,c.relkind,c.relowner,
            c.relrowsecurity,c.relforcerowsecurity FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('admin','uranus') ORDER BY n.nspname,c.relname""")
        source_relations = [r for r in relations if r[1] == "uranus" and r[3] in "rpvmf"]
        if not set(self.source_tables) <= {r[2] for r in source_relations}:
            problems.append("source_tables_missing")
        for _, _, name, kind, relowner, rls, force_rls in source_relations:
            if relowner != owner or kind not in "rp" or rls or force_rls:
                problems.append("source_owner_or_rls_or_indirect_relation:" + name)
        self.mark("role_inventory")
        roles = self.rows(
            """SELECT oid,rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,
            rolreplication,rolbypassrls,rolvaliduntil,rolconfig FROM pg_roles
            WHERE rolname=ANY(%s) ORDER BY rolname""",
            (list(ROLES),),
        )
        ids = {row[1]: row[0] for row in roles}
        missing = sorted(set(ROLES) - set(ids))
        for oid, name, login, *attributes in roles:
            if not login or any(attributes):
                problems.append("role_attributes_or_settings:" + name)
            self.mark("role_memberships")
            if self.rows("SELECT 1 FROM pg_auth_members WHERE member=%s OR roleid=%s", (oid, oid)):
                problems.append("role_membership:" + name)
            self.mark("role_database_privileges")
            if self.rows(
                """SELECT 1 FROM pg_database WHERE datdba=%s OR
                has_database_privilege(%s,oid,'CREATE')""",
                (oid, oid),
            ):
                problems.append("database_create_or_owner:" + name)
            self.mark("role_schema_privileges")
            if self.rows(
                """SELECT 1 FROM pg_namespace WHERE
                has_schema_privilege(%s,oid,'CREATE') AND NOT
                (%s='admin_migrator' AND nspname='admin')""",
                (oid, name),
            ):
                problems.append("schema_create:" + name)
            self.mark("role_external_ownership")
            if self.rows(
                """SELECT 1 FROM pg_shdepend WHERE refclassid='pg_authid'::regclass
                AND refobjid=%s AND deptype='o' AND (dbid=0 OR dbid<>(
                SELECT oid FROM pg_database WHERE datname=current_database()))""",
                (oid,),
            ):
                problems.append("external_object_ownership:" + name)
            self.mark("role_default_privileges")
            if self.rows("""SELECT 1 FROM pg_default_acl WHERE defaclrole=%s""", (oid,)):
                problems.append("unreviewed_default_privileges:" + name)
            self.mark("role_functions")
            if self.rows(
                """SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE p.proowner=%s OR (p.prosecdef AND n.nspname NOT IN
                ('pg_catalog','information_schema') AND has_schema_privilege(%s,n.oid,'USAGE')
                AND has_function_privilege(%s,p.oid,'EXECUTE'))""",
                (oid, oid, oid),
            ):
                problems.append("function_owner_or_security_definer:" + name)
            self.mark("role_types_extensions")
            if self.rows(
                """SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                WHERE t.typowner=%s AND NOT (%s='admin_migrator' AND n.nspname='admin')
                UNION ALL SELECT 1 FROM pg_extension WHERE extowner=%s""",
                (oid, name, oid),
            ):
                problems.append("type_or_extension_owner:" + name)
            self.mark("role_source_usage")
            if self.rows(
                """SELECT 1 FROM pg_namespace WHERE nspname='uranus'
                AND %s<>'uranus_reader' AND has_schema_privilege(%s,oid,'USAGE')""",
                (name, oid),
            ):
                problems.append("admin_role_source_usage:" + name)
            self.mark("role_source_privileges")
            if self.rows(
                """SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT IN ('admin','pg_catalog','information_schema')
                AND n.nspname NOT LIKE 'pg_toast%%' AND n.nspname NOT LIKE 'pg_temp%%'
                AND (c.relowner=%s OR (c.relkind IN ('r','p','v','m','f') AND (
                has_table_privilege(%s,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR has_any_column_privilege(%s,c.oid,'INSERT,UPDATE,REFERENCES')
                OR has_table_privilege(%s,c.oid,'SELECT WITH GRANT OPTION')
                OR has_any_column_privilege(%s,c.oid,'SELECT WITH GRANT OPTION')))
                OR (c.relkind='S' AND has_sequence_privilege(%s,c.oid,'USAGE,UPDATE')))""",
                (oid, oid, oid, oid, oid, oid),
            ):
                problems.append("source_or_external_privileges:" + name)
        self.mark("event_triggers")
        if self.rows("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'"):
            problems.append("event_trigger")
        self.mark("source_maintain")
        if self.rows(
            """SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
            LATERAL aclexplode(c.relacl) a WHERE n.nspname='uranus'
            AND a.privilege_type='MAINTAIN' AND a.grantee IN
            (SELECT oid FROM pg_roles WHERE rolname=ANY(%s) UNION ALL SELECT 0)""",
            (list(ROLES),),
        ):
            problems.append("source_maintain")
        # Existing reader grants are adopted, never repaired. A missing reader receives
        # only the explicit SELECT set above, in the role preparation transaction.
        self.mark("reader_privileges")
        if "uranus_reader" in ids:
            oid = ids["uranus_reader"]
            if (
                not source
                or not self.rows("SELECT has_schema_privilege(%s,%s,'USAGE')", (oid, source[0][0]))[
                    0
                ][0]
            ):
                problems.append("source_reader_usage")
            for relid, _, name, *_ in source_relations:
                if (
                    name in self.source_tables
                    and not self.rows("SELECT has_table_privilege(%s,%s,'SELECT')", (oid, relid))[
                        0
                    ][0]
                ):
                    problems.append("source_reader_select:" + name)
        current = None
        admin_objects = [r for r in relations if r[1] == "admin"]
        tables = [r[2] for r in admin_objects if r[3] in "rpvmf"]
        self.mark("admin_relations")
        if schema:
            if missing:
                problems.append("required_roles_missing")
            if schema[0][1] != ids.get("admin_migrator"):
                problems.append("admin_schema_owner")
            if set(tables) != set(self.manifest["runtime_grants"]):
                problems.append("admin_tables_missing_or_unknown")
            if {r[2] for r in admin_objects if r[3] == "i"} != set(self.manifest["admin_indexes"]):
                problems.append("admin_indexes_missing_or_unknown")
            self.mark("admin_columns")
            columns = dict(
                self.rows(
                    """SELECT c.relname,array_agg(a.attname::text ORDER BY a.attname)
                FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid
                WHERE c.relnamespace=%s AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
                GROUP BY c.relname""",
                    (schema[0][0],),
                )
            )
            if columns != self.manifest["admin_columns"]:
                problems.append("admin_columns_missing_or_unknown")
            for _, _, name, kind, relowner, rls, force_rls in admin_objects:
                if kind not in "rit" or relowner != ids.get("admin_migrator") or rls or force_rls:
                    problems.append("admin_object_owner_or_kind_or_rls:" + name)
            self.mark("admin_unknown_objects")
            if self.rows(
                """SELECT 1 FROM pg_proc WHERE pronamespace=%s
                UNION ALL SELECT 1 FROM pg_type WHERE typnamespace=%s AND typtype<>'c'
                AND typelem=0 UNION ALL SELECT 1 FROM pg_default_acl WHERE defaclnamespace=%s
                UNION ALL SELECT 1 FROM pg_operator WHERE oprnamespace=%s
                UNION ALL SELECT 1 FROM pg_collation WHERE collnamespace=%s""",
                (schema[0][0],) * 5,
            ):
                problems.append("unknown_admin_objects")
            self.mark("admin_extra_catalogs")
            for catalog, field in (
                ("pg_conversion", "connamespace"),
                ("pg_opclass", "opcnamespace"),
                ("pg_opfamily", "opfnamespace"),
                ("pg_ts_config", "cfgnamespace"),
                ("pg_ts_dict", "dictnamespace"),
                ("pg_ts_parser", "prsnamespace"),
                ("pg_ts_template", "tmplnamespace"),
            ):
                if self.rows(
                    sql.SQL("SELECT 1 FROM {} WHERE {}=%s").format(
                        sql.Identifier(catalog), sql.Identifier(field)
                    ),
                    (schema[0][0],),
                ):
                    problems.append("unknown_admin_objects:" + catalog)
            self.mark("version_relation")
            version = next((r for r in admin_objects if r[2] == "alembic_version"), None)
            # Never execute a foreign/view/RLS-backed or wrongly owned version relation.
            if (
                version
                and version[3] == "r"
                and version[4] == ids.get("admin_migrator")
                and not any(version[5:])
            ):
                columns = self.rows("""SELECT attname,atttypid::regtype::text FROM pg_attribute
                    WHERE attrelid='admin.alembic_version'::regclass
                    AND attnum>0 AND NOT attisdropped""")
                if columns == [("version_num", "character varying")]:
                    self.mark("migration_head")
                    heads = self.rows(
                        "SELECT left(version_num,65) FROM admin.alembic_version LIMIT 2"
                    )
                    if len(heads) == 1 and re.fullmatch(r"[0-9]{4}", heads[0][0] or ""):
                        current = heads[0][0]
                if current != self.manifest["head"]:
                    problems.append("migration_head_mismatch")
            else:
                problems.append("version_table_missing")
            if not problems:
                self.mark("boundary_contract")
                violations = self.rows(
                    self.boundary,
                    {
                        "head": self.manifest["head"],
                        "grants": json.dumps(self.manifest["runtime_grants"]),
                    },
                )[0][0]
                problems.extend(violations)
                self.mark("operator_privileges")
                for name, grants in OPERATOR_GRANTS.items():
                    for privilege in grants:
                        if not self.rows(
                            "SELECT has_table_privilege('admin_auth_operator',%s,%s)",
                            ("admin." + name, privilege),
                        )[0][0]:
                            problems.append("operator_missing_grant:" + name + ":" + privilege)
            # PUBLIC and foreign roles must never receive admin data grants.
            self.mark("admin_acl")
            if self.rows(
                """SELECT 1 FROM pg_class c,LATERAL aclexplode(c.relacl) a
                WHERE c.relnamespace=%s AND a.grantee NOT IN
                (SELECT oid FROM pg_roles WHERE rolname=ANY(%s))
                UNION ALL SELECT 1 FROM pg_namespace n,LATERAL aclexplode(n.nspacl) a
                WHERE n.oid=%s AND a.grantee NOT IN
                (SELECT oid FROM pg_roles WHERE rolname=ANY(%s))""",
                (schema[0][0], list(ROLES)[1:], schema[0][0], list(ROLES)[1:]),
            ):
                problems.append("unexpected_admin_acl")
            self.mark("admin_column_acl")
            if self.rows(
                """SELECT 1 FROM pg_attribute t JOIN pg_class c ON c.oid=t.attrelid,
                LATERAL aclexplode(t.attacl) a WHERE c.relnamespace=%s AND a.grantee NOT IN
                (SELECT oid FROM pg_roles WHERE rolname=ANY(%s))""",
                (schema[0][0], list(ROLES)[1:]),
            ):
                problems.append("unexpected_admin_column_acl")
        self.mark("classification")
        state = "DRIFTED" if problems else "READY" if schema else "ABSENT"
        allowed = environment in {"staging", "test"} and state == "ABSENT"
        return {
            "state": state,
            "current_head": current,
            "expected_head": self.manifest["head"],
            "bootstrap_allowed": allowed,
            "bootstrap_approved": approved,
            "changes_planned": allowed,
            "blockers": sorted(set(problems)),
            "table_count": len(tables),
            "tables": tables,
            "missing_roles": missing,
            "would_create_or_prepare_roles": sorted(ROLES) if allowed else [],
            "would_grant_temporary_database_create": allowed,
            "would_run_alembic": allowed,
            "target_head": self.manifest["head"],
            "would_apply_runtime_grants": allowed,
            "would_revoke_temporary_database_create": allowed,
            "would_verify_boundary": allowed,
        }

    def credentials(self, values):
        db = self.rows("SELECT current_database()")[0][0]
        port = int(self.conn.get_dsn_parameters()["port"])
        result = {}
        for role, key in ROLES.items():
            url = urlsplit(values.get(key, ""))
            require(
                url.scheme == "postgresql+asyncpg"
                and unquote(url.username or "") == role
                and url.hostname in {"localhost", "127.0.0.1", "::1"}
                and (url.port or 5432) == port
                and url.path == "/" + db
                and not url.query
                and not url.fragment
                and bool(url.password),
                "missing_or_invalid_adopted_credentials",
            )
            result[role] = dict(
                dbname=db,
                user=role,
                password=unquote(url.password),
                host=url.hostname,
                port=url.port or 5432,
                connect_timeout=10,
            )
        return result

    def prepare_roles(self, credentials, missing):
        for role in ROLES:
            if role not in missing:
                with (
                    psycopg2.connect(**credentials[role]) as conn,
                    conn.cursor() as cur,
                ):
                    cur.execute("SELECT current_user,session_user")
                    require(cur.fetchone() == (role, role), "adopted_identity_mismatch")
        for setting, value in (
            ("log_statement", "none"),
            ("log_min_duration_statement", "-1"),
            ("log_min_duration_sample", "-1"),
            ("log_transaction_sample_rate", "0"),
            ("log_min_error_statement", "panic"),
            ("log_parameter_max_length", "0"),
            ("log_parameter_max_length_on_error", "0"),
        ):
            self.rows("SELECT set_config(%s,%s,true)", (setting, value))
        for role in missing:
            verifier = encrypt_password(
                credentials[role]["password"], role, self.conn, "scram-sha-256"
            )
            self.rows(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %s"
                ).format(sql.Identifier(role)),
                (verifier,),
            )
        if "uranus_reader" in missing:
            self.rows("GRANT USAGE ON SCHEMA uranus TO uranus_reader")
            for name in self.source_tables:
                self.rows(
                    sql.SQL("GRANT SELECT ON uranus.{} TO uranus_reader").format(
                        sql.Identifier(name)
                    )
                )
        self.conn.commit()

    def revoke_create(self):
        """Idempotent cleanup; never adds rights or drops database objects."""
        self.conn.rollback()
        if not self.rows("SELECT 1 FROM pg_roles WHERE rolname='admin_migrator'"):
            return False
        db, had_create = self.rows("""SELECT current_database(),
            has_database_privilege('admin_migrator',current_database(),'CREATE')""")[0]
        if had_create:
            self.rows(
                sql.SQL("REVOKE CREATE ON DATABASE {} FROM admin_migrator").format(
                    sql.Identifier(db)
                )
            )
            self.conn.commit()
        require(
            not self.rows(
                "SELECT has_database_privilege('admin_migrator',current_database(),'CREATE')"
            )[0][0],
            "temporary_create_cleanup_failed",
        )
        return had_create

    def bootstrap(self, environment, approved, values, migrate):
        # This guard is inside the mutation implementation as well as in Ansible.
        require(environment in {"staging", "test"}, "production_bootstrap_forbidden")
        report = self.inspect(environment, approved)
        if report["state"] == "READY":
            return False
        require(
            report["state"] == "ABSENT" and approved is True,
            "admin_bootstrap_not_authorized",
        )
        credentials = self.credentials(values)
        self.prepare_roles(credentials, report["missing_roles"])
        require(
            self.inspect(environment)["state"] == "ABSENT",
            "prepared_roles_boundary_failed",
        )
        db = self.rows("SELECT current_database()")[0][0]
        try:
            self.rows(
                sql.SQL("GRANT CREATE ON DATABASE {} TO admin_migrator").format(sql.Identifier(db))
            )
            self.conn.commit()
            migrate(values["ADMIN_MIGRATION_DATABASE_URL"])
        finally:
            self.revoke_create()
        # All runtime/operator grants and full validation are one transaction.
        try:
            self.rows("GRANT USAGE ON SCHEMA admin TO admin_user,admin_auth_operator")
            for role, matrix in (
                ("admin_user", self.manifest["runtime_grants"]),
                ("admin_auth_operator", OPERATOR_GRANTS),
            ):
                for name, privileges in matrix.items():
                    self.rows(
                        sql.SQL("GRANT {} ON admin.{} TO {}").format(
                            sql.SQL(",".join(privileges)),
                            sql.Identifier(name),
                            sql.Identifier(role),
                        )
                    )
            require(
                self.inspect(environment)["state"] == "READY",
                "post_bootstrap_boundary_failed",
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return True


def release_migration(release, manifest, archive_hash, uv):
    path = Path(release)
    require(isinstance(uv, str) and bool(uv), "invalid_uv_path")
    uv_path = Path(uv)
    require(path == RELEASE_ROOT / manifest["commit"], "invalid_release_path")
    require(not path.is_symlink() and path.stat().st_uid == OWNER_UID, "untrusted_release")
    require(uv_path.is_absolute(), "invalid_uv_path")
    require((path / ".complete").read_text().strip() == archive_hash, "incomplete_release")
    require(
        json.loads((path / "release.json").read_text()) == manifest,
        "release_manifest_mismatch",
    )

    def migrate(dsn):
        # Passwords are never argv or subprocess output. No inherited application env.
        completed = subprocess.run(
            [
                str(uv_path),
                "run",
                "--no-cache",
                "--no-sync",
                "--offline",
                "--no-python-downloads",
                "--no-env-file",
                "python",
                "-B",
                str(path / "deployment/admin_database_migrate.py"),
            ],
            cwd=path / "backend",
            env={
                "PATH": "/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "UV_PYTHON_DOWNLOADS": "never",
                "ADMIN_MIGRATION_DATABASE_URL": dsn,
            },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
            check=False,
        )
        require(completed.returncode == 0, "release_migration_failed")

    return migrate


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "state": {
                "choices": ["plan", "bootstrap", "revoke_create"],
                "required": True,
            },
            "environment": {
                "choices": ["production", "staging", "test"],
                "required": True,
            },
            "approved": {"type": "bool", "default": False},
            "manifest": {"type": "dict", "required": True},
            "boundary": {"type": "str", "required": True},
            "credentials": {"type": "dict", "default": {}, "no_log": True},
            "release": {"type": "path"},
            "archive_hash": {"type": "str"},
            "uv": {"type": "path"},
        },
        supports_check_mode=True,
    )
    conn = None
    stage = "initializing"
    diagnostic = {}
    try:
        p = module.params
        stage = "authorization"
        writing = p["state"] != "plan" and not module.check_mode
        if writing:
            require(
                p["environment"] in {"staging", "test"} and p["approved"] is True,
                "admin_mutation_not_authorized",
            )
        stage = "postgres_connect"
        conn = psycopg2.connect(
            dbname="oklab",
            user="postgres",
            host="/var/run/postgresql",
            port=5432,
            connect_timeout=10,
            options="-c search_path=pg_catalog -c statement_timeout=10000 -c lock_timeout=2000",
        )
        stage = "session_setup"
        conn.set_session(readonly=not writing)
        stage = "construct_boundary"
        boundary = AdminDatabase(conn, p["manifest"], p["boundary"], diagnostic)
        changed = False
        if writing and p["state"] == "revoke_create":
            stage = "revoke_create"
            changed = boundary.revoke_create()
        elif writing:
            # Session lock spans the separate Alembic connection and commits.
            stage = "advisory_lock"
            diagnostic.clear()
            boundary.rows("SELECT pg_advisory_lock(762083)")
            stage = "bootstrap"
            changed = boundary.bootstrap(
                p["environment"],
                p["approved"],
                p["credentials"],
                release_migration(p["release"], p["manifest"], p["archive_hash"], p["uv"]),
            )
        stage = "inspect"
        report = boundary.inspect(p["environment"], p["approved"])
        stage = "rollback"
        diagnostic.clear()
        conn.rollback()
        module.exit_json(changed=changed, admin_database=report)
    except Exception as exc:
        # Never stringify database, filesystem, credential or subprocess exceptions.
        module.fail_json(
            msg="Admin database operation failed; no activation permitted. "
            f"Safe diagnostic stage={stage}, check={diagnostic.get('check', 'none')}, "
            f"exception_type={type(exc).__name__}. "
            "No exception text, SQL, credentials or connection data are exposed."
        )
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
