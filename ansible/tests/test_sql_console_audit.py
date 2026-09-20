"""The standalone evidence export cannot provision or reveal catalog literals."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg2
import yaml
from test_deployment import ANSIBLE, ROLE
from test_sql_console import CONTRACT, console


class ModuleExit(BaseException):
    pass


class ConsoleAuditTests(unittest.TestCase):
    def test_audit_entrypoint_is_read_only_even_without_check_mode(self):
        for check_mode in (False, True):
            with self.subTest(check_mode=check_mode):
                module = MagicMock()
                module.params = {"state": "audit", "contract": CONTRACT, "dsn": None}
                module.check_mode = check_mode
                module.exit_json.side_effect = ModuleExit
                conn = MagicMock()
                boundary = MagicMock()
                boundary.audit.return_value = {"blocker_counts": {"unreviewed_extension": 1}}
                with (
                    patch("ansible.module_utils.basic.AnsibleModule", return_value=module),
                    patch.object(console.psycopg2, "connect", return_value=conn) as connect,
                    patch.object(console, "Boundary", return_value=boundary),
                    self.assertRaises(ModuleExit),
                ):
                    console.main()
                self.assertEqual(connect.call_args.kwargs["dbname"], "oklab")
                self.assertEqual(connect.call_args.kwargs["host"], "/var/run/postgresql")
                self.assertIn("statement_timeout=10000", connect.call_args.kwargs["options"])
                conn.set_session.assert_called_once_with(
                    readonly=True, isolation_level="REPEATABLE READ"
                )
                conn.rollback.assert_called_once()
                conn.commit.assert_not_called()
                conn.close.assert_called_once()
                boundary.provision.assert_not_called()
                boundary.execute.assert_not_called()
                module.exit_json.assert_called_once_with(
                    changed=False, sql_console_audit=boundary.audit.return_value
                )

    def test_audit_refuses_a_writable_transaction(self):
        boundary = console.Boundary(MagicMock(), CONTRACT)
        with (
            patch.object(boundary, "rows", return_value=[("off",)]),
            patch.object(boundary, "inspect") as inspect,
            self.assertRaisesRegex(ValueError, "audit_requires_read_only_transaction"),
        ):
            boundary.audit()
        inspect.assert_not_called()

    def test_database_failure_does_not_export_driver_details(self):
        module = MagicMock()
        module.params = {"state": "audit", "contract": CONTRACT, "dsn": None}
        module.check_mode = False
        module.fail_json.side_effect = ModuleExit
        conn = MagicMock()
        boundary = MagicMock()
        boundary.audit.side_effect = psycopg2.Error("secret-fixture-driver-detail")
        with (
            patch("ansible.module_utils.basic.AnsibleModule", return_value=module),
            patch.object(console.psycopg2, "connect", return_value=conn),
            patch.object(console, "Boundary", return_value=boundary),
            self.assertRaises(ModuleExit),
        ):
            console.main()
        self.assertNotIn("secret-fixture", str(module.fail_json.call_args))
        module.exit_json.assert_not_called()
        conn.commit.assert_not_called()
        conn.close.assert_called_once()

    def test_metadata_details_hash_definition_and_option_literals(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            (
                123,
                "public",
                "geometry_columns",
                10,
                [
                    "v",
                    False,
                    False,
                    ["synthetic-secret-option"],
                    "SELECT 'synthetic-secret-body'",
                    [["column", "text", False]],
                ],
            )
        ]
        report = console.postgis_metadata(conn, include_details=True)
        self.assertNotIn("synthetic-secret", json.dumps(report))
        self.assertEqual(report[0]["structure"]["columns"], [["column", "text", False]])
        basic = console.postgis_metadata(conn)
        self.assertEqual(basic[0]["definition_sha256"], report[0]["definition_sha256"])
        self.assertNotIn("structure", basic[0])

    def test_standalone_play_only_invokes_audit_and_keeps_local_report_private(self):
        play = yaml.safe_load((ANSIBLE / "sql-console-audit.yml").read_text())[0]
        self.assertEqual(
            play["tasks"],
            [
                {
                    "name": "Collect evidence without deployment or secret adoption",
                    "ansible.builtin.include_role": {
                        "name": "uranus_admin",
                        "tasks_from": "sql_console_audit.yml",
                    },
                }
            ],
        )
        tasks = yaml.safe_load((ROLE / "tasks/sql_console_audit.yml").read_text())
        query = next(t for t in tasks if "uranus_sql_console" in t)
        self.assertEqual(query["uranus_sql_console"]["state"], "audit")
        self.assertEqual(query["become_user"], "postgres")
        self.assertTrue(query["no_log"])
        for task in tasks:
            for name in ("ansible.builtin.file", "ansible.builtin.copy"):
                if name not in task:
                    continue
                self.assertEqual(task["delegate_to"], "localhost")
                self.assertFalse(task["become"])
                self.assertEqual(task[name]["mode"], "0600" if name.endswith("copy") else "0700")
            self.assertFalse(
                any(
                    k in task
                    for k in (
                        "ansible.builtin.command",
                        "ansible.builtin.shell",
                        "ansible.builtin.import_tasks",
                    )
                )
            )


class ConsoleAuditPlayTests(unittest.TestCase):
    def test_export_permissions_check_mode_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            role = root / "roles/uranus_admin"
            for directory in ("tasks", "library", "files"):
                (role / directory).mkdir(parents=True)
            shutil.copy(ROLE / "tasks/sql_console_audit.yml", role / "tasks")
            shutil.copy(ROLE / "files/sql_console_contract.json", role / "files")
            shutil.copy(ANSIBLE / "sql-console-audit.yml", root)
            (role / "library/uranus_sql_console.py").write_text("""
