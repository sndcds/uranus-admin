"""Release packaging and narrowly scoped, transactional local release pin updates."""

import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "package_release", ROOT / "ansible/scripts/package_release.py"
)
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)

# Deliberately repeat the old value in unrelated keys. Only the selected release scalars may change.
INVENTORY = """# Keep inventory comments and formatting.
all:
  vars:
    ua_artifact: '/tmp/old.tar.gz' # unrelated scope
  children:
    uranus_admin:
      hosts:
        HOST:
          ua_release_sha: 'old-commit'
          ua_artifact: '/tmp/old.tar.gz' # release comment
          ua_artifact_sha256: 'old-checksum'
          ua_backup_reference: '/tmp/old.tar.gz'
    unrelated:
      hosts:
        elsewhere:
          ua_artifact: '/tmp/old.tar.gz'
"""
APPROVALS = """# Keep the reviewed approval decisions.
ua_release_sha: "old-commit"
ua_artifact: "/tmp/old.tar.gz" # approval comment
ua_artifact_sha256: "old-checksum"
ua_reviewed_dry_run: "existing review"
ua_apply_confirmation: "existing confirmation"
ua_backup_reference: "/tmp/old.tar.gz"
ua_maintenance_window: 'reviewed window' # preserve this comment
ua_secret_adoption_approved: false
ua_admin_database_bootstrap_approved: true
ua_admin_database_upgrade_approved: false
ua_disable_notification_timer_approved: true
ua_manage_notification_timer: false
ua_sql_console_provision_approved: false
"""


class LocalReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.ansible = self.root / "ansible"
        self.ansible.mkdir()
        self.output = self.root / "release.tar.gz"
        self.paths = [self.ansible / name for name in packager.LOCAL_RELEASE_PATHS]
        for path, text in zip(
            self.paths,
            (
                INVENTORY.replace("HOST", "uranus-admin-test"),
                APPROVALS,
                INVENTORY.replace("HOST", "webserver"),
            ),
            strict=True,
        ):
            path.write_text(text)
            path.chmod(0o600 if path.name == "approvals.local.yml" else 0o640)
        self.enterContext(patch.object(packager, "ANSIBLE", self.ansible))
        self.latest = self.enterContext(
            patch.object(packager, "latest_main", return_value=self.commit)
        )
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.stdout))
        self.enterContext(contextlib.redirect_stderr(self.stderr))

    def run_cli(self, *options, output=None):
        packager.main(["--output", str(output or self.output), *options])

    def snapshot(self):
        return [
            (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino, stat.S_IMODE(p.stat().st_mode))
            for p in self.paths
        ]

    def assert_archive(self):
        with tarfile.open(self.output) as archive:
            self.assertEqual(json.load(archive.extractfile("release.json"))["commit"], self.commit)

    @property
    def pins(self):
        return {
            "ua_release_sha": self.commit,
            "ua_artifact": str(self.output),
            "ua_artifact_sha256": "b" * 64,
        }

    def generated_pins(self):
        with contextlib.redirect_stdout(io.StringIO()):
            values = packager.package(self.commit, self.root / "reference.tar.gz")
        return {**values, "ua_artifact": str(self.output)}

    def assert_pins_updated(self):
        expected = json.loads(self.stdout.getvalue()) if self.stdout.getvalue() else self.pins
        for path, host in zip(self.paths, ("uranus-admin-test", None, "webserver"), strict=True):
            document = yaml.safe_load(path.read_text())
            values = (
                document["all"]["children"]["uranus_admin"]["hosts"][host] if host else document
            )
            self.assertEqual({key: values[key] for key in packager.RELEASE_KEYS}, expected)
        if self.output.exists():
            self.assertEqual(expected["ua_release_sha"], self.commit)
            self.assertEqual(
                expected["ua_artifact_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest()
            )

    def expected_bytes(self, path, original, pins):
        quote, indent = ('"', "") if path.name == "approvals.local.yml" else ("'", "          ")
        for key, old in (
            ("ua_release_sha", "old-commit"),
            ("ua_artifact", "/tmp/old.tar.gz"),
            ("ua_artifact_sha256", "old-checksum"),
        ):
            original = original.replace(
                f"{indent}{key}: {quote}{old}{quote}".encode(),
                f"{indent}{key}: {quote}{pins[key]}{quote}".encode(),
                1,
            )
        return original

    def test_without_flag_creates_archive_without_loading_yaml_or_touching_configuration(self):
        before = self.snapshot()
        with patch.object(
            packager, "yaml_parser", side_effect=AssertionError("unexpected YAML load")
        ):
            self.run_cli()
        self.assert_archive()
        self.assertEqual(self.snapshot(), before)
        self.assertIn("Local Ansible configuration was not modified", self.stderr.getvalue())
        # Existing machine-readable stdout remains a single JSON document.
        self.assertEqual(json.loads(self.stdout.getvalue())["ua_artifact"], str(self.output))

    def test_flag_updates_only_release_pins_and_preserves_approvals_permissions_and_comments(self):
        before = self.snapshot()
        self.run_cli("--update-local-inventories")
        self.assert_archive()
        self.assert_pins_updated()
        pins = json.loads(self.stdout.getvalue())
        self.assertEqual(set(pins), set(packager.RELEASE_KEYS))
        for path, (original, _, _, mode) in zip(self.paths, before, strict=True):
            self.assertEqual(path.read_bytes(), self.expected_bytes(path, original, pins))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
            self.assertIn(f"ansible/{path.name}", self.stderr.getvalue())
        self.assertEqual(list(self.ansible.glob(".package-release-*")), [])

    def test_identical_values_do_not_rewrite_files(self):
        packager.update_local_inventories(self.generated_pins())
        before = self.snapshot()
        with patch.object(packager, "stage_configuration", side_effect=AssertionError("rewrite")):
            self.run_cli("--update-local-inventories")
        self.assert_archive()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.stderr.getvalue().count("already up to date"), 9)

    def test_only_stale_checksum_scalar_is_rewritten(self):
        pins = self.generated_pins()
        packager.update_local_inventories(pins)
        path = self.paths[1]
        path.write_bytes(
            path.read_bytes().replace(pins["ua_artifact_sha256"].encode(), b"stale-checksum")
        )
        before = self.snapshot()
        self.run_cli("--update-local-inventories")
        self.assert_pins_updated()
        after = self.snapshot()
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[2], before[2])
        self.assertEqual(
            path.read_bytes(),
            before[1][0].replace(b"stale-checksum", pins["ua_artifact_sha256"].encode()),
        )

    def test_missing_key_in_last_file_changes_none(self):
        self.paths[-1].write_text(self.paths[-1].read_text().replace("ua_artifact:", "wrong_key:"))
        before = self.snapshot()
        with self.assertRaises(SystemExit):
            self.run_cli("--update-local-inventories")
        self.assert_archive()
        self.assertEqual(self.snapshot(), before)
        self.assertIn("inventory.local.yml: missing expected key", self.stderr.getvalue())
        self.assertIn(
            "all.children.uranus_admin.hosts.webserver.ua_artifact", self.stderr.getvalue()
        )

    def test_failed_archive_leaves_configuration_unchanged(self):
        before = self.snapshot()
        with patch.object(packager.tarfile.TarFile, "addfile", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.run_cli("--update-local-inventories")
        self.assertEqual(self.snapshot(), before)

    def test_fetch_failure_leaves_configuration_unchanged(self):
        self.latest.side_effect = subprocess.CalledProcessError(1, "git")
        before = self.snapshot()
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_cli("--update-local-inventories")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.output.exists())

    def test_unwritable_last_file_changes_none(self):
        self.paths[-1].chmod(0o400)
        before = self.snapshot()
        with self.assertRaises(SystemExit):
            self.run_cli("--update-local-inventories")
        self.assert_archive()
        self.assertEqual(self.snapshot(), before)
        self.assertIn("inventory.local.yml: file is not writable", self.stderr.getvalue())
        self.assertEqual(list(self.ansible.glob(".package-release-*")), [])

    def test_staging_failure_changes_none(self):
        before = self.snapshot()
        original = packager.stage_configuration

        def stage(path, content, mode):
            if path == self.paths[-1]:
                raise PermissionError(13, "denied", str(path))
            return original(path, content, mode)

        with patch.object(packager, "stage_configuration", side_effect=stage):
            with self.assertRaises(packager.ConfigurationError):
                packager.update_local_inventories(self.pins)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.ansible.glob(".package-release-*")), [])

    def test_replace_failure_rolls_back_already_updated_files(self):
        before = self.snapshot()
        replace = os.replace

        def fail_last(source, destination):
            if destination == self.paths[-1]:
                raise PermissionError(13, "denied", str(destination))
            replace(source, destination)

        with patch.object(packager.os, "replace", side_effect=fail_last):
            with self.assertRaises(packager.ConfigurationError):
                packager.update_local_inventories(self.pins)
        for path, (original, _, _, mode) in zip(self.paths, before, strict=True):
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
        self.assertEqual(list(self.ansible.glob(".package-release-*")), [])

    def test_dry_run_creates_archive_and_prints_changes_without_rewriting(self):
        before = self.snapshot()
        with patch.object(packager, "stage_configuration", side_effect=AssertionError("write")):
            self.run_cli("--update-local-inventories", "--dry-run")
        self.assert_archive()
        self.assertEqual(self.snapshot(), before)
        self.assertIn("Planned local Ansible release pin changes", self.stderr.getvalue())
        self.assertIn("'/tmp/old.tar.gz' ->", self.stderr.getvalue())
        pins = json.loads(self.stdout.getvalue())
        for key, value in pins.items():
            self.assertEqual(self.stderr.getvalue().count(f"{key}:"), 3)
            self.assertIn(repr(value), self.stderr.getvalue())

    def test_dry_run_requires_update_flag(self):
        with self.assertRaises(SystemExit):
            self.run_cli("--dry-run")
        self.latest.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_relative_output_is_stored_as_absolute_path(self):
        self.run_cli("--update-local-inventories", output=os.path.relpath(self.output))
        self.assert_archive()
        self.assert_pins_updated()

    def test_tilde_output_is_expanded_for_archive_and_yaml(self):
        # Isolate the home directory lookup without changing the process environment.
        expand = os.path.expanduser
        with patch(
            "os.path.expanduser",
            side_effect=lambda p: (
                str(self.root) + p[1:] if p == "~" or p.startswith("~/") else expand(p)
            ),
        ):
            self.run_cli("--update-local-inventories", output="~/release.tar.gz")
        self.assert_archive()
        self.assert_pins_updated()

    def test_paths_with_yaml_special_characters_round_trip(self):
        self.output = self.root / "release 'quoted' ü😀: #.tar.gz"
        self.run_cli("--update-local-inventories")
        self.assert_archive()
        self.assert_pins_updated()

    def test_missing_pin_in_any_file_changes_none(self):
        for path in self.paths:
            original = path.read_bytes()
            for key in packager.RELEASE_KEYS:
                with self.subTest(file=path.name, key=key):
                    path.write_bytes(original.replace(f"{key}:".encode(), f"wrong_{key}:".encode()))
                    before = self.snapshot()
                    with self.assertRaisesRegex(
                        packager.ConfigurationError, f"missing expected key .*{key}"
                    ):
                        packager.update_local_inventories(self.pins)
                    self.assertEqual(self.snapshot(), before)
            path.write_bytes(original)

    def test_invalid_or_ambiguous_pin_fails_without_leaking_values(self):
        for key in packager.RELEASE_KEYS:
            for value in (
                "[sensitive-unrelated-value",
                "[sensitive-unrelated-value]",
                "{nested: sensitive-unrelated-value}",
                "123",
                "| # retain comments\n  sensitive-unrelated-value",
                ">\n  sensitive-unrelated-value",
                "'sensitive-unrelated-value\n  continued'",
                f"one\n{key}: sensitive-unrelated-value",
                "&shared sensitive-unrelated-value\nother: *shared",
                "*shared",
            ):
                with self.subTest(key=key, value=value):
                    text = yaml.safe_dump({k: v for k, v in self.pins.items() if k != key})
                    self.paths[1].write_text(text + f"{key}: {value}\n")
                    before = self.snapshot()
                    with self.assertRaises(packager.ConfigurationError) as error:
                        packager.update_local_inventories(self.pins)
                    self.assertNotIn("sensitive-unrelated-value", str(error.exception))
                    self.assertEqual(self.snapshot(), before)

    def test_symlink_is_rejected_without_modifying_target(self):
        original = self.paths[1].read_bytes()
        target = self.root / "other.yml"
        self.paths[1].rename(target)
        self.paths[1].symlink_to(target)
        with self.assertRaisesRegex(packager.ConfigurationError, "not a symlink"):
            packager.update_local_inventories(self.pins)
        self.assertEqual(target.read_bytes(), original)

    def test_existing_deployment_lock_blocks_update(self):
        before = self.snapshot()
        lock = self.ansible / "approvals.local.yml.lock"
        lock.touch(mode=0o600)
        with lock.open("r+") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(packager.ConfigurationError, "in use"):
                packager.update_local_inventories(self.pins)
        self.assertEqual(self.snapshot(), before)

    def test_crlf_and_unicode_outside_path_are_unchanged(self):
        self.paths[1].write_bytes(("# Grüße\n" + APPROVALS).replace("\n", "\r\n").encode())
        before = self.paths[1].read_bytes()
        packager.update_local_inventories(self.pins)
        self.assertEqual(
            self.paths[1].read_bytes(),
            self.expected_bytes(self.paths[1], before, self.pins),
        )

    def test_unicode_line_separators_in_paths_are_escaped(self):
        self.output = self.root / "release\u0085\u2028\u2029.tar.gz"
        packager.update_local_inventories(self.pins)
        self.assert_pins_updated()

    def test_multiple_hosts_in_selected_group_are_updated(self):
        text = (
            self.paths[0]
            .read_text()
            .replace(
                "    unrelated:",
                "        second-host:\n          ua_artifact: /tmp/second.tar.gz\n"
                "          ua_release_sha: 'older-commit'\n"
                "          ua_artifact_sha256: 'older-checksum'\n    unrelated:",
            )
        )
        self.paths[0].write_text(text)
        packager.update_local_inventories(self.pins)
        hosts = yaml.safe_load(self.paths[0].read_text())["all"]["children"]["uranus_admin"][
            "hosts"
        ]
        for host in hosts.values():
            self.assertEqual({key: host[key] for key in packager.RELEASE_KEYS}, self.pins)

    def test_stale_approval_override_is_synchronized_with_generated_pins(self):
        pins = self.generated_pins()
        packager.update_local_inventories(pins)
        approvals = self.paths[1]
        approvals.write_bytes(
            approvals.read_bytes()
            .replace(pins["ua_release_sha"].encode(), b"0" * 40)
            .replace(pins["ua_artifact_sha256"].encode(), b"0" * 64)
        )
        self.run_cli("--update-local-inventories")
        self.assert_pins_updated()
        effective = subprocess.run(
            [
                sys.executable,
                "-m",
                "ansible.cli.inventory",
                "-i",
                str(self.paths[2]),
                "--host",
                "webserver",
                "-e",
                "@" + str(approvals),
            ],
            env={**os.environ, "ANSIBLE_LOCAL_TEMP": str(self.root / "ansible-tmp")},
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        values = json.loads(effective.stdout)
        self.assertEqual(
            {key: values[key] for key in packager.RELEASE_KEYS}, json.loads(self.stdout.getvalue())
        )

    def test_cli_uses_returned_package_metadata_without_recomputing(self):
        original_package = packager.package
        with patch.object(packager, "package", wraps=original_package) as package:
            with patch.object(packager, "update_local_inventories") as update:
                self.run_cli("--update-local-inventories")
        package.assert_called_once_with(self.commit, str(self.output))
        update.assert_called_once_with(json.loads(self.stdout.getvalue()), False)


if __name__ == "__main__":
    unittest.main()
