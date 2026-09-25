#!/usr/bin/python
"""Verify the published Nitro tree has no dependency on removable build paths."""

import hashlib
import json
from pathlib import Path


def verify_output(value):
    root = Path(value)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Nitro output must be a real directory")
    root = root.resolve(strict=True)
    if not (root / "server/index.mjs").is_file():
        raise ValueError("Nitro server entrypoint is missing")
    if not (root / "public").is_dir():
        raise ValueError("Nitro public directory is missing")
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Nitro output has a link outside the standalone runtime tree")

        if path.is_file() and path.relative_to(root).as_posix() != "uranus-admin-build.json":
            if path.suffix == ".map" or any(
                p == ".git" or p == ".env" or p.startswith(".env.")
                for p in path.relative_to(root).parts
            ):
                raise ValueError("Forbidden runtime file")
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = json.loads((root / "uranus-admin-build.json").read_text())
    manifest = json.loads((root.parent.parent / "release.json").read_text())
    if metadata["files"] != files or metadata["commit"] != manifest["commit"]:
        raise ValueError("Installed frontend differs from its release build")


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={"path": {"type": "path", "required": True}},
        supports_check_mode=True,
    )
    try:
        verify_output(module.params["path"])
    except (OSError, ValueError, RuntimeError, KeyError):
        module.fail_json(
            msg="Nitro output is incomplete or references paths outside its runtime tree"
        )
    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
