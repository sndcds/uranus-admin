"""Real Alembic from a packaged release; only disposable local *_test databases."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import psycopg2
import yaml
from psycopg2 import sql
from release_fixture import frontend_build
from test_deployment import ROLE, ROOT, filters, load, packager

admin_db = load("admin_bootstrap", ROLE / "library/uranus_admin_database.py")
TEST_URL = os.environ.get("ANSIBLE_TEST_DATABASE_URL", "")
BOUNDARY = (ROLE / "files/boundary.sql").read_text()
PASSWORD = "synthetic-admin-bootstrap-credential-only"


class AdminBootstrapContractTests(unittest.TestCase):
    def test_migrator_login_probe_is_read_only_and_closes_connection(self):
        boundary = object.__new__(admin_db.AdminDatabase)
        boundary.diagnostic = {}
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("admin_migrator", "admin_migrator")
        with (
            patch.object(boundary, "credentials", return_value={"admin_migrator": {}}),
            patch.object(admin_db.psycopg2, "connect", return_value=connection),
        ):
            boundary.verify_upgrade_credentials({})
        connection.set_session.assert_called_once_with(readonly=True)
        cursor.execute.assert_called_once_with("SELECT current_user,session_user")
        connection.commit.assert_not_called()
        connection.close.assert_called_once()

    def test_upgrade_authentication_failure_prevents_migration(self):
        boundary = object.__new__(admin_db.AdminDatabase)
        boundary.diagnostic = {}
        migration = MagicMock()
        with (
            patch.object(boundary, "inspect", return_value={"state": "UPGRADEABLE"}),
            patch.object(boundary, "credentials", return_value={"admin_migrator": {}}),
            patch.object(admin_db.psycopg2, "connect", side_effect=psycopg2.OperationalError),
        ):
            with self.assertRaises(psycopg2.OperationalError):
                boundary.upgrade("production", True, {}, migration)
        migration.assert_not_called()
        self.assertEqual(boundary.diagnostic, {"check": "migrator_connection"})

    def test_migrator_login_probe_runs_in_check_mode_without_mutation(self):
        for check_mode in (False, True):
            with self.subTest(check_mode=check_mode):
                module = MagicMock()
                module.params = {
                    "state": "verify_upgrade_credentials",
                    "environment": "production",
                    "approved": False,
                    "upgrade_approved": False,
                    "manifest": {},
                    "boundary": BOUNDARY,
                    "credentials": {},
                }
                module.check_mode = check_mode
                connection, boundary = MagicMock(), MagicMock()
                with (
                    patch("ansible.module_utils.basic.AnsibleModule", return_value=module),
                    patch.object(admin_db.psycopg2, "connect", return_value=connection),
                    patch.object(admin_db, "AdminDatabase", return_value=boundary),
                    patch.object(admin_db, "release_migration") as migration,
                ):
                    admin_db.main()
                connection.set_session.assert_called_once_with(readonly=True)
                boundary.verify_upgrade_credentials.assert_called_once_with({})
                boundary.bootstrap.assert_not_called()
                boundary.upgrade.assert_not_called()
                migration.assert_not_called()
                self.assertFalse(module.exit_json.call_args.kwargs["changed"])

    def test_migrator_probe_precedes_build_and_preserves_secret_suppression(self):
        tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
        probe = next(
            t
            for t in tasks
            if t.get("uranus_admin_database", {}).get("state") == "verify_upgrade_credentials"
        )
        self.assertTrue(probe["no_log"])
        self.assertFalse(probe["diff"])
        self.assertNotIn("check_mode", probe["when"])
        environment = next(
            t for t in tasks if t.get("ansible.builtin.import_tasks") == "environment_plan.yml"
        )
        deploy = next(t for t in tasks if t.get("ansible.builtin.import_tasks") == "deploy.yml")
        self.assertLess(tasks.index(environment), tasks.index(probe))
        self.assertLess(tasks.index(probe), tasks.index(deploy))

    def test_failed_login_reports_actionable_stage_without_driver_secrets(self):
        module = MagicMock()
        module.params = {
            "state": "verify_upgrade_credentials",
            "environment": "production",
            "manifest": self.diagnostic_manifest(),
            "boundary": BOUNDARY,
            "credentials": {},
        }
        module.check_mode = True
        module.fail_json.side_effect = SystemExit(1)
        secret = "postgresql://admin_migrator:secret-value@private-host/db"
        with (
            patch("ansible.module_utils.basic.AnsibleModule", return_value=module),
            patch.object(
                admin_db.AdminDatabase, "credentials", return_value={"admin_migrator": {}}
            ),
            patch.object(
                admin_db.psycopg2,
                "connect",
                side_effect=[MagicMock(), psycopg2.OperationalError(secret)],
            ),
        ):
            with self.assertRaises(SystemExit):
                admin_db.main()
        message = module.fail_json.call_args.kwargs["msg"]
        self.assertIn("stage=verify_upgrade_credentials, check=migrator_connection", message)
        self.assertIn("ADMIN_MIGRATION_DATABASE_URL", message)
        for forbidden in (secret, "secret-value", "private-host", "postgresql://"):
            self.assertNotIn(forbidden, message)

    def test_console_steps_run_after_bootstrap_changes_absent_to_ready(self):
        release = yaml.safe_load((ROLE / "tasks/release.yml").read_text())
        gate = next(t for t in release if t["name"].startswith("Bootstrap only the explicitly"))
        bootstrap = yaml.safe_load((ROLE / "tasks/admin_database_bootstrap.yml").read_text())
        transition = next(
            i for i, task in enumerate(bootstrap) if task["name"].startswith("Use READY")
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Run the real gate, state transition and console imports. External/database
            # work is represented only by in-memory markers in this control-flow fixture.
            (root / "admin_database_bootstrap.yml").write_text(
                yaml.safe_dump(bootstrap[transition:])
            )
            for step in ("plan", "provision", "verify"):
                (root / f"sql_console_{step}.yml").write_text(
                    yaml.safe_dump([{"ansible.builtin.set_fact": {f"console_{step}_ran": True}}])
                )
            plays = []
            for state in ("ABSENT", "READY", "DRIFTED"):
                plays.append(
                    {
                        "name": state,
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "ua_admin_database_verified": {"admin_database": {"state": "READY"}},
                            "ua_sql_console_required": True,
                        },
                        "tasks": [
                            {
                                "ansible.builtin.set_fact": {
                                    "ua_admin_database_plan": {"admin_database": {"state": state}},
                                    "console_plan_ran": False,
                                    "console_provision_ran": False,
                                    "console_verify_ran": False,
                                }
                            },
                            gate,
                            {
                                "ansible.builtin.assert": {
                                    "that": [
                                        f"console_{step}_ran == {state == 'ABSENT'}"
                                        for step in ("plan", "provision", "verify")
                                    ]
                                    + [
                                        "ua_admin_database_plan.admin_database.state == "
                                        + repr("READY" if state == "ABSENT" else state)
                                    ]
                                }
                            },
                        ],
                    }
                )
            playbook = root / "play.yml"
            playbook.write_text(yaml.safe_dump(plays))
            result = subprocess.run(
                [sys.executable, "-m", "ansible.cli.playbook", "-i", "localhost,", str(playbook)],
                env={
                    **os.environ,
                    "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                },
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def diagnostic_manifest(self):
        return {
            "commit": "a" * 40,
            "head": "0013",
            "runtime_grants": {"alembic_version": ["SELECT"]},
            "operator_grants": admin_db.OPERATOR_GRANTS,
            "admin_indexes": [],
            "admin_columns": {},
            "admin_upgrade_contracts": {},
        }

    def test_column_only_upgrade_keeps_the_same_table_grants(self):
        manifest = self.diagnostic_manifest()
        manifest["head"] = "0014"
        manifest["admin_upgrade_contracts"] = {
            "0013": {"schema_fingerprint": "b" * 64, "runtime_grants": manifest["runtime_grants"]}
        }
        admin_db.AdminDatabase(None, manifest, BOUNDARY, {})
        manifest["admin_upgrade_contracts"]["0013"]["runtime_grants"] = {
            "unexpected_table": ["SELECT"]
        }
        with self.assertRaisesRegex(ValueError, "invalid_admin_upgrade_contract"):
            admin_db.AdminDatabase(None, manifest, BOUNDARY, {})

    def test_malformed_boundary_fails_with_explicit_safe_stage(self):
        for boundary in ("", "source_tables(name) AS (('event'))"):
            diagnostic = {}
            with self.assertRaisesRegex(ValueError, "^invalid_source_contract$"):
                admin_db.AdminDatabase(None, self.diagnostic_manifest(), boundary, diagnostic)
            self.assertEqual(diagnostic, {"check": "source_contract"})

    def test_module_diagnostics_never_include_exception_text(self):
        secret = "postgresql://admin:secret-value@private-host/db SELECT sensitive FROM admin"
        for error_type in (
            IndexError,
            KeyError,
            psycopg2.ProgrammingError,
            psycopg2.InternalError,
        ):
            for stage in ("postgres_connect", "construct_boundary", "inspect"):
                with self.subTest(error=error_type.__name__, stage=stage):
                    module = MagicMock()
                    module.params = {
                        "state": "plan",
                        "environment": "production",
                        "approved": False,
                        "upgrade_approved": False,
                        "manifest": self.diagnostic_manifest(),
                        "boundary": BOUNDARY,
                    }
                    module.check_mode = True
                    module.fail_json.side_effect = SystemExit(1)
                    conn = MagicMock()
                    if stage == "construct_boundary":
                        # A malformed manifest must fail before any inspection query.
                        module.params["manifest"].pop("commit")
                        expected_type, check = "KeyError", "release_contract"
                    else:
                        expected_type = error_type.__name__
                        check = "inspection_session" if stage == "inspect" else "none"
                    conn.cursor.return_value.__enter__.return_value.execute.side_effect = (
                        error_type(secret)
                    )
                    with (
                        patch(
                            "ansible.module_utils.basic.AnsibleModule",
                            return_value=module,
                        ),
                        patch.object(admin_db.psycopg2, "connect", return_value=conn) as connect,
                    ):
                        if stage == "postgres_connect":
                            connect.side_effect = error_type(secret)
                        with self.assertRaises(SystemExit):
                            admin_db.main()
                    message = module.fail_json.call_args.kwargs["msg"]
                    self.assertIn(
                        f"stage={stage}, check={check}, exception_type={expected_type}",
                        message,
                    )
                    for forbidden in (
                        secret,
                        "secret-value",
                        "private-host",
                        "sensitive",
                        "postgresql://",
                    ):
                        self.assertNotIn(forbidden, message)
                    module.exit_json.assert_not_called()
                    if stage != "postgres_connect":
                        conn.close.assert_called_once()

    def test_release_migration_uses_only_uv_as_the_python_launcher(self):
        manifest = {"commit": "a" * 40}
        archive_hash = "b" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / manifest["commit"]
            (release / "deployment").mkdir(parents=True)
            (release / ".complete").write_text(archive_hash + "\n")
            (release / "release.json").write_text(json.dumps(manifest))
            completed = subprocess.CompletedProcess([], 0)
            with (
                patch.object(admin_db, "RELEASE_ROOT", root),
                patch.object(admin_db, "OWNER_UID", os.getuid()),
                patch.object(admin_db.subprocess, "run", return_value=completed) as run,
            ):
                admin_db.release_migration(
                    str(release), manifest, archive_hash, "/managed/toolchain/uv"
                )("secret-dsn")
        argv = run.call_args.args[0]
        self.assertEqual(
            argv[:9],
            [
                "/managed/toolchain/uv",
                "run",
                "--no-cache",
                "--no-sync",
                "--offline",
                "--no-python-downloads",
                "--no-env-file",
                "python",
                "-B",
            ],
        )
        self.assertNotIn(".venv/bin", " ".join(argv))
        self.assertEqual(run.call_args.kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(run.call_args.kwargs["env"]["UV_PYTHON_DOWNLOADS"], "never")

    def test_fixture_cleans_created_database_when_connect_fails(self):
        case = AdminBootstrapDatabaseTests("test_absent_plan_read_only_and_no_approval")
        case.parent = MagicMock()
        url = "postgresql://postgres:synthetic%40password@127.0.0.1:5432/fixture_test"
        with (
            patch.dict(globals(), TEST_URL=url),
            patch.object(psycopg2, "connect", side_effect=psycopg2.OperationalError) as connect,
        ):
            with self.assertRaises(psycopg2.OperationalError):
                case.setUp()
            connect.assert_called_once_with(url, dbname="uranus_admin_first_install_test")
            self.assertTrue(case.doCleanups())
        calls = case.parent.cursor.return_value.__enter__.return_value.execute.call_args_list
        self.assertIn("CREATE DATABASE", str(calls[0]))
        self.assertIn("DROP DATABASE", str(calls[1]))
        self.assertIn("uranus_admin_first_install_test", str(calls[1]))
        self.assertFalse(case._cleanups)

    def test_fixture_never_cleans_database_it_did_not_create(self):
        case = AdminBootstrapDatabaseTests("test_absent_plan_read_only_and_no_approval")
        case.parent = MagicMock()
        execute = case.parent.cursor.return_value.__enter__.return_value.execute
        execute.side_effect = psycopg2.errors.DuplicateDatabase
        with self.assertRaises(psycopg2.errors.DuplicateDatabase):
            case.setUp()
        self.assertTrue(case.doCleanups())
        execute.assert_called_once()
        self.assertIn("CREATE DATABASE", str(execute.call_args))

    def test_only_missing_role_console_dependencies_are_deferred(self):
        plan = {
            "state": "ABSENT",
            "bootstrap_allowed": True,
            "missing_roles": ["admin_user"],
        }
        blocked = [
            "missing_temp_contract_login_role:admin_user",
            "missing_execute_contract_login_role:pg_catalog.pg_sleep(double precision)",
            "unreviewed_function_path:public.evil()",
            "missing_preserved_temp",
            "missing_temp_contract_login_role:foreign_role",
        ]
        self.assertEqual(filters.console_bootstrap_blockers(blocked, plan), blocked[2:])
        self.assertEqual(
            filters.console_bootstrap_blockers(blocked, {**plan, "state": "READY"}),
            blocked,
        )
        self.assertEqual(
            filters.console_bootstrap_blockers(blocked, {**plan, "bootstrap_allowed": False}),
            blocked,
        )

    def test_real_apply_gate_and_source_guard_are_separate(self):
        tasks = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
        source = next(
            t for t in tasks if t["name"] == "Read database identity and mandatory object guards"
        )
        self.assertNotIn(
            "admin.alembic_version",
            source["community.postgresql.postgresql_query"]["query"],
        )
        gate = next(
            t for t in tasks if t["name"].startswith("Require separate admin bootstrap approval")
        )
        self.assertEqual(
            gate["ansible.builtin.assert"]["that"],
            "ua_admin_database_bootstrap_approved is sameas true",
        )
        self.assertIn("not ansible_check_mode", gate["when"])
        mutation = yaml.safe_load((ROLE / "tasks/admin_database_bootstrap.yml").read_text())
        self.assertIn(
            "ua_target_environment in ['staging', 'test']",
            mutation[0]["ansible.builtin.assert"]["that"],
        )
        guarded = next(t for t in mutation if "block" in t)["block"][0]
        module = guarded["block"][0]
        self.assertEqual(guarded["always"][0]["uranus_admin_database"]["state"], "revoke_create")
        self.assertTrue(module["no_log"])
        self.assertFalse(module["diff"])
        self.assertEqual(module["uranus_admin_database"]["uv"], "{{ ua_uv }}")
        self.assertNotIn("credentials", module.get("register", ""))
        for task in yaml.safe_load((ROLE / "tasks/activate.yml").read_text()):
            self.assertNotIn("ADMIN_MIGRATION_DATABASE_URL", str(task))


@unittest.skipUnless(TEST_URL, "No explicitly disposable ANSIBLE_TEST_DATABASE_URL supplied")
class AdminBootstrapDatabaseTests(unittest.TestCase):
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
        cls.url = url
        cls.parent = psycopg2.connect(TEST_URL)
        cls.parent.autocommit = True
        with cls.parent.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=ANY(%s)", (list(admin_db.ROLES),))
            if cur.fetchone():
                raise RuntimeError("Refuse pre-existing project roles")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        archive = cls.root / "release.tar.gz"
        packager.package("HEAD", archive, frontend_build(cls.root))
        cls.archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        with tarfile.open(archive) as source:
            cls.manifest = json.load(source.extractfile("release.json"))
            cls.release = cls.root / cls.manifest["commit"]
            cls.release.mkdir()
            source.extractall(cls.release, filter="data")
        (cls.release / ".complete").write_text(cls.archive_hash + "\n")
        (cls.release / "backend/.venv").symlink_to(ROOT / "backend/.venv")
        (cls.release / "deployment").mkdir()
        shutil.copy(ROLE / "files/admin_database_migrate.py", cls.release / "deployment")
        cls.uv = shutil.which("uv")
        if cls.uv is None or not (cls.release / "backend/.venv").exists():
            raise RuntimeError("Install locked backend dependencies before migration tests")

    @classmethod
    def tearDownClass(cls):
        cls.parent.close()
        cls.temporary.cleanup()

    def setUp(self):
        self.database = "uranus_admin_first_install_test"
        with self.parent.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(self.database)
                )
            )
        self.conn = None
        # Register immediately after CREATE: setUp failures do not call tearDown.
        self.addCleanup(self.cleanup)
        # get_dsn_parameters() deliberately omits the password. Preserve the validated
        # test URL, overriding only the name of the database this fixture just created.
        self.conn = psycopg2.connect(TEST_URL, dbname=self.database)
        self.boundary = admin_db.AdminDatabase(self.conn, self.manifest, BOUNDARY)
        self.execute("CREATE EXTENSION postgis")
        self.execute("CREATE SCHEMA uranus")
        for name in self.boundary.source_tables:
            self.execute(
                sql.SQL("CREATE TABLE uranus.{} (id integer PRIMARY KEY)").format(
                    sql.Identifier(name)
                )
            )
        self.execute("INSERT INTO uranus.event VALUES (17)")
        self.conn.commit()
        self.values = {
            key: (
                f"postgresql+asyncpg://{role}:{PASSWORD}@127.0.0.1:"
                f"{self.url.port or 5432}/{self.database}"
            )
            for role, key in admin_db.ROLES.items()
        }

    def cleanup(self):
        if self.conn is not None:
            self.conn.close()
        with self.parent.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(self.database))
            )
            for role in admin_db.ROLES:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

    def execute(self, query, params=()):
        return self.boundary.rows(query, params)

    def migrate(self, dsn):
        with (
            patch.object(admin_db, "RELEASE_ROOT", self.root),
            patch.object(admin_db, "OWNER_UID", os.getuid()),
        ):
            admin_db.release_migration(
                str(self.release), self.manifest, self.archive_hash, self.uv
            )(dsn)

    def alembic(self, *args):
        result = subprocess.run(
            [
                self.uv,
                "run",
                "--no-cache",
                "--no-sync",
                "--offline",
                "--no-python-downloads",
                "--no-env-file",
                "alembic",
                *args,
            ],
            cwd=self.release / "backend",
            env={
                "PATH": "/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "UV_PYTHON_DOWNLOADS": "never",
                "ADMIN_MIGRATION_DATABASE_URL": self.values["ADMIN_MIGRATION_DATABASE_URL"],
            },
            capture_output=True,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0)

    def bootstrap(self, environment="test", approved=True, migrate=None):
        return self.boundary.bootstrap(environment, approved, self.values, migrate or self.migrate)

    def snapshot_source(self):
        return {
            "objects": self.execute("""SELECT c.relname,c.relkind,c.relowner,c.relacl::text
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='uranus' ORDER BY c.relname"""),
            "data": self.execute("SELECT id FROM uranus.event ORDER BY id"),
            "extensions": self.execute(
                "SELECT extname,extversion,extowner FROM pg_extension ORDER BY extname"
            ),
        }

    def prepare_existing_roles(self):
        self.boundary.prepare_roles(self.boundary.credentials(self.values), list(admin_db.ROLES))

    def test_absent_plan_read_only_and_no_approval(self):
        self.conn.set_session(readonly=True)
        plan = self.boundary.inspect("test")
        self.assertEqual(plan["state"], "ABSENT")
        self.assertTrue(plan["would_run_alembic"])
        self.assertFalse(plan["bootstrap_approved"])
        self.assertEqual(self.execute("SELECT to_regnamespace('admin')"), [(None,)])
        self.conn.rollback()
        self.conn.set_session(readonly=False)
        with self.assertRaisesRegex(ValueError, "not_authorized"):
            self.bootstrap(approved=False)
        self.assertEqual(
            self.execute(
                "SELECT rolname FROM pg_roles WHERE rolname=ANY(%s)",
                (list(admin_db.ROLES),),
            ),
            [],
        )

    def test_production_absent_never_bootstraps_even_with_approval(self):
        for approved in (False, True):
            self.assertFalse(self.boundary.inspect("production", approved)["bootstrap_allowed"])
            with self.assertRaisesRegex(ValueError, "production_bootstrap_forbidden"):
                self.bootstrap(environment="production", approved=approved)

    def test_success_head_grants_create_revocation_and_idempotence(self):
        self.prepare_existing_roles()
        before = self.snapshot_source()
        self.assertTrue(self.bootstrap())
        self.assertEqual(self.snapshot_source(), before)
        self.assertEqual(self.boundary.inspect("test")["state"], "READY")
        self.assertEqual(
            self.execute("SELECT version_num FROM admin.alembic_version"),
            [(self.manifest["head"],)],
        )
        self.assertEqual(
            self.execute(
                "SELECT has_database_privilege('admin_migrator',current_database(),'CREATE')"
            ),
            [(False,)],
        )
        with patch.object(
            self.boundary,
            "prepare_roles",
            side_effect=AssertionError("must not prepare"),
        ):
            self.assertFalse(self.bootstrap(migrate=lambda _: self.fail("must not migrate")))
        for role in ("admin_user", "admin_auth_operator"):
            self.assertEqual(
                self.execute("SELECT has_schema_privilege(%s,'admin','CREATE')", (role,)),
                [(False,)],
            )

    def test_staging_missing_roles_bootstrap(self):
        self.assertTrue(self.bootstrap(environment="staging"))
        self.assertEqual(self.boundary.inspect("staging")["state"], "READY")

    def test_exact_0011_contract_upgrades_in_production_and_preserves_data(self):
        self.bootstrap()
        self.execute(
            "INSERT INTO admin.auth_login_bucket(key,attempts,window_end) "
            "VALUES ('preserved',3,now())"
        )
        self.conn.commit()
        self.alembic("downgrade", "0011")
        plan = self.boundary.inspect("production", upgrade_approved=True)
        self.assertEqual(plan["state"], "UPGRADEABLE")
        self.assertEqual(plan["current_head"], "0011")
        self.assertTrue(plan["would_run_alembic"])
        self.assertEqual(plan["blockers"], [])
        with self.assertRaisesRegex(ValueError, "admin_upgrade_not_authorized"):
            self.boundary.upgrade("production", False, self.values, self.migrate)
        self.assertTrue(self.boundary.upgrade("production", True, self.values, self.migrate))
        self.assertEqual(self.boundary.inspect("production")["state"], "READY")
        self.assertEqual(
            self.execute("SELECT attempts FROM admin.auth_login_bucket WHERE key='preserved'"),
            [(3,)],
        )

    def test_exact_0012_contract_upgrades_in_production(self):
        self.bootstrap()
        self.alembic("downgrade", "0012")
        plan = self.boundary.inspect("production", upgrade_approved=True)
        self.assertEqual(plan["state"], "UPGRADEABLE")
        self.assertEqual(plan["current_head"], "0012")
        self.assertTrue(self.boundary.upgrade("production", True, self.values, self.migrate))
        self.assertEqual(self.boundary.inspect("production")["state"], "READY")

    def test_exact_0013_column_upgrade_preserves_history_and_grants(self):
        self.bootstrap()
        self.alembic("downgrade", "0013")
        source_before = self.snapshot_source()
        self.execute("""INSERT INTO admin.auth_account(id,login,password_hash,is_active)
            VALUES ('00000000-0000-4000-8000-000000000800','snooze-migration','fixture',true)""")
        self.execute("""INSERT INTO admin.finding
            (id,rule,severity,entity_type,entity_id,message,first_seen_at,last_seen_at)
            VALUES ('snooze-migration','fixture','warning','event','fixture',
                    'Preserve',now(),now())""")
        self.execute("""INSERT INTO admin.assignment
            (id,finding_id,entity_type,entity_key,assigned_to_admin_id,assigned_by_subject,
             status,created_at,updated_at,version)
            VALUES ('00000000-0000-4000-8000-000000000810','snooze-migration','event','fixture',
                    '00000000-0000-4000-8000-000000000800','admin:fixture','open',now(),now(),1)""")
        self.execute("""INSERT INTO admin.assignment_event
            (id,assignment_id,version,kind,occurred_at,actor,assigned_to_admin_id,status)
            VALUES ('00000000-0000-4000-8000-000000000820',
                    '00000000-0000-4000-8000-000000000810',1,'created',now(),'admin:fixture',
                    '00000000-0000-4000-8000-000000000800','open')""")
        self.conn.commit()
        history_before = self.execute("SELECT to_jsonb(e) FROM admin.assignment_event e")
        self.conn.commit()  # Release the test reader before ALTER TABLE acquires its DDL lock.
        plan = self.boundary.inspect("production", upgrade_approved=True)
        self.assertEqual(plan["state"], "UPGRADEABLE")
        self.assertEqual(plan["current_head"], "0013")
        self.assertEqual(plan["blockers"], [])
        self.assertTrue(self.boundary.upgrade("production", True, self.values, self.migrate))
        self.assertEqual(self.boundary.inspect("production")["state"], "READY")
        self.assertEqual(self.snapshot_source(), source_before)
        self.assertEqual(
            self.execute("SELECT to_jsonb(e) - 'snoozed_until' FROM admin.assignment_event e"),
            history_before,
        )
        self.assertEqual(self.execute("SELECT snoozed_until FROM admin.assignment"), [(None,)])
        self.assertEqual(
            self.execute(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='admin' "
                "AND table_name IN ('assignment','assignment_event') "
                "AND column_name='snoozed_until' "
                "ORDER BY table_name"
            ),
            [("assignment",), ("assignment_event",)],
        )
        self.assertEqual(
            self.execute(
                "SELECT has_table_privilege('admin_user','admin.assignment','UPDATE'), "
                "has_table_privilege('admin_user','admin.assignment_event','UPDATE'), "
                "has_table_privilege('admin_user','admin.assignment_event','DELETE')"
            ),
            [(True, False, False)],
        )

    def test_exact_0014_upgrade_preserves_accounts_and_separates_journalist_grants(self):
        self.bootstrap()
        self.alembic("downgrade", "0014")
        source_before = self.snapshot_source()
        self.execute("""INSERT INTO admin.auth_account(id,login,password_hash,is_active)
            VALUES ('00000000-0000-4000-8000-000000000800','research-migration','fixture',true)""")
        self.execute("""INSERT INTO admin.auth_system_admin(account_id,granted_by)
            VALUES ('00000000-0000-4000-8000-000000000800','fixture-operator')""")
        before = self.execute("SELECT to_jsonb(a) FROM admin.auth_account a")
        grants_before = self.execute("SELECT to_jsonb(g) FROM admin.auth_system_admin g")
        self.conn.commit()
        plan = self.boundary.inspect("production", upgrade_approved=True)
        self.assertEqual(plan["state"], "UPGRADEABLE")
        self.assertEqual(plan["current_head"], "0014")
        self.assertEqual(plan["blockers"], [])
        self.assertTrue(self.boundary.upgrade("production", True, self.values, self.migrate))
        self.assertEqual(self.boundary.inspect("production")["state"], "READY")
        self.assertEqual(self.snapshot_source(), source_before)
        self.assertEqual(self.execute("SELECT to_jsonb(a) FROM admin.auth_account a"), before)
        self.assertEqual(
            self.execute("SELECT to_jsonb(g) FROM admin.auth_system_admin g"), grants_before
        )
        self.assertEqual(self.execute("SELECT count(*) FROM admin.auth_journalist"), [(0,)])
        self.assertEqual(
            self.execute(
                "SELECT has_table_privilege('admin_user','admin.auth_journalist','SELECT'), "
                "has_table_privilege('admin_user','admin.auth_journalist','INSERT,UPDATE,DELETE'), "
                "has_table_privilege('admin_auth_operator','admin.auth_journalist','INSERT'), "
                "has_table_privilege('admin_auth_operator','admin.auth_journalist','DELETE')"
            ),
            [(True, False, True, True)],
        )

    def test_existing_upgrade_login_is_checked_without_changing_schema(self):
        self.bootstrap()
        self.alembic("downgrade", "0011")
        self.boundary.verify_upgrade_credentials(self.values)
        self.assertEqual(self.boundary.inspect("production")["state"], "UPGRADEABLE")
        self.assertEqual(self.execute("SELECT version_num FROM admin.alembic_version"), [("0011",)])

    def test_unusable_migrator_login_blocks_before_alembic(self):
        self.bootstrap()
        self.alembic("downgrade", "0011")
        self.execute("ALTER ROLE admin_migrator NOLOGIN")
        self.conn.commit()
        try:
            with self.assertRaises(psycopg2.OperationalError):
                self.boundary.verify_upgrade_credentials(self.values)
            self.assertEqual(self.boundary.diagnostic["check"], "migrator_connection")
            self.assertEqual(
                self.execute("SELECT version_num FROM admin.alembic_version"), [("0011",)]
            )
        finally:
            self.execute("ALTER ROLE admin_migrator LOGIN")
            self.conn.commit()

    def test_0011_with_additional_drift_is_never_upgraded(self):
        self.bootstrap()
        self.alembic("downgrade", "0011")
        for mutation in (
            "ALTER TABLE admin.finding ADD COLUMN unexpected text",
            "CREATE INDEX unknown_admin_index ON admin.finding(rule)",
            "GRANT DELETE ON admin.finding TO admin_user",
            "GRANT SELECT ON admin.finding TO PUBLIC",
        ):
            with self.subTest(mutation=mutation):
                self.execute(mutation)
                plan = self.boundary.inspect("production", upgrade_approved=True)
                self.assertEqual(plan["state"], "DRIFTED")
                self.assertIn("upgrade_source_contract_mismatch", plan["blockers"])
                with self.assertRaisesRegex(ValueError, "admin_upgrade_not_authorized"):
                    self.boundary.upgrade("production", True, self.values, self.migrate)
                self.conn.rollback()

    def test_partial_schema_is_drifted_not_repaired(self):
        self.execute("CREATE SCHEMA admin")
        self.conn.commit()
        self.assertEqual(self.boundary.inspect("test")["state"], "DRIFTED")
        with self.assertRaisesRegex(ValueError, "not_authorized"):
            self.bootstrap()

    def test_ready_drift_head_owners_grants_objects_and_membership(self):
        self.bootstrap()
        mutations = (
            "UPDATE admin.alembic_version SET version_num='0000'",
            "ALTER SCHEMA admin OWNER TO postgres",
            "ALTER TABLE admin.finding OWNER TO admin_user",
            "GRANT admin_user TO admin_auth_operator",
            "GRANT CREATE ON DATABASE uranus_admin_first_install_test TO admin_migrator",
            "CREATE TABLE admin.unknown(id int)",
            "CREATE INDEX unknown_admin_index ON admin.finding(rule)",
            "ALTER TABLE admin.finding ADD COLUMN unexpected text",
            "ALTER TABLE admin.alembic_version RENAME TO old_version; "
            "CREATE VIEW admin.alembic_version AS SELECT version_num FROM admin.old_version",
            "CREATE FUNCTION admin.unknown() RETURNS int LANGUAGE sql AS 'SELECT 1'",
            "GRANT SELECT ON admin.finding TO PUBLIC",
            "GRANT DELETE ON admin.finding TO admin_user",
            "REVOKE SELECT ON admin.auth_account FROM admin_auth_operator",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.execute(mutation)
                self.assertEqual(self.boundary.inspect("test")["state"], "DRIFTED")
                with self.assertRaisesRegex(ValueError, "not_authorized"):
                    self.bootstrap()
                self.conn.rollback()

    def test_existing_unsafe_roles_source_rls_and_owner_fail_before_mutation(self):
        self.prepare_existing_roles()
        for mutation in (
            "ALTER ROLE admin_user CREATEDB",
            "GRANT admin_migrator TO admin_user",
            "GRANT CREATE ON DATABASE uranus_admin_first_install_test TO admin_user",
            "ALTER TABLE uranus.event ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE uranus.event OWNER TO admin_user",
            "GRANT UPDATE ON uranus.event TO admin_user",
        ):
            with self.subTest(mutation=mutation):
                self.execute(mutation)
                self.assertEqual(self.boundary.inspect("test")["state"], "DRIFTED")
                with self.assertRaisesRegex(ValueError, "not_authorized"):
                    self.bootstrap()
                self.conn.rollback()

    def test_alembic_failure_revokes_create_and_no_runtime_grants(self):
        def fail(_):
            self.assertEqual(
                self.execute(
                    "SELECT has_database_privilege('admin_migrator',current_database(),'CREATE')"
                ),
                [(True,)],
            )
            raise ValueError("injected_alembic_failure")

        with self.assertRaisesRegex(ValueError, "injected_alembic_failure"):
            self.bootstrap(migrate=fail)
        self.assertEqual(
            self.execute(
                "SELECT has_database_privilege('admin_migrator',current_database(),'CREATE')"
            ),
            [(False,)],
        )
        self.assertEqual(self.execute("SELECT to_regnamespace('admin')"), [(None,)])

    def test_grant_failure_rolls_back_migration_and_grants_atomically(self):
        launcher = self.release / "deployment/admin_database_migrate.py"
        original = launcher.read_text()
        launcher.write_text(
            original.replace(
                'await apply_grants(conn, manifest["runtime_grants"])',
                'await apply_grants(conn, manifest["runtime_grants"]); '
                "raise RuntimeError('injected')",
            )
        )
        try:
            with self.assertRaisesRegex(ValueError, "release_migration_failed"):
                self.bootstrap()
        finally:
            launcher.write_text(original)
        self.assertEqual(self.execute("SELECT to_regnamespace('admin')"), [(None,)])
        self.assertEqual(
            self.execute(
                "SELECT has_database_privilege('admin_migrator',current_database(),'CREATE')"
            ),
            [(False,)],
        )
        self.assertEqual(self.boundary.inspect("test")["state"], "ABSENT")

    def test_release_manifest_and_archive_mismatch_fail_before_execution(self):
        with (
            patch.object(admin_db, "RELEASE_ROOT", self.root),
            patch.object(admin_db, "OWNER_UID", os.getuid()),
        ):
            with self.assertRaisesRegex(ValueError, "incomplete_release"):
                admin_db.release_migration(str(self.release), self.manifest, "0" * 64, self.uv)

    def test_actual_alembic_failure_rolls_back_ddl_and_revokes_create(self):
        # Inject a failure after real migration DDL but before its transaction commits.
        env = self.release / "backend/migrations/env.py"
        original = env.read_text()
        env.write_text(
            original.replace(
                "context.run_migrations()",
                "context.run_migrations(); raise RuntimeError('injected')",
            )
        )
        try:
            with self.assertRaisesRegex(ValueError, "release_migration_failed"):
                self.bootstrap()
            self.assertEqual(self.execute("SELECT to_regnamespace('admin')"), [(None,)])
            self.assertEqual(
                self.execute(
                    "SELECT has_database_privilege('admin_migrator',current_database(),'CREATE')"
                ),
                [(False,)],
            )
        finally:
            env.write_text(original)

    def test_independent_create_cleanup_is_idempotent(self):
        self.prepare_existing_roles()
        self.execute(
            sql.SQL("GRANT CREATE ON DATABASE {} TO admin_migrator").format(
                sql.Identifier(self.database)
            )
        )
        self.conn.commit()
        self.assertTrue(self.boundary.revoke_create())
        self.assertFalse(self.boundary.revoke_create())

    def test_actual_ansible_check_apply_and_second_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "library"
            library.mkdir()
            code = (ROLE / "library/uranus_admin_database.py").read_text()
            start = code.index("        conn = psycopg2.connect(", code.index("def main():"))
            end = code.index("        conn.set_session", start)
            # Credentials remain in the inherited test environment, not generated code.
            code = (
                code[:start]
                + "        from os import environ\n"
                + "        conn = psycopg2.connect(environ['ANSIBLE_TEST_DATABASE_URL'], "
                + f"dbname={self.database!r})\n"
                + code[end:]
            )
            code = code.replace(
                'Path("/var/lib/uranus-admin/releases")', f"Path({str(self.root)!r})"
            )
            code = code.replace("OWNER_UID = 0", f"OWNER_UID = {os.getuid()}")
            (library / "uranus_admin_database.py").write_text(code)
            variables = root / "secrets.yml"
            variables.write_text(yaml.safe_dump({"adopted_credentials": self.values}))
            variables.chmod(0o600)
            play = [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {"ansible_python_interpreter": sys.executable},
                    "vars_files": [str(variables)],
                    "tasks": [
                        {
                            "uranus_admin_database": {
                                "state": "bootstrap",
                                "environment": "test",
                                "approved": True,
                                "manifest": self.manifest,
                                "boundary": BOUNDARY,
                                "credentials": "{{ adopted_credentials }}",
                                "release": str(self.release),
                                "archive_hash": self.archive_hash,
                                "uv": self.uv,
                            },
                            "register": "outcome",
                            "no_log": True,
                        },
                        {"ansible.builtin.debug": {"var": "outcome.admin_database"}},
                    ],
                }
            ]
            playbook = root / "play.yml"
            playbook.write_text(yaml.safe_dump(play))
            for check, changed, state in (
                (True, 0, "ABSENT"),
                (False, 1, "READY"),
                (False, 0, "READY"),
            ):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "ansible.cli.playbook",
                        "-i",
                        "localhost,",
                        str(playbook),
                        *(["--check", "--diff"] if check else []),
                    ],
                    env={
                        **os.environ,
                        "ANSIBLE_LIBRARY": str(library),
                        "ANSIBLE_LOCAL_TEMP": str(root / "local"),
                        "ANSIBLE_REMOTE_TEMP": str(root / "remote"),
                        # CI's system Python need not contain the uv test dependencies.
                        # Reject fallback even when a developer has psycopg2 globally.
                        "ANSIBLE_PYTHON_INTERPRETER": str(root / "unexpected-target-python"),
                    },
                    text=True,
                    capture_output=True,
                    timeout=90,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'"state": "{state}"', result.stdout)
                self.assertRegex(result.stdout, rf"changed={changed}\s")
                self.assertNotIn(PASSWORD, result.stdout + result.stderr)
                self.assertNotIn("postgresql+asyncpg://", result.stdout + result.stderr)
