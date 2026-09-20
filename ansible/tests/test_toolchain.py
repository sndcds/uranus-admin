"""Offline synthetic artifacts only; no installer downloads or production paths."""

import copy
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from test_deployment import ANSIBLE, ROLE, load

MODULE = ROLE / "library/uranus_toolchain.py"
toolchain = load("managed_toolchain", MODULE)
CATALOG = json.loads((ROLE / "files/toolchain-pins.json").read_text())
MANIFEST = {p["tool"]: p["selector"] for p in CATALOG["packages"]}


class ToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.anchor = Path(self.temp.name)
        self.root = self.anchor / "toolchain"
        self.catalog = copy.deepcopy(CATALOG)
        self.archives = {}
        for pin in self.catalog["packages"]:
            name = "/".join(filter(None, [pin["prefix"], pin["binary"]]))
            version = {"python": "Python ", "uv": "uv ", "node": "v", "pnpm": ""}[
                pin["tool"]
            ] + pin["version"]
            self.archives[pin["tool"]] = self.archive(
                [(name, f'#!/bin/sh\necho "{version}"\n'.encode(), 0o755)]
            )
            pin["sha256"] = hashlib.sha256(self.archives[pin["tool"]]).hexdigest()

    def archive(self, files):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for name, data, mode in files:
                member = tarfile.TarInfo(name)
                member.size, member.mode = len(data), mode
                archive.addfile(member, io.BytesIO(data))
        return output.getvalue()

    def chain(self):
        return toolchain.Toolchain(
            self.root,
            self.catalog,
            MANIFEST,
            "x86_64",
            uid=os.getuid(),
            gid=os.getgid(),
            anchor=self.anchor,
        )

    def prepare(self):
        self.root.mkdir(mode=0o755)
        (self.root / "archives").mkdir(mode=0o755)
        for pin in self.catalog["packages"]:
            path = self.root / "archives" / (pin["directory"] + ".tar")
            path.write_bytes(self.archives[pin["tool"]])
            path.chmod(0o644)

    def snapshot(self):
        return {
            str(p.relative_to(self.anchor)): (p.lstat().st_mode, p.lstat().st_mtime_ns)
            for p in self.anchor.rglob("*")
        }

    def test_missing_plan_is_read_only(self):
        before = self.snapshot()
        self.assertEqual({p["tool"] for p in self.chain().inspect()}, set(MANIFEST))
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.root.exists())

    def test_install_all_exact_versions_and_idempotency(self):
        self.prepare()
        self.assertTrue(self.chain().install())
        before = self.snapshot()
        self.assertEqual(self.chain().inspect(), [])
        self.assertFalse(self.chain().install())
        self.assertEqual(before, self.snapshot())
        for path in self.chain().paths().values():
            self.assertTrue(Path(path).is_relative_to(self.root))
            self.assertEqual(stat.S_IMODE(Path(path).stat().st_mode), 0o755)

    def test_archive_hash_mismatch_aborts_before_extraction(self):
        self.prepare()
        self.chain().archive(self.catalog["packages"][0]).write_bytes(b"corruption")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            self.chain().install()
        self.assertEqual({p.name for p in self.root.iterdir()}, {"archives"})

    def test_tampered_binary_and_unknown_files_abort_without_repair(self):
        self.prepare()
        self.chain().install()
        binary = Path(self.chain().paths()["uv"])
        original = binary.read_bytes()
        binary.write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.chain().inspect()
        self.assertEqual(binary.read_bytes(), b"altered")
        binary.write_bytes(original)
        unknown = binary.parent / "injected"
        unknown.write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "Unexpected installed file"):
            self.chain().inspect()
        unknown.unlink()
        (self.root / "unknown-installation").mkdir()
        with self.assertRaisesRegex(ValueError, "Unknown toolchain"):
            self.chain().inspect()

    def test_binary_symlink_and_wrong_permissions_abort(self):
        self.prepare()
        self.chain().install()
        binary = Path(self.chain().paths()["node"])
        original = binary.read_bytes()
        binary.unlink()
        binary.symlink_to("/usr/bin/true")
        with self.assertRaisesRegex(ValueError, "file type or symlink"):
            self.chain().inspect()
        binary.unlink()
        binary.write_bytes(original)
        binary.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "Writable managed path"):
            self.chain().inspect()

    def test_owner_is_verified(self):
        self.prepare()
        chain = self.chain()
        chain.uid += 1
        with self.assertRaisesRegex(ValueError, "Wrong owner"):
            chain.inspect()

    def test_unknown_partial_installation_is_not_repaired(self):
        self.prepare()
        (self.root / self.catalog["packages"][0]["directory"]).mkdir(mode=0o755)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Incomplete installation"):
            self.chain().install()
        self.assertEqual(before, self.snapshot())

    def test_wrong_version_in_otherwise_verified_archive_aborts(self):
        pin = self.catalog["packages"][1]
        bad = self.archive(
            [(pin["prefix"] + "/" + pin["binary"], b'#!/bin/sh\necho "uv 0.12.50"\n', 0o755)]
        )
        pin["sha256"] = hashlib.sha256(bad).hexdigest()
        self.archives["uv"] = bad
        self.prepare()
        with self.assertRaisesRegex(ValueError, "Wrong uv version"):
            self.chain().install()

    def test_every_tool_rejects_a_different_reported_version(self):
        self.prepare()
        self.chain().install()
        wrong = {
            "python": "Python 3.12.15",
            "uv": "uv 0.12.10",
            "node": "v22.23.2",
            "pnpm": "12.3.5",
        }
        for pin in self.catalog["packages"]:
            result = subprocess.CompletedProcess([], 0, stdout=wrong[pin["tool"]], stderr="")
            with (
                self.subTest(tool=pin["tool"]),
                patch.object(toolchain.subprocess, "run", return_value=result),
            ):
                with self.assertRaisesRegex(ValueError, "Wrong .* version"):
                    self.chain().verify_version(pin)

    def test_missing_pins_wrong_architecture_and_bad_urls_fail_closed(self):
        for key, value in [
            ("sha256", ""),
            ("sha256", "0" * 64),
            ("url", "https://example.invalid/latest"),
        ]:
            catalog = copy.deepcopy(self.catalog)
            catalog["packages"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                toolchain.select_packages(catalog, MANIFEST, "x86_64")
        with self.assertRaisesRegex(ValueError, "Unsupported architecture"):
            toolchain.select_packages(self.catalog, MANIFEST, "aarch64")
        with self.assertRaisesRegex(ValueError, "unreviewed toolchain"):
            toolchain.select_packages(self.catalog, {**MANIFEST, "uv": "0.12.10"}, "x86_64")

    def test_parent_symlink_and_unwritable_target_are_rejected(self):
        self.root.symlink_to(self.anchor, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "file type or symlink"):
            self.chain().inspect()
        self.root.unlink()
        with (
            patch.object(os, "access", return_value=False),
            self.assertRaisesRegex(ValueError, "not writable"),
        ):
            self.chain().inspect()

    def test_unsafe_archive_members_are_rejected(self):
        self.prepare()
        for name in ("../escape", "/tmp/escape"):
            pin = self.catalog["packages"][0]
            data = self.archive([(name, b"unsafe", 0o755)])
            pin["sha256"] = hashlib.sha256(data).hexdigest()
            self.chain().archive(pin).write_bytes(data)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                self.chain().install()

    def test_real_ansible_check_mode_plans_without_downloads_or_writes(self):
        role = self.anchor / "roles/uranus_admin"
        shutil.copytree(ROLE, role)
        (role / "tasks/main.yml").write_text("- ansible.builtin.import_tasks: toolchain.yml\n")
        (role / "files/toolchain-pins.json").write_text(json.dumps(self.catalog))
        module = MODULE.read_text().replace(
            'ROOT = Path("/opt/uranus-admin/toolchain")', f"ROOT = Path({str(self.root)!r})"
        )
        module = module.replace(
            'runtime_user="oklab",',
            f"uid={os.getuid()}, gid={os.getgid()}, anchor=Path({str(self.anchor)!r}),",
        )
        (role / "library/uranus_toolchain.py").write_text(module)
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "ua_root": str(self.root.parent),
                    "ua_action": "deploy",
                    "ua_manifest": MANIFEST,
                },
                "roles": ["uranus_admin"],
            }
        ]
        path = self.anchor / "play.yml"
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
                "--diff",
            ],
            text=True,
            capture_output=True,
            env={**os.environ, "ANSIBLE_LOCAL_TEMP": str(self.anchor / "ansible-tmp")},
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.root.exists())
        self.assertIn("changed=0", result.stdout)
        for pin in self.catalog["packages"]:
            self.assertIn(
                pin["tool"] + " " + pin["version"] + " missing -> would install", result.stdout
            )

    def test_project_temp_base_does_not_require_postgres_home_writes(self):
        from configparser import ConfigParser

        config = ConfigParser()
        config.read(ANSIBLE / "ansible.cfg")
        self.assertEqual(config["defaults"]["remote_tmp"], "/tmp")

    def test_build_and_runtime_use_managed_paths_without_tool_download_fallback(self):
        release = yaml.safe_load((ROLE / "tasks/release.yml").read_text())
        guard = next(task for task in release if "different Python interpreter" in task["name"])
        self.assertIn("{{ ua_python }}", guard["ansible.builtin.command"]["argv"])
        self.assertIn("sys._base_executable", " ".join(guard["ansible.builtin.command"]["argv"]))
        self.assertFalse(guard["changed_when"])
        build = next(task["block"] for task in release if "block" in task)
        commands = [task for task in build if "ansible.builtin.command" in task]
        self.assertEqual(len(commands), 3)
        for task in commands:
            argv = task["ansible.builtin.command"]["argv"]
            self.assertIn(argv[0], ("{{ ua_uv }}", "{{ ua_pnpm }}"))
            self.assertEqual(task["environment"]["PATH"], "{{ ua_build_path }}")
            if argv[0] == "{{ ua_pnpm }}":
                self.assertIn("--pm-on-fail=error", argv)
                self.assertIn("--runtime-on-fail=error", argv)
                self.assertEqual(task["environment"]["HOME"], "/var/cache/uranus-admin-build")
            else:
                self.assertIn("{{ ua_python }}", argv)
                self.assertEqual(task["environment"]["UV_PYTHON_DOWNLOADS"], "never")
        self.assertIn(
            "ExecStart={{ ua_uv }} run --no-sync --offline --no-python-downloads",
            (ROLE / "templates/python.service.j2").read_text(),
        )
        self.assertIn(
            "ExecStart={{ ua_node }}", (ROLE / "templates/frontend.service.j2").read_text()
        )

    def test_task_order_isolation_and_no_database_or_recovery_access(self):
        preflight = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
        tc = next(
            i
            for i, t in enumerate(preflight)
            if t.get("ansible.builtin.import_tasks") == "toolchain.yml"
        )
        db = next(
            i for i, t in enumerate(preflight) if "community.postgresql.postgresql_query" in t
        )
        self.assertLess(tc, db)
        tasks = yaml.safe_load((ROLE / "tasks/toolchain.yml").read_text())
        provision = next(t for t in tasks if "block" in t)
        self.assertIn("not ansible_check_mode", provision["when"])
        self.assertIn("ua_action == 'deploy'", provision["when"])
        download = next(
            t["ansible.builtin.get_url"]
            for t in provision["block"]
            if "ansible.builtin.get_url" in t
        )
        self.assertEqual(download["checksum"], "sha256:{{ item.sha256 }}")
        self.assertTrue(download["validate_certs"])
        self.assertEqual(toolchain.ROOT, Path("/opt/uranus-admin/toolchain"))
        text = (ROLE / "tasks/toolchain.yml").read_text() + MODULE.read_text()
        for forbidden in ("community.postgresql", "psql", "alembic", "rescue:", "curl ", "shell:"):
            self.assertNotIn(forbidden, text)
        for task in provision["block"]:
            if "ansible.builtin.file" in task:
                self.assertTrue(all(p.startswith("{{ ua_root }}") for p in task["loop"]))
        defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
        for variable in ("ua_python", "ua_uv", "ua_node", "ua_pnpm"):
            self.assertNotIn(variable, defaults)
