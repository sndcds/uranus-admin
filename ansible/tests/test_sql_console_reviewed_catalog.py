"""Reviewed deployment profile, using synthetic bodies in a disposable database.

Production SQL texts are deliberately not fixtures. Only fixture-local contract
copies receive hashes of the two harmless synthetic functions used below.
"""

import copy
import unittest

import psycopg2
import test_sql_console as base
from psycopg2 import sql

console = base.console
CONTRACT = base.CONTRACT
CONTRIB = ("hstore", "pg_trgm", "pgcrypto", "unaccent")


class ReviewedContractTests(unittest.TestCase):
    def test_separate_preservation_lists_and_pinned_custom_functions(self):
        self.assertEqual(CONTRACT["function_policy"]["preserve_role_contract"], "execute_roles")
        self.assertNotIn("oklab", CONTRACT["additional_database_temp_roles"])
        self.assertIn("oklab", CONTRACT["additional_execute_roles"])
        self.assertEqual(len(CONTRACT["additional_database_temp_roles"]), 14)
        custom = CONTRACT["function_policy"]["custom_functions"]
        self.assertEqual(len(custom), 12)
        for signature, entry in custom.items():
            self.assertRegex(entry["definition_sha256"], r"^[a-f0-9]{64}$")
            self.assertFalse(entry["security_definer"])
            self.assertTrue(
                console.restricted_function(
                    dict(
                        signature=signature,
                        name=signature.split(".")[1].split("(")[0],
                        extension=None,
                        security_definer=False,
                        volatility="i",
                    ),
                    CONTRACT["function_policy"],
                )
            )
        for key in ("execute_roles", "additional_execute_roles", "additional_database_temp_roles"):
            for roles in ([console.OWNER], [console.READER], ["public"], ["bad;sql"], ["x", "x"]):
                with self.subTest(key=key, roles=roles), self.assertRaises(ValueError):
                    console.validate_contract({**CONTRACT, key: roles})

    def test_contrib_support_is_exact_and_optional(self):
        snapshot = console.function_snapshot(CONTRACT, 16, "3.4.2")
        for name in CONTRIB:
            self.assertTrue(CONTRACT["allowed_extensions"][name]["optional"])
            self.assertEqual(
                snapshot[name]["functions"], len(snapshot[name]["restricted_functions"])
            )
            self.assertNotIn(name, console.function_snapshot(CONTRACT, 17, "3.5.2"))


