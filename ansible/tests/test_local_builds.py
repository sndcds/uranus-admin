"""Local storage and bounded build retention; all mutations use disposable fixtures."""

import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml
from jinja2 import Environment
from release_fixture import frontend_build
from test_deployment import ROLE, load

storage = load("local_storage", ROLE / "library/uranus_local_storage.py")
retention = load("build_retention", ROLE / "library/uranus_build_retention.py")
frontend_output = load("frontend_output", ROLE / "library/uranus_frontend_output.py")


class LocalStorageTests(unittest.TestCase):
    def test_missing_targets_are_planned_without_creating_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = storage.inspect_paths([root / "missing/build"], 0, [(Path("/"), "ext4")])
            self.assertEqual(result[0]["type"], "ext4")
            self.assertEqual(list(root.iterdir()), [])

    def test_remote_and_unknown_filesystems_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in ("nfs", "nfs4", "cifs", "fuse.sshfs", "overlay", "tmpfs"):
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "Non-local"):
                    storage.inspect_paths([directory], 0, [(Path("/"), kind)])

    def test_symlink_ancestors_and_nested_mounts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "link").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Redirected"):
                storage.inspect_paths([root / "link/build"], 0, [(Path("/"), "ext4")])
            with self.assertRaisesRegex(ValueError, "nested mount"):
                storage.inspect_paths([root], 0, [(Path("/"), "ext4"), (root / "child", "nfs")])

    def test_low_space_and_read_only_mounts_abort_without_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            usage = SimpleNamespace(f_flag=0, f_bavail=1, f_frsize=4096)
            with patch.object(storage.os, "statvfs", return_value=usage):
                with self.assertRaisesRegex(ValueError, "No automatic cleanup"):
                    storage.inspect_paths([directory], 6442450944, [(Path("/"), "ext4")])
                usage.f_flag = os.ST_RDONLY
                with self.assertRaisesRegex(ValueError, "not writable"):
                    storage.inspect_paths([directory], 0, [(Path("/"), "ext4")])

    def test_mountinfo_decodes_paths_and_uses_longest_mount(self):
        mounts = storage.mounts_from_text(
            "1 0 8:0 / / rw - ext4 /dev/root rw\n"
            "2 1 0:9 / /opt/nfs\\040data rw - nfs server:/data rw\n"
        )
        self.assertEqual(mounts[1], (Path("/opt/nfs data"), "nfs"))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Non-local"):
                storage.inspect_paths(
                    [directory], 0, [(Path("/"), "ext4"), (Path(directory), "nfs")]
                )

    def test_storage_guard_precedes_downloads_and_database_and_paths_are_local(self):
        defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
        self.assertEqual(defaults["ua_root"], "/var/lib/uranus-admin")
        self.assertEqual(defaults["ua_build_root"], str(retention.ROOT))
        tasks = yaml.safe_load((ROLE / "tasks/preflight.yml").read_text())
        guard = next(i for i, task in enumerate(tasks) if "uranus_local_storage" in task)
        toolchain = next(
            i
            for i, task in enumerate(tasks)
            if task.get("ansible.builtin.import_tasks") == "toolchain.yml"
        )
        database = next(
            i for i, task in enumerate(tasks) if "community.postgresql.postgresql_query" in task
        )
        self.assertLess(guard, toolchain)
        self.assertLess(toolchain, database)


class BuildRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "builds"
        self.root.mkdir(mode=0o755)
        self.names = [f"{i:040x}" for i in range(1, 6)]
        for index, name in enumerate(self.names):
            directory = self.root / name
            directory.mkdir(mode=0o755)
            marker = directory / ".build-complete"
            marker.write_text("a" * 64 + "\n")
            marker.chmod(0o644)
            os.utime(marker, ns=(index + 1, index + 1))
            (directory / "artifact").write_text("fixture")

    def run_retention(self, check=False, current=None, mounts=()):
        return retention.Retention(self.root, current or self.names[-1]).run(check, mounts)

    def test_keep_three_and_idempotency(self):
        result = self.run_retention()
        self.assertEqual(set(result["removed"]), set(self.names[:2]))
        self.assertEqual(set(p.name for p in self.root.iterdir()), set(self.names[2:]))
        self.assertEqual(self.run_retention()["removed"], [])

    def test_check_mode_changes_nothing(self):
        before = {str(path): path.lstat().st_mtime_ns for path in self.root.rglob("*")}
        result = self.run_retention(check=True)
        self.assertEqual(set(result["would_remove"]), set(self.names[:2]))
        self.assertEqual(result["removed"], [])
        self.assertEqual(
            before, {str(path): path.lstat().st_mtime_ns for path in self.root.rglob("*")}
        )

    def test_current_older_build_and_incomplete_unknown_directories_survive(self):
        (self.root / ("f" * 40)).mkdir(mode=0o755)
        (self.root / "backups").mkdir()
        result = self.run_retention(current=self.names[0])
        self.assertEqual(result["removed"], [self.names[1]])
        self.assertEqual(result["skipped"], 2)
        self.assertTrue((self.root / self.names[0]).exists())
        self.assertTrue((self.root / ("f" * 40)).exists())
        self.assertTrue((self.root / "backups").exists())

    def test_symlink_inside_deleted_build_never_touches_external_data(self):
        external = Path(self.temp.name) / "runtime-release"
        external.mkdir()
        (external / "keep").write_text("protected")
        (self.root / self.names[0] / "outside").symlink_to(external, target_is_directory=True)
        self.run_retention()
        self.assertEqual((external / "keep").read_text(), "protected")

    def test_redirected_build_root_and_candidate_are_rejected(self):
        link = Path(self.temp.name) / "redirect"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            retention.Retention(link, self.names[-1]).run(False, [])
        (self.root / ("e" * 40)).symlink_to(Path(self.temp.name), target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_retention()
        self.assertTrue((self.root / self.names[0]).exists())

    def test_marker_symlink_and_fifo_are_rejected_before_any_removal(self):
        marker = self.root / self.names[0] / ".build-complete"
        marker.unlink()
        marker.symlink_to(self.root / self.names[1] / ".build-complete")
        with self.assertRaises(OSError):
            self.run_retention()
        marker.unlink()
        os.mkfifo(marker)
        with self.assertRaisesRegex(ValueError, "Invalid completed-build"):
            self.run_retention()
        self.assertTrue((self.root / self.names[0]).exists())

    def test_mounts_and_unsafe_permissions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "mounted"):
            self.run_retention(mounts=[self.root / self.names[0] / "mounted"])
        self.root.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "build-root"):
            self.run_retention()

    def test_wrong_owner_and_changed_candidate_abort(self):
        with patch.object(retention.os, "geteuid", return_value=os.geteuid() + 1):
            with self.assertRaisesRegex(ValueError, "owner"):
                self.run_retention()
        cleaner = retention.Retention(self.root, self.names[-1])
        original = cleaner.candidate
        reads = {}

        def changed(fd, name):
            result = original(fd, name)
            reads[name] = reads.get(name, 0) + 1
            return (*result[:2], 999, result[3]) if reads[name] > 1 else result

        with patch.object(cleaner, "candidate", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed during retention"):
                cleaner.run(False, [])
        self.assertEqual(len(list(self.root.iterdir())), 5)

    def test_module_check_mode_and_apply_use_only_fixture_builds(self):
        module = Path(self.temp.name) / "retention_fixture.py"
        source = (ROLE / "library/uranus_build_retention.py").read_text()
        source = source.replace(
            f'ROOT = Path("{retention.ROOT}")', f"ROOT = Path({str(self.root)!r})"
        )
        user = pwd.getpwuid(os.geteuid()).pw_name
        source = source.replace('pwd.getpwnam("oklab")', f"pwd.getpwnam({user!r})")
        module.write_text(source)
        for check, expected_changed in ((True, True), (False, True), (False, False)):
            result = subprocess.run(
                [sys.executable, str(module)],
                input=json.dumps(
                    {
                        "ANSIBLE_MODULE_ARGS": {
                            "current_release": self.names[-1],
                            "_ansible_check_mode": check,
                        }
                    }
                ),
                text=True,
                capture_output=True,
                check=True,
                timeout=30,
            )
            result = json.loads(result.stdout)
            self.assertEqual(result["changed"], expected_changed)
            self.assertEqual(len(list(self.root.iterdir())), 5 if check else 3)
            if check:
                self.assertEqual(result["removed"], [])
                self.assertEqual(len(result["would_remove"]), 2)

    def test_cleanup_runs_only_after_deploy_and_never_in_rescue(self):
        tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
        deploy = next(
            i
            for i, task in enumerate(tasks)
            if task.get("ansible.builtin.import_tasks") == "deploy.yml"
        )
        cleanup = next(i for i, task in enumerate(tasks) if "uranus_build_retention" in task)
        self.assertGreater(cleanup, deploy)
        self.assertEqual(tasks[cleanup]["become_user"], "oklab")
        self.assertIn("ua_action == 'deploy'", tasks[cleanup]["when"])
        for name in ("system_recovery.yml", "activate.yml"):
            self.assertNotIn("uranus_build_retention", (ROLE / "tasks" / name).read_text())


class BuildPublicationTests(unittest.TestCase):
    def test_nitro_output_rejects_external_build_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = frontend_build(root)
            frontend_output.verify_output(output)
            (output / "outside").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "outside"):
                frontend_output.verify_output(output)
            (output / "outside").unlink()
            (output / "server/index.mjs").write_text("// tampered")
            with self.assertRaisesRegex(ValueError, "differs"):
                frontend_output.verify_output(output)

    def test_legacy_predecessor_requires_own_output_but_not_format_two_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = frontend_build(directory)
            (output / "uranus-admin-build.json").unlink()
            (output / "server/old.map").write_text("legacy source map")
            frontend_output.verify_output(output, require_build_metadata=False)
            (output / "server/index.mjs").unlink()
            with self.assertRaisesRegex(ValueError, "entrypoint is missing"):
                frontend_output.verify_output(output, require_build_metadata=False)

    @unittest.skipUnless(shutil.which("uv"), "uv absent")
    def test_final_python_environment_survives_removing_build_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build, runtime = root / "build/backend", root / "runtime/backend"
            build.mkdir(parents=True)
            (build / "pyproject.toml").write_text(
                '[project]\nname="runtime-fixture"\nversion="0.0.0"\n'
                'requires-python=">=3.13"\ndependencies=[]\n[tool.uv]\npackage=false\n'
            )
            shutil.copytree(build, runtime)
            uv = shutil.which("uv")
            environment = {
                k: v
                for k, v in os.environ.items()
                if not k.startswith("UV_") and k != "VIRTUAL_ENV"
            }
            environment.update(UV_CACHE_DIR=str(root / "cache"), UV_PYTHON_DOWNLOADS="never")
            subprocess.run(
                [uv, "lock", "--offline", "--python", sys.executable],
                cwd=build,
                env=environment,
                check=True,
                capture_output=True,
                timeout=30,
            )
            shutil.copy(build / "uv.lock", runtime / "uv.lock")
            tasks = yaml.safe_load((ROLE / "tasks/release.yml").read_text())
            install = next(
                task
                for task in next(t["block"] for t in tasks if "block" in t)
                if "Python runtime dependencies" in task["name"]
            )
            values = {"ua_uv": uv, "ua_python": sys.executable}
            command = [
                Environment().from_string(arg).render(values)
                for arg in install["ansible.builtin.command"]["argv"]
            ]
            environment["UV_PROJECT_ENVIRONMENT"] = str(runtime / ".venv")
            subprocess.run(
                command, cwd=build, env=environment, check=True, capture_output=True, timeout=30
            )
            self.assertFalse((build / ".venv").exists())
            shutil.rmtree(build.parent)
            environment.pop("UV_PROJECT_ENVIRONMENT")
            result = subprocess.run(
                [
                    uv,
                    "run",
                    "--no-cache",
                    "--no-sync",
                    "--offline",
                    "--no-python-downloads",
                    "--no-env-file",
                    "python",
                    "-c",
                    "import sys; print(sys.prefix)",
                ],
                cwd=runtime,
                env=environment,
                check=True,
                capture_output=True,
                timeout=30,
                text=True,
            )
            self.assertEqual(result.stdout.strip(), str(runtime / ".venv"))


