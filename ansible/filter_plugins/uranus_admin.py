"""Controller-side validation. Exceptions never contain environment values."""

import hashlib
import io
import json
import re
import tarfile
from urllib.parse import unquote, urlsplit

from ansible.errors import AnsibleFilterError
from dotenv.parser import parse_stream

PRIVILEGED = {
    "ADMIN_MIGRATION_DATABASE_URL",
    "ADMIN_AUTH_MANAGEMENT_DATABASE_URL",
    "DEV_ADMIN_TOKEN",
}
OVERRIDES = {
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_TIMEOUT_SECONDS",
    "URANUS_TIMESTAMP_TIMEZONE",
    "ADMIN_TIMEZONE",
    "EVENT_TIMEZONE",
    "URANUS_API_URL",
    "NOMINATIM_BASE_URL",
    "KULTURBYTES_APP_PUBLIC_BASE_URL",
    "AUTH_SESSION_SECONDS",
    "AUTH_IDLE_SECONDS",
}


def parse_environment(value):
    result = {}
    for binding in parse_stream(io.StringIO(value)):
        if binding.error:
            raise AnsibleFilterError("Environment syntax unsupported; no files changed")
        if binding.key is None:
            continue
        key, val = binding.key, binding.value
        if (
            not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
            or key in result
            or val is None
            or "${" in val
            or any(ord(c) < 32 or ord(c) == 127 for c in val)
        ):
            raise AnsibleFilterError("Environment contains duplicate/unsupported entries")
        result[key] = val
    return result


def render_environment(values):
    lines = []
    for key, val in sorted(values.items()):
        val = str(val)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or any(ord(c) < 32 for c in val):
            raise AnsibleFilterError("Unsafe environment entry")
        lines.append(key + '="' + val.replace("\\", "\\\\").replace('"', '\\"') + '"')
    return "\n".join(lines) + "\n"


def valid_target_origin(origin, environment):
    if not isinstance(origin, str) or not re.fullmatch(
        r"https://[a-z0-9]+(?:[.-][a-z0-9]+)*", origin
    ):
        return False
    return (origin == "https://admin.kulturbytes.de") == (environment == "production")


def console_bootstrap_blockers(blockers, admin_plan):
    """Defer only absent-role dependencies; all catalog/security drift still blocks."""
    if not admin_plan.get("bootstrap_allowed") or admin_plan.get("state") != "ABSENT":
        return blockers
    missing = set(admin_plan["missing_roles"])
    if not missing or not missing <= {
        "uranus_reader",
        "admin_user",
        "admin_migrator",
        "admin_auth_operator",
    }:
        return blockers
    return [
        b
        for b in blockers
        if b not in {"missing_temp_contract_login_role:" + name for name in missing}
        and not b.startswith("missing_execute_contract_login_role:")
    ]


def runtime_environment(
    values, allowed, overrides=None, debug=False, public_origin="https://admin.kulturbytes.de"
):
    values = dict(values)
    # Older releases neither require nor receive an adopted console credential.
    if "SQL_CONSOLE_DATABASE_URL" not in allowed:
        values.pop("SQL_CONSOLE_DATABASE_URL", None)
    if set(values) - set(allowed) - PRIVILEGED:
        raise AnsibleFilterError("Unknown backend environment keys; review before adoption")
    if set(overrides or {}) - OVERRIDES:
        raise AnsibleFilterError("Only documented non-secret overrides are allowed")
    result = {k: v for k, v in values.items() if k not in PRIVILEGED}
    result.update({k: str(v) for k, v in (overrides or {}).items()})
    identities = [("DATABASE_URL", "uranus_reader"), ("ADMIN_DATABASE_URL", "admin_user")]
    if "SQL_CONSOLE_DATABASE_URL" in allowed:
        identities.append(("SQL_CONSOLE_DATABASE_URL", "uranus_console_reader"))
    for key, role in identities:
        try:
            url = urlsplit(result[key])
            valid = (
                url.scheme == "postgresql+asyncpg"
                and unquote(url.username or "") == role
                and url.hostname in {"localhost", "127.0.0.1", "::1"}
                and url.port in {None, 5432}
                and url.path == "/oklab"
                and not url.query
                and not url.fragment
                and bool(url.password)
            )
            if key == "SQL_CONSOLE_DATABASE_URL":
                password = unquote(url.password or "")
                valid = (
                    valid
                    and len(password) >= 24
                    and password.isascii()
                    and all(32 < ord(c) < 127 for c in password)
                )
        except (KeyError, ValueError):
            valid = False
        if not valid:
            raise AnsibleFilterError("Runtime DSN must use its dedicated role and local oklab")
    result.update(
        {
            "APP_ENV": "production",
            "APP_HOST": "127.0.0.1",
            "APP_PORT": "8011",
            "DEV_AUTH_ENABLED": "false",
            "OPENAPI_ENABLED": "false",
            "AUTH_PUBLIC_ORIGIN": public_origin,
            "ADMIN_PUBLIC_BASE_URL": public_origin,
            "NOTIFICATIONS_DELIVERY_ENABLED": "false",
            "CORS_ORIGINS": "",
            "APP_DEBUG": "true" if debug else "false",
            "ALLOW_PRODUCTION_DEBUG": "true" if debug else "false",
            "LOG_LEVEL": "DEBUG" if debug else "INFO",
        }
    )
    return result


