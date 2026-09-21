#!/usr/bin/python
"""Read-only application infrastructure inventory; never adopt unknown file contents."""

import hashlib
import json
import os
import stat
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule

UNITS = tuple(
    f"uranus-admin-{component}.service" for component in ("backend", "check-worker", "frontend")
)
SITE = "/etc/nginx/sites-available/uranus-admin"
LINK = "/etc/nginx/sites-enabled/uranus-admin"
RATE = "/etc/nginx/conf.d/uranus-admin-ratelimit.conf"
LOGGING = "/etc/nginx/conf.d/uranus-admin-logging.conf"
UNIT_ROOT = "/etc/systemd/system"
PATHS = (SITE, LOGGING, RATE, *(f"{UNIT_ROOT}/{unit}" for unit in UNITS))
RECEIPT = "/etc/uranus-admin/managed-infrastructure.json"
LOG_DIRECTORY = "/var/log/nginx"
SYSTEMD_ROOTS = (
    "/etc/systemd/system",
    "/run/systemd/system",
    "/usr/lib/systemd/system",
    "/usr/local/lib/systemd/system",
    "/lib/systemd/system",
    "/etc/systemd/system.control",
    "/run/systemd/system.control",
)
OWNER = 0


def metadata(path):
    try:
        value = Path(path).lstat()
    except FileNotFoundError:
        return None
    return value


def regular(path, mode=None):
    value = metadata(path)
    if value is not None and (
        not stat.S_ISREG(value.st_mode)
        or (
            mode is not None
            and (
                value.st_uid != OWNER
                or value.st_gid != OWNER
                or stat.S_IMODE(value.st_mode) != mode
            )
        )
    ):
        raise ValueError(f"Conflicting managed file: {path}")
    return value


def inventory(environment, candidates, services):
    if environment not in {"production", "staging", "test"}:
        raise ValueError("Invalid target environment")
    if {item["path"] for item in candidates} != set(PATHS) or len(candidates) != len(PATHS):
        raise ValueError("Invalid managed infrastructure file set")
    bootstrap = environment != "production"
    parents = sorted({str(Path(path).parent) for path in (*PATHS, LINK, RECEIPT)} | {LOG_DIRECTORY})
    missing_parents = []
    for parent in parents:
        for ancestor in (Path(parent), *Path(parent).parents):
            value = metadata(ancestor)
            if value is None:
                if not bootstrap:
                    raise ValueError(f"Missing application infrastructure directory: {ancestor}")
                if str(ancestor) not in missing_parents:
                    missing_parents.append(str(ancestor))
            elif not stat.S_ISDIR(value.st_mode):
                raise ValueError(f"Redirected application infrastructure directory: {ancestor}")

    link = metadata(LINK)
    if link is None:
        if not bootstrap:
            raise ValueError("Production requires the existing Nginx site symlink")
    elif (
        not stat.S_ISLNK(link.st_mode)
        or os.path.abspath(os.path.join(Path(LINK).parent, os.readlink(LINK))) != SITE
    ):
        raise ValueError("Conflicting Nginx site symlink")

    previous = {}
    if bootstrap:
        # A missing unit can still acquire global/prefix drop-ins when first installed.
        for base in SYSTEMD_ROOTS:
            for name in ("service", "uranus-.service", "uranus-admin-.service", *UNITS):
                directory = Path(base) / (name + ".d")
                value = metadata(directory)
                if value is not None and (
                    not stat.S_ISDIR(value.st_mode) or any(directory.iterdir())
                ):
                    raise ValueError(f"Unreviewed systemd drop-ins: {directory}")
    if bootstrap and regular(RECEIPT, 0o600) is not None:
        if Path(RECEIPT).stat().st_size > 16384:
            raise ValueError("Invalid managed infrastructure receipt")
        previous = json.loads(Path(RECEIPT).read_text())
        if not isinstance(previous, dict) or set(previous) != set(PATHS):
            raise ValueError("Invalid managed infrastructure receipt")

    desired = {}
    missing = []
    for item in candidates:
        path = item["path"]
        digest = hashlib.sha256(item["content"].encode()).hexdigest()
        desired[path] = digest
        value = regular(path, 0o644 if bootstrap else None)
        if value is None:
            if not bootstrap and path != LOGGING:
                raise ValueError(f"Production requires existing managed infrastructure: {path}")
            if Path(path).name in services and path.startswith(UNIT_ROOT + "/"):
                raise ValueError(f"Service loaded from an unexpected unit location: {path}")
            missing.append(path)
            continue
        if value.st_size > 1024 * 1024:
            raise ValueError(f"Oversized managed infrastructure file: {path}")
        installed = Path(path).read_bytes()
        if path == RATE:
            if installed.split() != item["content"].encode().split():
                raise ValueError("Rate-zone configuration differs; review before deployment")
        elif bootstrap:
            known = previous.get(path, digest)
            if not isinstance(known, str) or hashlib.sha256(installed).hexdigest() != known:
                raise ValueError(f"Unreviewed managed infrastructure contents: {path}")

    return {
        "changed": False,
        "would_create": missing,
        "would_create_symlink": link is None,
        "would_create_directories": sorted(missing_parents, key=len),
        "missing_units": [Path(path).name for path in missing if path.startswith(UNIT_ROOT + "/")],
        "receipt": json.dumps(desired, sort_keys=True, indent=2) + "\n",
    }


def main():
    module = AnsibleModule(
        argument_spec={
            "environment": {
                "type": "str",
                "required": True,
                "choices": ["production", "staging", "test"],
            },
            "candidates": {"type": "list", "elements": "dict", "required": True},
            "services": {"type": "list", "elements": "str", "required": True},
        },
        supports_check_mode=True,
    )
    try:
        module.exit_json(**inventory(**module.params))
    except ValueError as error:
        # Fixed categories / managed paths only. Never return existing file contents.
        module.fail_json(msg=str(error))
    except (OSError, KeyError, TypeError):
        module.fail_json(msg="Application infrastructure inspection unavailable")


if __name__ == "__main__":
    main()
