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


def runtime_environment(values, allowed, overrides=None, debug=False):
    if set(values) - set(allowed) - PRIVILEGED:
        raise AnsibleFilterError("Unknown backend environment keys; review before adoption")
    if set(overrides or {}) - OVERRIDES:
        raise AnsibleFilterError("Only documented non-secret overrides are allowed")
    result = {k: v for k, v in values.items() if k not in PRIVILEGED}
    result.update({k: str(v) for k, v in (overrides or {}).items()})
    for key, role in (("DATABASE_URL", "uranus_reader"), ("ADMIN_DATABASE_URL", "admin_user")):
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
            "AUTH_PUBLIC_ORIGIN": "https://admin.kulturbytes.de",
            "ADMIN_PUBLIC_BASE_URL": "https://admin.kulturbytes.de",
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
        if not re.fullmatch(r"[0-9]{4}", manifest["head"]):
            raise AnsibleFilterError("Invalid migration head")
        if not manifest["runtime_grants"] or any(
            not re.fullmatch(r"[a-z_]+", k) or not set(v) <= {"SELECT", "INSERT", "UPDATE"}
            for k, v in manifest["runtime_grants"].items()
        ):
            raise AnsibleFilterError("Invalid runtime grants manifest")
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
                or service_states[name]["state"] != "running"
            )
        ],
    }


class FilterModule:
    def filters(self):
        return {
            "ua_parse_env": parse_environment,
            "ua_render_env": render_environment,
            "ua_runtime_env": runtime_environment,
            "ua_privileged_env": privileged_environment,
            "ua_manifest": artifact_manifest,
            "ua_activation_plan": activation_plan,
        }
