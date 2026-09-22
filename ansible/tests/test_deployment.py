"""Local safety regressions: no SSH, production connection or filesystem mutation."""

import ast
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import yaml
from ansible.errors import AnsibleFilterError
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"
ROLE = ANSIBLE / "roles/uranus_admin"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


filters = load("deployment_filters", ANSIBLE / "filter_plugins/uranus_admin.py")
packager = load("packager", ANSIBLE / "scripts/package_release.py")


def nginx_defaults():
    """Resolve the nested Ansible defaults for tests using plain Jinja rather than Ansible."""
    values = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    name = urlsplit(values["ua_public_origin"]).hostname
    values.update(
        ua_nginx_server_name=name,
        ua_tls_certificate=f"/etc/letsencrypt/live/{name}/fullchain.pem",
        ua_tls_certificate_key=f"/etc/letsencrypt/live/{name}/privkey.pem",
    )
    return values


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            "DATABASE_URL": "postgresql+asyncpg://uranus_reader:fake%23%24@localhost:5432/oklab",
            "ADMIN_DATABASE_URL": "postgresql+asyncpg://admin_user:fake@127.0.0.1:5432/oklab",
            "ADMIN_MIGRATION_DATABASE_URL": "privileged-test-value",
            "ADMIN_AUTH_MANAGEMENT_DATABASE_URL": "operator-test-value",
            "DEV_ADMIN_TOKEN": "dev-test-value",
        }

    def test_separation_and_debug_gates(self):
        for debug in (True, False):
            result = filters.runtime_environment(self.values, self.values, debug=debug)
            self.assertFalse(filters.PRIVILEGED & result.keys())
            self.assertEqual(result["DATABASE_URL"], self.values["DATABASE_URL"])
            self.assertEqual(result["APP_ENV"], "production")
            self.assertEqual(result["APP_DEBUG"], str(debug).lower())
            self.assertEqual(result["ALLOW_PRODUCTION_DEBUG"], str(debug).lower())
            for flag in ("DEV_AUTH_ENABLED", "OPENAPI_ENABLED", "NOTIFICATIONS_DELIVERY_ENABLED"):
                self.assertEqual(result[flag], "false")
        self.assertEqual(set(filters.privileged_environment(self.values)), filters.PRIVILEGED)

    def test_lossless_supported_environment_roundtrip(self):
        values = {"PASSWORD": "fake # $! \\ \" apostrophe' ä", "EMPTY": ""}
        self.assertEqual(filters.parse_environment(filters.render_environment(values)), values)

    def test_reject_ambiguous_input_without_leaking_values(self):
        for value in ("A=fake-secret\nA=other", "A=${SECRET}", "A", 'A="bad\nvalue"'):
            with self.assertRaises(AnsibleFilterError) as error:
                filters.parse_environment(value)
            self.assertNotIn("fake-secret", str(error.exception))

    def test_reject_wrong_identity_target_and_secret_overrides(self):
        for value in (
            "postgresql+asyncpg://postgres:fake-secret@localhost/oklab",
            "postgresql+asyncpg://uranus_reader:fake-secret@elsewhere/oklab",
            "postgresql+asyncpg://uranus_reader:fake-secret@localhost/other",
            "postgresql+asyncpg://uranus_reader:fake-secret@localhost/oklab?options=anything",
        ):
            with self.assertRaises(AnsibleFilterError) as error:
                filters.runtime_environment({**self.values, "DATABASE_URL": value}, self.values)
            self.assertNotIn("fake-secret", str(error.exception))
        with self.assertRaises(AnsibleFilterError):
            filters.runtime_environment(self.values, self.values, {"DATABASE_URL": "other"})
        with self.assertRaises(AnsibleFilterError):
            filters.runtime_environment({**self.values, "UNKNOWN": "fake-secret"}, self.values)


