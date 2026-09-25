"""Synthetic prebuilt Nitro output; never evidence of a real production build."""

import hashlib
import json
import subprocess
from pathlib import Path


def frontend_build(root, commit=None):
    commit = commit or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    output = Path(root) / "frontend/.output"
    (output / "server/node_modules/fixture").mkdir(parents=True, exist_ok=True)
    (output / "public").mkdir(exist_ok=True)
    files = {
        "server/index.mjs": b"// synthetic Nitro fixture",
        "public/favicon.ico": b"fixture",
        "server/node_modules/fixture/index.mjs": b"export default {}",
    }
    pnpm = json.loads(subprocess.check_output(["git", "show", commit + ":frontend/package.json"]))[
        "packageManager"
    ].removeprefix("pnpm@")
    for name, data in files.items():
        (output / name).write_bytes(data)
    metadata = {
        "commit": commit,
        "node": "22.22.3",
        "pnpm": pnpm,
        "platform": "linux-x64",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    (output / "uranus-admin-build.json").write_text(json.dumps(metadata))
    (Path(root) / "release.json").write_text(json.dumps({"commit": commit}))
    return output
