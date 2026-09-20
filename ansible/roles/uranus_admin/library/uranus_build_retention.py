#!/usr/bin/python
"""Bounded retention of completed build workspaces, never runtime releases or data."""

import os
import pwd
import re
import shutil
import stat
from pathlib import Path

ROOT = Path("/home/oklab/build/uranus-admin/.deployment-builds")
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def open_directory(path):
    fd = os.open("/", DIRECTORY_FLAGS)
    try:
        for part in Path(path).parts[1:]:
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


class Retention:
    def __init__(self, root, current_release, keep=3):
        if not re.fullmatch(r"[0-9a-f]{40}", current_release) or keep < 3:
            raise ValueError("Retention requires a full release SHA and at least three builds")
        self.root, self.current_release, self.keep = Path(root), current_release, keep
        self.changed = False

    def candidate(self, fd, name):
        child = os.open(name, DIRECTORY_FLAGS, dir_fd=fd)
        try:
            info = os.fstat(child)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise ValueError("Unexpected build owner or writable permissions")
            try:
                marker = os.open(
                    ".build-complete", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=child
                )
            except FileNotFoundError:
                return None
            with os.fdopen(marker, "rb") as stream:
                complete = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(complete.st_mode)
                    or complete.st_uid != os.geteuid()
                    or complete.st_nlink != 1
                    or complete.st_mode & 0o022
                    or not re.fullmatch(rb"[0-9a-f]{64}\n", stream.read(66))
                ):
                    raise ValueError("Invalid completed-build marker")
            return (info.st_dev, info.st_ino, complete.st_mtime_ns, complete.st_ino)
        finally:
            os.close(child)

    def run(self, check_mode, mount_targets):
        if not shutil.rmtree.avoids_symlink_attacks:
            raise ValueError("Descriptor-safe tree removal unavailable")
        if any(Path(target).is_relative_to(self.root) for target in mount_targets):
            raise ValueError("Build retention refuses mounted build directories")
        try:
            fd = open_directory(self.root)
        except FileNotFoundError:
            return {"removed": [], "would_remove": [], "kept": [], "skipped": 0}
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise ValueError("Unexpected build-root owner or writable permissions")
            completed, skipped = {}, 0
            for name in os.listdir(fd):
                if not re.fullmatch(r"[0-9a-f]{40}", name):
                    skipped += 1
                    continue
                identity = self.candidate(fd, name)
                if identity is None:
                    skipped += 1
                else:
                    completed[name] = identity
            ordered = sorted(completed, key=lambda name: (completed[name][2], name), reverse=True)
            kept = set(ordered[: self.keep]) | {self.current_release}
            candidates = [name for name in ordered if name not in kept]
            removed = []
            if not check_mode:
                for name in candidates:
                    if self.candidate(fd, name) != completed[name]:
                        raise ValueError("Build changed during retention; refusing deletion")
                    self.changed = True
                    shutil.rmtree(name, dir_fd=fd)
                    removed.append(name)
            return {
                "removed": removed,
                "would_remove": candidates,
                "kept": [name for name in ordered if name in kept],
                "skipped": skipped,
            }
        finally:
            os.close(fd)


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={"current_release": {"type": "str", "required": True}},
        supports_check_mode=True,
    )
    retention = None
    try:
        if os.geteuid() != pwd.getpwnam("oklab").pw_uid:
            raise ValueError("Build retention must run as oklab")
        targets = [
            re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), line.split()[4])
            for line in Path("/proc/self/mountinfo").read_text().splitlines()
        ]
        retention = Retention(ROOT, module.params["current_release"])
        result = retention.run(module.check_mode, targets)
    except (OSError, ValueError, KeyError) as exc:
        module.fail_json(
            msg=f"Build retention refused; runtime release unchanged: {exc}",
            changed=bool(retention and retention.changed),
        )
    module.exit_json(changed=bool(result["would_remove"]), **result)


if __name__ == "__main__":
    main()
