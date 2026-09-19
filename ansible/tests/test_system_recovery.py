"""Exercise real Ansible blocks/handlers and real temporary files, with simulated host I/O."""

import copy
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
NOTIFICATION = [
    "uranus-admin-notification-worker.service",
    "uranus-admin-notification-worker.timer",
]


class StaticRecoveryBoundaries(unittest.TestCase):
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

    def test_rescue_closure_is_system_only(self):
        allowed = {
            "ansible.builtin.copy",
            "ansible.builtin.file",
            "ansible.builtin.systemd_service",
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
        }

        def audit(tasks, in_rescue=False):
            for task in tasks:
                if in_rescue:
                    serialized = json.dumps(task)
                    self.assertNotRegex(
                        serialized,
                        r"(?i)\b(psql|alembic|pg_restore|pg_dump|dropdb|createdb|GRANT|REVOKE|TRUNCATE|postgresql)\b",
                    )
                    for key, args in task.items():
                        # Reject aliases/action/local_action as well as unknown FQCNs.
                        self.assertIn(key, allowed | keywords)
                        if key == "ansible.builtin.command":
                            self.assertEqual(args, "/usr/sbin/nginx -t")
                        if key == "ansible.builtin.import_tasks":
                            self.assertEqual(args, "system_recovery.yml")
                            audit(yaml.safe_load((ROLE / "tasks" / args).read_text()), True)
                for block in ("block", "rescue", "always"):
                    if block in task:
                        audit(task[block], in_rescue or block == "rescue")

        for path in (ROLE / "tasks").glob("*.yml"):
            audit(yaml.safe_load(path.read_text()))

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
    def run_activation(
        self,
        fail_task=None,
        manage=False,
        approved=False,
        first_adoption=False,
        notification_active=True,
    ):
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
            }
            for path in role.rglob("*.yml"):
                text = path.read_text()
                for old, new in replacements.items():
                    text = text.replace(old, new)
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
            (release_root / "current").symlink_to(old_release)
            if first_adoption:
                (release_root / "current").unlink()
            files = [
                *(root / "etc/systemd/system" / name for name in APP_SERVICES),
                root / "etc/nginx/sites-available/uranus-admin",
                root / "etc/nginx/conf.d/uranus-admin-logging.conf",
                config / "runtime.env",
                legacy / "backend/.env",
                legacy / "frontend/.env",
            ]
            originals = {}
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("original " + path.name + "\n")
                path.chmod(0o640)
                originals[str(path)] = (path.read_text(), 0o640)
            if first_adoption:
                for path in (
                    config / "runtime.env",
                    root / "etc/nginx/conf.d/uranus-admin-logging.conf",
                ):
                    path.unlink()
                    originals[str(path)] = None

            def stat(path):
                return {
                    "stat": {
                        "exists": path.exists(),
                        "mode": "0640",
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
            if not notification_active:
                for name in NOTIFICATION:
                    services[name]["active"] = False
                services[NOTIFICATION[1]]["unit_file_state"] = "disabled"
            state = {
                "services": services,
                "events": [],
                "fail_tasks": [fail_task] if fail_task else [],
                "config_dir": str(config),
                "current": str(release_root / "current"),
            }
            initial_services = copy.deepcopy(services)
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state))
            variables = {
                "ansible_remote_tmp": str(root / "remote-tmp"),
                "ansible_python_interpreter": sys.executable,
                "fixture_state": str(state_path),
                "ua_config_dir": str(config),
                "ua_root": str(release_root),
                "ua_release_dir": str(release),
                "ua_release_sha": "a" * 40,
                "ua_legacy_root": str(legacy),
                "ua_services": APP_SERVICES,
                "ua_action": "deploy",
                "ua_manage_notification_timer": manage,
                "ua_disable_notification_timer_approved": approved,
                "ua_runtime": {"APP_ENV": "production", "NOTIFICATIONS_DELIVERY_ENABLED": "false"},
                "ua_privileged": {},
                "ua_node": "/usr/bin/true",
                "ansible_facts": {
                    "services": {
                        name: {"state": "running" if s["active"] else "stopped"}
                        for name, s in services.items()
                    }
                },
                "ua_env_stats": {
                    "results": [
                        stat(config / "runtime.env"),
                        {"stat": {"exists": False}},
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
                + "\nnocows=True\n"
            )
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
                    "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                },
                capture_output=True,
                text=True,
                timeout=90,
            )
            observed = json.loads(state_path.read_text())
            output = result.stdout + result.stderr
            if fail_task:
                self.assertNotEqual(result.returncode, 0, output)
                if fail_task != "Validate prepared candidates":
                    self.assertIn("SYSTEM ROLLBACK completed", output)
                self.assertEqual(observed["services"], initial_services, output)
                if first_adoption:
                    self.assertFalse((release_root / "current").exists(), output)
                    self.assertFalse((release_root / "current").is_symlink(), output)
                else:
                    self.assertEqual((release_root / "current").resolve(), old_release, output)
                for name, original in originals.items():
                    path = Path(name)
                    if original is None:
                        self.assertFalse(path.exists(), output)
                    else:
                        self.assertEqual(path.read_text(), original[0], output)
                        self.assertEqual(path.stat().st_mode & 0o777, original[1], output)
            else:
                self.assertEqual(result.returncode, 0, output)
                self.assertEqual((release_root / "current").resolve(), release)
                health_events = [event for event in observed["events"] if event["kind"] == "uri"]
                self.assertEqual(len(health_events), 3)
                self.assertTrue(
                    all(event["pointer"] == str(old_release) for event in health_events)
                )
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
            else:
                self.assertTrue(mutations[0]["backups_match_originals"])
            return observed

    @staticmethod
    def adapt_host_io(tasks):
        for index, task in list(enumerate(tasks)):
            if task.get("name") == "Publish the successfully checked release pointer":
                tasks.insert(
                    index + 1,
                    {"name": "After pointer publication", "fixture_host": {"kind": "command"}},
                )
        for task in tasks:
            for name, kind in (
                ("ansible.builtin.systemd_service", "systemd"),
                ("ansible.builtin.command", "command"),
                ("ansible.builtin.uri", "uri"),
            ):
                if name in task:
                    args = task.pop(name)
                    task["fixture_host"] = {
                        "kind": kind,
                        **(args if isinstance(args, dict) else {"command": args}),
                    }
                    if kind == "uri":
                        task["retries"], task["delay"] = 0, 0
            for name in ("ansible.builtin.copy", "ansible.builtin.file"):
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


if __name__ == "__main__":
    unittest.main()
