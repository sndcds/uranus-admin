#!/usr/bin/env python3
"""Deploy one test/staging host: dry run, record approvals, then apply.

Invoking this command authorizes secret adoption, clean Admin bootstrap and SQL
console provisioning on the selected test/staging host. Production stays manual.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import yaml

ANSIBLE = Path(__file__).resolve().parents[1]
CONFIRMATION = "Ja, führe das Deployment jetzt aus."
RELEASE_KEYS = {"ua_release_sha", "ua_artifact", "ua_artifact_sha256"}
APPROVAL_KEYS = {
    "ua_apply_confirmation",
    "ua_reviewed_dry_run",
    "ua_maintenance_window",
    "ua_backup_reference",
    "ua_secret_adoption_approved",
    "ua_admin_database_bootstrap_approved",
    "ua_sql_console_provision_approved",
    "ua_manage_notification_timer",
    "ua_disable_notification_timer_approved",
}


class WorkflowError(Exception):
    """Only fixed, non-sensitive messages may be reported by the CLI."""


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def private_read(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_size > 16384
        ):
            raise WorkflowError("Approval file must be an owned regular file with mode 0600.")
        return source.read()


def private_write(path, value):
    """Replace complete files atomically; never follow a destination symlink."""
    fd, temporary = tempfile.mkstemp(prefix=".deploy-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as target:
            target.write(value)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def approval_lock(path):
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
        ):
            raise WorkflowError("Unsafe approval lock file.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WorkflowError("Another deployment is using this approval file.") from None
        yield
    finally:
        os.close(fd)


def decisions(original, maintenance_window, backup_reference):
    values = yaml.safe_load(original) if original else {}
    if not isinstance(values, dict) or set(values) - (APPROVAL_KEYS | RELEASE_KEYS):
        raise WorkflowError(
            "Approval file contains unsupported keys; "
            "use approval decisions and optional release pins."
        )
    if values.keys() & RELEASE_KEYS and not RELEASE_KEYS <= values.keys():
        raise WorkflowError(
            "Approval release pins require commit, artifact path and SHA256 together."
        )
    for key, override in (
        ("ua_maintenance_window", maintenance_window),
        ("ua_backup_reference", backup_reference),
    ):
        if override is not None:
            values[key] = override
        value = values.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 1000:
            raise WorkflowError("A real maintenance window and backup reference are required.")
    for key in APPROVAL_KEYS - {
        "ua_apply_confirmation",
        "ua_reviewed_dry_run",
        "ua_maintenance_window",
        "ua_backup_reference",
    }:
        if key in values and type(values[key]) is not bool:
            raise WorkflowError("Approval decisions must use YAML booleans.")
    if values.get("ua_manage_notification_timer", False) and not values.get(
        "ua_disable_notification_timer_approved", False
    ):
        raise WorkflowError("Notification management needs its existing separate approval.")
    values.update(
        ua_apply_confirmation="",
        ua_reviewed_dry_run="",
        ua_secret_adoption_approved=True,
        ua_admin_database_bootstrap_approved=True,
        ua_sql_console_provision_approved=True,
    )
    values.setdefault("ua_manage_notification_timer", False)
    return values


def inventory_host(path, host, env):
    result = subprocess.run(
        [sys.executable, "-m", "ansible.cli.inventory", "-i", str(path), "--list"],
        cwd=ANSIBLE.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise WorkflowError("Inventory inspection failed; no deployment started.")
    inventory = json.loads(result.stdout)
    pending, visited, hosts = ["uranus_admin"], set(), set()
    while pending:
        group = pending.pop()
        if group in visited:
            continue
        visited.add(group)
        values = inventory.get(group, {})
        hosts.update(values.get("hosts", []))
        pending.extend(values.get("children", []))
    if host not in hosts:
        raise WorkflowError("Select exactly one existing host in the uranus_admin inventory group.")
    values = inventory.get("_meta", {}).get("hostvars", {}).get(host, {})
    if values.get("ua_target_environment") not in {"test", "staging"}:
        raise WorkflowError(
            "Automatic apply is only available for test/staging; production is manual."
        )
    # Freeze connection selection, not expressions that can resolve to a different host.
    if (
        any(
            key.startswith("ansible_")
            and isinstance(value, str)
            and ("{{" in value or "{%" in value)
            for key, value in values.items()
        )
        or "inventory_dir" in json.dumps(values)
        or "inventory_file" in json.dumps(values)
    ):
        raise WorkflowError(
            "Use literal connection settings and absolute inventory-relative paths."
        )
    return values


def release_target(inventory_values, approval):
    """Honor the bounded release tuple from the former -e approval-file workflow."""
    selected = {
        **inventory_values,
        **{key: approval[key] for key in RELEASE_KEYS if key in approval},
    }
    for key, pattern in (
        ("ua_release_sha", r"[0-9a-f]{40}"),
        ("ua_artifact_sha256", r"[0-9a-f]{64}"),
    ):
        value = selected.get(key)
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise WorkflowError("The effective release must pin its commit and artifact SHA256.")
    artifact = selected.get("ua_artifact")
    if not isinstance(artifact, str) or not Path(artifact).is_absolute():
        raise WorkflowError("The effective release must specify an absolute artifact path.")
    return selected


def controller_digest():
    paths = {ANSIBLE / "ansible.cfg", ANSIBLE / "deploy.yml", Path(__file__).resolve()}
    for name in ("roles", "filter_plugins", "callback_plugins", "group_vars", "host_vars"):
        paths.update(
            p
            for p in (ANSIBLE / name).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    value = hashlib.sha256()
    for path in sorted(paths):
        value.update(str(path).encode() + b"\0" + digest(path).encode() + b"\0")
    return value.hexdigest()


def run(args):
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", args.host):
        raise WorkflowError("Host must be one literal inventory hostname, not a limit expression.")
    inventory = args.inventory.absolute()
    approvals = args.approvals.absolute()
    if not inventory.is_file() or inventory.is_symlink():
        raise WorkflowError("Use a regular static inventory file.")
    env = {**os.environ, "ANSIBLE_CONFIG": str(ANSIBLE / "ansible.cfg")}
    with approval_lock(approvals):
        original = private_read(approvals)
        approval = decisions(original, args.maintenance_window, args.backup_reference)
        controller = controller_digest()
        source_digest = digest(inventory)
        inventory_values = inventory_host(inventory, args.host, env)
        selected = release_target(inventory_values, approval)
        if digest(selected["ua_artifact"]) != selected["ua_artifact_sha256"]:
            raise WorkflowError("Artifact checksum does not match the pinned release.")
        # Each run keeps private, frozen inputs and an honest machine-check receipt.
        runs = ANSIBLE / "deploy-runs.local"
        runs.mkdir(mode=0o700, exist_ok=True)
        info = runs.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.getuid()
        ):
            raise WorkflowError("Deployment run directory must be owned and mode 0700.")
        directory = Path(tempfile.mkdtemp(prefix="run-", dir=runs))
        frozen_inventory, variables = directory / "inventory.json", directory / "variables.json"
        private_write(
            frozen_inventory,
            json.dumps({"all": {"children": {"uranus_admin": {"hosts": {args.host: selected}}}}}),
        )
        # Pin the target/release without promoting all inventory values above
        # role facts and input guards. Never accept arbitrary CLI extra variables.
        pinned = {
            key: selected[key]
            for key in (
                "ua_target_environment",
                "ua_release_sha",
                "ua_artifact",
                "ua_artifact_sha256",
                "ansible_host",
                "ansible_connection",
                "ansible_user",
                "ansible_port",
            )
            if key in selected
        }
        pinned["ua_action"] = "deploy"
        private_write(variables, json.dumps({**pinned, **approval}))
        command = [
            sys.executable,
            "-m",
            "ansible.cli.playbook",
            "-i",
            str(frozen_inventory),
            str(ANSIBLE / "deploy.yml"),
            "--limit",
            args.host,
            "-e",
            "@" + str(variables),
        ]
        if args.ask_become_pass:
            command.append("--ask-become-pass")
        print("Running deployment dry run; apply follows only on success.", flush=True)
        checked = subprocess.run(command + ["--check", "--diff"], cwd=ANSIBLE.parent, env=env)
        if checked.returncode:
            return checked.returncode
        if (
            controller_digest() != controller
            or digest(inventory) != source_digest
            or inventory_host(inventory, args.host, env) != inventory_values
            or digest(selected["ua_artifact"]) != selected["ua_artifact_sha256"]
            or private_read(approvals) != original
        ):
            raise WorkflowError("Deployment inputs changed during the dry run; rerun the command.")
        timestamp = datetime.now(UTC).isoformat()
        receipt_path = directory / "result.json"
        receipt = dict(
            host=args.host,
            environment=selected["ua_target_environment"],
            release_sha=selected["ua_release_sha"],
            artifact_sha256=selected["ua_artifact_sha256"],
            inventory_sha256=source_digest,
            controller_sha256=controller,
            dry_run_completed_at=timestamp,
            review="automated",
            dry_run_exit_code=0,
            apply_exit_code=None,
        )
        private_write(receipt_path, json.dumps(receipt, indent=2) + "\n")
        approval.update(
            ua_apply_confirmation=CONFIRMATION,
            ua_reviewed_dry_run=f"Automatischer Deployment-Dry-Run {timestamp}; {receipt_path}",
        )
        private_write(variables, json.dumps({**pinned, **approval}))
        private_write(approvals, yaml.safe_dump(approval, sort_keys=True, allow_unicode=True))
        print(
            "Dry run passed; approvals updated. Starting apply for the same target and release.",
            flush=True,
        )
        applied = subprocess.run(command, cwd=ANSIBLE.parent, env=env)
        receipt["apply_exit_code"] = applied.returncode
        receipt["apply_completed_at"] = datetime.now(UTC).isoformat()
        private_write(receipt_path, json.dumps(receipt, indent=2) + "\n")
        return applied.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--inventory", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--approvals", type=Path, default=ANSIBLE / "approvals.local.yml")
    parser.add_argument(
        "--maintenance-window", help="Real window; otherwise preserve approval file value"
    )
    parser.add_argument(
        "--backup-reference", help="Real backup evidence; otherwise preserve approval file value"
    )
    parser.add_argument("--ask-become-pass", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except WorkflowError as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Deployment interrupted.", file=sys.stderr)
        return 130
    except (OSError, ValueError, TypeError, yaml.YAMLError, subprocess.SubprocessError):
        # Library exception messages can contain inventory or credential values.
        print(
            "Deployment workflow failed; inspect local file permissions and controller setup.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
