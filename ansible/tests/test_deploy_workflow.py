"""Controller workflow regressions; synthetic local inventories, never SSH or production."""

import argparse
import contextlib
import hashlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from test_deployment import ANSIBLE, load

workflow = load("deploy_workflow", ANSIBLE / "scripts/deploy.py")


class DeployWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.controller = self.root / "ansible"
        self.controller.mkdir()
        (self.controller / "ansible.cfg").write_text("[defaults]\n")
        (self.controller / "deploy.yml").write_text("[]\n")
        self.inventory = self.root / "inventory.yml"
        self.inventory.write_text("synthetic inventory\n")
        self.artifact = self.root / "release.tar.gz"
        self.artifact.write_bytes(b"synthetic artifact; not deployed")
        self.values = dict(
            ua_target_environment="test",
            ansible_connection="local",
            ua_artifact=str(self.artifact),
            ua_artifact_sha256=workflow.digest(self.artifact),
            ua_release_sha="a" * 40,
        )
        self.approvals = self.root / "approvals.yml"
        self.args = argparse.Namespace(
            inventory=self.inventory,
            host="fixture",
            approvals=self.approvals,
            maintenance_window="Test window explicitly chosen by operator",
            backup_reference="Operator-verified synthetic recovery snapshot",
            ask_become_pass=False,
        )
        self.commands = []
        self.phase_hook = lambda check: None
        self.check_returncode = self.apply_returncode = 0
        self.patches = [
            patch.object(workflow, "ANSIBLE", self.controller),
            patch.object(workflow.subprocess, "run", side_effect=self.process),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def process(self, command, **kwargs):
        self.assertEqual(kwargs["env"]["ANSIBLE_CONFIG"], str(self.controller / "ansible.cfg"))
        if "ansible.cli.inventory" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "uranus_admin": {"children": ["test_targets"]},
                        "test_targets": {"hosts": ["fixture"]},
                        "_meta": {"hostvars": {"fixture": self.values}},
                    }
                ),
            )
        self.commands.append(command)
        check = "--check" in command
        if not check:
            persisted = yaml.safe_load(self.approvals.read_text())
            self.assertEqual(persisted["ua_apply_confirmation"], workflow.CONFIRMATION)
            self.assertIn("Automatischer", persisted["ua_reviewed_dry_run"])
            self.assertEqual(stat.S_IMODE(self.approvals.stat().st_mode), 0o600)
        self.phase_hook(check)
        return subprocess.CompletedProcess(
            command, self.check_returncode if check else self.apply_returncode
        )

    def run_workflow(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return workflow.run(self.args)

    def write_approvals(self, values):
        self.approvals.write_text(yaml.safe_dump(values))
        self.approvals.chmod(0o600)

    def test_success_automatically_records_then_applies_the_same_frozen_inputs(self):
        self.assertEqual(self.run_workflow(), 0)
        self.assertEqual(self.commands[0], self.commands[1] + ["--check", "--diff"])
        private_inventory = Path(self.commands[0][self.commands[0].index("-i") + 1])
        self.assertNotEqual(private_inventory, self.inventory)
        selected = json.loads(private_inventory.read_text())["all"]["children"]["uranus_admin"]
        self.assertEqual(selected["hosts"], {"fixture": self.values})
        record = json.loads((private_inventory.parent / "result.json").read_text())
        self.assertEqual(record["review"], "automated")
        self.assertEqual(record["dry_run_exit_code"], 0)
        self.assertEqual(record["apply_exit_code"], 0)
        self.assertEqual(record["artifact_sha256"], workflow.digest(self.artifact))
        approval = yaml.safe_load(self.approvals.read_text())
        for key in ("secret_adoption", "admin_database_bootstrap", "sql_console_provision"):
            self.assertTrue(approval[f"ua_{key}_approved"])
        self.assertFalse(approval["ua_manage_notification_timer"])
        for file in private_inventory.parent.iterdir():
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(private_inventory.parent.stat().st_mode), 0o700)

    def test_staging_and_existing_references_are_preserved(self):
        self.values["ua_target_environment"] = "staging"
        self.write_approvals(
            dict(
                ua_maintenance_window="Existing chosen window",
                ua_backup_reference="Existing backup",
                ua_manage_notification_timer=True,
                ua_disable_notification_timer_approved=True,
            )
        )
        self.args.maintenance_window = self.args.backup_reference = None
        self.assertEqual(self.run_workflow(), 0)
        values = yaml.safe_load(self.approvals.read_text())
        self.assertEqual(values["ua_backup_reference"], "Existing backup")
        self.assertEqual(values["ua_maintenance_window"], "Existing chosen window")
        self.assertTrue(values["ua_disable_notification_timer_approved"])

    def test_failed_dry_run_never_applies_or_changes_approvals(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    self.write_approvals({"ua_apply_confirmation": "old approval"})
                before = workflow.private_read(self.approvals)
                self.commands.clear()
                self.check_returncode = 2
                self.assertEqual(self.run_workflow(), 2)
                self.assertEqual(workflow.private_read(self.approvals), before)
                self.assertEqual(len(self.commands), 1)

    def test_production_missing_environment_unknown_host_and_patterns_never_run_playbooks(self):
        for environment, host in (
            ("production", "fixture"),
            (None, "fixture"),
            ("test", "other"),
            ("test", "all"),
            ("test", "fixture:*"),
        ):
            with self.subTest(environment=environment, host=host):
                self.values["ua_target_environment"] = environment
                self.args.host = host
                with self.assertRaises(workflow.WorkflowError):
                    self.run_workflow()
                self.assertEqual(self.commands, [])
                self.assertFalse(self.approvals.exists())

    def test_no_fabricated_references_or_automatic_notification_approval(self):
        for values in (
            {"ua_manage_notification_timer": True},
            {"ua_target_environment": "test"},
            {"ua_manage_notification_timer": "false"},
        ):
            with self.subTest(values=values):
                self.write_approvals(values)
                with self.assertRaises(workflow.WorkflowError):
                    self.run_workflow()
                self.assertEqual(self.commands, [])
        self.approvals.unlink()
        self.args.backup_reference = None
        with self.assertRaises(workflow.WorkflowError):
            self.run_workflow()
        self.assertEqual(self.commands, [])

    def test_changes_during_dry_run_refuse_apply_and_preserve_approvals(self):
        original_values = self.values.copy()
        for kind in ("inventory", "resolved", "artifact", "controller", "approval"):
            with self.subTest(kind=kind):
                self.values = original_values.copy()
                self.artifact.write_bytes(b"synthetic artifact; not deployed")
                self.write_approvals({"ua_apply_confirmation": "previous"})
                before = self.approvals.read_bytes()
                self.commands.clear()

                def mutate(check, kind=kind):
                    self.assertTrue(check)
                    if kind == "resolved":
                        self.values["ansible_host"] = "changed.invalid"
                    else:
                        file = {
                            "inventory": self.inventory,
                            "artifact": self.artifact,
                            "controller": self.controller / "deploy.yml",
                            "approval": self.approvals,
                        }[kind]
                        file.write_text("changed during dry run\n")

                self.phase_hook = mutate
                with self.assertRaises(workflow.WorkflowError):
                    self.run_workflow()
                self.assertEqual(len(self.commands), 1)
                self.assertEqual(
                    self.approvals.read_bytes(),
                    b"changed during dry run\n" if kind == "approval" else before,
                )

    def test_artifact_mismatch_and_templated_connection_fail_before_dry_run(self):
        for key, value in (
            ("ua_artifact_sha256", "0" * 64),
            ("ansible_host", "{{ target }}"),
            ("ansible_ssh_private_key_file", "{{ inventory_dir }}/key"),
        ):
            with self.subTest(key=key):
                previous = self.values.copy()
                self.values[key] = value
                with self.assertRaises(workflow.WorkflowError):
                    self.run_workflow()
                self.assertEqual(self.commands, [])
                self.values = previous

    def test_approval_permissions_symlinks_and_concurrent_run_are_refused(self):
        self.approvals.write_text("{}")
        self.approvals.chmod(0o644)
        with self.assertRaises(workflow.WorkflowError):
            self.run_workflow()
        self.approvals.unlink()
        self.approvals.symlink_to(self.inventory)
        with self.assertRaises(OSError):
            self.run_workflow()
        self.approvals.unlink()
        with workflow.approval_lock(self.approvals), self.assertRaises(workflow.WorkflowError):
            self.run_workflow()
        self.assertEqual(self.commands, [])

    def test_apply_failure_is_reported_without_retry(self):
        self.apply_returncode = 4
        self.assertEqual(self.run_workflow(), 4)
        self.assertEqual(len(self.commands), 2)
        record = next((self.controller / "deploy-runs.local").glob("*/result.json"))
        self.assertEqual(json.loads(record.read_text())["apply_exit_code"], 4)

    def test_inventory_facts_are_not_promoted_to_extra_vars_and_repeats_check_again(self):
        self.values.update(ua_action="inspect", ua_manifest={"untrusted": "inventory"})
        self.assertEqual(self.run_workflow(), 0)
        variables = Path(self.commands[0][self.commands[0].index("-e") + 1][1:])
        values = json.loads(variables.read_text())
        self.assertEqual(values["ua_action"], "deploy")
        self.assertNotIn("ua_manifest", values)
        self.args.maintenance_window = self.args.backup_reference = None
        self.assertEqual(self.run_workflow(), 0)
        self.assertEqual(["--check" in c for c in self.commands], [True, False, True, False])

    def test_failed_approval_write_does_not_start_apply(self):
        self.write_approvals({"ua_apply_confirmation": "previous"})
        original = self.approvals.read_bytes()
        write = workflow.private_write

        def fail_on_approval(path, value):
            if path == self.approvals:
                raise OSError("synthetic failure")
            write(path, value)

        with patch.object(workflow, "private_write", side_effect=fail_on_approval):
            with self.assertRaises(OSError):
                self.run_workflow()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.approvals.read_bytes(), original)

    def test_invalid_yaml_error_does_not_echo_approval_contents(self):
        self.approvals.write_text("value: [SECRET_SENTINEL")
        self.approvals.chmod(0o600)
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(
                workflow.main(
                    [
                        "-i",
                        str(self.inventory),
                        "--host",
                        "fixture",
                        "--approvals",
                        str(self.approvals),
                    ]
                ),
                1,
            )
        self.assertNotIn("SECRET_SENTINEL", output.getvalue())
        self.assertEqual(self.commands, [])


