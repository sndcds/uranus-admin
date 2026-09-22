"""Run the ACL prerequisite tasks locally with synthetic connection-user tools."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from test_deployment import ANSIBLE, ROLE


class TemporaryPermissionTests(unittest.TestCase):
    def test_acl_prerequisite_in_check_and_apply(self):
        preflight = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
        start = next(
            i for i, task in enumerate(preflight) if "ua_connection_uid" == task.get("register")
        )
        tasks = preflight[start : start + 3]
        # The guard must run before toolchain preparation or postgres user tasks.
        first_dependent = next(
            i
            for i, task in enumerate(preflight)
            if task.get("become_user") or task.get("ansible.builtin.import_tasks")
        )
        self.assertLess(start + 2, first_dependent)
        for check in (False, True):
            with self.subTest(check=check), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plays = []
                for name, uid, exit_code, rejected in (
                    ("available", 1000, 0, False),
                    ("missing", 1000, None, True),
                    ("broken", 1000, 1, True),
                    ("root_without_acl", 0, None, False),
                ):
                    bindir = root / name
                    bindir.mkdir()
                    identity = bindir / "id"
                    identity.write_text(f"#!/bin/sh\necho {uid}\n")
                    identity.chmod(0o755)
                    if exit_code is not None:
                        executable = bindir / "setfacl"
                        executable.write_text(f"#!/bin/sh\nexit {exit_code}\n")
                        executable.chmod(0o755)
                    plays.append(
                        {
                            "name": name,
                            "hosts": "localhost",
                            "connection": "local",
                            "gather_facts": False,
                            # Prove probes override the deployment play's become.
                            "become": True,
                            "environment": {"PATH": str(bindir)},
                            "vars": {
                                "ansible_python_interpreter": sys.executable,
                                "ansible_become": True,
                            },
                            "tasks": [
                                {"ansible.builtin.set_fact": {"guard_rejected": False}},
                                {
                                    "block": tasks,
                                    "rescue": [
                                        {
                                            "ansible.builtin.assert": {
                                                "that": (
                                                    "'sudo apt-get install acl' "
                                                    "in ansible_failed_result.msg"
                                                )
                                            }
                                        },
                                        {"ansible.builtin.set_fact": {"guard_rejected": True}},
                                    ],
                                },
                                {
                                    "ansible.builtin.assert": {
                                        "that": [
                                            f"guard_rejected == {rejected}",
                                            "not ua_connection_uid.changed",
                                            "not ua_setfacl.changed",
                                        ]
                                    }
                                },
                            ],
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
                        "localhost,",
                        str(playbook),
                        *(["--check"] if check else []),
                    ],
                    env={
                        **os.environ,
                        "ANSIBLE_CONFIG": str(ANSIBLE / "ansible.cfg"),
                        "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                        "ANSIBLE_NOCOLOR": "1",
                    },
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