@unittest.skipUnless(base.TEST_URL, "No explicitly disposable ANSIBLE_TEST_DATABASE_URL supplied")
class ReviewedCatalogDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.ConsoleDatabaseTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        base.ConsoleDatabaseTests.tearDownClass.__func__(cls)

    def setUp(self):
        base.ConsoleDatabaseTests.setUp(self)

    def tearDown(self):
        base.ConsoleDatabaseTests.tearDown(self)

    def profile(self):
        if self.conn.server_version != 160015:
            # Compatibility CI asserts refusal, rather than pretending the PG16
            # extension fingerprints have been reviewed for a different build.
            self.boundary.execute("CREATE EXTENSION hstore")
            self.assertTrue(
                any(
                    b.startswith("unreviewed_extension_version:hstore:")
                    for b in self.boundary.inspect()["blockers"]
                )
            )
            return None
        self.boundary.execute("CREATE ROLE oklab LOGIN CREATEDB INHERIT")
        self.boundary.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO oklab").format(sql.Identifier(self.database))
        )
        for role in CONTRACT["additional_database_temp_roles"]:
            self.boundary.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOINHERIT").format(sql.Identifier(role))
            )
        self.boundary.execute(
            sql.SQL("GRANT TEMPORARY ON DATABASE {} TO PUBLIC").format(
                sql.Identifier(self.database)
            )
        )
        for name in CONTRIB:
            if name == "pgcrypto":
                self.boundary.execute("SET LOCAL ROLE oklab")
            self.boundary.execute(
                sql.SQL("CREATE EXTENSION {} WITH SCHEMA public").format(sql.Identifier(name))
            )
            self.boundary.execute("RESET ROLE")
        for name in ("geometry_columns", "geography_columns", "spatial_ref_sys"):
            self.boundary.execute(
                sql.SQL("ALTER {} public.{} OWNER TO oklab").format(
                    sql.SQL("TABLE" if name == "spatial_ref_sys" else "VIEW"), sql.Identifier(name)
                )
            )
        self.boundary.execute("""CREATE FUNCTION public.normalize_german(text) RETURNS text
            LANGUAGE sql IMMUTABLE AS $$ SELECT $1 $$""")
        self.boundary.execute("""CREATE FUNCTION uranus.update_modified_at() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            NEW.modified_at := CURRENT_TIMESTAMP; RETURN NEW; END $$""")
        for signature in ("public.normalize_german(text)", "uranus.update_modified_at()"):
            self.boundary.execute(
                sql.SQL("ALTER FUNCTION {} OWNER TO oklab").format(sql.SQL(signature))
            )
        contract = copy.deepcopy(CONTRACT)
        for f in console.function_catalog(self.conn):
            if f["signature"] in contract["function_policy"]["custom_functions"]:
                contract["function_policy"]["custom_functions"][f["signature"]][
                    "definition_sha256"
                ] = f["definition_sha256"]
        self.boundary = console.Boundary(self.conn, contract)
        return contract

    def test_profile_preserves_existing_rights_and_is_idempotent(self):
        if not self.profile():
            return
        before = self.boundary.inspect()
        self.assertEqual(before["blockers"], [])
        self.assertTrue(before["temp_reconcile"]["allowed"])
        self.assertEqual(len(before["execute_reconcile"]["changes"]), 96 + 95 + 131 + 2)
        self.assertTrue(self.boundary.provision(base.PASSWORD))
        self.assertEqual(self.boundary.inspect()["blockers"], [])
        self.assertFalse(self.boundary.provision(base.PASSWORD))
        signatures = [x["signature"] for x in before["execute_reconcile"]["changes"]]
        roles = CONTRACT["execute_roles"] + CONTRACT["additional_execute_roles"]
        for signature in signatures:
            for role, allowed in self.boundary.rows(
                "SELECT rolname,has_function_privilege(oid,%s,'EXECUTE') "
                "FROM pg_roles WHERE rolname=ANY(%s)",
                (signature, roles + [console.OWNER, console.READER]),
            ):
                self.assertEqual(allowed, role in roles, (signature, role))
        for role, allowed in self.boundary.rows(
            "SELECT rolname,has_database_privilege(oid,current_database(),'TEMP') "
            "FROM pg_roles WHERE rolname=ANY(%s)",
            (roles + [console.OWNER, console.READER],),
        ):
            self.assertEqual(allowed, role in roles, role)
        for role in (console.OWNER, console.READER):
            for call in (
                "public.normalize_german('x')",
                "public.similarity('a','b')",
                "public.digest('x','sha256')",
            ):
                self.boundary.execute("SAVEPOINT denied_call")
                self.boundary.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                    self.boundary.rows("SELECT " + call)
                self.boundary.execute("ROLLBACK TO SAVEPOINT denied_call")
        # This pure native type-I/O path is not governed by function EXECUTE ACLs.
        # Its reviewed implementation must remain harmless even with ACLs removed.
        self.boundary.execute("SET LOCAL ROLE uranus_console_reader")
        self.assertEqual(self.boundary.rows("SELECT 'a=>b'::public.hstore"), [('"a"=>"b"',)])
        self.boundary.execute("RESET ROLE")
        self.boundary.execute("SET LOCAL ROLE hackathon_user")
        self.assertEqual(self.boundary.rows("SELECT public.similarity('same','same')"), [(1.0,)])
        self.assertEqual(
            self.boundary.rows("SELECT public.normalize_german('fixture')"), [("fixture",)]
        )
        self.boundary.execute("CREATE TEMP TABLE fixture_app_temp(value integer)")
        self.boundary.execute("DROP TABLE fixture_app_temp")
        self.boundary.execute("RESET ROLE")
        self.assertEqual(
            self.boundary.rows(
                "SELECT pg_get_userbyid(relowner) FROM pg_class "
                "WHERE oid='public.spatial_ref_sys'::regclass"
            ),
            [("oklab",)],
        )

    def test_profile_drift_and_unreviewed_dependencies_block_without_mutation(self):
        if not self.profile():
            return
        cases = [
            ("ALTER FUNCTION public.normalize_german(text) COST 99", "unreviewed_custom_function:"),
            (
                "ALTER FUNCTION public.normalize_german(text) SECURITY DEFINER",
                "unreviewed_custom_function:",
            ),
            (
                "ALTER FUNCTION public.normalize_german(text) OWNER TO postgres",
                "unreviewed_custom_function:",
            ),
            (
                "ALTER FUNCTION public.similarity(text,text) COST 99",
                "unreviewed_function_catalog:pg_trgm",
            ),
            (
                "UPDATE pg_extension SET extversion='1.9' WHERE extname='hstore'",
                "unreviewed_extension_version:hstore:",
            ),
            (
                "ALTER FUNCTION public.digest(text,text) OWNER TO oklab",
                "unreviewed_function_owner_or_language:",
            ),
            ("ALTER ROLE oklab CREATEROLE", "unreviewed_extension_schema_or_owner:pgcrypto"),
            (
                "CREATE ROLE fixture_member; GRANT oklab TO fixture_member",
                "unreviewed_custom_function:",
            ),
            ("CREATE ROLE fixture_unknown LOGIN", "unexpected_public_temp_consumer:"),
            (
                "CREATE VIEW public.fixture_callback AS SELECT public.normalize_german('x')",
                "unreviewed_custom_function_dependency:",
            ),
            (
                "CREATE OPERATOR public.!! (RIGHTARG=text, FUNCTION=public.normalize_german)",
                "unreviewed_custom_function_dependency:",
            ),
        ]
        for query, prefix in cases:
            with self.subTest(prefix=prefix):
                self.boundary.execute("SAVEPOINT drift")
                self.boundary.execute(query)
                self.assertTrue(
                    any(b.startswith(prefix) for b in self.boundary.inspect()["blockers"])
                )
                with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
                    self.boundary.provision(base.PASSWORD)
                self.assertEqual(
                    self.boundary.rows(
                        "SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,)
                    ),
                    [],
                )
                self.boundary.execute("ROLLBACK TO SAVEPOINT drift")

    def test_no_regrant_after_manual_hardening_and_lists_are_independent(self):
        contract = self.profile()
        if not contract:
            return
        modified = copy.deepcopy(contract)
        modified["additional_execute_roles"].remove("hackathon_user")
        separate = console.Boundary(self.conn, modified).inspect()
        self.assertTrue(separate["temp_reconcile"]["allowed"])
        self.assertTrue(
            any(
                b.startswith("unexpected_execute_consumer:") and b.endswith(":hackathon_user")
                for b in separate["blockers"]
            )
        )
        self.assertTrue(self.boundary.provision(base.PASSWORD))
        self.boundary.execute(
            "REVOKE EXECUTE ON FUNCTION public.normalize_german(text) FROM hackathon_user"
        )
        self.assertIn(
            "missing_preserved_execute:public.normalize_german(text)",
            self.boundary.inspect()["blockers"],
        )
        self.boundary.execute(
            sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM hackathon_user").format(
                sql.Identifier(self.database)
            )
        )
        self.assertIn("missing_preserved_temp", self.boundary.inspect()["blockers"])
        with self.assertRaisesRegex(ValueError, "sql_console_blocked"):
            self.boundary.provision(base.PASSWORD)
        self.assertFalse(
            self.boundary.rows(
                "SELECT has_function_privilege('hackathon_user',"
                "'public.normalize_german(text)','EXECUTE')"
            )[0][0]
        )

    def test_all_profile_actions_roll_back_on_late_failure(self):
        if not self.profile():
            return
        original = self.boundary.execute
        before = self.boundary.rows("SELECT oid,proacl::text FROM pg_proc ORDER BY oid")
        self.boundary.execute("SAVEPOINT before_apply")

        def fail_late(query, args=()):
            original(query, args)
            rendered = query if isinstance(query, str) else query.as_string(self.conn)
            if "ALTER ROLE" in rendered and "PASSWORD" in rendered:
                raise RuntimeError("synthetic late failure")

        self.boundary.execute = fail_late
        with self.assertRaisesRegex(RuntimeError, "synthetic late failure"):
            self.boundary.provision(base.PASSWORD)
        self.boundary.execute = original
        self.boundary.execute("ROLLBACK TO SAVEPOINT before_apply")
        self.assertEqual(
            before, self.boundary.rows("SELECT oid,proacl::text FROM pg_proc ORDER BY oid")
        )
        self.assertTrue(self.boundary.inspect()["public_temp"])
        self.assertEqual(
            self.boundary.rows("SELECT 1 FROM pg_roles WHERE rolname=%s", (console.READER,)), []
        )
