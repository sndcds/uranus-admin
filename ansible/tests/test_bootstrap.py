"""Managed-object conflicts use temporary files; no target or database connection."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_target_contract
import yaml
from ansible.errors import AnsibleFilterError
from test_deployment import ROLE, filters, load

infrastructure = load("bootstrap_infrastructure", ROLE / "library/uranus_infrastructure.py")


class InfrastructureContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        paths = {
            name: str(self.root / getattr(infrastructure, name).lstrip("/"))
            for name in ("SITE", "LINK", "RATE", "LOGGING", "RECEIPT", "UNIT_ROOT", "LOG_DIRECTORY")
        }
        paths["SYSTEMD_ROOTS"] = tuple(
            str(self.root / p.lstrip("/")) for p in infrastructure.SYSTEMD_ROOTS
        )
        paths["PATHS"] = (
            paths["SITE"],
            paths["LOGGING"],
            paths["RATE"],
            *(paths["UNIT_ROOT"] + "/" + unit for unit in infrastructure.UNITS),
        )
        paths["OWNER"] = os.getuid()
        self.patcher = patch.multiple(infrastructure, **paths)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.candidates = [
            {"path": p, "content": "managed fixture " + Path(p).name + "\n", "mode": "0644"}
            for p in infrastructure.PATHS
        ]
        for item in self.candidates:
            path = Path(item["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item["content"])
            path.chmod(0o644)
        Path(infrastructure.LOG_DIRECTORY).mkdir(parents=True)
        Path(infrastructure.RECEIPT).parent.mkdir(parents=True)
        self.link = Path(infrastructure.LINK)
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(infrastructure.SITE)

    def plan(self, environment="test"):
        return infrastructure.inventory(environment, self.candidates, ["nginx.service"])

    def test_matching_objects_accepted_in_all_environments(self):
        for environment in ("production", "staging", "test"):
            with self.subTest(environment=environment):
                plan = self.plan(environment)
                self.assertEqual(plan["would_create"], [])
                self.assertFalse(plan["would_create_symlink"])
                self.assertFalse(plan["changed"])

    def test_missing_link_requires_production_baseline(self):
        self.link.unlink()
        with self.assertRaisesRegex(ValueError, "Production requires"):
            self.plan("production")
        for environment in ("test", "staging"):
            self.assertTrue(self.plan(environment)["would_create_symlink"])
        self.assertFalse(self.link.exists())

    def test_wrong_link_regular_file_and_directory_always_conflict(self):
        self.link.unlink()
        for kind in ("symlink", "file", "directory"):
            if kind == "symlink":
                self.link.symlink_to(self.root / "foreign")
            elif kind == "file":
                self.link.write_text("foreign site")
            else:
                self.link.mkdir()
            for environment in ("production", "staging", "test"):
                with (
                    self.subTest(kind=kind, environment=environment),
                    self.assertRaisesRegex(ValueError, "Conflicting Nginx"),
                ):
                    self.plan(environment)
            if kind == "directory":
                self.link.rmdir()
            else:
                self.link.unlink()

    def test_missing_site_rate_and_units_only_allowed_outside_production(self):
        for item in self.candidates:
            if item["path"] == infrastructure.LOGGING:
                continue  # Production already managed this optional snippet before bootstrap.
            path = Path(item["path"])
            path.unlink()
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Production requires"):
                self.plan("production")
            for environment in ("test", "staging"):
                self.assertIn(str(path), self.plan(environment)["would_create"])
            self.assertFalse(path.exists())
            path.write_text(item["content"])
            path.chmod(0o644)

    def test_existing_rate_conflicts_in_all_environments(self):
        path = Path(infrastructure.RATE)
        path.write_text("foreign zones")
        for environment in ("production", "staging", "test"):
            with (
                self.subTest(environment=environment),
                self.assertRaisesRegex(ValueError, "Rate-zone"),
            ):
                self.plan(environment)
        self.assertEqual(path.read_text(), "foreign zones")

    def test_foreign_files_symlinks_modes_and_dropins_block_bootstrap(self):
        for environment in ("test", "staging"):
            for item in self.candidates:
                path = Path(item["path"])
                path.write_text("foreign configuration")
                with (
                    self.subTest(path=path, environment=environment),
                    self.assertRaises(ValueError),
                ):
                    self.plan(environment)
                path.write_text(item["content"])
                path.chmod(0o666)
                with self.assertRaises(ValueError):
                    self.plan(environment)
                path.chmod(0o644)
            for name in ("service", "uranus-admin-.service", infrastructure.UNITS[0]):
                dropin = Path(infrastructure.UNIT_ROOT) / (name + ".d")
                dropin.mkdir()
                (dropin / "override.conf").write_text("foreign drop-in")
                with self.assertRaisesRegex(ValueError, "drop-ins"):
                    self.plan(environment)
                (dropin / "override.conf").unlink()
                dropin.rmdir()

    def test_receipt_allows_managed_upgrade_but_never_unreviewed_drift(self):
        initial = self.plan()
        receipt = Path(infrastructure.RECEIPT)
        receipt.write_text(initial["receipt"])
        receipt.chmod(0o600)
        self.candidates[0]["content"] = "reviewed new candidate"
        self.plan()
        installed = Path(self.candidates[0]["path"])
        installed.write_text("unreviewed edit")
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            self.plan()
        self.assertEqual(installed.read_text(), "unreviewed edit")
        receipt.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "Conflicting managed file"):
            self.plan()

    def test_receipt_rejects_unknown_paths(self):
        receipt = Path(infrastructure.RECEIPT)
        receipt.write_text(json.dumps({"/etc/foreign": "0" * 64}))
        receipt.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "Invalid managed infrastructure receipt"):
            self.plan()

    def test_missing_service_snapshot_only_allowed_for_managed_bootstrap_units(self):
        missing = {
            "item": infrastructure.UNITS[0],
            "stdout": "LoadState=not-found\nActiveState=inactive\nUnitFileState=",
        }
        nginx = {
            "item": "nginx.service",
            "stdout": "LoadState=loaded\nActiveState=active\nUnitFileState=enabled",
        }
        with self.assertRaises(AnsibleFilterError):
            filters.service_snapshot([missing, nginx], "production")
        for environment in ("test", "staging"):
            result = filters.service_snapshot([missing, nginx], environment)
            self.assertFalse(result[infrastructure.UNITS[0]]["exists"])
            with self.assertRaises(AnsibleFilterError):
                filters.service_snapshot([{**missing, "item": "nginx.service"}], environment)

    def test_https_origin_is_explicit_and_cannot_target_production_from_test(self):
        for environment in ("test", "staging"):
            self.assertTrue(
                filters.valid_target_origin("https://fixture.example.invalid", environment)
            )
            self.assertFalse(
                filters.valid_target_origin("https://admin.kulturbytes.de", environment)
            )
            for origin in (
                "http://fixture.example.invalid",
                "https://host/path",
                "https://user@host",
                "https://host;",
                "",
                None,
            ):
                self.assertFalse(filters.valid_target_origin(origin, environment))
        self.assertFalse(
            filters.valid_target_origin("https://fixture.example.invalid", "production")
        )

    def test_canonical_bootstrap_source_preserves_privileged_entries_without_legacy(self):
        config = Path(infrastructure.RECEIPT).parent
        source = config / "runtime.env"
        source.write_text(
            filters.render_environment(
                {
                    "DATABASE_URL": "postgresql+asyncpg://uranus_reader:fixture@localhost:5432/oklab",
                    "ADMIN_DATABASE_URL": "postgresql+asyncpg://admin_user:fixture@localhost:5432/oklab",
                    "SQL_CONSOLE_DATABASE_URL": "postgresql+asyncpg://uranus_console_reader:long-synthetic-fixture-password@localhost:5432/oklab",
                    "ADMIN_MIGRATION_DATABASE_URL": "privileged-fixture-only",
                }
            )
        )
        source.chmod(0o600)
        content = (ROLE / "tasks/environment_plan.yml").read_text()
        content = content.replace(".stat.uid == 0", f".stat.uid == {os.getuid()}")
        content = content.replace(".stat.gid == 0", f".stat.gid == {os.getgid()}")
        tasks = yaml.safe_load(content)
        missing_source_guard = next(t for t in tasks if t["name"].startswith("Require an explicit"))
        runner = test_target_contract.TargetContractTests("test_production_is_default")
        runner.run_cases(
            [
                ("canonical test source", "host123", {"ua_target_environment": "test"}, None),
                (
                    "production needs legacy adoption",
                    "staging-admin",
                    {},
                    missing_source_guard["ansible.builtin.assert"]["fail_msg"],
                ),
            ],
            extra_tasks=[
                {
                    "ansible.builtin.set_fact": {
                        "ua_config_dir": str(config),
                        "ua_legacy_root": str(self.root / "absent-legacy"),
                        "ua_manifest": {
                            "environment_keys": [
                                "DATABASE_URL",
                                "ADMIN_DATABASE_URL",
                                "SQL_CONSOLE_DATABASE_URL",
                            ]
                        },
                    }
                },
                *tasks,
                {
                    "ansible.builtin.assert": {
                        "that": [
                            "'ADMIN_MIGRATION_DATABASE_URL' not in ua_runtime",
                            "ua_privileged.ADMIN_MIGRATION_DATABASE_URL "
                            "== 'privileged-fixture-only'",
                            "ua_runtime.AUTH_PUBLIC_ORIGIN == ua_public_origin",
                        ]
                    },
                    "no_log": True,
                },
            ],
        )
        self.assertIn("privileged-fixture-only", source.read_text())
