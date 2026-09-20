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
        with cls.parent.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname IN (%s,%s)", (console.OWNER, console.READER)
            )
            if cur.fetchone():
                raise RuntimeError("Refuse pre-existing console roles")
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (cls.database,))
            if cur.fetchone():
                raise RuntimeError("Refuse pre-existing console fixture database")
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
            # tests below restore PUBLIC exposure and prove the production module blocks.
            cur.execute(
                sql.SQL("REVOKE TEMPORARY, CREATE ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(cls.database)
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

    def test_public_temp_inventory_blocks_without_revoke(self):
        self.boundary.execute(
            sql.SQL("GRANT TEMPORARY ON DATABASE {} TO PUBLIC").format(
                sql.Identifier(self.database)
            )
        )
        report = self.boundary.inspect()
        self.assertTrue(report["public_temp"])
        self.assertIn("postgres", report["temp_login_roles"])
        self.assertIn(
            "public_temp_requires_external_review_no_automatic_revoke", report["blockers"]
        )
        with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
            self.boundary.provision(PASSWORD)
        self.assertEqual(
            self.boundary.rows("SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,)), []
        )
        self.assertTrue(self.boundary.inspect()["public_temp"])

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