class ArtifactTests(unittest.TestCase):
    def test_latest_main_fetches_new_remote_commit_without_switching_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, checkout = root / "remote", root / "checkout"

            def git(path, *args):
                return subprocess.check_output(
                    ["git", "-C", str(path), *args], text=True, stderr=subprocess.PIPE
                ).strip()

            remote.mkdir()
            git(remote, "init", "--initial-branch=main")
            git(remote, "config", "user.name", "Local test")
            git(remote, "config", "user.email", "fixture@example.invalid")
            (remote / "source").write_text("first")
            git(remote, "add", "source")
            git(remote, "commit", "-m", "first")
            git(root, "clone", str(remote), str(checkout))
            initial = git(checkout, "rev-parse", "HEAD")
            git(checkout, "switch", "-c", "unrelated-feature")
            (checkout / "source").write_text("uncommitted local work")
            (remote / "source").write_text("latest main")
            git(remote, "commit", "-am", "second")
            latest = git(remote, "rev-parse", "HEAD")
            self.assertNotEqual(initial, latest)
            self.assertEqual(packager.latest_main(checkout), latest)
            self.assertEqual(git(checkout, "rev-parse", "HEAD"), initial)
            self.assertEqual(git(checkout, "branch", "--show-current"), "unrelated-feature")
            self.assertEqual((checkout / "source").read_text(), "uncommitted local work")
            # A previously successful fetch must never become an offline fallback.
            git(checkout, "remote", "set-url", "origin", str(root / "missing"))
            with self.assertRaises(subprocess.CalledProcessError):
                packager.latest_main(checkout)

    def test_cli_fetch_failure_never_packages_stale_sources(self):
        with (
            patch.object(packager, "latest_main", side_effect=RuntimeError("fetch failed")),
            patch.object(packager, "package") as package,
            tempfile.TemporaryDirectory() as directory,
        ):
            output = Path(directory) / "release.tar.gz"
            with self.assertRaisesRegex(RuntimeError, "fetch failed"):
                packager.main(["--output", str(output)])
            package.assert_not_called()
            self.assertFalse(output.exists())

    def test_cli_passes_fetched_commit_to_packager_and_preserves_existing_archive(self):
        with (
            patch.object(packager, "latest_main", return_value="a" * 40) as latest,
            patch.object(packager, "package") as package,
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            output = Path(directory) / "release.tar.gz"
            packager.main(["--output", str(output)])
            package.assert_called_once_with("a" * 40, str(output))
            output.write_bytes(b"existing archive")
            latest.reset_mock()
            package.reset_mock()
            with self.assertRaises(SystemExit):
                packager.main(["--output", str(output)])
            latest.assert_not_called()
            package.assert_not_called()
            self.assertEqual(output.read_bytes(), b"existing archive")

    def test_controller_filters_and_preflight_expressions_in_check_mode(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            artifact = root / "release.tar.gz"
            packager.package("HEAD", artifact)
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            preflight = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
            assertions = [
                task
                for task in preflight
                if task["name"]
                in (
                    "Require the audited Ubuntu release",
                    "Require the audited rate zones without silently changing shared definitions",
                )
            ]
            zones = (
                "limit_req_zone $binary_remote_addr zone=uranus_admin_general:10m rate=10r/s;\n"
                "limit_req_zone $binary_remote_addr zone=uranus_admin_api:10m rate=5r/s;\n\n"
                "limit_conn_zone $binary_remote_addr zone=uranus_admin_conn:10m;\n"
            )
            variables = {
                "artifact": str(artifact),
                "digest": digest,
                "commit": commit,
                "ua_release_dir": "/var/lib/uranus-admin/releases/" + commit,
                "ua_config_dir": "/etc/uranus-admin",
                "ua_uv": "/usr/local/bin/uv",
                "ua_os_release": {
                    "content": base64.b64encode(b'ID=ubuntu\nVERSION_ID="24.04"\n').decode()
                },
                "ua_rate_zones": {"content": base64.b64encode(zones.encode()).decode()},
            }
            play = [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": variables,
                    "tasks": [
                        {
                            "ansible.builtin.set_fact": {
                                "manifest": "{{ artifact | ua_manifest(digest, commit) }}"
                            }
                        },
                        {"ansible.builtin.assert": {"that": "manifest.commit == commit"}},
                        *assertions,
                        {
                            "ansible.builtin.set_fact": {
                                "unit": "{{ lookup('template', '"
                                + str(ROLE / "templates/backend.service.j2")
                                + "') }}"
                            }
                        },
                        {
                            "ansible.builtin.assert": {
                                "that": "'EnvironmentFile=/etc/uranus-admin/runtime.env' in unit"
                            }
                        },
                    ],
                }
            ]
            path = root / "play.yml"
            path.write_text(yaml.safe_dump(play))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ansible.cli.playbook",
                    "-i",
                    "localhost,",
                    str(path),
                    "--check",
                ],
                env={
                    **os.environ,
                    "ANSIBLE_CONFIG": str(ANSIBLE / "ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                },
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_archive_rejects_traversal_links_secrets_and_writable_sources(self):
        for name, kind, mode in (
            ("backend/../escape", tarfile.REGTYPE, 0o644),
            ("backend/app/link", tarfile.SYMTYPE, 0o644),
            ("backend/.env", tarfile.REGTYPE, 0o600),
            ("backend/tests/fixture.py", tarfile.REGTYPE, 0o644),
            ("backend/app/mutable.py", tarfile.REGTYPE, 0o666),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.tar.gz"
                with tarfile.open(path, "w:gz") as archive:
                    member = tarfile.TarInfo(name)
                    member.type, member.mode = kind, mode
                    archive.addfile(member)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(AnsibleFilterError):
                    filters.artifact_manifest(path, digest, "a" * 40)

    def test_manifest_capability_requires_exact_environment_key_list(self):
        for keys in ("SQL_CONSOLE_DATABASE_URL", ["DATABASE_URL", "DATABASE_URL"], [None]):
            with self.subTest(keys=keys), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "manifest.tar.gz"
                content = json.dumps(
                    {
                        "commit": "a" * 40,
                        "head": "0012",
                        "runtime_grants": {"finding": ["SELECT"]},
                        "environment_keys": keys,
                    }
                ).encode()
                with tarfile.open(path, "w:gz") as archive:
                    entry = tarfile.TarInfo("release.json")
                    entry.mode, entry.size = 0o644, len(content)
                    archive.addfile(entry, io.BytesIO(content))
                with self.assertRaisesRegex(AnsibleFilterError, "capability contract"):
                    filters.artifact_manifest(
                        path, hashlib.sha256(path.read_bytes()).hexdigest(), "a" * 40
                    )

    def test_old_admin_manifest_is_rejected_before_target_access(self):
        complete = {
            "commit": "a" * 40,
            "head": "0012",
            "runtime_grants": {"finding": ["SELECT"]},
            "environment_keys": ["DATABASE_URL"],
            "operator_grants": {"alembic_version": ["SELECT"]},
            "admin_indexes": ["alembic_version_pkc"],
            "admin_columns": {"alembic_version": ["version_num"]},
        }
        for key in ("operator_grants", "admin_indexes", "admin_columns"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                manifest = {k: v for k, v in complete.items() if k != key}
                path = Path(directory) / "old-manifest.tar.gz"
                content = json.dumps(manifest).encode()
                with tarfile.open(path, "w:gz") as archive:
                    entry = tarfile.TarInfo("release.json")
                    entry.mode, entry.size = 0o644, len(content)
                    archive.addfile(entry, io.BytesIO(content))
                with self.assertRaisesRegex(AnsibleFilterError, "Repackage the selected release"):
                    filters.artifact_manifest(
                        path, hashlib.sha256(path.read_bytes()).hexdigest(), "a" * 40
                    )

    def test_reproducible_committed_sources_and_current_metadata(self):
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            paths = [Path(directory) / name for name in ("one.tar.gz", "two.tar.gz")]
            for path in paths:
                packager.package(commit, path)
            self.assertEqual(paths[0].read_bytes(), paths[1].read_bytes())
            digest = hashlib.sha256(paths[0].read_bytes()).hexdigest()
            manifest = filters.artifact_manifest(paths[0], digest, commit)
            self.assertEqual(manifest["head"], "0013")
            self.assertEqual(len(manifest["runtime_grants"]), 19)
            self.assertNotIn("DELETE", json.dumps(manifest["runtime_grants"]))
            with self.assertRaises(AnsibleFilterError):
                filters.artifact_manifest(paths[0], "0" * 64, commit)


class DeploymentBoundaryTests(unittest.TestCase):
    def test_idempotent_and_service_specific_activation(self):
        backend, worker, frontend = (
            "uranus-admin-backend.service",
            "uranus-admin-check-worker.service",
            "uranus-admin-frontend.service",
        )
        states = {name: {"state": "running"} for name in (backend, worker, frontend)}
        plan = filters.activation_plan([], states, "/etc/uranus-admin")
        self.assertEqual(plan["restart_services"], [])
        self.assertFalse(plan["nginx_changed"])
        self.assertFalse(plan["units_changed"])
        plan = filters.activation_plan(
            ["/etc/uranus-admin/runtime.env"], states, "/etc/uranus-admin"
        )
        self.assertEqual(plan["restart_services"], [backend, worker])
        plan = filters.activation_plan(
            ["/etc/nginx/sites-available/uranus-admin"], states, "/etc/uranus-admin"
        )
        self.assertEqual(plan["restart_services"], [])
        self.assertTrue(plan["nginx_changed"])
        plan = filters.activation_plan(
            ["/etc/systemd/system/" + frontend], states, "/etc/uranus-admin"
        )
        self.assertEqual(plan["restart_services"], [frontend])
        states[worker]["state"] = "stopped"
        self.assertEqual(
            filters.activation_plan([], states, "/etc/uranus-admin")["restart_services"], [worker]
        )

    def test_real_apply_refused_before_host_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "inventory.yml"
            inventory.write_text(
                yaml.safe_dump(
                    {
                        "all": {
                            "children": {
                                "uranus_admin": {
                                    "hosts": {"localhost": {"ansible_connection": "local"}}
                                }
                            }
                        }
                    }
                )
            )
            env = {
                **os.environ,
                "ANSIBLE_CONFIG": str(ANSIBLE / "ansible.cfg"),
                "ANSIBLE_LOCAL_TEMP": directory + "/tmp",
                "ANSIBLE_NOCOLOR": "1",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ansible.cli.playbook",
                    "-i",
                    str(inventory),
                    str(ANSIBLE / "deploy.yml"),
                    "-e",
                    "ansible_become=false",
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Apply requires reviewed dry run", result.stdout)
            self.assertNotIn("Read the hostname", result.stdout)

    def test_existing_postgresql_preflight_stays_read_only(self):
        def walk(tasks):
            for task in tasks:
                for name, args in task.items():
                    if name == "ansible.builtin.file" and args.get("recurse"):
                        # venv/bin/python links to the system interpreter; never chmod its target.
                        self.assertIs(args.get("follow"), False)
                    if name == "ansible.builtin.file" and args.get("state") == "link":
                        self.assertIs(args.get("follow"), False)
                    if name.startswith("community.postgresql."):
                        self.assertEqual(name, "community.postgresql.postgresql_query")
                        self.assertEqual(args["login_db"], "oklab")
                        self.assertIn(
                            "default_transaction_read_only=on", args["connect_params"]["options"]
                        )
                    if name == "uranus_sql_console":
                        self.assertIn(args["state"], {"plan", "provision", "verify", "audit"})
                        if args["state"] == "audit":
                            self.assertTrue(task["no_log"])
                        if args["state"] == "provision":
                            self.assertTrue(task["no_log"])
                            self.assertFalse(task["diff"])
                    if name in ("block", "rescue", "always"):
                        walk(args)

        for path in (ROLE / "tasks").glob("*.yml"):
            walk(yaml.safe_load(path.read_text()))
        text = "\n".join(p.read_text() for p in (ROLE / "tasks").glob("*.yml"))
        for forbidden in (
            "alembic upgrade",
            "pg_restore",
            "dropdb",
            "createdb",
            "postgresql_privs",
        ):
            self.assertNotIn(forbidden, text)

    def test_runtime_verifier_has_no_mutating_entrypoint(self):
        tree = ast.parse((ROLE / "files/verify_runtime.py").read_text())
        modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertNotIn("app.main", modules)
        self.assertNotIn("app.check_worker", modules)
        self.assertIn("app.source_schema_verify", modules)

    def test_runtime_verification_uses_uv_without_sync_or_downloads(self):
        tasks = yaml.safe_load((ROLE / "tasks/release.yml").read_text())
        interpreter = next(task for task in tasks if "different Python interpreter" in task["name"])
        self.assertIn("--no-cache", interpreter["ansible.builtin.command"]["argv"])
        verification = next(task for task in tasks if "actual runtime DSNs" in task["name"])
        self.assertEqual(
            verification["ansible.builtin.command"]["argv"][:8],
            [
                "{{ ua_uv }}",
                "run",
                "--no-cache",
                "--no-sync",
                "--offline",
                "--no-python-downloads",
                "--no-env-file",
                "python",
            ],
        )
        build = next(task for task in tasks if "block" in task)["block"]
        install = next(task for task in build if "Python runtime dependencies" in task["name"])
        self.assertEqual(
            install["ansible.builtin.command"]["argv"],
            [
                "{{ ua_uv }}",
                "run",
                "--locked",
                "--no-dev",
                "--no-env-file",
                "--python",
                "{{ ua_python }}",
                "python",
                "--version",
            ],
        )

    @unittest.skipUnless(shutil.which("uv"), "uv absent")
    def test_rendered_python_services_start_without_home_cache_or_release_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "release/backend"
            project.mkdir(parents=True)
            (project / "pyproject.toml").write_text(
                '[project]\nname = "runtime-fixture"\nversion = "0.0.0"\n'
                'requires-python = ">=3.13"\ndependencies = []\n'
                "[tool.uv]\npackage = false\n"
            )
            dotenv = root / "unexpected.env"
            dotenv.write_text("UA_TEST_DOTENV=unexpected\n")
            app = project / "app"
            app.mkdir()
            (app / "__init__.py").touch()
            probe = (
                "import os, sys\n"
                "assert sys.prefix != sys.base_prefix\n"
                "assert 'UA_TEST_DOTENV' not in os.environ\n"
                "print('runtime-started')\n"
            )
            for entrypoint in ("__main__.py", "check_worker.py"):
                (app / entrypoint).write_text(probe)
            environment = {
                **os.environ,
                "UV_CACHE_DIR": str(root / "cache"),
                "UV_ENV_FILE": str(dotenv),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            environment.pop("VIRTUAL_ENV", None)
            environment.pop("UV_PROJECT_ENVIRONMENT", None)
            environment.pop("UA_TEST_DOTENV", None)
            uv = shutil.which("uv")
            subprocess.run(
                [
                    uv,
                    "run",
                    "--offline",
                    "--no-python-downloads",
                    "--no-env-file",
                    "--python",
                    sys.executable,
                    "python",
                    "--version",
                ],
                cwd=project,
                env=environment,
                check=True,
                capture_output=True,
                timeout=30,
            )
            home = root / "home"
            (home / ".cache").mkdir(parents=True)
            # A regular-file sentinel rejects cache directory access even as root.
            # This reproduces the unavailable Home cache without needing systemd.
            cache = home / ".cache/uv"
            cache.write_text("persistent cache unavailable")
            environment["HOME"] = str(home)
            for key in ("UV_CACHE_DIR", "XDG_CACHE_HOME", "UV_NO_CACHE"):
                environment.pop(key, None)
            before = {str(p.relative_to(project)): p.stat().st_mtime_ns for p in project.rglob("*")}
            templates = Environment(
                loader=FileSystemLoader(ROLE / "templates"), undefined=StrictUndefined
            )
            for component in ("backend", "check-worker"):
                with self.subTest(component=component):
                    unit = templates.get_template(component + ".service.j2").render(
                        ua_release_dir=str(project.parent),
                        ua_config_dir=str(root / "etc"),
                        ua_uv=uv,
                    )
                    command = shlex.split(
                        next(
                            line for line in unit.splitlines() if line.startswith("ExecStart=")
                        ).removeprefix("ExecStart=")
                    )
                    # Negative control: the previous startup fails on this fixture.
                    old = subprocess.run(
                        [arg for arg in command if arg != "--no-cache"],
                        cwd=project,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertNotEqual(old.returncode, 0)
                    self.assertIn(str(cache), old.stderr)
                    result = subprocess.run(
                        command,
                        cwd=project,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), "runtime-started")
            self.assertEqual(cache.read_text(), "persistent cache unavailable")
            self.assertEqual(
                before,
                {str(p.relative_to(project)): p.stat().st_mtime_ns for p in project.rglob("*")},
            )

    def test_units_and_proxy_preserve_boundaries(self):
        env = Environment(loader=FileSystemLoader(ROLE / "templates"), undefined=StrictUndefined)
        values = {
            "ua_release_dir": "/var/lib/uranus-admin/releases/" + "a" * 40,
            "ua_config_dir": "/etc/uranus-admin",
            "ua_node": "/usr/bin/node",
            "ua_uv": "/usr/local/bin/uv",
        }
        for name in ("backend", "check-worker", "frontend", "notification-worker"):
            unit = env.get_template(name + ".service.j2").render(values)
            self.assertIn("User=oklab", unit)
            if name != "frontend":
                self.assertIn(
                    "ExecStart=/usr/local/bin/uv run --no-cache --no-sync --offline "
                    "--no-python-downloads --no-env-file python -m app",
                    unit,
                )
                self.assertNotIn(".venv/bin", unit)
            self.assertIn("UMask=0027", unit)
            self.assertIn("UnsetEnvironment=", unit)
            for setting in ("ProtectSystem=strict", "ProtectHome=read-only", "PrivateTmp=true"):
                self.assertIn(setting, unit)
            self.assertNotIn("ReadWritePaths=", unit)
        notification = env.get_template("notification-worker.service.j2").render(values)
        self.assertIn("Type=oneshot", notification)
        self.assertIn("python -m app.notification_worker --once", notification)
        self.assertIn("EnvironmentFile=/etc/uranus-admin/runtime.env", notification)
        self.assertNotIn("[Install]", notification)
        self.assertNotIn("Restart=", notification)
        frontend = env.get_template("frontend.service.j2").render(values)
        self.assertNotIn("EnvironmentFile=", frontend)
        self.assertIn("NUXT_TRUSTED_INGRESS_IPS=127.0.0.1", frontend)
        site = env.get_template("nginx-site.conf.j2").render(
            {**yaml.safe_load((ROLE / "defaults/main.yml").read_text()), **values}
        )
        self.assertIn("limit_req_status 429;", site)
        self.assertIn("limit_conn_status 429;", site)
        self.assertNotIn("unsafe-eval", site)
        websocket = site.split("location = /api/admin/api/v1/sql-console/ws {", 1)[1]
        websocket = websocket.split("location ^~ /api/admin/", 1)[0]
        for directive in (
            "proxy_set_header Upgrade $http_upgrade;",
            'proxy_set_header Connection "upgrade";',
            "limit_req zone=uranus_admin_api burst=20 nodelay;",
            "Content-Security-Policy",
            "connect-src 'self'",
            "if (-f ",
            "return 503;",
            'Cache-Control "private, no-store"',
        ):
            self.assertIn(directive, websocket)
        self.assertEqual(site.count("proxy_set_header Upgrade $http_upgrade;"), 1)
        self.assertEqual(site.count("error_log /var/log/nginx/uranus-admin-error.log warn;"), 2)
        self.assertNotIn("error_log /dev/null", site)
        error_block = site.split("location @rate_limited", 1)[1]
        self.assertIn("Strict-Transport-Security", error_block)
        self.assertIn("Content-Security-Policy", error_block)

    @unittest.skipUnless(shutil.which("systemd-analyze"), "systemd-analyze absent")
    def test_systemd_candidate_syntax_without_starting_units(self):
        env = Environment(loader=FileSystemLoader(ROLE / "templates"), undefined=StrictUndefined)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "frontend").mkdir()
            (root / "runtime.env").write_text("")
            values = {
                "ua_release_dir": directory,
                "ua_config_dir": directory,
                "ua_node": "/usr/bin/true",
                "ua_uv": "/usr/bin/true",
            }
            paths = []
            for name in ("backend", "check-worker", "frontend", "notification-worker"):
                path = root / ("uranus-admin-" + name + ".service")
                path.write_text(env.get_template(name + ".service.j2").render(values))
                paths.append(str(path))
            timer = root / "uranus-admin-notification-worker.timer"
            timer.write_text(env.get_template("notification-worker.timer.j2").render(values))
            paths.append(str(timer))
            result = subprocess.run(
                ["systemd-analyze", "verify", "--man=no", *paths],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("nginx") and shutil.which("openssl"), "nginx/openssl absent")
    def test_nginx_candidate_syntax_with_local_fixture_certificate(self):
        env = Environment(loader=FileSystemLoader(ROLE / "templates"), undefined=StrictUndefined)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "logs").mkdir()
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(root / "key.pem"),
                    "-out",
                    str(root / "cert.pem"),
                    "-subj",
                    "/CN=fixture.invalid",
                    "-days",
                    "1",
                ],
                check=True,
                capture_output=True,
            )
            site = env.get_template("nginx-site.conf.j2").render(nginx_defaults())
            for old, new in {
                "listen 80;": "listen 127.0.0.1:18080;",
                "listen [::]:80;": "",
                "listen 443 ssl http2;": "listen 127.0.0.1:18443 ssl http2;",
                "listen [::]:443 ssl http2;": "",
                "/etc/letsencrypt/live/admin.kulturbytes.de/fullchain.pem": str(root / "cert.pem"),
                "/etc/letsencrypt/live/admin.kulturbytes.de/privkey.pem": str(root / "key.pem"),
                "/var/log/nginx/uranus-admin-access.log": str(root / "access.log"),
                "/var/log/nginx/uranus-admin-error.log": str(root / "error.log"),
            }.items():
                site = site.replace(old, new)
            config = (
                "pid " + str(root / "nginx.pid") + "; error_log stderr; events {} http {\n"
                "limit_req_zone $binary_remote_addr zone=uranus_admin_general:10m rate=10r/s;\n"
                "limit_req_zone $binary_remote_addr zone=uranus_admin_api:10m rate=5r/s;\n"
                "limit_conn_zone $binary_remote_addr zone=uranus_admin_conn:10m;\n"
                + env.get_template("nginx-logging.conf.j2").render()
                + "\n"
                + site
                + "\n}"
            )
            (root / "nginx.conf").write_text(config)
            result = subprocess.run(
                [
                    shutil.which("nginx"),
                    "-t",
                    "-p",
                    directory,
                    "-c",
                    str(root / "nginx.conf"),
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
