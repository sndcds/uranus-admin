"""Exercise real Ansible blocks/handlers and real temporary files, with simulated host I/O."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from ansible.errors import AnsibleFilterError
from test_deployment import ANSIBLE, ROLE, filters

APP_SERVICES = [
    "uranus-admin-backend.service",
    "uranus-admin-check-worker.service",
    "uranus-admin-frontend.service",
]
GEOCODE = [
    "uranus-admin-geocode-worker.service",
    "uranus-admin-geocode-worker.timer",
]
NOTIFICATION = [
    "uranus-admin-notification-worker.service",
    "uranus-admin-notification-worker.timer",
]


class StaticRecoveryBoundaries(unittest.TestCase):
    def test_production_allows_missing_geocode_units_and_running_oneshot(self):
        base = [
            {
                "item": "nginx.service",
                "stdout": "LoadState=loaded\nActiveState=active\nUnitFileState=enabled",
            }
        ]
        for environment in ("production", "staging", "test"):
            missing = [
                {
                    "item": name,
                    "stdout": "LoadState=not-found\nActiveState=inactive\nUnitFileState=",
                }
                for name in GEOCODE
            ]
            snapshot = filters.service_snapshot(base + missing, environment)
            self.assertTrue(all(not snapshot[name]["exists"] for name in GEOCODE))
        running = {
            "item": GEOCODE[0],
            "stdout": "LoadState=loaded\nActiveState=activating\nUnitFileState=static",
        }
        self.assertTrue(filters.service_snapshot(base + [running])[GEOCODE[0]]["active"])

    def test_candidate_and_installed_verification_include_geocode_units(self):
        release = (ROLE / "tasks/release.yml").read_text()
        activation = (ROLE / "tasks/activate.yml").read_text()
        for text in (release, activation):
            verify = next(
                line for line in text.splitlines() if "['systemd-analyze', 'verify']" in line
            )
            self.assertIn("ua_geocode_units", verify)

    def test_notification_management_requires_its_own_apply_approval(self):
        defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
        gates = yaml.safe_load((ROLE / "tasks/inputs.yml").read_text())[:2]
        for manage, approved, allowed in (
            (False, False, True),
            (True, False, False),
            (True, True, True),
        ):
            with (
                self.subTest(manage=manage, approved=approved),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                variables = {
                    **defaults,
                    "ua_action": "deploy",
                    "ua_manage_notification_timer": manage,
                    "ua_disable_notification_timer_approved": approved,
                    "ua_apply_confirmation": "Ja, führe das Deployment jetzt aus.",
                    "ua_reviewed_dry_run": "fixture",
                    "ua_maintenance_window": "fixture",
                    "ua_backup_reference": "fixture",
                    "ua_secret_adoption_approved": True,
                }
                play = [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": variables,
                        "tasks": gates,
                    }
                ]
                (root / "play.yml").write_text(yaml.safe_dump(play))
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "ansible.cli.playbook",
                        "-i",
                        "localhost,",
                        str(root / "play.yml"),
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
                self.assertEqual(result.returncode == 0, allowed, result.stdout + result.stderr)

    def test_rendered_file_lists_never_expose_runtime_contents(self):
        for task in yaml.safe_load((ROLE / "tasks/file_plan.yml").read_text()):
            if "ua_files" in task.get("ansible.builtin.set_fact", {}):
                self.assertTrue(task.get("no_log"), task["name"])

    def test_rescue_closure_is_system_only(self):
        allowed = {
            "ansible.builtin.copy",
            "ansible.builtin.file",
            "ansible.builtin.systemd_service",
            "ansible.builtin.service_facts",
            "ansible.builtin.command",
            "ansible.builtin.fail",
            "ansible.builtin.import_tasks",
        }
        keywords = {
            "name",
            "when",
            "loop",
            "loop_control",
            "no_log",
            "diff",
            "changed_when",
            "block",
            "rescue",
            "always",
            "ignore_errors",
            "register",
            "failed_when",
        }

        def audit(tasks, in_rescue=False, admin_database_mutation=False):
            for task in tasks:
                if in_rescue:
                    serialized = json.dumps(task)
                    self.assertNotRegex(
                        serialized,
                        r"(?i)\b(psql|alembic|pg_restore|pg_dump|dropdb|createdb|GRANT|REVOKE|TRUNCATE|postgresql)\b",
                    )
                    for key, args in task.items():
                        # Reject aliases/action/local_action as well as unknown FQCNs.
                        extra = (
                            {"uranus_admin_database", "ansible.builtin.debug", "become_user"}
                            if admin_database_mutation
                            else set()
                        )
                        self.assertIn(key, allowed | keywords | extra)
                        if key == "uranus_admin_database":
                            self.assertEqual(args["state"], "plan")
                            self.assertNotIn("credentials", args)
                        if key == "ansible.builtin.command":
                            self.assertIn(
                                args,
                                (
                                    "/usr/sbin/nginx -t",
                                    {
                                        "argv": [
                                            "systemctl",
                                            "show",
                                            "{{ item }}",
                                            "--property=LoadState",
                                            "--value",
                                        ]
                                    },
                                ),
                            )
                            if isinstance(args, dict):
                                self.assertIn(
                                    task["loop"],
                                    (
                                        "{{ ua_notification_units | reverse | list }}",
                                        "{{ ua_geocode_units | reverse | list }}",
                                    ),
                                )
                                self.assertFalse(task["changed_when"])
                        if key == "ansible.builtin.import_tasks":
                            self.assertEqual(args, "system_recovery.yml")
                            audit(yaml.safe_load((ROLE / "tasks" / args).read_text()), True)
                for block in ("block", "rescue", "always"):
                    if block in task:
                        audit(
                            task[block],
                            in_rescue or block == "rescue",
                            admin_database_mutation,
                        )

        for path in (ROLE / "tasks").glob("*.yml"):
            audit(
                yaml.safe_load(path.read_text()),
                admin_database_mutation=path.name
                in {"admin_database_bootstrap.yml", "admin_database_upgrade.yml"},
            )

    def test_postgresql_modules_stay_in_read_only_preflight(self):
        def walk(tasks, path):
            for task in tasks:
                for key, value in task.items():
                    if "postgresql" in key:
                        self.assertEqual(path.name, "preflight.yml")
                        self.assertEqual(key, "community.postgresql.postgresql_query")
                        self.assertIn(
                            "default_transaction_read_only=on", value["connect_params"]["options"]
                        )
                    if key in ("block", "rescue", "always"):
                        walk(value, path)

        for path in (ROLE / "tasks").glob("*.yml"):
            walk(yaml.safe_load(path.read_text()), path)

    def test_stable_service_state_validation(self):
        results = [
            {"item": name, "stdout": "LoadState=loaded\nActiveState=active\nUnitFileState=enabled"}
            for name in APP_SERVICES + ["nginx.service"]
        ]
        self.assertTrue(filters.service_snapshot(results)[APP_SERVICES[0]]["active"])
        for unsafe in ("activating", "deactivating", "reloading"):
            bad = copy.deepcopy(results)
            bad[0]["stdout"] = bad[0]["stdout"].replace(
                "ActiveState=active", "ActiveState=" + unsafe
            )
            with self.assertRaises(AnsibleFilterError):
                filters.service_snapshot(bad)


class ActivationIntegrationTests(unittest.TestCase):
    def test_geocode_production_timer_is_enabled_and_idempotent(self):
        self.run_activation(repeat_without_activation=True)

    def test_geocode_unit_change_reloads_without_restarting_other_services(self):
        self.run_activation(geocode_reapply="unit")

    def test_geocode_disabled_timer_is_repaired_without_other_restarts(self):
        self.run_activation(geocode_reapply="disabled")

    def test_geocode_production_check_mode_creates_nothing(self):
        self.run_activation(check=True)

    def test_geocode_first_install_recovers_after_timer_activation(self):
        self.run_activation("After geocode timer activation")

    def test_geocode_existing_active_states_and_files_recover(self):
        self.run_activation("After geocode timer activation", geocode_existing=True)

    def test_geocode_existing_inactive_states_and_files_recover(self):
        self.run_activation(
            "After geocode timer activation", geocode_existing=True, geocode_active=False
        )

    def test_geocode_timer_health_failure_recovers(self):
        self.run_activation("Check geocode timer enablement and activity")

    def run_activation(
        self,
        fail_task=None,
        manage=False,
        approved=False,
        first_adoption=False,
        notification_active=True,
        geocode_existing=False,
        geocode_active=True,
        geocode_reapply=None,
        originally_on=False,
        recovery_fail_task=None,
        check=False,
        repeat_without_activation=False,
        maintenance_responses=None,
        console_archive=False,
        operator_changed=False,
        bootstrap=False,
        bootstrap_environment="test",
        missing_legacy=False,
    ):
        first_adoption = first_adoption or bootstrap
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            role = root / "roles/uranus_admin"
            shutil.copytree(ROLE, role)
            plugin_dir = root / "filter_plugins"
            plugin_dir.mkdir()
            # Relocate only filesystem paths; all conditions, blocks, handlers and filters are real.
            replacements = {
                "/etc/systemd": str(root / "etc/systemd"),
                "/etc/nginx": str(root / "etc/nginx"),
                "/etc/uranus-admin": str(root / "config"),
                "/var/log/nginx": str(root / "var/log/nginx"),
                "/run/systemd": str(root / "run/systemd"),
                "/usr/lib/systemd": str(root / "usr/lib/systemd"),
            }
            infrastructure_module = role / "library/uranus_infrastructure.py"
            module_text = infrastructure_module.read_text().replace(
                "OWNER = 0", f"OWNER = {os.getuid()}"
            )
            for old, new in replacements.items():
                module_text = module_text.replace(old, new)
            infrastructure_module.write_text(module_text)
            for path in role.rglob("*.yml"):
                text = path.read_text()
                for old, new in replacements.items():
                    text = text.replace(old, new)
                # Match root ownership checks to the unprivileged fixture owner.
                if path.name in ("deploy.yml", "file_plan.yml", "prepare_activation.yml"):
                    text = text.replace(".stat.uid != 0", f".stat.uid != {os.getuid()}")
                    text = text.replace(".stat.gid != 0", f".stat.gid != {os.getgid()}")
                if path.name == "maintenance_inspect.yml":
                    text = text.replace(".uid == 0", f".uid == {os.getuid()}")
                tasks = yaml.safe_load(text)
                if isinstance(tasks, list):
                    self.adapt_host_io(tasks)
                    path.write_text(yaml.safe_dump(tasks, sort_keys=False))
            plugin = (ANSIBLE / "filter_plugins/uranus_admin.py").read_text()
            for old, new in replacements.items():
                plugin = plugin.replace(old, new)
            (plugin_dir / "uranus_admin.py").write_text(plugin)
            actions = root / "action_plugins"
            actions.mkdir()
            shutil.copy(ANSIBLE / "tests/fixtures/fixture_host.py", actions / "fixture_host.py")
            # Isolate activation from production preflight/build. Neither is bypassable in the role.
            (role / "tasks/main.yml").write_text("- ansible.builtin.import_tasks: deploy.yml\n")
            (role / "tasks/release.yml").write_text(
                yaml.safe_dump(
                    [{"name": "Validate prepared candidates", "fixture_host": {"kind": "command"}}]
                )
            )
            config = root / "config"
            legacy = root / "legacy"
            release_root = root / "releases-root"
            release = release_root / "releases/new"
            old_release = release_root / "releases/old"
            for path in (config, legacy / "backend", legacy / "frontend", release, old_release):
                path.mkdir(parents=True)
            # The previous deployment may predate release format 2. Its already
            # built output and exact old unit must survive every recovery path.
            old_output = old_release / "frontend/.output/server/index.mjs"
            old_output.parent.mkdir(parents=True)
            old_output.write_text("// previous complete Nitro runtime")
            (release_root / "current").symlink_to(old_release)
            if first_adoption:
                (release_root / "current").unlink()
            maintenance = release_root / "maintenance"
            marker = maintenance / "enabled"
            if originally_on:
                (maintenance / "assets").mkdir(parents=True)
                maintenance.chmod(0o755)
                (maintenance / "assets").chmod(0o755)
                marker.write_text("original maintenance marker\n")
                marker.chmod(0o644)
            files = [
                *(root / "etc/systemd/system" / name for name in APP_SERVICES),
                root / "etc/nginx/sites-available/uranus-admin",
                root / "etc/nginx/conf.d/uranus-admin-logging.conf",
                config / "runtime.env",
                legacy / "backend/.env",
                legacy / "frontend/.env",
            ]
            geocode_files = [root / "etc/systemd/system" / name for name in GEOCODE]
            files.extend(geocode_files if geocode_existing else [])
            originals = {str(path): None for path in geocode_files} if not geocode_existing else {}
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                original = "original " + path.name + "\n"
                if path.name == "uranus-admin-frontend.service":
                    original += f"ExecStart=/retained/node {old_output}\n"
                if originally_on and path == root / "etc/nginx/sites-available/uranus-admin":
                    original += "error_page 503 =503 /__maintenance.html;\n"
                path.write_text(original)
                path.chmod(0o640)
                originals[str(path)] = (path.read_text(), 0o640)
            if first_adoption:
                for path in (
                    config / "runtime.env",
                    root / "etc/nginx/conf.d/uranus-admin-logging.conf",
                ):
                    path.unlink()
                    originals[str(path)] = None
            if bootstrap:
                for path in files[:5]:
                    path.unlink(missing_ok=True)
                    originals[str(path)] = None
                default_site = root / "etc/nginx/sites-enabled/default"
                default_site.parent.mkdir(parents=True, exist_ok=True)
                default_site.write_text("unrelated default site\n")

            if missing_legacy:
                (legacy / "backend/.env").unlink()
                (legacy / "backend").rmdir()
                originals[str(legacy / "backend/.env")] = None

            operator_values = {"ADMIN_MIGRATION_DATABASE_URL": "existing-operator-fixture"}
            console_values = {**operator_values, "SQL_CONSOLE_DATABASE_URL": "console-fixture"}
            operator_path = config / "operator.env"
            if console_archive:
                operator_path.write_text(filters.render_environment(operator_values))
                operator_path.chmod(0o600)

            def stat(path):
                if not path.exists():
                    return {"stat": {"exists": False}}
                return {
                    "stat": {
                        "exists": path.exists(),
                        "mode": f"{path.stat().st_mode & 0o777:04o}",
                        "checksum": hashlib.sha1(path.read_bytes()).hexdigest(),
                        "uid": os.getuid(),
                        "gid": os.getgid(),
                    }
                }

            services = {
                name: {"active": True, "unit_file_state": "enabled"}
                for name in APP_SERVICES + ["nginx.service"] + NOTIFICATION
            }
            services[APP_SERVICES[1]] = {"active": False, "unit_file_state": "disabled"}
            services[NOTIFICATION[0]]["unit_file_state"] = "static"
            if geocode_existing:
                services[GEOCODE[0]] = {"active": geocode_active, "unit_file_state": "static"}
                services[GEOCODE[1]] = {
                    "active": geocode_active,
                    "unit_file_state": "enabled" if geocode_active else "disabled",
                }
            if not notification_active:
                for name in NOTIFICATION:
                    services[name]["active"] = False
                services[NOTIFICATION[1]]["unit_file_state"] = "disabled"
            if bootstrap:
                for name in APP_SERVICES + (NOTIFICATION if manage else []):
                    services.pop(name)
            state = {
                "services": services,
                "events": [],
                "fail_tasks": [t for t in (fail_task, recovery_fail_task) if t],
                "originals": {k: v[0] for k, v in originals.items() if v},
                "marker": str(marker),
                "maintenance": str(maintenance),
                "nginx_site": str(root / "etc/nginx/sites-available/uranus-admin"),
                "loaded_maintenance_capable": originally_on,
                "maintenance_responses": maintenance_responses or [],
                "config_dir": str(config),
                "current": str(release_root / "current"),
                "unit_dir": str(root / "etc/systemd/system"),
                "app_units": APP_SERVICES
                + GEOCODE
                + (NOTIFICATION if bootstrap and manage else []),
            }
            initial_services = copy.deepcopy(services)
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state))
            if bootstrap:
                # Exercise first creation of the private config/recovery directory too.
                config.rmdir()
            variables = {
                "ansible_remote_tmp": str(root / "remote-tmp"),
                "ansible_python_interpreter": sys.executable,
                "fixture_state": str(state_path),
                "ua_config_dir": str(config),
                "ua_root": str(release_root),
                "ua_maintenance_root": str(maintenance),
                "ua_maintenance_marker": str(marker),
                "ua_release_dir": str(release),
                "ua_release_sha": "a" * 40,
                "ua_legacy_root": str(legacy),
                "ua_services": APP_SERVICES,
                "ua_action": "deploy",
                "ua_target_environment": bootstrap_environment if bootstrap else "production",
                "ua_public_origin": "https://fixture.example.invalid"
                if bootstrap
                else "https://admin.kulturbytes.de",
                "ua_manage_notification_timer": manage,
                "ua_disable_notification_timer_approved": approved,
                "ua_runtime": {"APP_ENV": "production", "NOTIFICATIONS_DELIVERY_ENABLED": "false"},
                "ua_privileged": console_values if console_archive else {},
                "ua_node": "/usr/bin/true",
                "ua_uv": "/usr/bin/true",
                "ansible_facts": {
                    "services": {
                        name: {"state": "running" if s["active"] else "stopped"}
                        for name, s in services.items()
                    }
                },
                "ua_env_stats": {
                    "results": [
                        stat(config / "runtime.env"),
                        stat(operator_path) if console_archive else {"stat": {"exists": False}},
                        stat(legacy / "backend/.env"),
                        stat(legacy / "frontend/.env"),
                    ]
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
            (root / "play.yml").write_text(yaml.safe_dump(play))
            (root / "ansible.cfg").write_text(
                "[defaults]\nroles_path="
                + str(root / "roles")
                + "\nfilter_plugins="
                + str(plugin_dir)
                + "\naction_plugins="
                + str(actions)
                + "\nnocows=True\n[connection]\npipelining=True\n"
            )
            if operator_changed:
                operator_path.write_text("NEW_OPERATOR_ENTRY=concurrent-fixture\n")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ansible.cli.playbook",
                    "-i",
                    "localhost,",
                    str(root / "play.yml"),
                    *(["--check", "--diff"] if check else []),
                ],
                env={
                    **os.environ,
                    "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                },
                capture_output=True,
                text=True,
                # Real file/module work grows with maintenance and recovery coverage.
                timeout=240,
            )
            observed = json.loads(state_path.read_text())
            output = result.stdout + result.stderr
            if bootstrap:
                if missing_legacy:
                    self.assertFalse((legacy / "backend/.env").exists(), output)
                self.assertEqual(default_site.read_text(), "unrelated default site\n")
                if check:
                    self.assertFalse(config.exists(), output)
                else:
                    self.assertEqual(config.stat().st_mode & 0o777, 0o700, output)
                managed = [
                    *files[:5],
                    *geocode_files,
                    *(
                        root / "etc/systemd/system" / unit
                        for unit in (NOTIFICATION if manage else [])
                    ),
                    root / "etc/nginx/conf.d/uranus-admin-ratelimit.conf",
                    config / "managed-infrastructure.json",
                ]
                link = root / "etc/nginx/sites-enabled/uranus-admin"
                if check or fail_task:
                    self.assertEqual(result.returncode == 0, check, output)
                    if check:
                        self.assertIn("would_create_nginx_site_symlink", output)
                        self.assertIn("would_install_units", output)
                    else:
                        self.assertIn("SYSTEM ROLLBACK completed", output)
                    self.assertTrue(all(not p.exists() for p in managed), output)
                    self.assertFalse(link.is_symlink(), output)
                    self.assertEqual(observed["services"], initial_services, output)
                    self.assertFalse((release_root / "current").is_symlink(), output)
                else:
                    self.assertEqual(result.returncode, 0, output)
                    self.assertTrue(all(p.is_file() for p in managed), output)
                    self.assertEqual(link.resolve(), files[3])
                    self.assertTrue(
                        all(observed["services"][name]["active"] for name in APP_SERVICES)
                    )
                    self.assertEqual((release_root / "current").resolve(), release)
                    if manage:
                        self.assertTrue(observed["services"][NOTIFICATION[1]]["active"])
                        self.assertEqual(
                            observed["services"][NOTIFICATION[1]]["unit_file_state"], "enabled"
                        )
                        self.assertEqual(
                            observed["services"][NOTIFICATION[0]],
                            {"active": False, "unit_file_state": "static"},
                        )
                        start = next(
                            i
                            for i, e in enumerate(observed["events"])
                            if e["task"]
                            == (
                                "Enable managed test and staging notifications "
                                "after successful healthchecks"
                            )
                        )
                        self.assertTrue(
                            all(
                                i < start
                                for i, e in enumerate(observed["events"])
                                if e["kind"] == "uri"
                            )
                        )
                    repeated = subprocess.run(
                        result.args,
                        env={
                            **os.environ,
                            "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
                            "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                        },
                        capture_output=True,
                        text=True,
                        timeout=240,
                    )
                    self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
                    self.assertRegex(repeated.stdout, r"changed=0\s")
                return observed
            if operator_changed:
                self.assertNotEqual(result.returncode, 0, output)
                self.assertEqual(
                    operator_path.read_text(), "NEW_OPERATOR_ENTRY=concurrent-fixture\n"
                )
                self.assertFalse(any(e["kind"] == "systemd" for e in observed["events"]))
                return observed
            if console_archive:
                self.assertEqual(
                    filters.parse_environment(operator_path.read_text()), console_values
                )
            if check:
                self.assertEqual(result.returncode, 0, output)
                self.assertEqual(old_output.read_text(), "// previous complete Nitro runtime")
                for name, original in originals.items():
                    path = Path(name)
                    if original is None:
                        self.assertFalse(path.exists(), output)
                    else:
                        self.assertEqual(path.read_text(), original[0], output)
                        self.assertEqual(path.stat().st_mode & 0o777, original[1], output)
                self.assertFalse(marker.exists())
                self.assertFalse(maintenance.exists())
                self.assertFalse(any(e["kind"] == "systemd" for e in observed["events"]))
                self.assertIn("would_verify_http_503", output)
                self.assertIn("would_enable_before_service_stop", output)
                return observed
            if fail_task:
                self.assertTrue(any(e["task"] == fail_task for e in observed["events"]), output)
                if recovery_fail_task:
                    self.assertTrue(
                        any(e["task"] == recovery_fail_task for e in observed["events"]), output
                    )
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertIn("SYSTEM RECOVERY FAILED", output)
                    self.assertIn("Maintenance mode remains active", output)
                    self.assertTrue(marker.is_file(), output)
                    return observed
                self.assertNotEqual(result.returncode, 0, output)
                if fail_task != "Validate prepared candidates":
                    self.assertIn("SYSTEM ROLLBACK completed", output)
                self.assertEqual(observed["services"], initial_services, output)
                if first_adoption:
                    self.assertFalse((release_root / "current").exists(), output)
                    self.assertFalse((release_root / "current").is_symlink(), output)
                else:
                    self.assertEqual((release_root / "current").resolve(), old_release, output)
                self.assertEqual(old_output.read_text(), "// previous complete Nitro runtime")
                for name, original in originals.items():
                    path = Path(name)
                    if original is None:
                        self.assertFalse(path.exists(), output)
                    else:
                        self.assertEqual(path.read_text(), original[0], output)
                        self.assertEqual(path.stat().st_mode & 0o777, original[1], output)
            else:
                self.assertEqual(result.returncode, 0, output)
                self.assertTrue(observed["services"][GEOCODE[1]]["active"])
                self.assertEqual(observed["services"][GEOCODE[1]]["unit_file_state"], "enabled")
                self.assertEqual((release_root / "current").resolve(), release)
                health_events = [event for event in observed["events"] if event["kind"] == "uri"]
                self.assertEqual(
                    len(health_events), 5 + max(0, len(maintenance_responses or []) - 1)
                )
                self.assertTrue(
                    all(event["pointer"] == str(old_release) for event in health_events)
                )
            self.assertEqual(marker.exists(), originally_on, output)
            if originally_on:
                self.assertTrue(observed["loaded_maintenance_capable"], output)
                self.assertEqual(marker.read_text(), "original maintenance marker\n", output)
            if fail_task != "Validate prepared candidates":
                metadata = json.loads(
                    next(config.glob("recovery/*/attempt-*/manifest.json")).read_text()
                )
                self.assertEqual(metadata["maintenance"]["enabled"], originally_on)
            if not manage:
                self.assertEqual(
                    {k: observed["services"][k] for k in NOTIFICATION},
                    {k: initial_services[k] for k in NOTIFICATION},
                )
                self.assertFalse(any(e.get("unit") in NOTIFICATION for e in observed["events"]))
                self.assertEqual(
                    (legacy / "backend/.env").read_text(),
                    originals[str(legacy / "backend/.env")][0],
                )
            mutations = [e for e in observed["events"] if e["kind"] == "systemd"]
            if fail_task == "Validate prepared candidates":
                self.assertFalse(mutations)
            elif mutations:
                self.assertTrue(mutations[0]["backups_match_originals"])
            stops = [
                e
                for e in observed["events"]
                if e.get("unit") in APP_SERVICES and e.get("state") == "stopped"
            ]
            if fail_task == "Check public HTTP 503 maintenance content and headers":
                self.assertFalse(stops, output)
            elif stops:
                drain = next(
                    e
                    for e in observed["events"]
                    if e["task"] == "Drain previous nginx workers before stopping applications"
                )
                self.assertLess(observed["events"].index(drain), observed["events"].index(stops[0]))
                verifications = [
                    e
                    for e in observed["events"]
                    if e["task"] == "Check public HTTP 503 maintenance content and headers"
                ]
                self.assertLess(
                    observed["events"].index(drain),
                    observed["events"].index(verifications[0]),
                )
                verify = verifications[-1]
                self.assertTrue(verify["maintenance_files_ready"], output)
                self.assertTrue(verify["maintenance_active"], output)
                self.assertLess(
                    observed["events"].index(verify), observed["events"].index(stops[0])
                )
                self.assertTrue(
                    all(e["maintenance_active"] and e["public_maintenance"] for e in stops), output
                )
                recovery_starts = [
                    e
                    for e in observed["events"]
                    if e["task"]
                    == "Restore affected application services to their actual previous states"
                ]
                self.assertTrue(
                    all(
                        e["maintenance_active"] and e["public_maintenance"] for e in recovery_starts
                    ),
                    output,
                )
                if recovery_starts:
                    reload = next(
                        e
                        for e in observed["events"]
                        if e["task"] == "Reload the valid previous nginx configuration"
                    )
                    self.assertGreater(
                        observed["events"].index(reload),
                        observed["events"].index(recovery_starts[-1]),
                    )
            if repeat_without_activation or geocode_reapply:
                count = len(observed["events"])
                if geocode_reapply == "unit":
                    with geocode_files[0].open("a") as stream:
                        stream.write("\n# Synthetic previous unit version\n")
                elif geocode_reapply == "disabled":
                    observed["services"][GEOCODE[1]] = {
                        "active": False,
                        "unit_file_state": "disabled",
                    }
                if geocode_reapply:
                    observed["originals"] = {
                        str(p): p.read_text() for p in files + geocode_files if p.is_file()
                    }
                    state_path.write_text(json.dumps(observed))
                variables["ua_maintenance_public_title"] = "Aktualisiertes öffentliches Zeitfenster"
                (root / "play.yml").write_text(yaml.safe_dump(play))
                repeated = subprocess.run(
                    result.args,
                    env={
                        **os.environ,
                        "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
                        "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                    },
                    capture_output=True,
                    text=True,
                    timeout=240,
                )
                self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
                after = json.loads(state_path.read_text())
                mutations = [e for e in after["events"][count:] if e["kind"] == "systemd"]
                if geocode_reapply:
                    self.assertFalse(any(e.get("unit") in APP_SERVICES for e in mutations))
                    self.assertEqual(
                        any(e["task"] == "Reload changed systemd units" for e in mutations),
                        geocode_reapply == "unit",
                    )
                    self.assertTrue(after["services"][GEOCODE[1]]["active"])
                    self.assertEqual(after["services"][GEOCODE[1]]["unit_file_state"], "enabled")
                else:
                    self.assertFalse(mutations)
                self.assertEqual(marker.exists(), originally_on)
                self.assertIn(
                    variables["ua_maintenance_public_title"],
                    (maintenance / "maintenance.html").read_text(),
                )
            return observed

    @staticmethod
    def adapt_host_io(tasks):
        for index, task in reversed(list(enumerate(tasks))):
            if task.get("name") in (
                "Publish the successfully checked release pointer",
                "Install reviewed configuration",
                "Stop only affected application services",
                "Enable managed test and staging notifications after successful healthchecks",
                "Enable geocoding in every environment after successful healthchecks",
            ):
                tasks.insert(
                    index + 1,
                    {
                        "name": (
                            "After geocode timer activation"
                            if task["name"].startswith("Enable geocoding")
                            else "After notification timer activation"
                            if task["name"].startswith("Enable managed test")
                            else "After pointer publication"
                            if task["name"].startswith("Publish")
                            else (
                                "After service stop"
                                if task["name"].startswith("Stop")
                                else "After configuration installation"
                            )
                        ),
                        "fixture_host": {"kind": "command"},
                    },
                )
        for task in tasks:
            for name, kind in (
                ("ansible.builtin.systemd_service", "systemd"),
                ("ansible.builtin.service_facts", "service_facts"),
                ("ansible.builtin.command", "command"),
                ("ansible.builtin.uri", "uri"),
                ("ansible.builtin.wait_for", "wait_for"),
            ):
                if name in task:
                    args = task.pop(name)
                    task["fixture_host"] = {
                        "kind": kind,
                        **(args if isinstance(args, dict) else {"command": args}),
                    }
                    if kind == "uri":
                        # Exercise real until/failed_when retries for maintenance.
                        if task["name"] != "Check public HTTP 503 maintenance content and headers":
                            task["retries"] = 0
                        task["delay"] = 0
            for name in (
                "ansible.builtin.copy",
                "ansible.builtin.file",
                "ansible.builtin.template",
            ):
                if name in task:
                    for key, value in (("owner", str(os.getuid())), ("group", str(os.getgid()))):
                        if task[name].get(key) == "root":
                            task[name][key] = value
            for block in ("block", "rescue", "always"):
                if block in task:
                    ActivationIntegrationTests.adapt_host_io(task[block])

    def test_default_leaves_notifications_and_shared_environment_unchanged(self):
        self.assertIs(
            yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
                "ua_manage_notification_timer"
            ],
            False,
        )
        self.run_activation()

    def test_explicit_management_disables_notifications(self):
        observed = self.run_activation(manage=True, approved=True)
        self.assertFalse(observed["services"][NOTIFICATION[1]]["active"])
        self.assertEqual(observed["services"][NOTIFICATION[1]]["unit_file_state"], "disabled")
        self.assertFalse(observed["services"][NOTIFICATION[0]]["active"])

    def test_bad_candidates_never_interrupt_services(self):
        self.run_activation("Validate prepared candidates")

    def test_health_failure_restores_running_and_stopped_services(self):
        self.run_activation("Check backend liveness and database readiness")

    def test_public_login_failure_restores_first_adoption(self):
        self.run_activation("Check the public HTTPS login route", first_adoption=True)

    def test_nginx_verify_failure_recovers_system_only(self):
        self.run_activation("Verify the complete installed nginx configuration")

    def test_nginx_reload_failure_recovers_system_only(self):
        self.run_activation("Reload changed nginx configuration")

    def test_optional_notification_states_are_restored_on_failure(self):
        self.run_activation("Check the public HTTPS login route", manage=True, approved=True)

    def test_previously_inactive_notifications_stay_inactive_on_recovery(self):
        self.run_activation(
            "Check the public HTTPS login route",
            manage=True,
            approved=True,
            notification_active=False,
        )

    def test_failure_after_pointer_change_restores_previous_link(self):
        self.run_activation("After pointer publication")

    def test_failure_after_first_pointer_change_restores_absence(self):
        self.run_activation("After pointer publication", first_adoption=True)

    def test_maintenance_verification_failure_never_stops_apps(self):
        self.run_activation("Check public HTTP 503 maintenance content and headers")

    def test_transient_redirect_and_invalid_503_require_complete_contract(self):
        observed = self.run_activation(
            maintenance_responses=[
                {
                    "status": 302,
                    "content": '<meta http-equiv="refresh" content="0; url=/login?redirect=/">',
                },
                {"status": 503, "content": "Unrelated unavailable page"},
                {"status": 503, "retry_after": "1"},
                {"status": 503},
            ]
        )
        checks = [e for e in observed["events"] if "response_status" in e]
        self.assertEqual([e["response_status"] for e in checks], [302, 503, 503, 503])

    def test_persistent_redirect_recovers_without_stopping_apps(self):
        observed = self.run_activation(
            "Check public HTTP 503 maintenance content and headers",
            maintenance_responses=[{"status": 302, "content": "Redirect to login"}],
        )
        checks = [e for e in observed["events"] if "response_status" in e]
        self.assertEqual(len(checks), 11)
        self.assertTrue(all(e["response_status"] == 302 for e in checks))

    def test_unchanged_release_refreshes_public_copy_without_switching(self):
        self.run_activation(originally_on=True, repeat_without_activation=True)

    def test_original_maintenance_on_is_preserved_on_success(self):
        self.run_activation(originally_on=True)

    def test_original_maintenance_on_is_preserved_on_recovery(self):
        self.run_activation("Check backend liveness and database readiness", originally_on=True)

    def test_failure_immediately_after_service_stop(self):
        self.run_activation("After service stop")

    def test_local_frontend_failure_recovers(self):
        self.run_activation("Check local frontend login while public maintenance is active")

    def test_drain_failure_never_interrupts_apps(self):
        observed = self.run_activation("Drain previous nginx workers before stopping applications")
        self.assertFalse(
            any(e.get("unit") in APP_SERVICES for e in observed["events"] if e["kind"] == "systemd")
        )

    def test_service_start_failure_keeps_maintenance_through_recovery(self):
        self.run_activation("Start affected application services")

    def test_failure_immediately_after_file_installation(self):
        self.run_activation("After configuration installation")

    def test_failed_disable_rearms_maintenance_before_recovery_stops(self):
        self.run_activation("Reload nginx after maintenance removal")

    def test_failed_recovery_keeps_marker_and_reports_operator_action(self):
        self.run_activation(
            "Check backend liveness and database readiness",
            recovery_fail_task="Verify restored nginx configuration before any reload",
        )

    def test_failed_service_recovery_keeps_marker(self):
        self.run_activation(
            "Reload nginx after maintenance removal",
            recovery_fail_task=(
                "Restore affected application services to their actual previous states"
            ),
        )

    def test_console_secret_archive_survives_system_recovery(self):
        self.run_activation("Check backend liveness and database readiness", console_archive=True)

    def test_concurrent_operator_archive_change_aborts_before_service_mutation(self):
        self.run_activation(console_archive=True, operator_changed=True)

    def test_check_mode_does_not_activate_maintenance(self):
        self.run_activation(check=True)

    def test_bootstrap_check_mode_creates_nothing(self):
        self.run_activation(bootstrap=True, check=True)

    def test_bootstrap_apply_and_second_apply_changed_zero(self):
        self.run_activation(bootstrap=True)

    def test_staging_bootstrap_apply_and_second_apply_changed_zero(self):
        self.run_activation(bootstrap=True, bootstrap_environment="staging")

    def test_bootstrap_failure_removes_new_files_link_and_services(self):
        self.run_activation("Check backend liveness and database readiness", bootstrap=True)

    def test_bootstrap_failure_before_daemon_reload_removes_new_units(self):
        self.run_activation("After configuration installation", bootstrap=True)

    def test_notification_bootstrap_needs_no_legacy_environment(self):
        self.run_activation(bootstrap=True, manage=True, approved=True, missing_legacy=True)

    def test_notification_bootstrap_dry_run_creates_nothing(self):
        self.run_activation(bootstrap=True, manage=True, approved=True, check=True)

    def test_notification_bootstrap_starts_timer_and_repeats_without_changes(self):
        self.run_activation(bootstrap=True, manage=True, approved=True)

    def test_notification_staging_bootstrap_starts_timer_and_repeats_without_changes(self):
        self.run_activation(
            bootstrap=True, bootstrap_environment="staging", manage=True, approved=True
        )

    def test_notification_bootstrap_recovers_after_health_failure(self):
        self.run_activation(
            "Check backend liveness and database readiness",
            bootstrap=True,
            manage=True,
            approved=True,
        )

    def test_notification_bootstrap_recovers_after_timer_enable_failure(self):
        self.run_activation(
            "Enable managed test and staging notifications after successful healthchecks",
            bootstrap=True,
            manage=True,
            approved=True,
        )

    def test_notification_bootstrap_removes_enabled_timer_on_failure(self):
        self.run_activation(
            "After notification timer activation", bootstrap=True, manage=True, approved=True
        )

    def test_notification_bootstrap_recovers_before_daemon_reload(self):
        self.run_activation(
            "After configuration installation", bootstrap=True, manage=True, approved=True
        )


if __name__ == "__main__":
    unittest.main()
