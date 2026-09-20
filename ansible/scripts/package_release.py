#!/usr/bin/env python3
"""Package committed application sources only; no working-tree files or secrets."""

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
        "python": "3.13",
        "node": "22.22.3",
        "uv": "0.12.5",
        "pnpm": json.loads(files["frontend/package.json"])["packageManager"].split("@")[-1],
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.output).exists():
        parser.error("Output already exists; choose a new artifact path")
    package(args.revision, args.output)
