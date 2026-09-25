#!/usr/bin/python
"""Verify the published Nitro tree has no dependency on removable build paths."""

import hashlib
import json
from pathlib import Path


def verify_output(value, require_build_metadata=True):
    root = Path(value)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Nitro output must be a real directory")
    root = root.resolve(strict=True)
    if (root / "server").is_symlink() or (root / "server/index.mjs").is_symlink():
        raise ValueError("Nitro runtime entrypoint must belong to this release")
    if not (root / "server/index.mjs").is_file():
        raise ValueError("Nitro server entrypoint is missing")
    if (root / "public").is_symlink() or not (root / "public").is_dir():
        raise ValueError("Nitro public directory is missing")
    # Installed predecessors can predate format 2 and contain source maps.
    # They need their own existing runtime, never a rebuild during recovery.
    if not require_build_metadata:
        return
    files = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(
                "Nitro output contains a link or special file outside its file contract"
            )
        if path.suffix in {".map", ".pem", ".key"} or any(
            p in {".git", ".env", ".npmrc", ".pnpmrc"} or p.startswith(".env.")
            for p in relative.parts
        ):
            raise ValueError("Forbidden runtime file")
        if path.is_file() and relative.as_posix() != "uranus-admin-build.json":
            files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = json.loads((root / "uranus-admin-build.json").read_text())
    manifest = json.loads((root.parent.parent / "release.json").read_text())
    if metadata["files"] != files or metadata["commit"] != manifest["commit"]:
        raise ValueError("Installed frontend differs from its release build")


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "path": {"type": "path", "required": True},
            "require_build_metadata": {"type": "bool", "default": True},
        },
        supports_check_mode=True,
    )
    try:
        verify_output(module.params["path"], module.params["require_build_metadata"])
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        module.fail_json(
            msg="Nitro output is incomplete, modified or redirected. Restore a complete release; "
            "never build on the target host."
        )
    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
