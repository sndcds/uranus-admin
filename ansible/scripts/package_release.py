#!/usr/bin/env python3
"""Package latest origin/main with a verified prebuilt frontend; never run a build."""

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
LOCAL_RELEASE_PATHS = {
    "inventory.lxd.yml": ("all", "children", "uranus_admin", "hosts"),
    "approvals.local.yml": (),
    "inventory.local.yml": ("all", "children", "uranus_admin", "hosts"),
}
RELEASE_KEYS = ("ua_release_sha", "ua_artifact", "ua_artifact_sha256")


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


def release_pin_changes(path, prefix, release_values, yaml):
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
        for key in RELEASE_KEYS:
            value = required(host_node, key_path, key)
            label = ".".join((*key_path, key))
            if (
                not isinstance(value, yaml.ScalarNode)
                or value.tag != "tag:yaml.org,2002:str"
                or value.style not in (None, "'", '"')
                or value.start_mark.line != value.end_mark.line
            ):
                raise ConfigurationError(f"{path.name}: {label} must be an inline string")
            new = release_values[key]
            changes.append((label, value.value, new))
            if value.value == new:
                continue
            # A single quoted scalar is escaped according to YAML, not shell syntax.
            replacement = (
                "'" + new.replace("'", "''") + "'"
                if value.style == "'" and new.isprintable()
                else yaml.safe_dump(
                    new, default_style='"', allow_unicode=False, width=float("inf")
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


def update_local_inventories(release_values, dry_run=False):
    yaml = yaml_parser()
    try:
        with local_configuration_lock():
            plans = [
                release_pin_changes(ANSIBLE / filename, prefix, release_values, yaml)
                for filename, prefix in LOCAL_RELEASE_PATHS.items()
            ]
            if not dry_run:
                replace_configurations(plans)
    except OSError as error:
        name = Path(error.filename).name if error.filename else "local configuration"
        raise ConfigurationError(
            f"{name}: cannot read, stage or replace local configuration"
        ) from None
    title = (
        "Planned local Ansible release pin changes"
        if dry_run
        else "Updated local Ansible release pins"
    )
    print(f"\n{title}:", file=sys.stderr)
    for path, _, _, _, changes in plans:
        print(f"  ansible/{path.name}:", file=sys.stderr)
        for key, old, new in changes:
            status = "already up to date" if old == new else f"{old!r} -> {new!r}"
            print(f"    {key}:\n      {status}", file=sys.stderr)
    print(f"\nRelease package:\n  {release_values['ua_artifact']}", file=sys.stderr)


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


NODE_VERSION = "22.22.3"
BUILD_METADATA = "uranus-admin-build.json"
ENTRYPOINT = "frontend/.output/server/index.mjs"


def frontend_files(output):
    """Read only the standalone runtime tree; never follow links or package source deps."""
    root = Path(output)
    if (
        root.is_symlink()
        or not (root / "server/index.mjs").is_file()
        or not (root / "public").is_dir()
    ):
        raise ValueError(
            "Frontend production build missing. "
            "Run build_release.py on the build host before packaging."
        )
    files = {}
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if (
            path.is_symlink()
            or any(
                part in {".git", ".env", ".npmrc", ".pnpmrc"} or part.startswith(".env.")
                for part in parts
            )
            or path.suffix in {".map", ".pem", ".key"}
        ):
            raise ValueError("Unsafe frontend build member (links, secrets or source maps)")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Frontend build contains a special file")
        files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def verified_frontend(output, commit, pnpm):
    files = frontend_files(output)
    try:
        metadata = json.loads(files.pop(BUILD_METADATA))
    except (KeyError, ValueError):
        raise ValueError("Frontend build metadata missing; run the release build first") from None
    expected = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    if (
        metadata.get("commit") != commit
        or metadata.get("node") != NODE_VERSION
        or metadata.get("pnpm") != pnpm
        or metadata.get("platform") != "linux-x64"
        or metadata.get("files") != expected
    ):
        raise ValueError(
            "Stale or modified frontend build: commit, toolchain or file hashes do not match"
        )
    files[BUILD_METADATA] = json.dumps(metadata, sort_keys=True, indent=2).encode()
    return {"frontend/.output/" + name: data for name, data in files.items()}


def package(revision, output, frontend_output=None):
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
            if backend:
                files[member.name] = source.extractfile(member).read()
    pnpm = json.loads(subprocess.check_output(["git", "show", commit + ":frontend/package.json"]))[
        "packageManager"
    ].removeprefix("pnpm@")
    files.update(verified_frontend(frontend_output or "frontend/.output", commit, pnpm))
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
        "format_version": 2,
        "frontend_build": {
            "kind": "nuxt-nitro",
            "entrypoint": ENTRYPOINT,
            "commit": commit,
            "node": NODE_VERSION,
            "pnpm": pnpm,
            "platform": "linux-x64",
        },
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
        "node": NODE_VERSION,
        "uv": "0.12.5",
        "pnpm": pnpm,
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
        public = tarfile.TarInfo("frontend/.output/public")
        public.type, public.mode, public.mtime = tarfile.DIRTYPE, 0o755, 0
        archive.addfile(public)
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(Path(output).read_bytes()).hexdigest()
    with Path(str(output) + ".sha256").open("x") as checksum:
        name = Path(output).name
        escaped = name.replace("\\", "\\\\").replace("\n", "\\n")
        checksum.write(("\\" if escaped != name else "") + digest + "  " + escaped + "\n")
    release_values = {
        "ua_release_sha": commit,
        "ua_artifact": str(Path(output).resolve()),
        "ua_artifact_sha256": digest,
    }
    print(json.dumps(release_values, indent=2))
    return release_values


def main(argv=None, build=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", required=True, help="New archive path (~ and relative paths supported)"
    )
    parser.add_argument(
        "--update-local-inventories",
        action="store_true",
        help="Update the local Ansible release pins (ua_release_sha, ua_artifact and "
        "ua_artifact_sha256); requires the controller requirements. Commit, checksum and "
        "artifact path are synchronized. Approval decisions remain unchanged.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show local configuration changes without writing them (requires "
        "--update-local-inventories). The release archive is still created.",
    )
    parser.add_argument(
        "--frontend-output",
        help="Verified .output from build_release.py (never built by packaging)",
    )
    parser.add_argument("--expected-commit", help="Abort if fetched main moved since CI checkout")
    if build:
        parser.add_argument(
            "--production-e2e",
            action="store_true",
            help="Run production E2E using the CI-pinned Playwright Docker image",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Run frontend lint, typecheck and unit tests in the clean build checkout",
        )
    args = parser.parse_args(argv)
    if args.dry_run and not args.update_local_inventories:
        parser.error("--dry-run requires --update-local-inventories")
    output = Path(args.output).expanduser().resolve()
    if any(p.exists() or p.is_symlink() for p in (output, Path(str(output) + ".sha256"))):
        parser.error("Output or checksum already exists; choose a new artifact path")
    if args.update_local_inventories:
        try:
            yaml_parser()
        except ConfigurationError as error:
            parser.error(str(error))
    commit = latest_main()
    if args.expected_commit and args.expected_commit != commit:
        parser.error("Latest main moved since checkout; restart with the new main commit")
    if build:
        if args.frontend_output:
            parser.error("build_release.py always creates its own clean frontend build")
        from build_release import build_frontend

        with tempfile.TemporaryDirectory(prefix="uranus-release-") as directory:
            frontend = build_frontend(
                commit, Path(directory), verify=args.verify, production_e2e=args.production_e2e
            )
            release_values = package(commit, str(output), frontend)
    elif args.frontend_output:
        release_values = package(commit, str(output), args.frontend_output)
    else:
        release_values = package(commit, str(output))
    print(f"Release package created:\n  {output}", file=sys.stderr)
    if args.update_local_inventories:
        if not output.is_file() or output.stat().st_size == 0:
            parser.error(
                "Release archive was not successfully created; local configuration unchanged"
            )
        try:
            update_local_inventories(release_values, args.dry_run)
        except ConfigurationError as error:
            parser.error(str(error))
    else:
        print("\nLocal Ansible configuration was not modified.", file=sys.stderr)


if __name__ == "__main__":
    main()
