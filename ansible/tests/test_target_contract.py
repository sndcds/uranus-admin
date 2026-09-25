"""Execute target/input guards locally; never contact or mutate a deployment target."""

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import yaml

ANSIBLE = Path(__file__).resolve().parents[1]
ROLE = ANSIBLE / "roles/uranus_admin"
ENVIRONMENTS = ("production", "staging", "test")
HOSTS = ("uranus-admin-test", "staging-admin", "host123")
CONTRACT_ERROR = (
    "Target does not satisfy the Uranus Admin deployment contract. "
    "Do not bypass preflight or safety gates."
)
APPLY_ERROR = (
    "Apply requires reviewed dry run, backup reference, maintenance window, "
    "secret approval and separate approval when managing notifications."
)
APPROVALS = {
    "ua_action": "deploy",
    "ua_apply_confirmation": "Ja, führe das Deployment jetzt aus.",
    "ua_reviewed_dry_run": "synthetic reviewed dry run",
    "ua_maintenance_window": "synthetic maintenance window",
    "ua_backup_reference": "synthetic backup reference",
    "ua_secret_adoption_approved": True,
}


class TargetContractTests(unittest.TestCase):
    def run_cases(self, cases, *, extra_tasks=(), options=(), check=False):
        """Each case runs the real input tasks with an authenticated synthetic artifact."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "release.tar.gz"
            manifest = json.dumps(
                {
                    "commit": "a" * 40,
                    "head": "0012",
                    "runtime_grants": {
                        "finding": ["SELECT"],
                        "finding_event": ["SELECT", "INSERT"],
                    },
                    "environment_keys": [],
                    "operator_grants": {"alembic_version": ["SELECT"]},
                    "admin_indexes": ["finding_pkey"],
                    "admin_columns": {"finding": ["uuid"]},
                    "admin_upgrade_contracts": {
                        "0011": {
                            "schema_fingerprint": "b" * 64,
                            "runtime_grants": {"finding": ["SELECT"]},
                        }
                    },
                }
            ).encode()
            with tarfile.open(artifact, "w:gz") as archive:
                member = tarfile.TarInfo("release.json")
                member.mode, member.size = 0o644, len(manifest)
                archive.addfile(member, io.BytesIO(manifest))
            variables = {
                **yaml.safe_load((ROLE / "defaults/main.yml").read_text()),
                "ua_artifact": str(artifact),
                "ua_artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "ua_release_sha": "a" * 40,
            }
            plays = []
            for label, host, overrides, error in cases:
                tasks = [
                    {"ansible.builtin.set_fact": {"guard_rejected": False}},
                    {
                        "block": [
                            {"ansible.builtin.include_tasks": str(ROLE / "tasks/inputs.yml")},
                            *extra_tasks,
                        ],
                        "rescue": [
                            {
                                "ansible.builtin.assert": {
                                    "that": "ansible_failed_result.msg == expected_error"
                                }
                            },
                            {"ansible.builtin.set_fact": {"guard_rejected": True}},
                        ],
                    },
                    {
                        "ansible.builtin.assert": {
                            "that": "guard_rejected == (expected_error is not none)"
                        }
                    },
                ]
                plays.append(
                    {
                        "name": label,
                        "hosts": host,
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            **variables,
                            "ua_public_origin": (
                                "https://fixture.example.invalid"
                                if overrides.get("ua_target_environment") in ("test", "staging")
                                else "https://admin.kulturbytes.de"
                            ),
                            **overrides,
                            "expected_error": error,
                        },
                        # Exercise the input guard under real Ansible CLI tag values.
                        "tags": ["always"],
                        "tasks": tasks,
                    }
                )
            playbook = root / "play.yml"
            playbook.write_text(yaml.safe_dump(plays))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ansible.cli.playbook",
                    "-i",
                    ",".join(HOSTS) + ",",
                    str(playbook),
                    *(["--check"] if check else []),
                    *options,
                ],
                env={
                    **os.environ,
                    "ANSIBLE_CONFIG": str(ANSIBLE / "ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                    "ANSIBLE_NOCOLOR": "1",
                },
                capture_output=True,
                text=True,
                timeout=180,
            )
            if options:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(
                    "Do not bypass preflight or safety gates", result.stdout + result.stderr
                )
                self.assertNotIn("TASK [", result.stdout)
                return result.stdout
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for label, *_ in cases:
                self.assertIn(label, result.stdout)
            return result.stdout

    def test_arbitrary_hostnames_and_all_environments_accept_same_contract(self):
        preflight = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
        # Execute the complete hostname phase, stopping before OS/service inspection.
        os_index = next(
            i
            for i, task in enumerate(preflight)
            if task["name"] == "Read the operating system release"
        )
        cases = [
            (f"accept {host} {environment}", host, {"ua_target_environment": environment}, None)
            for host in HOSTS
            for environment in ENVIRONMENTS
        ]
        output = self.run_cases(cases, extra_tasks=preflight[:os_index], check=True)
        self.assertIn("system_hostname", output)
        self.assertIn("inventory_hostname", output)
        self.assertNotIn('"system_hostname": "unavailable"', output)

    def test_production_is_default(self):
        self.assertEqual(
            yaml.safe_load((ROLE / "defaults/main.yml").read_text())["ua_target_environment"],
            "production",
        )
        self.run_cases([("default production", HOSTS[0], {}, None)])

    def test_real_preflight_link_contract_in_all_environments(self):
        tasks = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
        guard = next(
            t for t in tasks if t["name"] == "Reject a different reverse proxy routing arrangement"
        )
        cases = []
        for environment in ENVIRONMENTS:
            for kind, stat in {
                "missing": {"exists": False},
                "correct": {
                    "exists": True,
                    "islnk": True,
                    "lnk_source": "/etc/nginx/sites-available/uranus-admin",
                },
                "wrong": {
                    "exists": True,
                    "islnk": True,
                    "lnk_source": "/etc/nginx/sites-available/foreign",
                },
                "file": {"exists": True, "islnk": False},
                "directory": {"exists": True, "islnk": False},
            }.items():
                allowed = kind == "correct" or (kind == "missing" and environment != "production")
                cases.append(
                    (
                        f"link {environment} {kind}",
                        HOSTS[0],
                        {
                            "ua_target_environment": environment,
                            "ua_nginx_site_link": {"stat": stat},
                        },
                        None if allowed else guard["ansible.builtin.assert"]["fail_msg"],
                    )
                )
        self.run_cases(cases, extra_tasks=[guard])

    def test_real_preflight_requires_nginx_and_production_app_services(self):
        tasks = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
        guard = next(t for t in tasks if t["name"] == "Require the audited existing installation")
        cases = []
        for environment in ENVIRONMENTS:
            for services in (
                {},
                {"nginx.service": {}},
                {
                    "nginx.service": {},
                    "uranus-admin-backend.service": {},
                    "uranus-admin-check-worker.service": {},
                    "uranus-admin-frontend.service": {},
                },
            ):
                allowed = "nginx.service" in services and (
                    environment != "production" or len(services) == 4
                )
                # A loop failure has an aggregate message rather than the individual assertion msg.
                cases.append(
                    (
                        f"services {environment} {len(services)}",
                        HOSTS[0],
                        {
                            "ua_target_environment": environment,
                            "ansible_facts": {"services": services},
                        },
                        None if allowed else "One or more items failed",
                    )
                )
        self.run_cases(cases, extra_tasks=[guard])

    def test_invalid_environments_fail_closed(self):
        self.run_cases(
            [
                (
                    f"reject environment {i}",
                    HOSTS[0],
                    {"ua_target_environment": value},
                    CONTRACT_ERROR,
                )
                for i, value in enumerate(
                    ("dev", "local", "", None, "Production", " test", True, 1, [])
                )
            ]
        )

    def test_path_socket_port_and_maintenance_guards_in_every_environment(self):
        invalid = {
            "ua_action": "unknown",
            "ua_root": "/tmp/runtime",
            "ua_legacy_root": "/tmp/legacy",
            "ua_build_root": "/tmp/builds",
            "ua_min_free_bytes": 1,
            "ua_config_dir": "/tmp/config",
            "ua_service_user": "root",
            "ua_service_group": "root",
            "ua_services": [],
            "ua_geocode_units": ["unrelated.service"],
            "ua_pg_port": 5433,
            "ua_pg_socket": "/tmp",
            "ua_maintenance_page_enabled": "yes",
            "ua_maintenance_root": "/tmp/maintenance",
            "ua_maintenance_marker": "/tmp/enabled",
            "ua_maintenance_retry_after": 0,
            "ua_maintenance_public_title": "",
            "ua_maintenance_public_message": "",
            "ua_maintenance_public_window": "x" * 201,
        }
        self.run_cases(
            [
                (
                    f"reject {environment} {key}",
                    HOSTS[0],
                    {"ua_target_environment": environment, key: value},
                    CONTRACT_ERROR,
                )
                for environment in ENVIRONMENTS
                for key, value in invalid.items()
            ]
        )

    def test_apply_approvals_required_in_every_environment(self):
        cases = []
        for environment in ENVIRONMENTS:
            approved = {**APPROVALS, "ua_target_environment": environment}
            cases.append((f"approved {environment}", HOSTS[0], approved, None))
            for key in APPROVALS.keys() - {"ua_action"}:
                denied = {**approved, key: False if key.endswith("approved") else ""}
                cases.append((f"deny {environment} {key}", HOSTS[0], denied, APPLY_ERROR))
            cases.append(
                (
                    f"deny notifications {environment}",
                    HOSTS[0],
                    {**approved, "ua_manage_notification_timer": True},
                    APPLY_ERROR,
                )
            )
            cases.append(
                (
                    f"approved notifications {environment}",
                    HOSTS[0],
                    {
                        **approved,
                        "ua_manage_notification_timer": True,
                        "ua_disable_notification_timer_approved": True,
                    },
                    None,
                )
            )
        self.run_cases(cases)

    def test_console_approval_required_in_every_environment(self):
        guard = yaml.safe_load((ROLE / "tasks/sql_console_provision.yml").read_text())[0]
        cases = []
        for environment in ENVIRONMENTS:
            for approved in (False, True):
                cases.append(
                    (
                        f"console {environment} {approved}",
                        HOSTS[0],
                        {
                            **APPROVALS,
                            "ua_target_environment": environment,
                            "ua_sql_console_provision_approved": approved,
                        },
                        None if approved else guard["ansible.builtin.assert"]["fail_msg"],
                    )
                )
        self.run_cases(cases, extra_tasks=[guard])

    def test_tags_and_skip_tags_rejected_in_every_environment(self):
        for option in ("--tags", "--skip-tags", "--start-at-task"):
            with self.subTest(option=option):
                self.run_cases(
                    [
                        (
                            f"deny {option} {environment}",
                            HOSTS[0],
                            {"ua_target_environment": environment},
                            CONTRACT_ERROR,
                        )
                        for environment in ENVIRONMENTS
                    ],
                    options=[option, "preflight"],
                )

    def test_role_has_no_fixed_hostname_or_environment_bypass(self):
        text = "\n".join(path.read_text() for path in ROLE.rglob("*.yml"))
        self.assertNotIn("ua_expected_hostname", text)
        self.assertNotIn("webserver", text)
        # Database guards must never depend on the target environment.
        tasks = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
        for task in tasks:
            if "community.postgresql.postgresql_query" in task:
                self.assertNotIn("ua_target_environment", json.dumps(task))
