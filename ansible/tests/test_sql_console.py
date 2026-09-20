"""Console boundary attacks only in a separate, disposable local *_test database."""

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import psycopg2
import yaml
from psycopg2 import sql
from test_deployment import ROLE, filters, load

console = load("console_boundary", ROLE / "library/uranus_sql_console.py")
CONTRACT = json.loads((ROLE / "files/sql_console_contract.json").read_text())
TEST_URL = os.environ.get("ANSIBLE_TEST_DATABASE_URL", "")
PASSWORD = "synthetic-console-credential-only-12345"


class ConsoleContractTests(unittest.TestCase):
    def test_exact_postgresql_and_postgis_snapshot_selection(self):
        expected = {(16, "3.4.2"), (16, "3.4.3"), (17, "3.5.2")}
        self.assertEqual(
            {
                (int(major), version)
                for major, catalog in CONTRACT["function_policy"]["catalogs"].items()
                for version in catalog["postgis_versions"]
            },
            expected,
        )
        for major, version in expected:
            with self.subTest(major=major, version=version):
                selected = console.function_snapshot(CONTRACT, major, version)
                self.assertEqual(selected["postgis"]["version"], version)
                self.assertEqual(selected["audited_postgresql_version_num"] // 10000, major)
        for major in (15, 16, 17, 18):
            for version in (None, "3.4.2", "3.4.3", "3.4.4", "3.5.1", "3.5.2", "3.5.3", "4.0.0"):
                if (major, version) not in expected:
                    self.assertEqual(console.function_snapshot(CONTRACT, major, version), {})
        production = console.function_snapshot(CONTRACT, 16, "3.4.2")
        compatibility = console.function_snapshot(CONTRACT, 16, "3.4.3")
        self.assertEqual(production["audited_postgresql_version_num"], 160015)
        self.assertNotEqual(
            production["postgis"]["catalog_sha256"], compatibility["postgis"]["catalog_sha256"]
        )
        self.assertEqual(production["core"], compatibility["core"])
        self.assertEqual(production["plpgsql"], compatibility["plpgsql"])

    def test_contract_is_explicit_and_versioned(self):
        console.validate_contract(CONTRACT)
        self.assertEqual(sum(len(v["columns"]) for v in CONTRACT["views"].values()), 31)
        for name, view in CONTRACT["views"].items():
            definition = console.definition(name, view)
            self.assertNotIn("*", definition)
            self.assertNotIn("(", definition)
            self.assertEqual(view["owner_select_columns"], [c["name"] for c in view["columns"]])
        self.assertEqual(CONTRACT["version"], 4)
        self.assertEqual(
            set(CONTRACT["database_temp_roles"]),
            {"uranus_reader", "admin_user", "admin_migrator", "admin_auth_operator"},
        )
        for roles in ([], [console.READER], [console.OWNER], ["public"], ["a", "a"], ["bad;sql"]):
            with (
                self.subTest(roles=roles),
                self.assertRaisesRegex(ValueError, "invalid_database_temp_roles"),
            ):
                console.validate_contract({**CONTRACT, "database_temp_roles": roles})
        self.assertNotIn("user", CONTRACT["views"])
        self.assertNotIn("organization_member_link", CONTRACT["views"])

    def test_no_dsn_fallback_and_older_release_does_not_require_console(self):
        original = {"DATABASE_URL": "source-secret", "ADMIN_DATABASE_URL": "admin-secret"}
        with self.assertRaisesRegex(ValueError, "missing_or_invalid"):
            console.console_password(None)
        for dsn in (
            "postgresql+asyncpg://uranus_reader:" + PASSWORD + "@localhost/oklab",
            "postgresql+asyncpg://admin_user:" + PASSWORD + "@localhost/oklab",
            "postgresql+asyncpg://uranus_console_reader:" + PASSWORD + "@elsewhere/oklab",
            "postgresql+asyncpg://uranus_console_reader:" + PASSWORD + "@localhost/oklab?options=x",
        ):
            with self.assertRaises(ValueError):
                console.console_password(dsn)
        with self.assertRaisesRegex(Exception, "Missing SQL_CONSOLE_DATABASE_URL"):
            filters.console_environment(original, {}, ["SQL_CONSOLE_DATABASE_URL"])
        self.assertEqual(filters.console_environment(original, {}, []), original)
        dsn = "postgresql+asyncpg://uranus_console_reader:" + PASSWORD + "@localhost/oklab"
        adopted = filters.console_environment(
            original, {"SQL_CONSOLE_DATABASE_URL": dsn}, ["SQL_CONSOLE_DATABASE_URL"]
        )
        self.assertEqual(adopted["SQL_CONSOLE_DATABASE_URL"], dsn)
        self.assertEqual(console.console_password(dsn), PASSWORD)
        self.assertNotIn("SQL_CONSOLE_DATABASE_URL", filters.console_environment(adopted, {}, []))
        with self.assertRaisesRegex(Exception, "no automatic rotation"):
            filters.console_environment(
                adopted, {"SQL_CONSOLE_DATABASE_URL": "different"}, ["SQL_CONSOLE_DATABASE_URL"]
            )

    def test_console_archive_survives_older_releases_without_replacing_secrets(self):
        existing = {"ADMIN_MIGRATION_DATABASE_URL": "operator-fixture"}
        source = {"SQL_CONSOLE_DATABASE_URL": "console-fixture"}
        archived = filters.archive_console(existing, source, existing)
        self.assertEqual(archived, {**existing, **source})
        self.assertEqual(filters.archive_console({}, {}, archived), archived)
        self.assertEqual(filters.archive_console(existing, source, archived), archived)
        with self.assertRaisesRegex(Exception, "no automatic rotation"):
            filters.archive_console(existing, {"SQL_CONSOLE_DATABASE_URL": "different"}, archived)

    def test_scram_adoption_preserves_password_and_rejects_rotation(self):
        verifier = console.scram(PASSWORD)
        self.assertTrue(console.password_matches(PASSWORD, verifier))
        self.assertFalse(console.password_matches("different", verifier))
        self.assertFalse(console.password_matches(PASSWORD, "md5-unreviewed"))

    def test_console_steps_precede_build_activation_and_do_not_enter_recovery(self):
        tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
        includes = [
            t["ansible.builtin.import_tasks"] for t in tasks if "ansible.builtin.import_tasks" in t
        ]
        self.assertLess(includes.index("preflight.yml"), includes.index("sql_console_plan.yml"))
        for before, after in (
            ("sql_console_plan.yml", "sql_console_provision.yml"),
            ("sql_console_provision.yml", "sql_console_verify.yml"),
            ("sql_console_verify.yml", "deploy.yml"),
        ):
            self.assertLess(includes.index(before), includes.index(after))
        for task in tasks:
            if task.get("ansible.builtin.import_tasks") in {
                "sql_console_provision.yml",
                "sql_console_verify.yml",
            }:
                self.assertIn("not ansible_check_mode", task["when"])
                self.assertIn("ua_action == 'deploy'", task["when"])
        provision = yaml.safe_load((ROLE / "tasks/sql_console_provision.yml").read_text())
        self.assertIn(
            "ua_sql_console_provision_approved is sameas true",
            provision[0]["ansible.builtin.assert"]["that"],
        )
        self.assertTrue(provision[1]["no_log"])
        self.assertFalse(provision[1]["diff"])
        for name in ("activate.yml", "system_recovery.yml"):
            self.assertNotIn("sql_console", (ROLE / "tasks" / name).read_text())


@unittest.skipUnless(TEST_URL, "No explicitly disposable ANSIBLE_TEST_DATABASE_URL supplied")
class ConsoleDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = urlsplit(TEST_URL)
        if (
            url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or not re.fullmatch(r"/[a-z][a-z0-9_]*_test", url.path)
            or url.query
            or url.fragment
        ):
            raise RuntimeError("Refuse non-local or non-test database")
        cls.parent = psycopg2.connect(TEST_URL)
        cls.parent.autocommit = True
        cls.database = url.path[1:-5] + "_console_test"
        cls.created_app_roles = []
        with cls.parent.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname IN (%s,%s)", (console.OWNER, console.READER)
            )
            if cur.fetchone():
                raise RuntimeError("Refuse pre-existing console roles")
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (cls.database,))
            if cur.fetchone():
                raise RuntimeError("Refuse pre-existing console fixture database")
            for role in CONTRACT["database_temp_roles"]:
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
                if not cur.fetchone():
                    cur.execute(
                        sql.SQL("CREATE ROLE {} LOGIN NOINHERIT").format(sql.Identifier(role))
                    )
                    cls.created_app_roles.append(role)
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(cls.database)
                )
            )
        cls.connection_args = {
            **cls.parent.get_dsn_parameters(),
            "dbname": cls.database,
            "password": unquote(url.password or ""),
        }
        cls.conn = psycopg2.connect(**cls.connection_args)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION postgis")
            cur.execute("CREATE SCHEMA uranus; CREATE SCHEMA admin")
            cur.execute(
                "CREATE TYPE uranus.event_release_status AS ENUM ('draft','inherited','released')"
            )
            for name, view in CONTRACT["views"].items():
                columns = sql.SQL(", ").join(
                    sql.SQL("{} {}").format(sql.Identifier(c["name"]), sql.SQL(c["type"]))
                    for c in view["columns"]
                )
                cur.execute(
                    sql.SQL("CREATE TABLE uranus.{} ({})").format(sql.Identifier(name), columns)
                )
            cur.execute("ALTER TABLE uranus.organization ADD api_import_token text")
            cur.execute('CREATE TABLE uranus."user" (password_hash text, activate_token text)')
            cur.execute("CREATE TABLE uranus.organization_member_link (accept_token text)")
            cur.execute("CREATE TABLE uranus.password_reset (token text)")
            cur.execute("CREATE TABLE admin.auth_account (password_hash text)")
            cur.execute("INSERT INTO uranus.organization_member_link VALUES ('fixture-secret')")
            cur.execute(
                "INSERT INTO uranus.event_date (uuid,start_date) VALUES "
                "('00000000-0000-0000-0000-000000000001','2026-09-20')"
            )
            # These are isolated FIXTURE defaults, never deployment operations. Separate
            # tests below exercise the versioned PUBLIC TEMP migration and blockers.
            cur.execute(
                sql.SQL("REVOKE TEMPORARY, CREATE ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(cls.database)
                )
            )
            for role in CONTRACT["database_temp_roles"]:
                cur.execute(
                    sql.SQL("GRANT TEMPORARY ON DATABASE {} TO {}").format(
                        sql.Identifier(cls.database), sql.Identifier(role)
                    )
                )
        cls.conn.autocommit = False

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        with cls.parent.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(cls.database)))
            for role in cls.created_app_roles:
                cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        cls.parent.close()

    def setUp(self):
        self.boundary = console.Boundary(self.conn, CONTRACT)
        self.boundary.execute("SET LOCAL search_path=pg_catalog")

    def tearDown(self):
        self.conn.rollback()
        # Only the subprocess fixture test commits. Cleanup its own known console roles.
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,))
            committed_console = bool(cur.fetchone())
            cur.execute("DROP SCHEMA IF EXISTS uranus_console CASCADE")
            for role in (console.READER, console.OWNER):
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
                if cur.fetchone():
                    cur.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                    cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            cur.execute(
                sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(self.database)
                )
            )
            for role in CONTRACT["database_temp_roles"]:
                cur.execute(
                    sql.SQL("GRANT TEMPORARY ON DATABASE {} TO {}").format(
                        sql.Identifier(self.database), sql.Identifier(role)
                    )
                )
            if committed_console:
                # Restore the stock ACLs only after subprocess tests that committed.
                # No fixture pre-hardening: subsequent tests see normal PostGIS again.
                cur.execute("SET LOCAL search_path=pg_catalog")
                snapshot = self.installed_snapshot()
                for function in console.function_catalog(self.conn):
                    entry = (
                        snapshot.get(function["extension"] or "core", {})
                        .get("restricted_functions", {})
                        .get(function["signature"])
                    )
                    if entry and entry["public_execute"]:
                        target = sql.SQL("{}.{}({})").format(
                            sql.Identifier(function["schema"]),
                            sql.Identifier(function["name"]),
                            sql.SQL(function["arguments"]),
                        )
                        cur.execute(
                            sql.SQL("GRANT EXECUTE ON FUNCTION {} TO PUBLIC").format(target)
                        )
                        cur.execute(
                            sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM {}").format(
                                target,
                                sql.SQL(", ").join(
                                    map(sql.Identifier, CONTRACT["database_temp_roles"])
                                ),
                            )
                        )
        self.conn.commit()

    def provision(self):
        report = self.boundary.inspect(PASSWORD)
        self.assertEqual(report["blockers"], [], report)
        try:
            self.assertTrue(self.boundary.provision(PASSWORD))
        except ValueError:
            self.fail(str(self.boundary.report()))
        self.assertEqual(self.boundary.inspect(PASSWORD)["changes_planned"], [])

    def denied(self, query):
        with self.conn.cursor() as cur:
            cur.execute("SAVEPOINT attack")
            cur.execute("SET LOCAL SESSION AUTHORIZATION uranus_console_reader")
            try:
                cur.execute(query)
            except psycopg2.Error as exc:
                self.assertEqual(exc.pgcode, "42501")
            else:
                self.fail("Reader attack unexpectedly succeeded: " + query)
            finally:
                cur.execute("ROLLBACK TO SAVEPOINT attack")

    def test_plan_read_only_apply_and_second_apply_changed_zero(self):
        self.conn.rollback()
        self.boundary.execute("SET TRANSACTION READ ONLY")
        report = self.boundary.inspect()
        self.assertIn("would create role uranus_console_owner", report["changes_planned"])
        self.assertIn("would create role uranus_console_reader", report["changes_planned"])
        self.assertIn("would create schema uranus_console", report["changes_planned"])
        self.assertIn("would set role search_path", report["changes_planned"])
        self.assertEqual(
            self.boundary.rows("SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,)), []
        )
        self.conn.rollback()
        self.boundary.execute("SET LOCAL search_path=pg_catalog")
        self.provision()
        self.assertFalse(self.boundary.provision(PASSWORD))

    def test_alias_expression_json_cte_and_subquery_attacks(self):
        self.provision()
        for query in (
            "SELECT accept_token FROM uranus.organization_member_link",
            "SELECT accept_token AS harmless FROM uranus.organization_member_link",
            "SELECT upper(accept_token) FROM uranus.organization_member_link",
            "SELECT to_jsonb(m) FROM uranus.organization_member_link m",
            "WITH q AS (SELECT accept_token FROM uranus.organization_member_link) SELECT * FROM q",
            "SELECT * FROM (SELECT accept_token FROM uranus.organization_member_link) q",
            'SELECT password_hash FROM uranus."user"',
            'SELECT activate_token FROM uranus."user"',
            "SELECT api_import_token FROM uranus.organization",
            "SELECT token FROM uranus.password_reset",
            "SELECT password_hash FROM admin.auth_account",
        ):
            with self.subTest(query=query):
                self.denied(query)

    def test_safe_views_and_new_source_column_not_exposed(self):
        self.provision()
        self.boundary.execute("ALTER TABLE uranus.event_date ADD new_secret text")
        self.assertEqual(self.boundary.inspect()["blockers"], [])
        with self.conn.cursor() as cur:
            cur.execute("SET LOCAL SESSION AUTHORIZATION uranus_console_reader")
            for name, view in CONTRACT["views"].items():
                cur.execute(sql.SQL("SELECT * FROM uranus_console.{}").format(sql.Identifier(name)))
                self.assertEqual(
                    [d.name for d in cur.description], [c["name"] for c in view["columns"]]
                )
            cur.execute("SELECT to_jsonb(v) FROM uranus_console.event_date v")
            self.assertNotIn("new_secret", cur.fetchone()[0])

    def test_writes_temp_and_role_switch_fail_without_read_only_transaction(self):
        self.provision()
        for query in (
            "INSERT INTO uranus_console.event_date (uuid) VALUES (NULL)",
            "UPDATE uranus_console.event_date SET all_day=true",
            "DELETE FROM uranus_console.event_date",
            "INSERT INTO uranus.event_date (uuid) VALUES (NULL)",
            "CREATE TABLE uranus_console.x(id int)",
            "CREATE TABLE public.x(id int)",
            "CREATE TEMP TABLE x(id int)",
            "SET ROLE uranus_console_owner",
            "SET ROLE postgres",
        ):
            with self.subTest(query=query):
                self.denied(query)
        self.assertFalse(
            self.boundary.rows(
                "SELECT has_database_privilege(%s,current_database(),'TEMPORARY')",
                (console.READER,),
            )[0][0]
        )

    def test_unsafe_attributes_memberships_and_grants_fail_closed(self):
        self.provision()
        if not self.boundary.rows("SELECT 1 FROM pg_roles WHERE rolname='admin_user'"):
            self.boundary.execute("CREATE ROLE admin_user LOGIN")
        for query in (
            "ALTER ROLE uranus_console_owner LOGIN",
            "ALTER ROLE uranus_console_owner SUPERUSER",
            "ALTER ROLE uranus_console_reader REPLICATION",
            "GRANT admin_user TO uranus_console_reader",
            "ALTER ROLE uranus_console_reader SUPERUSER",
            "ALTER ROLE uranus_console_reader CREATEROLE",
            "ALTER ROLE uranus_console_reader CREATEDB",
            "ALTER ROLE uranus_console_reader BYPASSRLS",
            "GRANT uranus_console_owner TO uranus_console_reader",
            "GRANT postgres TO uranus_console_reader",
            "GRANT SELECT ON uranus.organization TO uranus_console_reader",
            "GRANT SELECT(api_import_token) ON uranus.organization TO uranus_console_reader",
            "GRANT UPDATE(uuid) ON uranus.event TO uranus_console_reader",
            "GRANT SELECT ON uranus.event TO uranus_console_owner",
            "GRANT SELECT(api_import_token) ON uranus.organization TO uranus_console_owner",
            "GRANT SELECT ON uranus_console.event TO uranus_console_reader WITH GRANT OPTION",
            "ALTER DEFAULT PRIVILEGES FOR ROLE uranus_console_owner GRANT "
            "SELECT ON TABLES TO uranus_console_reader",
            "GRANT USAGE ON SCHEMA admin TO uranus_console_reader",
            "GRANT USAGE ON SCHEMA uranus_console TO PUBLIC",
            "GRANT SELECT ON uranus_console.event TO PUBLIC",
            "GRANT SELECT ON pg_catalog.pg_authid TO uranus_console_reader",
            "GRANT SELECT(stavalues1) ON pg_catalog.pg_statistic TO PUBLIC",
            "GRANT EXECUTE ON FUNCTION pg_catalog.sqrt(double precision) "
            "TO uranus_console_reader WITH GRANT OPTION",
            "GRANT USAGE ON TYPE uranus.event_release_status "
            "TO uranus_console_reader WITH GRANT OPTION",
            "GRANT SET ON PARAMETER session_replication_role TO uranus_console_reader",
        ):
            with self.subTest(query=query):
                self.boundary.execute("SAVEPOINT unsafe")
                self.boundary.execute(query)
                self.assertTrue(self.boundary.inspect()["blockers"])
                self.boundary.execute("ROLLBACK TO SAVEPOINT unsafe")
        if self.conn.server_version >= 170000:
            self.boundary.execute("GRANT MAINTAIN ON uranus.event TO uranus_console_reader")
            self.assertTrue(self.boundary.inspect()["blockers"])

    def public_temp_fixture(self):
        for role in CONTRACT["database_temp_roles"]:
            self.boundary.execute(
                sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM {}").format(
                    sql.Identifier(self.database), sql.Identifier(role)
                )
            )
        self.boundary.execute(
            sql.SQL("GRANT TEMPORARY ON DATABASE {} TO PUBLIC").format(
                sql.Identifier(self.database)
            )
        )

    def database_acl(self):
        return self.boundary.rows(
            "SELECT datacl::text FROM pg_database WHERE datname=current_database()"
        )

    def test_public_temp_safe_migration_preserves_app_roles_and_other_privileges(self):
        self.public_temp_fixture()
        before = self.database_acl()
        report = self.boundary.inspect()
        self.assertTrue(report["public_temp"])
        self.assertEqual(report["blockers"], [])
        self.assertEqual(
            report["temp_inventory"]["public_consumers"], sorted(CONTRACT["database_temp_roles"])
        )
        self.assertEqual(
            report["temp_reconcile"],
            {
                "allowed": True,
                "would_grant_explicit": CONTRACT["database_temp_roles"],
                "would_revoke_public_temp": True,
            },
        )
        self.assertEqual(self.database_acl(), before)
        # Pre-existing direct TEMP on an approved role is already in the desired state.
        role = CONTRACT["database_temp_roles"][0]
        self.boundary.execute(
            sql.SQL("GRANT TEMPORARY ON DATABASE {} TO {}").format(
                sql.Identifier(self.database), sql.Identifier(role)
            )
        )
        self.assertNotIn(role, self.boundary.inspect()["temp_reconcile"]["would_grant_explicit"])
        attributes = self.boundary.rows(
            "SELECT oid,rolname,rolcanlogin,rolinherit FROM pg_roles ORDER BY oid"
        )
        other_acl = self.boundary.rows("""SELECT grantee,privilege_type,is_grantable
            FROM pg_database d, LATERAL aclexplode(datacl) a
            WHERE datname=current_database() AND privilege_type<>'TEMPORARY' ORDER BY 1,2""")
        self.provision()
        self.assertFalse(self.boundary.inspect()["public_temp"])
        self.assertFalse(self.boundary.provision(PASSWORD))
        for role in CONTRACT["database_temp_roles"] + [console.READER, console.OWNER]:
            self.assertEqual(
                self.boundary.rows(
                    "SELECT has_database_privilege(%s,current_database(),'TEMPORARY')", (role,)
                )[0][0],
                role in CONTRACT["database_temp_roles"],
            )
        self.assertEqual(
            self.boundary.rows(
                """SELECT grantee,privilege_type,is_grantable
            FROM pg_database d, LATERAL aclexplode(datacl) a
            WHERE datname=current_database() AND privilege_type<>'TEMPORARY'
            AND grantee<>(SELECT oid FROM pg_roles WHERE rolname=%s) ORDER BY 1,2""",
                (console.READER,),
            ),
            other_acl,
        )
        self.assertEqual(
            self.boundary.rows(
                "SELECT oid,rolname,rolcanlogin,rolinherit FROM pg_roles "
                "WHERE rolname NOT IN (%s,%s) ORDER BY oid",
                (console.READER, console.OWNER),
            ),
            attributes,
        )
        self.denied("CREATE TEMP TABLE test(id int)")

    def test_unknown_public_temp_consumer_blocks_without_acl_changes(self):
        self.public_temp_fixture()
        self.boundary.execute("CREATE ROLE reporting_user LOGIN")
        before = self.database_acl()
        report = self.boundary.inspect()
        self.assertIn("unexpected_public_temp_consumer:reporting_user", report["blockers"])
        self.assertFalse(report["temp_reconcile"]["allowed"])
        with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
            self.boundary.provision(PASSWORD)
        self.assertEqual(self.database_acl(), before)
        self.assertEqual(
            self.boundary.rows("SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,)), []
        )

    def test_direct_unauthorized_temp_and_membership_paths_block(self):
        self.boundary.execute("CREATE ROLE reporting_user LOGIN")
        for grantee in ("reporting_user", "temp_group"):
            self.boundary.execute("SAVEPOINT temp_path")
            if grantee == "temp_group":
                self.boundary.execute("CREATE ROLE temp_group NOLOGIN")
                self.boundary.execute("GRANT temp_group TO reporting_user")
            self.boundary.execute(
                sql.SQL("GRANT TEMPORARY ON DATABASE {} TO {}").format(
                    sql.Identifier(self.database), sql.Identifier(grantee)
                )
            )
            before = self.database_acl()
            report = self.boundary.inspect()
            self.assertIn("unexpected_direct_temp_grantee:" + grantee, report["blockers"])
            if grantee == "temp_group":
                self.assertIn(
                    "unexpected_temp_membership_path:reporting_user:temp_group", report["blockers"]
                )
                self.assertIn(
                    dict(role="reporting_user", source="temp_group", inherited=True, set_role=True),
                    report["temp_inventory"]["membership_paths"],
                )
            with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                self.boundary.provision(PASSWORD)
            self.assertEqual(self.database_acl(), before)
            self.boundary.execute("ROLLBACK TO SAVEPOINT temp_path")
        # Even NOINHERIT / indirect SET ROLE paths to approved TEMP are not adopted.
        self.boundary.execute("ALTER ROLE reporting_user NOINHERIT")
        self.boundary.execute("CREATE ROLE temp_bridge NOLOGIN NOINHERIT")
        self.boundary.execute(
            sql.SQL("GRANT {} TO temp_bridge").format(
                sql.Identifier(CONTRACT["database_temp_roles"][0])
            )
        )
        self.boundary.execute("GRANT temp_bridge TO reporting_user")
        report = self.boundary.inspect()
        self.assertIn(
            "unexpected_temp_membership_path:reporting_user:" + CONTRACT["database_temp_roles"][0],
            report["blockers"],
        )
        self.assertFalse(
            self.boundary.rows(
                "SELECT has_database_privilege('reporting_user',current_database(),'TEMPORARY')"
            )[0][0]
        )

    def test_public_temp_with_existing_console_roles_and_direct_temp_attack(self):
        self.provision()
        self.public_temp_fixture()
        self.assertEqual(self.boundary.inspect()["blockers"], [])
        self.assertTrue(self.boundary.provision(PASSWORD))
        for role in (console.READER, console.OWNER):
            self.boundary.execute("SAVEPOINT console_temp")
            self.public_temp_fixture()
            self.boundary.execute(
                sql.SQL("GRANT TEMPORARY ON DATABASE {} TO {}").format(
                    sql.Identifier(self.database), sql.Identifier(role)
                )
            )
            self.assertIn(
                "unexpected_direct_temp_grantee:" + role, self.boundary.inspect()["blockers"]
            )
            with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                self.boundary.provision(PASSWORD)
            self.boundary.execute("ROLLBACK TO SAVEPOINT console_temp")

    def test_temp_rollback_after_revoke_before_final_verification(self):
        self.public_temp_fixture()
        self.conn.commit()
        before = self.database_acl()
        self.conn.rollback()
        execute = self.boundary.execute
        seen = []

        def fail_after_revoke(query, args=()):
            execute(query, args)
            if isinstance(query, sql.Composed) and query.as_string(self.conn).startswith(
                "REVOKE TEMPORARY"
            ):
                seen.append(True)
                self.assertFalse(
                    self.boundary.rows(
                        "SELECT has_database_privilege('public',current_database(),'TEMPORARY')"
                    )[0][0]
                )
                raise ValueError("injected_after_revoke")

        with self.assertRaisesRegex(ValueError, "injected_after_revoke"), self.conn:
            with patch.object(self.boundary, "execute", side_effect=fail_after_revoke):
                self.boundary.provision(PASSWORD)
        self.assertEqual(seen, [True])
        self.assertEqual(self.database_acl(), before)
        self.assertTrue(self.boundary.inspect()["public_temp"])
        self.assertEqual(
            self.boundary.rows(
                "SELECT 1 FROM pg_roles WHERE rolname IN (%s,%s)", (console.READER, console.OWNER)
            ),
            [],
        )

    def test_temp_contract_missing_roles_grant_options_and_owner_dependency(self):
        self.provision()
        self.public_temp_fixture()
        app_role = CONTRACT["database_temp_roles"][0]
        cases = (
            (
                sql.SQL("ALTER ROLE {} NOLOGIN").format(sql.Identifier(app_role)),
                "missing_temp_contract_login_role:" + app_role,
            ),
            (
                sql.SQL("GRANT TEMPORARY ON DATABASE {} TO {} WITH GRANT OPTION").format(
                    sql.Identifier(self.database), sql.Identifier(app_role)
                ),
                "unexpected_temp_grant_option:" + app_role,
            ),
        )
        for query, blocker in cases:
            self.boundary.execute("SAVEPOINT temp_contract")
            self.boundary.execute(query)
            self.assertIn(blocker, self.boundary.inspect()["blockers"])
            with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                self.boundary.provision(PASSWORD)
            self.boundary.execute("ROLLBACK TO SAVEPOINT temp_contract")
        self.boundary.execute("CREATE ROLE fixture_database_owner LOGIN")
        self.boundary.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO fixture_database_owner").format(
                sql.Identifier(self.database)
            )
        )
        # The intrinsic database owner retains its own ACL, without any new grant.
        self.assertEqual(self.boundary.inspect()["blockers"], [])
        self.boundary.execute(
            sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM fixture_database_owner").format(
                sql.Identifier(self.database)
            )
        )
        self.assertIn(
            "database_owner_temp_depends_on_public:fixture_database_owner",
            self.boundary.inspect()["blockers"],
        )

    def test_real_module_failure_rolls_back_temp_and_console_objects(self):
        self.public_temp_fixture()
        self.conn.commit()
        before = self.database_acl()
        before_functions = self.function_acls()
        self.conn.rollback()
        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory) / "console_failure_fixture.py"
            source = self.fixture_module()
            # Inject a failure at the real post-apply verification boundary. Production
            # has no failure/bypass switch. The module's own finally/close must rollback.
            needle = "        self.inspect(password)\n        require(\n"
            self.assertEqual(source.count(needle), 1)
            source = source.replace(
                needle,
                '        require(self.rows("SELECT has_database_privilege('
                "'public',current_database(),'TEMPORARY')\")[0][0], "
                '"injected_after_revoke")\n' + needle,
            )
            module.write_text(source)
            result = subprocess.run(
                [sys.executable, str(module)],
                input=json.dumps(
                    {
                        "ANSIBLE_MODULE_ARGS": {
                            "state": "provision",
                            "contract": CONTRACT,
                            "dsn": "postgresql+asyncpg://uranus_console_reader:"
                            + PASSWORD
                            + "@localhost/"
                            + self.database,
                        }
                    }
                ),
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("boundary rejected", json.loads(result.stdout)["msg"])
            self.assertNotIn(PASSWORD, result.stdout + result.stderr)
        self.assertEqual(self.database_acl(), before)
        self.assertEqual(self.function_acls(), before_functions)
        self.assertTrue(self.boundary.inspect()["public_temp"])
        self.assertEqual(
            self.boundary.rows(
                "SELECT 1 FROM pg_roles WHERE rolname IN (%s,%s)", (console.READER, console.OWNER)
            ),
            [],
        )
        self.assertEqual(
            self.boundary.rows("SELECT 1 FROM pg_namespace WHERE nspname=%s", (console.SCHEMA,)), []
        )

    def test_new_roles_noinherit_and_existing_inherit_roles_refused(self):
        self.provision()
        self.assertEqual(
            self.boundary.rows(
                "SELECT rolinherit FROM pg_roles WHERE rolname IN (%s,%s)",
                (console.READER, console.OWNER),
            ),
            [(False,), (False,)],
        )
        for role in (console.READER, console.OWNER):
            self.boundary.execute("SAVEPOINT inherit_role")
            self.boundary.execute(sql.SQL("ALTER ROLE {} INHERIT").format(sql.Identifier(role)))
            before = self.database_acl()
            self.assertIn("unsafe_role_inherit:" + role, self.boundary.inspect()["blockers"])
            with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                self.boundary.provision(PASSWORD)
            self.assertTrue(
                self.boundary.rows("SELECT rolinherit FROM pg_roles WHERE rolname=%s", (role,))[0][
                    0
                ]
            )
            self.assertEqual(self.database_acl(), before)
            self.boundary.execute("ROLLBACK TO SAVEPOINT inherit_role")

    def test_unexpected_object_not_dropped(self):
        self.provision()
        for query in (
            "CREATE VIEW uranus_console.foreign_view AS SELECT 1 AS value",
            "CREATE FUNCTION uranus_console.foreign_function() RETURNS "
            "int LANGUAGE sql AS 'SELECT 1'",
            "CREATE TYPE uranus_console.foreign_type AS ENUM ('x')",
            'CREATE COLLATION uranus_console.foreign_collation FROM pg_catalog."C"',
        ):
            self.boundary.execute("SAVEPOINT unexpected")
            self.boundary.execute(query)
            self.assertIn("unexpected_sql_console_object", self.boundary.inspect()["blockers"])
            with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                self.boundary.provision(PASSWORD)
            self.boundary.execute("ROLLBACK TO SAVEPOINT unexpected")

    def test_view_definition_drift_planned_and_reconciled(self):
        self.provision()
        self.boundary.execute(
            "CREATE OR REPLACE VIEW uranus_console.organization AS SELECT "
            "uuid,created_at,modified_at,holding_org_uuid,NOT nonprofit "
            "AS nonprofit FROM uranus.organization"
        )
        report = self.boundary.inspect()
        self.assertIn("would update view organization", report["changes_planned"])
        self.assertEqual(report["blockers"], [])
        self.assertTrue(self.boundary.provision(PASSWORD))
        self.assertFalse(self.boundary.provision(PASSWORD))

    def test_source_type_drift_and_sensitive_column_absence_block(self):
        self.boundary.execute("ALTER TABLE uranus.event ALTER COLUMN min_price TYPE numeric")
        self.boundary.execute("ALTER TABLE uranus.password_reset DROP COLUMN token")
        report = self.boundary.inspect()
        self.assertIn("source_column_type_mismatch:event.min_price", report["blockers"])
        self.assertIn("sensitive_source_column_missing:password_reset.token", report["blockers"])

    def test_function_extension_large_object_and_sequence_paths(self):
        self.provision()
        for query in (
            "CREATE FUNCTION public.escalation() RETURNS int LANGUAGE sql "
            "SECURITY DEFINER AS 'SELECT 1'",
            "CREATE FUNCTION public.unreviewed() RETURNS int LANGUAGE sql VOLATILE AS 'SELECT 1'",
            "GRANT EXECUTE ON FUNCTION pg_catalog.lo_create(oid) TO uranus_console_reader",
            "CREATE FUNCTION public.stable_wrapper() RETURNS int LANGUAGE sql STABLE AS 'SELECT 1'",
            "CREATE EXTENSION dblink WITH SCHEMA public",
            "CREATE FOREIGN DATA WRAPPER fixture_fdw; "
            "GRANT USAGE ON FOREIGN DATA WRAPPER fixture_fdw TO uranus_console_reader",
            "CREATE FOREIGN DATA WRAPPER fixture_fdw; "
            "CREATE SERVER fixture_server FOREIGN DATA WRAPPER fixture_fdw; "
            "GRANT USAGE ON FOREIGN SERVER fixture_server TO uranus_console_reader",
            "CREATE FOREIGN DATA WRAPPER fixture_fdw; "
            "CREATE SERVER fixture_server FOREIGN DATA WRAPPER fixture_fdw; "
            "CREATE USER MAPPING FOR PUBLIC SERVER fixture_server",
            "CREATE SEQUENCE uranus.secret_sequence; GRANT USAGE ON "
            "uranus.secret_sequence TO uranus_console_reader",
            "SELECT lo_create(7654321); GRANT SELECT ON LARGE OBJECT "
            "7654321 TO uranus_console_reader",
        ):
            with self.subTest(query=query):
                self.boundary.execute("SAVEPOINT path")
                self.boundary.execute(query)
                self.assertTrue(self.boundary.inspect()["blockers"])
                self.boundary.execute("ROLLBACK TO SAVEPOINT path")

    def test_missing_grants_are_reconciled_and_password_never_rotated(self):
        self.provision()
        self.boundary.execute("REVOKE SELECT ON uranus_console.event FROM uranus_console_reader")
        self.boundary.execute("REVOKE SELECT(uuid) ON uranus.event FROM uranus_console_owner")
        self.assertTrue(self.boundary.provision(PASSWORD))
        self.assertIn(
            "console_password_mismatch_no_automatic_rotation",
            self.boundary.inspect("different")["blockers"],
        )

    def installed_snapshot(self, contract=CONTRACT):
        version = self.boundary.rows("SELECT extversion FROM pg_extension WHERE extname='postgis'")[
            0
        ][0]
        return console.function_snapshot(contract, self.conn.server_version // 10000, version)

    def function_acls(self):
        return self.boundary.rows("SELECT oid,proacl::text FROM pg_proc ORDER BY oid")

    def test_normal_postgis_execute_plan_preservation_and_idempotency(self):
        before = self.function_acls()
        report = self.boundary.inspect()
        self.assertEqual(report["blockers"], [])
        snapshot = self.installed_snapshot()
        # CI binds this test to the actual server/image combination, never a mocked
        # extversion. The production baseline runs on real Ubuntu PG 16.15/3.4.2.
        self.assertEqual(self.conn.server_version, snapshot["audited_postgresql_version_num"])
        expected_stack = os.environ.get("ANSIBLE_TEST_EXPECTED_STACK")
        if expected_stack:
            self.assertEqual(
                f"{self.conn.server_version}/{snapshot['postgis']['version']}", expected_stack
            )
        expected = {
            sig
            for group in ("core", "postgis")
            for sig, function in snapshot[group]["restricted_functions"].items()
            if function["public_execute"]
        }
        changes = report["execute_reconcile"]["changes"]
        self.assertEqual({c["signature"] for c in changes}, expected)
        for change in changes:
            self.assertEqual(change["would_grant_explicit"], CONTRACT["database_temp_roles"])
            self.assertTrue(change["would_revoke_public_execute"])
        self.assertEqual(self.function_acls(), before)
        self.assertEqual(
            next(e for e in report["extensions"] if e["name"] == "plpgsql")["status"], "allowed"
        )
        self.assertEqual(
            next(e for e in report["extensions"] if e["name"] == "postgis")["status"],
            "reconcile_required",
        )
        self.provision()
        for signature in expected:
            rights = dict(
                self.boundary.rows(
                    """SELECT rolname,
                has_function_privilege(oid,%s,'EXECUTE') FROM pg_roles
                WHERE rolname=ANY(%s)""",
                    (signature, CONTRACT["database_temp_roles"] + [console.OWNER, console.READER]),
                )
            )
            self.assertEqual(
                rights,
                {
                    **dict.fromkeys(CONTRACT["database_temp_roles"], True),
                    console.OWNER: False,
                    console.READER: False,
                },
            )
        # Stock privileged grants survive; no app gains stock non-PUBLIC privileges.
        self.assertTrue(
            self.boundary.rows(
                "SELECT has_function_privilege('pg_monitor','pg_catalog.pg_ls_logdir()','EXECUTE')"
            )[0][0]
        )
        self.assertFalse(
            self.boundary.rows(
                "SELECT has_function_privilege('admin_user',"
                "'pg_catalog.pg_read_file(text)','EXECUTE')"
            )[0][0]
        )
        self.assertFalse(self.boundary.provision(PASSWORD))
        self.assertEqual(self.boundary.report()["execute_reconcile"]["changes"], [])
        self.assertTrue(
            all(
                e["status"] == "allowed" and e["blocked_functions"] == 0
                for e in self.boundary.report()["extensions"]
            )
        )

    def test_reviewed_postgis_function_and_standard_metadata_remain_usable(self):
        self.provision()
        self.boundary.execute("SAVEPOINT safe_postgis")
        self.boundary.execute("SET LOCAL SESSION AUTHORIZATION uranus_console_reader")
        self.assertEqual(self.boundary.rows("SELECT public.st_x(public.st_point(1,2))"), [(1.0,)])
        for name in ("spatial_ref_sys", "geometry_columns", "geography_columns"):
            self.assertTrue(
                self.boundary.rows(
                    "SELECT has_table_privilege(current_user,%s,'SELECT')", ("public." + name,)
                )[0][0]
            )
        self.assertEqual(self.boundary.rows("SHOW search_path"), [("pg_catalog",)])
        self.boundary.execute("ROLLBACK TO SAVEPOINT safe_postgis")

    def test_unknown_execute_consumer_blocks_without_acl_changes(self):
        self.boundary.execute("CREATE ROLE reporting_user LOGIN")
        before = self.function_acls()
        report = self.boundary.inspect()
        self.assertFalse(report["public_temp"])
        self.assertIn(
            "unexpected_execute_consumer:pg_catalog.set_config(text, text, boolean):reporting_user",
            report["blockers"],
        )
        inventory = next(
            f
            for f in report["execute_inventory"]
            if f["signature"] == "pg_catalog.set_config(text, text, boolean)"
        )
        self.assertIn("reporting_user", inventory["effective_login_roles"])
        self.assertFalse(report["execute_reconcile"]["allowed"])
        with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
            self.boundary.provision(PASSWORD)
        self.assertEqual(self.function_acls(), before)
        self.assertEqual(
            self.boundary.rows("SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,)), []
        )

    def test_direct_execute_grants_and_membership_paths_fail_closed(self):
        self.provision()
        cases = (
            (
                "CREATE ROLE reporting_user LOGIN; "
                "GRANT EXECUTE ON FUNCTION pg_catalog.lo_create(oid) TO reporting_user",
                "unexpected_function_grantee:pg_catalog.lo_create(oid):reporting_user",
            ),
            (
                "CREATE ROLE execute_group NOLOGIN; "
                "GRANT EXECUTE ON FUNCTION pg_catalog.lo_create(oid) TO execute_group",
                "unexpected_function_grantee:pg_catalog.lo_create(oid):execute_group",
            ),
            (
                "GRANT EXECUTE ON FUNCTION pg_catalog.pg_stat_reset() TO uranus_console_reader",
                "unexpected_function_grantee:pg_catalog.pg_stat_reset():uranus_console_reader",
            ),
            (
                "CREATE ROLE reporting_user LOGIN NOINHERIT; GRANT admin_user TO reporting_user",
                "unexpected_execute_membership_path:pg_catalog.lo_create(oid):reporting_user:admin_user",
            ),
            (
                "CREATE ROLE reporting_user LOGIN NOINHERIT; GRANT pg_monitor TO reporting_user",
                "unexpected_execute_membership_path:pg_catalog.pg_ls_logdir():reporting_user:pg_monitor",
            ),
        )
        for query, blocker in cases:
            with self.subTest(blocker=blocker):
                self.boundary.execute("SAVEPOINT execute_path")
                self.boundary.execute(query)
                before = self.function_acls()
                self.assertIn(blocker, self.boundary.inspect()["blockers"])
                with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                    self.boundary.provision(PASSWORD)
                self.assertEqual(self.function_acls(), before)
                self.boundary.execute("ROLLBACK TO SAVEPOINT execute_path")

    def test_restricted_calls_fail_with_insufficient_privilege(self):
        self.provision()
        for query in (
            "SELECT pg_catalog.lo_create(0)",
            "SELECT pg_catalog.lo_get(0)",
            "SELECT pg_catalog.pg_read_file('/nonexistent-fixture-file')",
            "SELECT pg_catalog.pg_ls_dir('/nonexistent-fixture-directory')",
            "SELECT pg_catalog.pg_cancel_backend(-1)",
            "SELECT pg_catalog.pg_terminate_backend(-1)",
            "SELECT pg_catalog.pg_reload_conf()",
            "SELECT pg_catalog.pg_stat_reset()",
            "SELECT pg_catalog.pg_stat_clear_snapshot()",
            "SELECT pg_catalog.pg_stat_force_next_flush()",
            "SELECT pg_catalog.pg_show_all_file_settings()",
            "SELECT pg_catalog.set_config('application_name','fixture',true)",
            "SELECT pg_catalog.pg_sleep(0)",
            "SELECT public.postgis_extensions_upgrade()",
            "SELECT public.st_fromflatgeobuftotable('public','forbidden',decode('','hex'))",
            "SELECT public.st_findextent('uranus','event','uuid')",
            "SELECT public.st_transformpipeline(public.st_point(1,2),'+proj=pipeline',4326)",
        ):
            with self.subTest(query=query):
                self.denied(query)
        for role in (console.READER, console.OWNER):
            self.boundary.execute("SAVEPOINT direct_console_execute")
            self.boundary.execute(
                sql.SQL(
                    "GRANT EXECUTE ON FUNCTION pg_catalog.set_config(text,text,boolean) TO {}"
                ).format(sql.Identifier(role))
            )
            self.assertIn(
                "unexpected_function_grantee:pg_catalog.set_config(text, text, boolean):" + role,
                self.boundary.inspect()["blockers"],
            )
            self.boundary.execute("ROLLBACK TO SAVEPOINT direct_console_execute")

    def test_unknown_functions_extensions_and_postgis_security_definer(self):
        cases = (
            (
                "CREATE FUNCTION public.unreviewed() RETURNS int LANGUAGE sql STABLE AS 'SELECT 1'",
                "unreviewed_function_path:public.unreviewed()",
            ),
            (
                "CREATE FUNCTION public.volatile_helper() RETURNS int "
                "LANGUAGE sql VOLATILE AS 'SELECT 1'",
                "unreviewed_function_path:public.volatile_helper()",
            ),
            (
                "CREATE FUNCTION public.postgis_like() RETURNS int "
                "LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'",
                "unreviewed_function_path:public.postgis_like()",
            ),
            (
                "ALTER FUNCTION public.st_x(public.geometry) SECURITY DEFINER",
                "unreviewed_function_path:public.st_x(public.geometry)",
            ),
            (
                "CREATE FUNCTION public.private_helper() RETURNS int LANGUAGE sql "
                "SECURITY DEFINER AS 'SELECT 1'; "
                "REVOKE EXECUTE ON FUNCTION public.private_helper() FROM PUBLIC",
                "unreviewed_function_path:public.private_helper()",
            ),
            ("CREATE EXTENSION dblink WITH SCHEMA public", "unreviewed_extension:dblink"),
        )
        for query, blocker in cases:
            with self.subTest(blocker=blocker):
                self.boundary.execute("SAVEPOINT function_unknown")
                self.boundary.execute(query)
                before = self.function_acls()
                report = self.boundary.inspect()
                self.assertIn(blocker, report["blockers"])
                if "dblink" in query:
                    self.assertTrue(
                        any(
                            b.startswith("unreviewed_function_path:public.dblink(")
                            for b in report["blockers"]
                        )
                    )
                with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                    self.boundary.provision(PASSWORD)
                self.assertEqual(self.function_acls(), before)
                self.boundary.execute("ROLLBACK TO SAVEPOINT function_unknown")

    def test_extension_catalog_version_owner_and_definition_drift(self):
        self.provision()
        cases = (
            *(
                (
                    "UPDATE pg_extension SET extversion='" + version + "' WHERE extname='postgis'",
                    "unreviewed_extension_version:postgis:" + version,
                )
                for version in ("3.4.4", "3.5.1", "3.5.3")
            ),
            (
                "UPDATE pg_extension SET extversion='4.0.0' WHERE extname='postgis'",
                "unreviewed_extension_version:postgis:4.0.0",
            ),
            (
                "UPDATE pg_extension SET extversion='3.99.0' WHERE extname='postgis'",
                "unreviewed_extension_version:postgis:3.99.0",
            ),
            (
                "UPDATE pg_extension SET extowner=(SELECT oid FROM pg_roles "
                "WHERE rolname='uranus_console_reader') WHERE extname='postgis'",
                "unreviewed_extension_schema_or_owner:postgis",
            ),
            (
                "ALTER FUNCTION public.st_x(public.geometry) OWNER TO uranus_console_owner",
                "unreviewed_function_owner_or_language:public.st_x(public.geometry)",
            ),
            (
                "ALTER FUNCTION public.st_x(public.geometry) VOLATILE",
                "unreviewed_function_catalog:postgis",
            ),
            (
                "ALTER EXTENSION postgis DROP FUNCTION public.st_x(public.geometry)",
                "unreviewed_function_path:public.st_x(public.geometry)",
            ),
            (
                "ALTER TABLE public.spatial_ref_sys ADD COLUMN surprise text",
                "unreviewed_postgis_metadata",
            ),
            (
                "CREATE FUNCTION pg_catalog.counterfeit_core() RETURNS int "
                "LANGUAGE sql IMMUTABLE AS 'SELECT 1'",
                "unreviewed_function_catalog:core",
            ),
        )
        for query, blocker in cases:
            with self.subTest(blocker=blocker):
                self.boundary.execute("SAVEPOINT function_drift")
                self.boundary.execute(query)
                self.assertIn(blocker, self.boundary.inspect()["blockers"])
                with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                    self.boundary.provision(PASSWORD)
                self.boundary.execute("ROLLBACK TO SAVEPOINT function_drift")

    def test_snapshot_catalog_and_restricted_definition_hashes_fail_closed(self):
        for group in ("core", "plpgsql", "postgis"):
            modified = copy.deepcopy(CONTRACT)
            self.installed_snapshot(modified)[group]["catalog_sha256"] = "0" * 64
            boundary = console.Boundary(self.conn, modified)
            before = self.function_acls()
            self.assertIn("unreviewed_function_catalog:" + group, boundary.inspect()["blockers"])
            with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                boundary.provision(PASSWORD)
            self.assertEqual(self.function_acls(), before)
        for group in ("core", "postgis"):
            modified = copy.deepcopy(CONTRACT)
            restricted = self.installed_snapshot(modified)[group]["restricted_functions"]
            signature = next(iter(restricted))
            restricted[signature]["definition_sha256"] = "0" * 64
            boundary = console.Boundary(self.conn, modified)
            self.assertIn(
                "unreviewed_function_definition:" + signature, boundary.inspect()["blockers"]
            )
            with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                boundary.provision(PASSWORD)

    def test_documented_production_baseline_preflight(self):
        snapshot = self.installed_snapshot()
        if snapshot["postgis"]["version"] != "3.4.2":
            # Other matrix entries exercise the same complete boundary below; do not
            # relabel their catalog as the production stack or introduce test skips.
            self.assertIn(snapshot["postgis"]["version"], {"3.4.3", "3.5.2"})
        else:
            self.assertEqual(self.conn.server_version, 160015)
            self.assertEqual(snapshot["postgis"]["functions"], 776)
            self.assertEqual(len(snapshot["postgis"]["restricted_functions"]), 95)
        self.public_temp_fixture()
        before_functions, before_database = self.function_acls(), self.database_acl()
        report = self.boundary.inspect()
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["temp_reconcile"]["would_revoke_public_temp"])
        self.assertTrue(report["execute_reconcile"]["changes"])
        self.assertEqual(
            (self.function_acls(), self.database_acl()), (before_functions, before_database)
        )
        self.provision()
        for role in (console.OWNER, console.READER):
            self.assertFalse(
                self.boundary.rows(
                    "SELECT has_database_privilege(%s,current_database(),'TEMPORARY')", (role,)
                )[0][0]
            )
            for group in ("core", "postgis"):
                for signature in snapshot[group]["restricted_functions"]:
                    self.assertFalse(
                        self.boundary.rows(
                            "SELECT has_function_privilege(%s,%s,'EXECUTE')", (role, signature)
                        )[0][0]
                    )
        self.assertFalse(self.boundary.provision(PASSWORD))

    def test_execute_only_adopts_recorded_stock_public_rights(self):
        for query, blocker in (
            (
                "GRANT EXECUTE ON FUNCTION pg_catalog.pg_read_file(text) TO PUBLIC",
                "unexpected_public_execute:pg_catalog.pg_read_file(text)",
            ),
            (
                "REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text,text,boolean) FROM PUBLIC",
                "missing_preserved_execute:pg_catalog.set_config(text, text, boolean)",
            ),
        ):
            with self.subTest(blocker=blocker):
                self.boundary.execute("SAVEPOINT execute_stock")
                self.boundary.execute(query)
                before = self.function_acls()
                self.assertIn(blocker, self.boundary.inspect()["blockers"])
                with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                    self.boundary.provision(PASSWORD)
                self.assertEqual(self.function_acls(), before)
                self.boundary.execute("ROLLBACK TO SAVEPOINT execute_stock")

    def test_execute_rollback_also_restores_temp_and_console_roles(self):
        self.public_temp_fixture()
        self.conn.commit()
        before_functions, before_database = self.function_acls(), self.database_acl()
        self.conn.rollback()
        execute = self.boundary.execute
        seen = []

        def fail_after_execute_revoke(query, args=()):
            execute(query, args)
            if isinstance(query, sql.Composed) and query.as_string(self.conn).startswith(
                "REVOKE EXECUTE"
            ):
                seen.append(True)
                self.assertNotEqual(self.function_acls(), before_functions)
                self.assertFalse(
                    self.boundary.rows(
                        "SELECT has_database_privilege('public',current_database(),'TEMPORARY')"
                    )[0][0]
                )
                raise ValueError("injected_after_execute_revoke")

        with self.assertRaisesRegex(ValueError, "injected_after_execute_revoke"), self.conn:
            with patch.object(self.boundary, "execute", side_effect=fail_after_execute_revoke):
                self.boundary.provision(PASSWORD)
        self.assertEqual(seen, [True])
        self.assertEqual(self.function_acls(), before_functions)
        self.assertEqual(self.database_acl(), before_database)
        self.assertEqual(
            self.boundary.rows(
                "SELECT 1 FROM pg_roles WHERE rolname IN (%s,%s)", (console.OWNER, console.READER)
            ),
            [],
        )

    def fixture_module(self):
        source = (ROLE / "library/uranus_sql_console.py").read_text()
        source = source.replace('database="oklab"', "database=" + repr(self.database))
        start = source.index("conn = psycopg2.connect(")
        end = source.index("        conn.set_session", start)
        return (
            source[:start]
            + "conn = psycopg2.connect(**"
            + repr({**self.connection_args, "options": "-c search_path=pg_catalog"})
            + ")\n"
            + source[end:]
        )

    def test_real_ansible_check_diff_approval_and_idempotency(self):
        self.public_temp_fixture()
        self.conn.commit()
        original_acl = self.database_acl()
        original_function_acls = self.function_acls()
        self.conn.rollback()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            role = root / "roles/uranus_admin"
            for folder in ("tasks", "library", "files"):
                (role / folder).mkdir(parents=True)
            for name in (
                "sql_console_plan.yml",
                "sql_console_provision.yml",
                "sql_console_verify.yml",
            ):
                shutil.copy(ROLE / "tasks" / name, role / "tasks" / name)
            shutil.copy(
                ROLE / "files/sql_console_contract.json", role / "files/sql_console_contract.json"
            )
            (role / "library/uranus_sql_console.py").write_text(self.fixture_module())
            tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
            console_tasks = [
                t
                for t in tasks
                if t.get("ansible.builtin.import_tasks", "").startswith("sql_console_")
            ]
            console_tasks.append(
                {
                    "name": "Fixture release reached",
                    "ansible.builtin.copy": {
                        "content": "build may begin",
                        "dest": str(root / "reached"),
                    },
                    "when": "not ansible_check_mode",
                }
            )
            (role / "tasks/main.yml").write_text(yaml.safe_dump(console_tasks))
            variables = {
                "ansible_python_interpreter": sys.executable,
                "ansible_become": False,
                "ua_action": "deploy",
                "ua_manifest": {"environment_keys": ["SQL_CONSOLE_DATABASE_URL"]},
                "ua_sql_console_provision_approved": False,
                "ua_runtime": {
                    "SQL_CONSOLE_DATABASE_URL": "postgresql+asyncpg://uranus_console_reader:"
                    + PASSWORD
                    + "@localhost/"
                    + self.database
                },
            }
            play = [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": variables,
                    "roles": ["uranus_admin"],
                }
            ]
            path = root / "play.yml"

            def run(check=False):
                path.write_text(yaml.safe_dump(play))
                path.chmod(0o600)
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "ansible.cli.playbook",
                        "-i",
                        "localhost,",
                        str(path),
                        *(["--check", "--diff"] if check else []),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "ANSIBLE_LOCAL_TEMP": str(root / "tmp")},
                )
                self.assertNotIn(PASSWORD, result.stdout + result.stderr)
                return result

            check = run(True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn("would create role uranus_console_reader", check.stdout)
            self.assertIn("would revoke PUBLIC TEMPORARY", check.stdout)
            self.assertIn("would revoke PUBLIC EXECUTE pg_catalog.set_config", check.stdout)
            self.assertEqual(self.function_acls(), original_function_acls)
            for role in CONTRACT["database_temp_roles"]:
                self.assertIn("would grant explicit TEMPORARY " + role, check.stdout)
            self.assertEqual(self.database_acl(), original_acl)
            self.assertIn("changed=0", check.stdout)
            self.assertFalse((root / "reached").exists())
            self.assertEqual(
                self.boundary.rows("SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,)), []
            )
            self.conn.rollback()
            denied = run()
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("ua_sql_console_provision_approved=true", denied.stdout)
            self.assertFalse((root / "reached").exists())
            variables["ua_sql_console_provision_approved"] = True
            first = run()
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("changed=2", first.stdout)  # boundary + fixture build marker
            second = run()
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("changed=0", second.stdout)
            # A catalog failure must prevent reaching the simulated release build.
            (root / "reached").unlink()
            self.boundary.execute("GRANT uranus_console_owner TO uranus_console_reader")
            self.conn.commit()
            blocked = run()
            self.assertNotEqual(blocked.returncode, 0)
            self.assertFalse((root / "reached").exists())
            self.assertIn("role_membership", blocked.stdout)
            self.boundary.execute("REVOKE uranus_console_owner FROM uranus_console_reader")
            self.conn.commit()
            variables["ua_manifest"]["environment_keys"] = []
            old = run(True)
            self.assertEqual(old.returncode, 0, old.stdout + old.stderr)
            self.assertNotIn("would create role", old.stdout)
            self.assertEqual(
                len(
                    self.boundary.rows("SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,))
                ),
                1,
            )

    def test_real_module_check_apply_verify_and_effective_login(self):
        self.conn.rollback()
        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory) / "console_fixture.py"
            module.write_text(self.fixture_module())
            dsn = (
                "postgresql+asyncpg://uranus_console_reader:"
                + PASSWORD
                + "@localhost/"
                + self.database
            )
            for state, check, changed in (
                ("provision", True, False),
                ("provision", False, True),
                ("provision", False, False),
                ("verify", False, False),
            ):
                result = subprocess.run(
                    [sys.executable, str(module)],
                    input=json.dumps(
                        {
                            "ANSIBLE_MODULE_ARGS": {
                                "state": state,
                                "contract": CONTRACT,
                                "dsn": dsn,
                                "_ansible_check_mode": check,
                            }
                        }
                    ),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn(PASSWORD, result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report["changed"], changed)
                if check:
                    self.assertIn(
                        "would create role uranus_console_reader",
                        report["sql_console"]["changes_planned"],
                    )
                    self.assertEqual(
                        self.boundary.rows(
                            "SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,)
                        ),
                        [],
                    )
                    self.conn.rollback()
            args = {**self.connection_args, "user": console.READER, "password": PASSWORD}
            with psycopg2.connect(**args) as reader, reader.cursor() as cur:
                cur.execute(
                    "SELECT "
                    "current_user,current_setting('search_path'),has_database_privilege(current_user,current_database(),'TEMPORARY')"
                )
                self.assertEqual(cur.fetchone(), (console.READER, console.SEARCH_PATH, False))
                cur.execute("SELECT * FROM uranus_console.event_date")
                self.assertEqual(len(cur.fetchall()), 1)


if __name__ == "__main__":
    unittest.main()
