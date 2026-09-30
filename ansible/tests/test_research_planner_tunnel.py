"""Tunnel deployment boundary tests; no real SSH connections or model requests."""

import ast
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from test_deployment import ROLE, ROOT, filters, load, nginx_defaults

inspector = load("planner_tunnel", ROLE / "library/uranus_planner_tunnel.py")
UNIT = "uranus-admin-research-planner-tunnel.service"


class PlannerTunnelTests(unittest.TestCase):
    def setUp(self):
        self.defaults = nginx_defaults()
        self.config = dict(
            host="planner.example.invalid",
            ssh_port=22,
            user="research-planner-tunnel",
            local_port=8090,
            remote_host="127.0.0.1",
            remote_port=8090,
            key="/etc/uranus-admin/research-planner-ssh-key",
            known="/etc/uranus-admin/research-planner-known_hosts",
        )

    def test_defaults_and_backend_timeout(self):
        for key, value in {
            "tunnel_enabled": False,
            "ssh_host": "",
            "ssh_port": 22,
            "local_port": 8090,
            "remote_host": "127.0.0.1",
            "remote_port": 8090,
            "ssh_user": "research-planner-tunnel",
        }.items():
            self.assertEqual(self.defaults["ua_research_planner_" + key], value)
        tree = ast.parse((ROOT / "backend/app/config.py").read_text())
        field = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name)
            and n.target.id == "research_planner_timeout_seconds"
        )
        self.assertEqual(
            {k.arg: k.value.value for k in field.value.keywords}, {"default": 30, "ge": 1, "le": 30}
        )

    def test_scalar_validation_rejects_injection_and_unsafe_destinations(self):
        self.assertTrue(filters.valid_planner_tunnel(**self.config))
        cases = {
            "host": [
                "",
                "-oProxyCommand=evil",
                "a\nExecStart=evil",
                "user@host",
                "https://host",
                "a b",
                "a%H",
                "$(evil)",
                "host;evil",
            ],
            "user": ["", "root", "-oUser=root", "user@host", "a b", "a\nEnvironment=evil"],
            "ssh_port": [0, 65536, "22", True, "22 -oProxyCommand=evil"],
            "local_port": [0, 65536, False, "8090"],
            "remote_port": [0, 65536, True, "8090"],
            "remote_host": ["", "localhost", "::1", "10.0.0.1", "127.0.0.2"],
            "key": [
                "relative/key",
                "/tmp/key name",
                "/etc/../key",
                "/etc//key",
                "/etc/%H",
                "/etc/$KEY",
                "/etc/key\nExecStart=evil",
                "/etc/key\\other",
            ],
            "known": ["relative", "/etc/../known", "/etc/%d", "/etc/a b", "/etc/a\n", "/dev/null/"],
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.assertFalse(filters.valid_planner_tunnel(**{**self.config, key: value}))
        self.assertFalse(
            filters.valid_planner_tunnel(**{**self.config, "known": self.config["key"]})
        )
        for port in (1, 65535):
            self.assertTrue(
                filters.valid_planner_tunnel(
                    **{**self.config, "ssh_port": port, "local_port": port, "remote_port": port}
                )
            )

    def render(self, **extra):
        env = Environment(loader=FileSystemLoader(ROLE / "templates"), undefined=StrictUndefined)
        values = {
            **self.defaults,
            "ua_planner_tunnel": {"credential_revision": "synthetic-metadata"},
            "ua_research_planner_ssh_host": "planner.example.invalid",
            **extra,
        }
        return env.get_template("research-planner-tunnel.service.j2").render(values)

    def test_real_ansible_inventory_scalar_validation(self):
        cases = [{**self.config, "expected": True}]
        for field, value in (
            ("ssh_port", "22"),
            ("ssh_port", True),
            ("local_port", 0),
            ("remote_port", 65536),
            ("host", ""),
            ("remote_host", "localhost"),
            ("key", "relative/key"),
            ("known", "/etc/%d"),
        ):
            cases.append({**self.config, field: value, "expected": False})
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {"cases": cases},
                "tasks": [
                    {
                        "ansible.builtin.assert": {
                            "that": "item.expected == (item.host | ua_valid_planner_tunnel("
                            "item.ssh_port, item.user, item.local_port, item.remote_host, "
                            "item.remote_port, item.key, item.known))",
                        },
                        "loop": "{{ cases }}",
                    }
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "play.yml"
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
                    "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(Path(directory) / "tmp"),
                },
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unit_has_fixed_arguments_and_private_systemd_credentials(self):
        unit = self.render(
            ua_research_planner_ssh_port=2222,
            ua_research_planner_local_port=18090,
            ua_research_planner_remote_port=28090,
            ua_research_planner_ssh_user="planner-fixture",
            ua_research_planner_ssh_key_path="/etc/fixture/key",
            ua_research_planner_known_hosts_path="/etc/fixture/known",
        )
        for text in (
            "-N -T",
            "-F /dev/null",
            "BatchMode=yes",
            "ExitOnForwardFailure=yes",
            "StrictHostKeyChecking=yes",
            "IdentitiesOnly=yes",
            "IdentityAgent=none",
            "ServerAliveInterval=30",
            "ServerAliveCountMax=3",
            "-p 2222",
            "-L 127.0.0.1:18090:127.0.0.1:28090",
            "planner-fixture@planner.example.invalid",
            "LoadCredential=planner-ssh-key:/etc/fixture/key",
            "LoadCredential=planner-known-hosts:/etc/fixture/known",
            "-i %d/planner-ssh-key",
            "UserKnownHostsFile=%d/planner-known-hosts",
            "User=oklab",
            "Group=oklab",
            "Restart=on-failure",
            "RestartSec=5s",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "PrivateDevices=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
            "ProtectKernelTunables=true",
            "ProtectKernelModules=true",
            "ProtectControlGroups=true",
            "RestrictSUIDSGID=true",
            "LockPersonality=true",
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            "UMask=0077",
        ):
            self.assertIn(text, unit)
        for text in (
            "StrictHostKeyChecking=no",
            "UserKnownHostsFile=/dev/null",
            "ProxyCommand",
            "EnvironmentFile=",
            "RESEARCH_PLANNER_API_KEY",
            "PRIVATE KEY",
        ):
            self.assertNotIn(text, unit)
        self.assertNotIn("0.0.0.0", unit)
        if shutil.which("systemd-analyze"):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / UNIT
                path.write_text(unit)
                result = subprocess.run(
                    ["systemd-analyze", "verify", str(path)], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_backend_only_wants_after_tunnel_when_enabled(self):
        env = Environment(loader=FileSystemLoader(ROLE / "templates"), undefined=StrictUndefined)
        values = {
            **self.defaults,
            "ua_release_dir": "/fixture",
            "ua_config_dir": "/etc/uranus-admin",
            "ua_uv": "/usr/bin/true",
        }
        for enabled in (True, False):
            for name in ("backend", "check-worker", "geocode-worker"):
                unit = env.get_template(name + ".service.j2").render(
                    {**values, "ua_research_planner_tunnel_enabled": enabled}
                )
                self.assertEqual(UNIT in unit, enabled and name == "backend")
                self.assertNotIn("Requires=" + UNIT, unit)
                self.assertNotIn("LoadCredential=", unit)
                if enabled and name == "backend":
                    self.assertIn("After=" + UNIT, unit)
                    self.assertIn("Wants=" + UNIT, unit)

    def test_reconcile_is_idempotent_and_does_not_restart_other_services(self):
        running = {"exists": True, "active": True, "enabled": True}
        self.assertFalse(filters.planner_reconcile(True, running, []))
        self.assertTrue(filters.planner_reconcile(True, running, ["/etc/systemd/system/" + UNIT]))
        self.assertTrue(filters.planner_reconcile(True, {}, []))
        self.assertTrue(filters.planner_reconcile(False, running, []))
        self.assertFalse(filters.planner_reconcile(False, {}, []))
        states = {
            name: {"state": "running"}
            for name in (
                "uranus-admin-backend.service",
                "uranus-admin-check-worker.service",
                "uranus-admin-frontend.service",
            )
        }
        self.assertEqual(
            filters.activation_plan(["/etc/systemd/system/" + UNIT], states, "/etc/uranus-admin")[
                "restart_services"
            ],
            [],
        )
        snapshot = filters.service_snapshot(
            [
                {
                    "item": "nginx.service",
                    "stdout": "LoadState=loaded\nActiveState=active\nUnitFileState=enabled",
                },
                {
                    "item": UNIT,
                    "stdout": "LoadState=not-found\nActiveState=inactive\nUnitFileState=",
                },
            ]
        )
        self.assertFalse(snapshot[UNIT]["exists"])

    def test_role_wiring_health_and_secret_boundaries(self):
        inputs = (ROLE / "tasks/inputs.yml").read_text()
        self.assertIn("ua_valid_planner_tunnel", inputs)
        inspect = yaml.safe_load((ROLE / "tasks/research_planner_inspect.yml").read_text())[0]
        self.assertTrue(inspect["no_log"])
        self.assertFalse(inspect["diff"])
        health = yaml.safe_load((ROLE / "tasks/healthchecks_local.yml").read_text())
        probe = next(t for t in health if "planner tunnel without" in t["name"])
        args = probe["ansible.builtin.uri"]
        self.assertTrue(args["url"].endswith("/health"))
        self.assertEqual(args["follow_redirects"], "none")
        self.assertFalse(args["use_proxy"])
        self.assertFalse(args["use_netrc"])
        self.assertNotIn("headers", args)
        self.assertIn("{'status': 'ok'}", probe["until"])
        self.assertTrue(probe["no_log"])
        self.assertIn("tunnel_enabled", probe["when"])
        text = (ROLE / "tasks/activate.yml").read_text()
        self.assertLess(
            text.index("Reconcile the optional tunnel"), text.index("Start affected application")
        )
        self.assertIn("Require the local tunnel port to be free", text)
        for name in ("release.yml", "activate.yml"):
            self.assertIn(UNIT, (ROLE / "tasks" / name).read_text())
        recovery = (ROLE / "tasks/system_recovery.yml").read_text()
        self.assertIn("Restore the previously managed tunnel", recovery)
        # SSH variables are not application Settings and cannot enter the runtime allowlist.
        settings = (ROOT / "backend/app/config.py").read_text()
        self.assertNotIn("research_planner_ssh", settings)
        self.assertNotIn("PRIVATE KEY", (ROLE / "tasks/file_plan.yml").read_text())
        self.assertNotIn("read_bytes", (ROLE / "library/uranus_planner_tunnel.py").read_text())


class CredentialInspectionTests(unittest.TestCase):
    def file_info(self, mode=0o600, uid=0, gid=0, size=42):
        return SimpleNamespace(
            st_mode=stat.S_IFREG | mode,
            st_uid=uid,
            st_gid=gid,
            st_size=size,
            st_ino=1,
            st_mtime_ns=1,
            st_ctime_ns=1,
        )

    def test_key_and_known_hosts_metadata(self):
        parent = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        for modes in ({0o400, 0o600}, {0o400, 0o444, 0o600, 0o644}):
            for mode in modes:
                # File is checked after /etc/example, /etc, /.
                with patch.object(
                    Path, "lstat", side_effect=[parent, parent, parent, self.file_info(mode)]
                ):
                    inspector.protected_file("/etc/example/key", modes)
        for info in (
            self.file_info(0o644),
            self.file_info(0o640),
            self.file_info(uid=1000),
            self.file_info(gid=1000),
            self.file_info(size=0),
            self.file_info(size=1024 * 1024 + 1),
            SimpleNamespace(st_mode=stat.S_IFLNK | 0o777),
        ):
            with (
                self.subTest(info=info),
                patch.object(Path, "lstat", side_effect=[parent, parent, parent, info]),
            ):
                with self.assertRaises(ValueError):
                    inspector.protected_file("/etc/example/key", {0o400, 0o600})
        for bad_parent in (
            SimpleNamespace(st_mode=stat.S_IFLNK | 0o777),
            SimpleNamespace(st_mode=stat.S_IFDIR | 0o777, st_uid=0),
            SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=1000),
        ):
            with patch.object(Path, "lstat", return_value=bad_parent):
                with self.assertRaises(ValueError):
                    inspector.protected_file("/etc/example/key", {0o600})

    def test_inspection_never_reads_keys_and_detects_rotation(self):
        info = self.file_info()
        with (
            patch.object(os.path, "lexists", return_value=False),
            patch.object(os, "access", return_value=True),
            patch.object(inspector, "protected_file", return_value=info),
            patch.object(
                Path, "open", side_effect=AssertionError("Private key contents must not be read")
            ),
        ):
            first = inspector.inspect(True, "/etc/key", "/etc/known")
            info.st_mtime_ns = 2
            self.assertNotEqual(
                first["credential_revision"],
                inspector.inspect(True, "/etc/key", "/etc/known")["credential_revision"],
            )
            self.assertEqual(set(first), {"changed", "managed", "credential_revision"})
            self.assertNotIn("PRIVATE", json.dumps(first))
        with (
            patch.object(os.path, "lexists", return_value=False),
            patch.object(
                inspector,
                "protected_file",
                side_effect=AssertionError("Disabled feature must not require keys"),
            ),
        ):
            self.assertFalse(inspector.inspect(False, "/etc/key", "/etc/known")["managed"])

    def test_missing_credentials_fail(self):
        with (
            patch.object(os.path, "lexists", return_value=False),
            patch.object(os, "access", return_value=True),
            patch.object(inspector, "protected_file", side_effect=FileNotFoundError),
        ):
            with self.assertRaises(FileNotFoundError):
                inspector.inspect(True, "/etc/missing", "/etc/known")

    def test_unmanaged_units_and_dropins_are_never_adopted(self):
        with (
            patch.object(os.path, "lexists", side_effect=lambda p: p == inspector.UNIT_PATH),
            patch.object(inspector, "protected_file"),
            patch.object(Path, "open", return_value=io.BytesIO(b"# operator owned\n")),
        ):
            with self.assertRaisesRegex(ValueError, "unmanaged"):
                inspector.inspect(False, "/etc/key", "/etc/known")
        for path in (
            Path("/run/systemd/system") / UNIT,
            Path("/etc/systemd/system/service.d"),
            Path("/etc/systemd/system/uranus-admin-.service.d"),
            Path("/etc/systemd/system") / (UNIT + ".d"),
        ):
            with (
                self.subTest(path=path),
                patch.object(
                    os.path, "lexists", side_effect=lambda p, expected=path: p == expected
                ),
                patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFDIR)),
                patch.object(Path, "iterdir", return_value=iter([Path("override.conf")])),
            ):
                with self.assertRaisesRegex(ValueError, "alternate location|drop-ins"):
                    inspector.inspect(True, "/etc/key", "/etc/known")

    def test_managed_disabled_unit_needs_no_credentials(self):
        with (
            patch.object(os.path, "lexists", side_effect=lambda p: p == inspector.UNIT_PATH),
            patch.object(inspector, "protected_file") as protected,
            patch.object(Path, "open", return_value=io.BytesIO(inspector.MARKER)),
        ):
            self.assertTrue(inspector.inspect(False, "/etc/key", "/etc/known")["managed"])
            protected.assert_called_once_with(inspector.UNIT_PATH, {0o644})