def privileged_environment(values):
    return {key: value for key, value in values.items() if key in PRIVILEGED}


def artifact_manifest(path, expected_hash, expected_sha):
    """Read a bounded, authenticated archive without extracting or executing its code."""
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise AnsibleFilterError("Select a full release commit")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise AnsibleFilterError("Select the reviewed archive SHA256")
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise AnsibleFilterError("Archive checksum mismatch")
        with tarfile.open(path, "r:gz") as archive:
            names = set()
            total = 0
            for member in archive:
                total += member.size
                if total > 256 * 1024 * 1024 or len(names) > 20000:
                    raise AnsibleFilterError("Release archive exceeds source limits")
                name = member.name.rstrip("/")
                parts = name.split("/")
                if (
                    name in names
                    or member.mode & 0o7022
                    or any(p in {"", ".", ".."} for p in parts)
                    or name.startswith("/")
                    or not (member.isfile() or member.isdir())
                    or any(p == ".env" or p.startswith(".env.") for p in parts)
                    or parts[0] not in {"backend", "frontend", "release.json"}
                    or any(p in {"tests", ".git", ".venv", "node_modules"} for p in parts)
                ):
                    raise AnsibleFilterError("Unsafe archive member")
                names.add(name)
            member = archive.getmember("release.json")
            if member.size > 65536:
                raise AnsibleFilterError("Release manifest too large")
            manifest = json.load(archive.extractfile(member))
        if manifest["commit"] != expected_sha:
            raise AnsibleFilterError("Release commit mismatch")
        keys = manifest["environment_keys"]
        if (
            not isinstance(keys, list)
            or any(
                not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
                for key in keys
            )
            or len(keys) != len(set(keys))
        ):
            raise AnsibleFilterError("Invalid release environment capability contract")
        if not re.fullmatch(r"[0-9]{4}", manifest["head"]):
            raise AnsibleFilterError("Invalid migration head")
        if not manifest["runtime_grants"] or any(
            not re.fullmatch(r"[a-z_]+", k) or not set(v) <= {"SELECT", "INSERT", "UPDATE"}
            for k, v in manifest["runtime_grants"].items()
        ):
            raise AnsibleFilterError("Invalid runtime grants manifest")
        for key, expected_type in (
            ("operator_grants", dict),
            ("admin_indexes", list),
            ("admin_columns", dict),
        ):
            if not isinstance(manifest.get(key), expected_type) or not manifest[key]:
                raise AnsibleFilterError(
                    "Release manifest lacks the admin database contract (" + key + "). "
                    "Repackage the selected release with the current package_release.py; "
                    "review its new archive SHA256. No database repair is needed for this error."
                )
        return manifest
    except (OSError, ValueError, KeyError, TypeError, AttributeError, tarfile.TarError):
        raise AnsibleFilterError("Release archive or manifest unavailable/invalid") from None


def activation_plan(changed_paths, service_states, config_dir):
    """Keep restarts tied to executable/config changes or an already stopped service."""
    runtime_changed = config_dir + "/runtime.env" in changed_paths
    services = [
        "uranus-admin-backend.service",
        "uranus-admin-check-worker.service",
        "uranus-admin-frontend.service",
    ]
    return {
        "runtime_changed": runtime_changed,
        "units_changed": any(p.startswith("/etc/systemd/") for p in changed_paths),
        "nginx_changed": any(p.startswith("/etc/nginx/") for p in changed_paths),
        "restart_services": [
            name
            for name in services
            if (
                "/etc/systemd/system/" + name in changed_paths
                or (runtime_changed and name != "uranus-admin-frontend.service")
                or service_states.get(name, {}).get("state") != "running"
            )
        ],
    }


