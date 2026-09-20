"""Console boundary attacks only in a separate, disposable local *_test database."""

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
    def test_contract_is_explicit_and_versioned(self):
        console.validate_contract(CONTRACT)
        self.assertEqual(sum(len(v["columns"]) for v in CONTRACT["views"].values()), 31)
        for name, view in CONTRACT["views"].items():
            definition = console.definition(name, view)
            self.assertNotIn("*", definition)
            self.assertNotIn("(", definition)
            self.assertEqual(view["owner_select_columns"], [c["name"] for c in view["columns"]])
        self.assertEqual(CONTRACT["version"], 2)
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
            cur.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC")
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
            cur.execute(
                """SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n
                ON n.oid=p.pronamespace WHERE p.proname=ANY(%s) OR p.prosecdef OR p.oid>=16384 OR
                (n.nspname NOT IN ('pg_catalog','information_schema'))""",
                (console.DANGEROUS,),
            )
            for (function,) in cur.fetchall():
                cur.execute(
                    sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM PUBLIC").format(sql.SQL(function))
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
            "GRANT EXECUTE ON FUNCTION pg_catalog.lo_create(oid) TO PUBLIC",
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
