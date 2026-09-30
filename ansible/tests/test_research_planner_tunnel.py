"""Tunnel deployment boundary tests; no real SSH connections or model requests."""

import ast
import io
import json
import os
import re
import shutil
import socket
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
            qdrant_local_port=6333,
            qdrant_remote_port=6333,
            embedding_local_port=6335,
            embedding_remote_port=6335,
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
            "qdrant_local_port": 6333,
            "qdrant_remote_port": 6333,
            "embedding_local_port": 6335,
            "embedding_remote_port": 6335,
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
            "qdrant_local_port": [0, 65536, True, "6333", 8090, 6335],
            "qdrant_remote_port": [0, 65536, False, "6333"],
            "embedding_local_port": [0, 65536, False, "6335", 8090, 6333],
            "embedding_remote_port": [0, 65536, True, "6335"],
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
            ("qdrant_local_port", "6333"),
            ("qdrant_local_port", 8090),
            ("qdrant_remote_port", False),
            ("embedding_local_port", 6333),
            ("embedding_remote_port", 65536),
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
                            "item.remote_port, item.key, item.known, item.qdrant_local_port, "
                            "item.qdrant_remote_port, item.embedding_local_port, "
                            "item.embedding_remote_port))",
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
            "ConnectTimeout=15",
            "GlobalKnownHostsFile=/dev/null",
            "UpdateHostKeys=no",
            "PreferredAuthentications=publickey",
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

    def run_tasks(self, tasks, variables=None, check=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "play.yml"
            path.write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": "localhost",
                            "connection": "local",
                            "gather_facts": False,
                            "vars": {**self.defaults, **(variables or {})},
                            "tasks": tasks,
                        }
                    ]
                )
            )
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ansible.cli.playbook",
                    "-i",
                    "localhost,",
                    str(path),
                    "--diff",
                    *(["--check"] if check else []),
                ],
                env={
                    **os.environ,
                    "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(Path(directory) / "tmp"),
                },
                capture_output=True,
                text=True,
                timeout=120,
            )

    def test_exact_three_loopback_forwards_with_defaults_and_custom_ports(self):
        for ports in (
            (8090, 8090, 6333, 6333, 6335, 6335),
            (18090, 28090, 16333, 26333, 16335, 26335),
        ):
            overrides = dict(
                zip(
                    (
                        "ua_research_planner_local_port",
                        "ua_research_planner_remote_port",
                        "ua_research_planner_qdrant_local_port",
                        "ua_research_planner_qdrant_remote_port",
                        "ua_research_planner_embedding_local_port",
                        "ua_research_planner_embedding_remote_port",
                    ),
                    ports,
                    strict=True,
                )
            )
            unit = self.render(
                **overrides,
                ua_runtime={
                    "RESEARCH_PLANNER_API_KEY": "synthetic-planner-secret",
                    "QDRANT_API_KEY": "synthetic-qdrant-secret",
                    "EMBEDDING_API_KEY": "synthetic-embedding-secret",
                },
            )
            self.assertEqual(
                re.findall(r"-L (\S+)", unit),
                [
                    f"127.0.0.1:{local}:127.0.0.1:{remote}"
                    for local, remote in zip(ports[::2], ports[1::2], strict=True)
                ],
            )
            self.assertEqual(unit.count("ExecStart="), 1)
            self.assertNotIn("synthetic-", unit.replace("synthetic-metadata", ""))
            self.assertNotIn("API_KEY", unit)

    def test_real_ansible_runtime_preflight_and_secret_redaction(self):
        tasks = yaml.safe_load((ROLE / "tasks/environment_plan.yml").read_text())[-3:]
        self.assertTrue(all(task["no_log"] for task in tasks))
        runtime = {
            "SEMANTIC_SEARCH_NONCOMMERCIAL_JINA": "true",
            "RESEARCH_PLANNER_URL": "http://127.0.0.1:18090",
            "RESEARCH_PLANNER_API_KEY": "synthetic-planner-secret-" * 2,
            "QDRANT_URL": "http://127.0.0.1:16333",
            "QDRANT_API_KEY": "synthetic-qdrant-secret",
            "EMBEDDING_URL": "http://127.0.0.1:16335",
            "EMBEDDING_API_KEY": "synthetic-embedding-secret",
        }
        cases = [(runtime, True, True)]
        for field in ("QDRANT_API_KEY", "EMBEDDING_API_KEY", "RESEARCH_PLANNER_API_KEY"):
            cases.append(({k: v for k, v in runtime.items() if k != field}, True, False))
            for empty in ("", "   "):
                cases.append(({**runtime, field: empty}, True, False))
        for field, default_port in (
            ("QDRANT_URL", 6333),
            ("EMBEDDING_URL", 6335),
            ("RESEARCH_PLANNER_URL", 8090),
        ):
            for url in (
                f"http://127.0.0.1:{default_port}",
                "http://localhost:16333",
                "https://remote.invalid:6333",
                "",
            ):
                cases.append(({**runtime, field: url}, True, False))
        planner_only = {k: v for k, v in runtime.items() if k.startswith("RESEARCH_PLANNER_")}
        cases.extend([(planner_only, True, True), ({}, False, True), (runtime, False, True)])
        for value in ("false", "0", "off"):
            cases.append(
                ({**planner_only, "SEMANTIC_SEARCH_NONCOMMERCIAL_JINA": value}, True, True)
            )
        for value in ("True", "1", "on", "yes", "t", "y"):
            cases.append(
                ({**planner_only, "SEMANTIC_SEARCH_NONCOMMERCIAL_JINA": value}, True, False)
            )
        play_tasks = []
        for index, (values, enabled, expected) in enumerate(cases):
            play_tasks.extend(
                [
                    {
                        "ansible.builtin.set_fact": {
                            "ua_runtime": values,
                            "ua_research_planner_tunnel_enabled": enabled,
                            "fixture_valid": True,
                        },
                        "no_log": True,
                    },
                    {
                        "block": tasks,
                        "rescue": [
                            {"ansible.builtin.set_fact": {"fixture_valid": False}},
                        ],
                    },
                    {
                        "name": f"Check preflight case {index}",
                        "ansible.builtin.assert": {
                            "that": f"fixture_valid == {expected}",
                        },
                    },
                ]
            )
        result = self.run_tasks(
            play_tasks,
            {
                "ua_research_planner_local_port": 18090,
                "ua_research_planner_qdrant_local_port": 16333,
                "ua_research_planner_embedding_local_port": 16335,
            },
            check=True,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        for key in ("RESEARCH_PLANNER_API_KEY", "QDRANT_API_KEY", "EMBEDDING_API_KEY"):
            self.assertNotIn(runtime[key], output)

    def test_collisions_fail_without_stopping_foreign_listeners(self):
        activation = yaml.safe_load((ROLE / "tasks/activate.yml").read_text())
        block = next(task["block"] for task in activation if "block" in task)
        collision = next(t for t in block if "local tunnel ports to be free" in t["name"])
        stop = next(
            t
            for t in block
            if t.get("ansible.builtin.systemd_service", {}).get("state") == "stopped"
            and t["ansible.builtin.systemd_service"].get("name") == UNIT
        )
        start = next(t for t in block if "Reconcile the optional tunnel" in t["name"])
        self.assertLess(block.index(stop), block.index(collision))
        self.assertLess(block.index(collision), block.index(start))
        self.assertIn("ua_previous_services", str(stop["when"]))
        self.assertEqual(collision["ansible.builtin.wait_for"]["host"], "127.0.0.1")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(64)
            occupied = listener.getsockname()[1]
            fields = [
                "ua_research_planner_local_port",
                "ua_research_planner_qdrant_local_port",
                "ua_research_planner_embedding_local_port",
            ]
            self.assertEqual(collision["loop"], ["{{ " + field + " }}" for field in fields])
            tasks = []
            for field in fields:
                tasks.extend(
                    [
                        {"ansible.builtin.set_fact": {"fixture_collision": False}},
                        {
                            "block": [{**collision, "loop": ["{{ " + field + " }}"]}],
                            "rescue": [{"ansible.builtin.set_fact": {"fixture_collision": True}}],
                        },
                        {"ansible.builtin.assert": {"that": "fixture_collision"}},
                    ]
                )
            variables = {
                "ua_planner_reconcile": True,
                "ua_research_planner_tunnel_enabled": True,
                **dict.fromkeys(fields, occupied),
            }
            result = self.run_tasks(tasks, variables)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with socket.create_connection(("127.0.0.1", occupied), timeout=1):
                pass  # The unrelated listener survived every failed check.
            result = self.run_tasks(
                [collision], {**variables, "ua_research_planner_tunnel_enabled": False}
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("skipping:", result.stdout)

    def test_vector_health_is_bounded_tcp_only_and_conditional(self):
        health = yaml.safe_load((ROLE / "tasks/healthchecks_local.yml").read_text())
        task = next(t for t in health if "local vector forwards" in t["name"])
        self.assertEqual(task["when"], "ua_research_vector_enabled")
        self.assertEqual(
            task["loop"],
            [
                "{{ ua_research_planner_qdrant_local_port }}",
                "{{ ua_research_planner_embedding_local_port }}",
            ],
        )
        self.assertEqual(
            task["ansible.builtin.wait_for"],
            {
                "host": "127.0.0.1",
                "port": "{{ item }}",
                "state": "started",
                "connect_timeout": 2,
                "timeout": 30,
            },
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(8)
            result = self.run_tasks(
                [task],
                {
                    "ua_research_vector_enabled": True,
                    "ua_research_planner_qdrant_local_port": listener.getsockname()[1],
                    "ua_research_planner_embedding_local_port": listener.getsockname()[1],
                },
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_tasks([task], {"ua_research_vector_enabled": False})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("skipping:", result.stdout)

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
        self.assertIn("Require the local tunnel ports to be free", text)
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