class FilterModule:
    def filters(self):
        return {
            "ua_parse_env": parse_environment,
            "ua_console_environment": console_environment,
            "ua_archive_console": archive_console,
            "ua_render_env": render_environment,
            "ua_runtime_env": runtime_environment,
            "ua_valid_target_origin": valid_target_origin,
            "ua_console_bootstrap_blockers": console_bootstrap_blockers,
            "ua_privileged_env": privileged_environment,
            "ua_manifest": artifact_manifest,
            "ua_activation_plan": activation_plan,
            "ua_service_snapshot": service_snapshot,
            "ua_recovery_files": recovery_files,
        }


def service_snapshot(results, environment="production"):
    """Accept stable states that can be restored without unmasking or inventing enablement."""
    snapshot = {}
    for result in results:
        name = result["item"]
        fields = dict(line.split("=", 1) for line in result["stdout"].splitlines() if "=" in line)
        if (
            environment in {"staging", "test"}
            and name
            in {
                "uranus-admin-backend.service",
                "uranus-admin-check-worker.service",
                "uranus-admin-frontend.service",
                "uranus-admin-notification-worker.service",
                "uranus-admin-notification-worker.timer",
            }
            and fields.get("LoadState") == "not-found"
            and fields.get("ActiveState") == "inactive"
            and fields.get("UnitFileState", "") == ""
        ):
            snapshot[name] = {
                "exists": False,
                "state": "stopped",
                "active": False,
                "enabled": False,
                "unit_file_state": "",
            }
            continue
        allowed = {"enabled", "disabled"}
        active_states = {"active"}
        if name == "uranus-admin-notification-worker.service":
            allowed.add("static")
            # A running Type=oneshot remains activating until its bounded command exits.
            active_states.add("activating")
        if (
            fields.get("LoadState") != "loaded"
            or fields.get("ActiveState") not in active_states | {"inactive", "failed"}
            or fields.get("UnitFileState") not in allowed
        ):
            raise AnsibleFilterError(
                "Unstable, masked or unsupported unit state; review before activation"
            )
        snapshot[name] = {
            "exists": True,
            "state": "running" if fields["ActiveState"] in active_states else "stopped",
            "active": fields["ActiveState"] in active_states,
            "enabled": fields["UnitFileState"] == "enabled",
            "unit_file_state": fields["UnitFileState"],
        }
    if not snapshot["nginx.service"]["active"]:
        raise AnsibleFilterError("The existing proxy must be running before activation")
    return snapshot


def recovery_files(results, changed_paths, directory):
    """Metadata only: no previous or candidate environment contents in the manifest."""
    return [
        {
            "path": result["item"]["path"],
            "backup": directory + "/file-" + str(index),
            "exists": result["stat"]["exists"],
            **{key: result["stat"][key] for key in ("uid", "gid", "mode") if key in result["stat"]},
        }
        for index, result in enumerate(results)
        if result["item"]["path"] in changed_paths
    ]


def console_environment(values, operator, allowed):
    """Adopt one explicit secret; no derivation from source/admin credentials."""
    result = dict(values)
    key = "SQL_CONSOLE_DATABASE_URL"
    if key not in allowed:
        result.pop(key, None)
        return result
    if key in operator:
        if key in result and result[key] != operator[key]:
            raise AnsibleFilterError("Console credential differs; no automatic rotation")
        result[key] = operator[key]
    if not result.get(key):
        raise AnsibleFilterError("Missing SQL_CONSOLE_DATABASE_URL; no fallback")
    return result


def archive_console(privileged, source, existing):
    """Preserve an explicit console secret when deploying an older release.

    The existing task guard has already compared all legacy privileged entries.
    This adds only the console key, never replaces a different archived value.
    """
    result = {**privileged, **existing}
    key = "SQL_CONSOLE_DATABASE_URL"
    if key in source:
        if key in result and result[key] != source[key]:
            raise AnsibleFilterError("Console credential differs; no automatic rotation")
        result[key] = source[key]
    return result