class NoTargetFrontendBuildTests(unittest.TestCase):
    def test_all_target_tasks_and_services_exclude_frontend_tooling(self):
        # Deliberately stronger than checking literal 'pnpm build': catches split
        # argv lists, templated ua_pnpm and new package-manager wrapper commands.
        import re

        for directory in ("tasks", "templates"):
            for path in (ROLE / directory).iterdir():
                if path.is_file():
                    with self.subTest(path=path):
                        self.assertIsNone(
                            re.search(r"\b(pnpm|npm|npx|nuxi|vite|tsc)\b|ua_pnpm", path.read_text())
                        )
        unit = (ROLE / "templates/frontend.service.j2").read_text()
        self.assertIn(
            "ExecStart={{ ua_node }} {{ ua_release_dir }}/frontend/.output/server/index.mjs", unit
        )
        for setting in (
            "User=oklab",
            "NITRO_HOST=127.0.0.1",
            "ProtectSystem=strict",
            "Restart=on-failure",
        ):
            self.assertIn(setting, unit)

    def test_check_mode_skips_release_preparation(self):
        tasks = yaml.safe_load((ROLE / "tasks/deploy.yml").read_text())
        release = next(t for t in tasks if t.get("ansible.builtin.import_tasks") == "release.yml")
        self.assertEqual(release["when"], "not ansible_check_mode")

    def test_recovery_restores_units_and_release_pointer_without_building(self):
        tasks = yaml.safe_load((ROLE / "tasks/system_recovery.yml").read_text())
        restore = next(
            t
            for t in tasks
            if t["name"] == "Restore previous managed file contents and permissions"
        )
        self.assertTrue(restore["ansible.builtin.copy"]["remote_src"])
        pointer = next(t for t in tasks if "previous release pointer if" in t["name"])
        self.assertEqual(
            pointer["ansible.builtin.file"]["src"], "{{ ua_previous_current.stat.lnk_target }}"
        )

    def test_release_workflow_builds_main_and_uploads_pinned_artifact(self):
        from test_deployment import ROOT

        workflow = yaml.safe_load((ROOT / ".github/workflows/release-artifact.yml").read_text())
        steps = workflow["jobs"]["release"]["steps"]
        checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["ref"], "main")
        node = next(s for s in steps if s.get("uses", "").startswith("actions/setup-node@"))
        self.assertEqual(node["with"]["node-version"], "22.22.3")
        build = next(s for s in steps if s.get("id") == "release")["run"]
        for required in ("build_release.py", "--expected-commit", "--verify", "--production-e2e"):
            self.assertIn(required, build)
        upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertIn(".tar.gz.sha256", upload["with"]["path"])
        self.assertNotIn("secrets.", json.dumps(workflow))
