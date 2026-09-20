#!/usr/bin/python
"""Read-only deployment storage checks; reject remote mounts and redirected parents."""

import os
import re
import stat
from pathlib import Path

LOCAL_FILESYSTEMS = frozenset({"ext4", "xfs", "btrfs", "zfs"})


def mounts_from_text(text):
    mounts = []
    for line in text.splitlines():
        fields, filesystem = line.split(" - ", 1)
        target = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields.split()[4])
        mounts.append((Path(target), filesystem.split()[0]))
    return mounts


def inspect_paths(paths, min_free_bytes, mounts):
    results = []
    for value in paths:
        path = Path(value)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("Storage target must be an absolute normalized path")
        nearest = None
        for parent in reversed([path, *path.parents]):
            try:
                metadata = parent.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(f"Redirected or non-directory storage path: {parent}")
            nearest = parent
        candidates = [(target, kind) for target, kind in mounts if nearest.is_relative_to(target)]
        if not candidates:
            raise ValueError(f"Cannot determine filesystem: {path}")
        target, kind = max(candidates, key=lambda entry: len(entry[0].parts))
        if kind not in LOCAL_FILESYSTEMS:
            raise ValueError(f"Non-local or unsupported filesystem for {path}: {kind}")
        if any(child != path and child.is_relative_to(path) for child, _ in mounts):
            raise ValueError(f"Unexpected nested mount under managed storage: {path}")
        usage = os.statvfs(nearest)
        if usage.f_flag & os.ST_RDONLY or not os.access(nearest, os.W_OK):
            raise ValueError(f"Storage target is not writable: {path}")
        free = usage.f_bavail * usage.f_frsize
        if free < min_free_bytes:
            raise ValueError(
                f"Insufficient local free space for {path}: {free} bytes; "
                f"require {min_free_bytes}. No automatic cleanup."
            )
        results.append({"path": str(path), "mount": str(target), "type": kind, "free_bytes": free})
    return results


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "paths": {"type": "list", "elements": "path", "required": True},
            "min_free_bytes": {"type": "int", "required": True},
        },
        supports_check_mode=True,
    )
    try:
        mounts = mounts_from_text(Path("/proc/self/mountinfo").read_text())
        filesystems = inspect_paths(module.params["paths"], module.params["min_free_bytes"], mounts)
    except (OSError, ValueError, IndexError) as exc:
        module.fail_json(msg=f"Local storage check failed: {exc}")
    module.exit_json(changed=False, filesystems=filesystems)


if __name__ == "__main__":
    main()