from ansible.module_utils.basic import AnsibleModule
module = AnsibleModule(argument_spec={
    "state": {"type": "str", "choices": ["audit"]}, "contract": {"type": "dict"}
}, supports_check_mode=True)
module.exit_json(changed=False, sql_console_audit={
    "blocker_counts": {"unreviewed_extension": 1}, "private_fixture": "catalog-fixture-only"
})
""")
            (root / "inventory.yml").write_text(
                yaml.safe_dump(
                    {
                        "all": {
                            "children": {
                                "uranus_admin": {
                                    "hosts": {
                                        "fixture": {
                                            "ansible_connection": "local",
                                            "ansible_become": False,
                                            "ansible_python_interpreter": sys.executable,
                                        }
                                    }
                                }
                            }
                        },
                    }
                )
            )
            (root / "ansible.cfg").write_text(
                "[defaults]\nroles_path=roles\nnocows=True\nremote_tmp=/tmp\n"
            )
            env = {
                **os.environ,
                "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
                "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
            }
            cmd = [
                sys.executable,
                "-m",
                "ansible.cli.playbook",
                "-i",
                "inventory.yml",
                "sql-console-audit.yml",
            ]

            def run(*args):
                result = subprocess.run(
                    cmd + list(args),
                    cwd=root,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=60,
                )
                self.assertNotIn("catalog-fixture-only", result.stdout)
                return result

            report = root / "sql-console-audit.local/fixture.json"
            check = run("--check", "--diff")
            self.assertEqual(check.returncode, 0, check.stdout)
            self.assertFalse(report.exists())
            self.assertFalse(report.parent.exists())
            apply = run("--diff")
            self.assertEqual(apply.returncode, 0, apply.stdout)
            self.assertEqual(
                json.loads(report.read_text())["private_fixture"], "catalog-fixture-only"
            )
            self.assertEqual(report.stat().st_mode & 0o777, 0o600)
            self.assertEqual(report.parent.stat().st_mode & 0o777, 0o700)
            original = report.read_bytes()
            check = run("--check", "--diff")
            self.assertEqual(check.returncode, 0, check.stdout)
            self.assertEqual(report.read_bytes(), original)
            report.unlink()
            outside = root / "preserved.json"
            outside.write_text("preserve-existing-file")
            report.symlink_to(outside)
            refused = run()
            self.assertNotEqual(refused.returncode, 0, refused.stdout)
            self.assertEqual(outside.read_text(), "preserve-existing-file")


if __name__ == "__main__":
    unittest.main()
