#!/usr/bin/env python3
"""Fetch and package latest origin/main; no working-tree files or secrets."""

import argparse
import ast
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path


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
            or not excluded
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
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if Path(args.output).exists():
        parser.error("Output already exists; choose a new artifact path")
    commit = latest_main()
    package(commit, args.output)


if __name__ == "__main__":
    main()