class RealControllerWorkflowTests(unittest.TestCase):
    def test_actual_ansible_check_then_apply_uses_only_a_local_synthetic_playbook(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = root / "ansible"
            controller.mkdir()
            (controller / "ansible.cfg").write_text("[defaults]\nnocows=True\nremote_tmp=/tmp\n")
            marker = root / "applied"
            (controller / "deploy.yml").write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": "uranus_admin",
                            "gather_facts": False,
                            "tasks": [
                                {
                                    "ansible.builtin.assert": {
                                        "that": [
                                            "ua_target_environment == 'test'",
                                            "ansible_check_mode or ua_apply_confirmation == "
                                            "'Ja, führe das Deployment jetzt aus.'",
                                            "ansible_check_mode or "
                                            "ua_reviewed_dry_run.startswith('Automatischer')",
                                        ]
                                    }
                                },
                                {
                                    "ansible.builtin.copy": {
                                        "content": "applied",
                                        "dest": str(marker),
                                        "mode": "0600",
                                    },
                                    "when": "not ansible_check_mode",
                                },
                            ],
                        }
                    ]
                )
            )
            artifact = root / "synthetic.tar.gz"
            artifact.write_bytes(b"synthetic")
            inventory = root / "inventory.yml"
            inventory.write_text(
                yaml.safe_dump(
                    {
                        "all": {
                            "children": {
                                "uranus_admin": {
                                    "hosts": {
                                        "fixture": {
                                            "ansible_connection": "local",
                                            "ua_target_environment": "test",
                                            "ua_release_sha": "a" * 40,
                                            "ua_artifact": str(artifact),
                                            "ua_artifact_sha256": hashlib.sha256(
                                                b"synthetic"
                                            ).hexdigest(),
                                        }
                                    }
                                }
                            }
                        }
                    }
                )
            )
            args = argparse.Namespace(
                inventory=inventory,
                host="fixture",
                approvals=root / "approvals.yml",
                maintenance_window="Synthetic local test",
                backup_reference="Disposable fixture",
                ask_become_pass=False,
            )
            with (
                patch.object(workflow, "ANSIBLE", controller),
                patch.dict(
                    os.environ,
                    {
                        "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                    },
                ),
            ):
                self.assertEqual(workflow.run(args), 0)
            self.assertEqual(marker.read_text(), "applied")
            self.assertEqual(
                yaml.safe_load(args.approvals.read_text())["ua_apply_confirmation"],
                workflow.CONFIRMATION,
            )


if __name__ == "__main__":
    unittest.main()
