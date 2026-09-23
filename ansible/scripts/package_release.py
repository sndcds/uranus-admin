#!/usr/bin/env python3
"""Fetch and package latest origin/main; no working-tree files or secrets."""

import argparse
import ast
import fcntl
import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path

ANSIBLE = Path(__file__).resolve().parents[1]
# Inventory host names are operator-defined; only direct hosts in this group apply.
LOCAL_ARTIFACT_PATHS = {
    "inventory.lxd.yml": ("all", "children", "uranus_admin", "hosts"),
    "approvals.local.yml": (),
    "inventory.local.yml": ("all", "children", "uranus_admin", "hosts"),
}


class ConfigurationError(Exception):
    """A diagnostic that never includes unrelated local configuration values."""


def yaml_parser():
    try:
        import yaml
    except ImportError:
        raise ConfigurationError(
            "Local updates require PyYAML from the existing controller requirements. "
            "Add --with-requirements ansible/requirements-controller.txt to uv run."
        ) from None
    return yaml


def artifact_changes(path, prefix, output, yaml):
    """Use YAML scalar source marks to preserve every unrelated byte, including comments."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ConfigurationError(f"{path.name}: expected an owned regular file, not a symlink")
    original = path.read_bytes()
    try:
        source = original.decode("utf-8")
        # Shared nodes could also change non-release values. Require explicit local values.
        if any(isinstance(t, (yaml.AliasToken, yaml.AnchorToken)) for t in yaml.scan(source)):
            raise ConfigurationError(f"{path.name}: YAML anchors/aliases are not supported")
        root = yaml.compose(source, Loader=yaml.SafeLoader)
    except (UnicodeError, yaml.YAMLError):
        raise ConfigurationError(f"{path.name}: invalid UTF-8 YAML") from None

    def mapping(node, key_path):
        label = ".".join(key_path) or "<root>"
        if not isinstance(node, yaml.MappingNode):
            raise ConfigurationError(f"{path.name}: expected mapping at {label}")
        result = {}
        for key, value in node.value:
            if key.tag != "tag:yaml.org,2002:str" or key.value in result:
                raise ConfigurationError(f"{path.name}: ambiguous YAML keys at {label}")
            result[key.value] = value
        return result

    def required(node, key_path, key):
        values = mapping(node, key_path)
        if key not in values:
            raise ConfigurationError(
                f"{path.name}: missing expected key {'.'.join((*key_path, key))}"
            )
        return values[key]

    node = root
    for index, key in enumerate(prefix):
        node = required(node, prefix[:index], key)
    hosts = mapping(node, prefix) if prefix else {None: node}
    if not hosts:
        raise ConfigurationError(f"{path.name}: expected at least one uranus_admin host")
    changes, replacements = [], []
    for host, host_node in hosts.items():
        key_path = (*prefix, host) if prefix else ()
        value = required(host_node, key_path, "ua_artifact")
        label = ".".join((*key_path, "ua_artifact"))
        if (
            not isinstance(value, yaml.ScalarNode)
            or value.tag != "tag:yaml.org,2002:str"
            or value.style not in (None, "'", '"')
        ):
            raise ConfigurationError(f"{path.name}: {label} must be an inline string")
        changes.append((label, value.value))
        if value.value == output:
            continue
        # A single quoted scalar is escaped according to YAML, not shell syntax.
        replacement = (
            "'" + output.replace("'", "''") + "'"
            if value.style == "'" and output.isprintable()
            else yaml.safe_dump(
                output, default_style='"', allow_unicode=False, width=float("inf")
            ).rstrip("\n")
        )
        replacements.append((value.start_mark.index, value.end_mark.index, replacement))
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    return path, original, source.encode("utf-8"), stat.S_IMODE(info.st_mode), changes


@contextmanager
def local_configuration_lock():
    # Share the deployment workflow's lock so approval changes cannot race an apply.
    path = ANSIBLE / "approvals.local.yml.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
        ):
            raise ConfigurationError("Unsafe local approval lock file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ConfigurationError(
                "Local approval configuration is in use; retry later"
            ) from None
        yield
    finally:
        os.close(fd)


def stage_configuration(path, content, mode):
    fd, name = tempfile.mkstemp(prefix=".package-release-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(content)
            target.flush()
            os.fchmod(target.fileno(), mode)
            os.fsync(target.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def replace_configurations(plans):
    """Stage every write and rollback copy before replacing the first destination."""
    staged, replaced, keep = [], [], set()
    try:
        for path, original, updated, mode, _ in plans:
            if original == updated:
                continue
            if not mode & 0o222 or not os.access(path, os.W_OK):
                raise ConfigurationError(f"{path.name}: file is not writable")
            backup = stage_configuration(path, original, mode)
            staged.append([path, backup, None])
            staged[-1][2] = stage_configuration(path, updated, mode)
        # Detect edits made while planning/staging, including non-cooperating editors.
        for path, original, _, mode, _ in plans:
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != mode
                or path.read_bytes() != original
            ):
                raise ConfigurationError(f"{path.name}: changed during preparation; retry")
        for path, backup, temporary in staged:
            os.replace(temporary, path)
            replaced.append((path, backup))
    except BaseException:
        for path, backup in reversed(replaced):
            try:
                os.replace(backup, path)
            except OSError:
                keep.add(backup)
                print(f"Rollback failed for {path}; original retained at {backup}", file=sys.stderr)
        raise
    finally:
        for _, backup, temporary in staged:
            for path in (backup, temporary):
                if path is not None and path not in keep:
                    path.unlink(missing_ok=True)


def update_local_inventories(output, dry_run=False):
    yaml = yaml_parser()
    try:
        with local_configuration_lock():
            plans = [
                artifact_changes(ANSIBLE / filename, prefix, str(output), yaml)
                for filename, prefix in LOCAL_ARTIFACT_PATHS.items()
            ]
            if not dry_run:
                replace_configurations(plans)
    except OSError as error:
        name = Path(error.filename).name if error.filename else "local configuration"
        raise ConfigurationError(
            f"{name}: cannot read, stage or replace local configuration"
        ) from None
    title = (
        "Planned local Ansible configuration changes"
        if dry_run
        else "Updated local Ansible configuration"
    )
    print(f"\n{title}:", file=sys.stderr)
    for path, _, _, _, changes in plans:
        for key, old in changes:
            status = "already up to date" if old == str(output) else f"{old!r} -> {str(output)!r}"
            print(f"  ansible/{path.name}: {key}: {status}", file=sys.stderr)
    print(f"\nRelease package:\n  {output}", file=sys.stderr)


def literal_assignment(source, name):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("Required release metadata missing")


def latest_main(repository=None):
    # Never fall back to a stale tracking ref or the currently checked-out branch.
    subprocess.run(
        ["git", "fetch", "--no-tags", "origin", "refs/heads/main"],
        cwd=repository,
        check=True,
    )
    return subprocess.check_output(
        ["git", "rev-parse", "--verify", "FETCH_HEAD^{commit}"],
        cwd=repository,
        text=True,
    ).strip()


def admin_indexes(source):
    """Inventory declared index names without executing code from the release."""
    names = {"alembic_version_pkc"}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "Index":
            names.add(ast.literal_eval(node.args[0]))
        elif node.func.attr == "Table":
            table = ast.literal_eval(node.args[0])
            names.add(table + "_pkey")
            for argument in node.args[2:]:
                if not isinstance(argument, ast.Call) or not isinstance(
                    argument.func, ast.Attribute
                ):
                    continue
                if argument.func.attr == "UniqueConstraint":
                    names.add(
                        next(
                            ast.literal_eval(k.value) for k in argument.keywords if k.arg == "name"
                        )
                    )
                elif argument.func.attr == "Column" and any(
                    k.arg == "unique" and ast.literal_eval(k.value) for k in argument.keywords
                ):
                    names.add(table + "_" + ast.literal_eval(argument.args[0]) + "_key")
    return sorted(names)


def admin_columns(source):
    columns = {"alembic_version": ["version_num"]}
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Table"
        ):
            columns[ast.literal_eval(node.args[0])] = sorted(
                ast.literal_eval(argument.args[0])
                for argument in node.args[2:]
                if isinstance(argument, ast.Call)
                and isinstance(argument.func, ast.Attribute)
                and argument.func.attr == "Column"
            )
    return columns


def package(revision, output):
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", revision + "^{commit}"], text=True
    ).strip()
    raw = subprocess.check_output(["git", "archive", "--format=tar", commit, "backend", "frontend"])
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as source:
        for member in source:
            parts = member.name.split("/")
            if not member.isfile() or any(
                p in {"tests", "docs", "node_modules", ".venv", ".git"}
                or p == ".env"
                or p.startswith(".env.")
                for p in parts
            ):
                continue
            backend = member.name.startswith(
                ("backend/app/", "backend/migrations/")
            ) or member.name in {"backend/alembic.ini", "backend/pyproject.toml", "backend/uv.lock"}
            frontend = member.name.startswith(
                ("frontend/app/", "frontend/server/", "frontend/shared/", "frontend/public/")
            ) or member.name in {
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
                "frontend/pnpm-workspace.yaml",
                "frontend/nuxt.config.ts",
                "frontend/tsconfig.json",
                "frontend/eslint.config.mjs",
            }
            if backend or frontend:
                files[member.name] = source.extractfile(member).read()
    required_release_sources = {
        "backend/app/admin_upgrade_contracts.py",
        "backend/app/admin_tables.py",
        "backend/app/auth/diagnostics.py",
        "backend/app/storage_preflight.py",
    }
    if not required_release_sources <= files.keys():
        raise ValueError(
            "Fetched main does not contain the required release database contracts; "
            "merge and fetch the complete controller/release change before packaging"
        )
    revisions = {}
    for name, data in files.items():
        if name.startswith("backend/migrations/versions/") and name.endswith(".py"):
            revisions[literal_assignment(data, "revision")] = literal_assignment(
                data, "down_revision"
            )
    heads = set(revisions) - set(revisions.values())
    if len(heads) != 1:
        raise ValueError("Release must have exactly one migration head")
    settings = ast.parse(files["backend/app/config.py"])
    keys = [
        n.target.id.upper()
        for cls in settings.body
        if isinstance(cls, ast.ClassDef) and cls.name == "Settings"
        for n in cls.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    ]
    manifest = {
        "commit": commit,
        "head": heads.pop(),
        "environment_keys": keys,
        "runtime_grants": literal_assignment(
            files["backend/app/storage_preflight.py"], "RUNTIME_GRANTS"
        ),
        "operator_grants": literal_assignment(
            files["backend/app/auth/diagnostics.py"], "OPERATOR_GRANTS"
        ),
        "admin_indexes": admin_indexes(files["backend/app/admin_tables.py"]),
        "admin_columns": admin_columns(files["backend/app/admin_tables.py"]),
        "python": "3.13",
        "node": "22.22.3",
        "uv": "0.12.5",
        "pnpm": json.loads(files["frontend/package.json"])["packageManager"].split("@")[-1],
    }
    upgrade_target = literal_assignment(
        files["backend/app/admin_upgrade_contracts.py"], "ADMIN_UPGRADE_TARGET"
    )
    upgrade_contracts = literal_assignment(
        files["backend/app/admin_upgrade_contracts.py"], "ADMIN_UPGRADE_CONTRACTS"
    )
    if upgrade_target != manifest["head"]:
        raise ValueError("Admin upgrade contracts must target the release migration head")
    manifest["admin_upgrade_contracts"] = {}
    for origin, contract in upgrade_contracts.items():
        excluded = set(contract["target_only_tables"])
        if (
            not isinstance(origin, str)
            or origin not in revisions
            or origin == manifest["head"]
            or not isinstance(contract["schema_fingerprint"], str)
            or len(contract["schema_fingerprint"]) != 64
            or not excluded < set(manifest["runtime_grants"])
        ):
            raise ValueError("Invalid admin upgrade contract")
        manifest["admin_upgrade_contracts"][origin] = {
            "schema_fingerprint": contract["schema_fingerprint"],
            "runtime_grants": {
                name: grants
                for name, grants in manifest["runtime_grants"].items()
                if name not in excluded
            },
        }
    files["release.json"] = json.dumps(manifest, sort_keys=True, indent=2).encode()
    with (
        open(output, "xb") as target,
        gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(Path(output).read_bytes()).hexdigest()
    print(
        json.dumps(
            {
                "ua_release_sha": commit,
                "ua_artifact": str(Path(output).resolve()),
                "ua_artifact_sha256": digest,
            },
            indent=2,
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", required=True, help="New archive path (~ and relative paths supported)"
    )
    parser.add_argument(
        "--update-local-inventories",
        action="store_true",
        help="Update ua_artifact in the local Ansible inventories and approval file; "
        "requires the controller requirements. Commit, checksum and approvals stay unchanged.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show local configuration changes without writing them (requires "
        "--update-local-inventories). The release archive is still created.",
    )
    args = parser.parse_args(argv)
    if args.dry_run and not args.update_local_inventories:
        parser.error("--dry-run requires --update-local-inventories")
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        parser.error("Output already exists; choose a new artifact path")
    if args.update_local_inventories:
        try:
            yaml_parser()
        except ConfigurationError as error:
            parser.error(str(error))
    commit = latest_main()
    package(commit, str(output))
    print(f"Release package created:\n  {output}", file=sys.stderr)
    if args.update_local_inventories:
        if not output.is_file() or output.stat().st_size == 0:
            parser.error(
                "Release archive was not successfully created; local configuration unchanged"
            )
        try:
            update_local_inventories(output, args.dry_run)
        except ConfigurationError as error:
            parser.error(str(error))
    else:
        print("\nLocal Ansible configuration was not modified.", file=sys.stderr)


if __name__ == "__main__":
    main()
