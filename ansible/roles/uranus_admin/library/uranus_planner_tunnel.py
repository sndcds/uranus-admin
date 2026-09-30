#!/usr/bin/python
"""Read-only tunnel ownership/credential checks; never read private key contents."""

import hashlib
import os
import stat
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule

UNIT = "uranus-admin-research-planner-tunnel.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT
MARKER = b"# Ansible-managed Uranus Admin research planner tunnel\n"
OWNER = 0
SYSTEMD_ROOTS = (
    "/etc/systemd/system",
    "/run/systemd/system",
    "/usr/lib/systemd/system",
    "/usr/local/lib/systemd/system",
    "/lib/systemd/system",
    "/etc/systemd/system.control",
    "/run/systemd/system.control",
)


def protected_file(path, modes):
    for parent in Path(path).parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != OWNER or info.st_mode & 0o022:
            raise ValueError("Credential/unit parent must be a protected root-owned directory")
    info = Path(path).lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != OWNER
        or info.st_gid != OWNER
        or stat.S_IMODE(info.st_mode) not in modes
        or not 0 < info.st_size <= 1024 * 1024
    ):
        raise ValueError("Credential/unit must be a nonempty protected root-owned regular file")
    return info


def inspect(enabled, key_path, known_hosts_path):
    exists = os.path.lexists(UNIT_PATH)
    if exists:
        protected_file(UNIT_PATH, {0o644})
        with UNIT_PATH.open("rb") as unit:
            if unit.read(len(MARKER)) != MARKER:
                raise ValueError("Refusing to adopt an unmanaged planner tunnel unit")
    if enabled or exists:
        for base in SYSTEMD_ROOTS:
            alternate = Path(base) / UNIT
            if alternate != UNIT_PATH and os.path.lexists(alternate):
                raise ValueError("Planner tunnel unit exists in an alternate location")
            for prefix in (
                "service",
                "uranus-.service",
                "uranus-admin-.service",
                "uranus-admin-research-.service",
                "uranus-admin-research-planner-.service",
                UNIT,
            ):
                directory = Path(base) / (prefix + ".d")
                if os.path.lexists(directory) and (
                    not stat.S_ISDIR(directory.lstat().st_mode) or any(directory.iterdir())
                ):
                    raise ValueError("Unreviewed planner tunnel systemd drop-ins")
    revision = "disabled"
    if enabled:
        if not os.access("/usr/bin/ssh", os.X_OK):
            raise ValueError("Install the OpenSSH client before enabling the tunnel")
        metadata = []
        for path, modes in (
            (key_path, {0o400, 0o600}),
            (known_hosts_path, {0o400, 0o444, 0o600, 0o644}),
        ):
            info = protected_file(path, modes)
            metadata.append((path, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
        # Detect operator rotation without reading, hashing or copying key material.
        revision = hashlib.sha256(repr(metadata).encode()).hexdigest()
    return {"changed": False, "managed": exists, "credential_revision": revision}


def main():
    module = AnsibleModule(
        argument_spec={
            "enabled": {"type": "bool", "required": True},
            "key_path": {"type": "path", "required": True},
            "known_hosts_path": {"type": "path", "required": True},
        },
        supports_check_mode=True,
    )
    try:
        module.exit_json(**inspect(**module.params))
    except ValueError as error:
        module.fail_json(msg=str(error))
    except OSError:
        module.fail_json(msg="Planner tunnel credential/unit inspection unavailable")


if __name__ == "__main__":
    main()
