"""Effective privilege tests in an explicitly disposable local PostgreSQL database.

No app fixture, migration or test ever connects to production. This fixture creates
synthetic catalog objects only, not a claim about the Uranus source contract.
"""

import json
import os
import re
import unittest
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import sql
from test_deployment import ROOT, packager

TEST_URL = os.environ.get("ANSIBLE_TEST_DATABASE_URL", "")
QUERY = (ROOT / "ansible/roles/uranus_admin/files/boundary.sql").read_text()
GRANTS = packager.literal_assignment(
    (ROOT / "backend/app/storage_preflight.py").read_text(), "RUNTIME_GRANTS"
)
ROLES = ("uranus_reader", "admin_user", "admin_migrator", "admin_auth_operator")


@unittest.skipUnless(TEST_URL, "No explicitly disposable ANSIBLE_TEST_DATABASE_URL supplied")
class DatabaseBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = urlsplit(TEST_URL)
        if (
            url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or not re.fullmatch(r"/[a-z][a-z0-9_]*_test", url.path)
            or url.query
            or url.fragment
        ):
            raise RuntimeError("Refuse non-local or non-test database")
        cls.conn = psycopg2.connect(TEST_URL)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            if cur.fetchone()[0] != url.path[1:]:
                raise RuntimeError("Wrong test database")
            cur.execute("SELECT 1 FROM pg_namespace WHERE nspname IN ('uranus','admin')")
            if cur.fetchone():
                raise RuntimeError("Refuse pre-existing schemas")
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)", (list(ROLES),))
            if cur.fetchone():
                raise RuntimeError("Refuse pre-existing project roles")
            for role in ROLES:
                cur.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT").format(sql.Identifier(role)))
            cur.execute("CREATE SCHEMA uranus")
            cur.execute("CREATE SCHEMA admin AUTHORIZATION admin_migrator")
            cur.execute("GRANT USAGE ON SCHEMA uranus TO uranus_reader")
            cur.execute("GRANT USAGE ON SCHEMA admin TO admin_user, admin_auth_operator")
            sources = re.findall(
                r"\('([a-z_]+)'\)",
                QUERY.split("source_tables(name) AS (", 1)[1].split("), problems", 1)[0],
            )
            for name in sources:
                cur.execute(
                    sql.SQL("CREATE TABLE uranus.{} (id int PRIMARY KEY)").format(
                        sql.Identifier(name)
                    )
                )
            cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA uranus TO uranus_reader")
            for name, privileges in GRANTS.items():
                columns = "version_num text" if name == "alembic_version" else "id int PRIMARY KEY"
                cur.execute(
                    sql.SQL("CREATE TABLE admin.{} ({})").format(
                        sql.Identifier(name), sql.SQL(columns)
                    )
                )
                cur.execute(
                    sql.SQL("ALTER TABLE admin.{} OWNER TO admin_migrator").format(
                        sql.Identifier(name)
                    )
                )
                cur.execute(
                    sql.SQL("GRANT {} ON admin.{} TO admin_user").format(
                        sql.SQL(",".join(privileges)), sql.Identifier(name)
                    )
                )
            cur.execute("INSERT INTO admin.alembic_version VALUES ('0012')")
            cur.execute("GRANT SELECT ON admin.alembic_version TO admin_auth_operator")
            cur.execute("GRANT SELECT,INSERT,UPDATE ON admin.auth_account TO admin_auth_operator")
            cur.execute(
                "GRANT SELECT,INSERT,DELETE ON admin.auth_system_admin TO admin_auth_operator"
            )
            cur.execute("GRANT SELECT,UPDATE ON admin.auth_session TO admin_auth_operator")
        cls.conn.autocommit = False

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def violations(self, changes=None):
        with self.conn.cursor() as cur:
            if changes:
                cur.execute(changes)
            cur.execute(QUERY, {"head": "0012", "grants": json.dumps(GRANTS)})
            return cur.fetchone()[0]

    def test_valid_boundary_in_read_only_transaction(self):
        with self.conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
        self.assertEqual(self.violations(), [])

    def test_reject_source_table_and_column_writes(self):
        for change in (
            "GRANT UPDATE ON uranus.event TO uranus_reader",
            "GRANT UPDATE(id) ON uranus.event TO admin_user",
            "GRANT INSERT ON uranus.event TO admin_migrator",
            "GRANT SELECT ON uranus.event TO uranus_reader WITH GRANT OPTION",
        ):
            with self.subTest(change=change):
                self.assertTrue(self.violations(change))
                self.conn.rollback()

    def test_reject_admin_excess_privileges(self):
        for change in (
            "GRANT DELETE ON admin.finding TO admin_user",
            "GRANT UPDATE(id) ON admin.record_mark_event TO admin_user",
            "GRANT SELECT(id) ON admin.finding TO admin_user WITH GRANT OPTION",
            "GRANT UPDATE ON admin.finding TO uranus_reader",
            "GRANT DELETE ON admin.auth_session TO admin_auth_operator",
            "GRANT UPDATE(id) ON admin.finding TO admin_auth_operator",
            "GRANT CREATE ON SCHEMA admin TO admin_user",
            "ALTER ROLE admin_user SUPERUSER",
            "GRANT admin_migrator TO admin_user",
            "GRANT USAGE ON SCHEMA uranus TO admin_migrator",
        ):
            with self.subTest(change=change):
                self.assertTrue(self.violations(change))
                self.conn.rollback()

    def test_reject_missing_grants_and_stale_head(self):
        for change in (
            "REVOKE SELECT ON admin.auth_account FROM admin_user",
            "UPDATE admin.alembic_version SET version_num='0010'",
            "ALTER TABLE admin.finding OWNER TO admin_user",
            "ALTER TABLE uranus.event RENAME TO event_missing",
        ):
            with self.subTest(change=change):
                self.assertTrue(self.violations(change))
                self.conn.rollback()

    def test_reject_indirect_mutation_paths(self):
        for change in (
            "ALTER TABLE admin.finding ADD FOREIGN KEY (id) REFERENCES uranus.event(id)",
            "CREATE FUNCTION public.fixture_escalation() RETURNS int LANGUAGE sql "
            "SECURITY DEFINER AS 'SELECT 1'",
            "CREATE SEQUENCE uranus.fixture_seq; "
            "GRANT USAGE ON uranus.fixture_seq TO uranus_reader",
            "ALTER DEFAULT PRIVILEGES FOR ROLE admin_migrator GRANT ALL ON TABLES TO admin_user",
            "GRANT CREATE ON SCHEMA public TO admin_user",
            "CREATE SEQUENCE admin.unexpected_seq",
            "CREATE TYPE public.fixture_type AS ENUM ('test'); "
            "ALTER TYPE public.fixture_type OWNER TO admin_user",
        ):
            with self.subTest(change=change):
                self.assertTrue(self.violations(change))
                self.conn.rollback()

    def test_maintain_privilege_on_supported_servers(self):
        if self.conn.server_version >= 170000:
            self.assertTrue(self.violations("GRANT MAINTAIN ON uranus.event TO uranus_reader"))
        else:
            # PostgreSQL 16 has no MAINTAIN privilege; the same audit SQL must still run.
            self.assertEqual(self.violations(), [])

    def test_reader_cannot_write_even_in_read_write_transaction(self):
        with self.conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE uranus_reader")
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("INSERT INTO uranus.event VALUES (1)")


if __name__ == "__main__":
    unittest.main()
