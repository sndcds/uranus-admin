#!/usr/bin/env python3
"""BUILD HOST ONLY: build freshly fetched main, then package its complete runtime.

Never invoked by Ansible or a service. No production configuration is read.
"""

import hashlib
import io
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import package_release as release

PLAYWRIGHT_IMAGE = (
    "mcr.microsoft.com/playwright:v1.63.0-noble@sha256:"
    "eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27"
)


def build_environment(home):
    # Allowlist, not a secret-name denylist: no inherited NUXT_*, credentials,
    # NODE_OPTIONS, npm config, proxy credentials or application environment.
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_STATE_HOME": str(home / "state"),
        "PNPM_CONFIG_DIR": str(home / "config"),
        "NPM_CONFIG_USERCONFIG": "/dev/null",
        "NPM_CONFIG_GLOBALCONFIG": "/dev/null",
        "CI": "true",
        "TZ": "UTC",
        "LANG": "C.UTF-8",
    }


def smoke_output(output, environment):
    """Start a copy outside the source tree so developer node_modules cannot help."""
    with tempfile.TemporaryDirectory(prefix="uranus-nitro-smoke-") as directory:
        standalone = Path(directory) / ".output"
        shutil.copytree(output, standalone)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = {
            **environment,
            "NODE_ENV": "production",
            "NITRO_HOST": "127.0.0.1",
            "NITRO_PORT": str(port),
            "NUXT_ADMIN_API_BASE": "http://127.0.0.1:1",
            "NUXT_PUBLIC_MAP_TILE_ATTRIBUTION": "release-runtime-probe",
        }
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with subprocess.Popen(
            ["node", str(standalone / "server/index.mjs")],
            cwd=directory,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) as process:
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        raise ValueError("Standalone Nitro server exited before readiness")
                    try:
                        with opener.open(f"http://127.0.0.1:{port}/login", timeout=2) as response:
                            body = response.read().decode()
                            if response.status == 200 and "release-runtime-probe" in body:
                                return
                    except (OSError, urllib.error.URLError):
                        pass
                    time.sleep(0.1)
                raise ValueError("Standalone Nitro smoke/runtime-config check failed")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def materialize_output(output):
    if output.is_symlink() or not output.is_dir():
        raise ValueError("Frontend production build missing or redirected")
    # Nitro traces a small runtime node_modules tree with internal package links.
    # Materialize ONLY links contained in .output; never copy developer dependencies.
    for path in output.rglob("*"):
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(output.resolve()):
            raise ValueError("Nitro emitted a link outside its standalone output")
    materialized = output.with_name(".output-materialized")
    shutil.copytree(output, materialized, symlinks=False)
    shutil.rmtree(output)
    materialized.rename(output)


def build_frontend(commit, workspace, verify=False, production_e2e=False):
    if Path("/etc/uranus-admin/runtime.env").exists():
        raise ValueError("Refusing frontend build on a configured Uranus Admin target host")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("Release builds require Linux x86_64, matching the target runtime")
    workspace.mkdir(parents=True, exist_ok=True)
    frontend = workspace / "frontend"
    if frontend.exists():
        raise ValueError("Release build requires a fresh workspace")
    raw = subprocess.check_output(["git", "archive", "--format=tar", commit, "frontend"])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            parts = Path(member.name).parts
            if any(
                p in {".git", "node_modules", ".output", ".nuxt", ".npmrc", ".pnpmrc"}
                or p == ".env"
                or p.startswith(".env.")
                for p in parts
            ):
                continue
            if not member.isfile():
                if not member.isdir():
                    raise ValueError("Release frontend sources must not contain links")
                continue
            destination = workspace / member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.extractfile(member).read())
    home = workspace / "build-home"
    home.mkdir()
    environment = build_environment(home)
    pnpm = json.loads((frontend / "package.json").read_text())["packageManager"]
    expected_pnpm = pnpm.removeprefix("pnpm@")
    for tool, expected in (("node", "v" + release.NODE_VERSION), ("pnpm", expected_pnpm)):
        actual = subprocess.check_output(
            [tool, "--version"], cwd=frontend, env=environment, text=True
        ).strip()
        if actual != expected:
            raise ValueError(
                f"Release build requires {tool} {expected}; "
                "install the pinned tool on the build host"
            )
    command = ["pnpm", "--pm-on-fail=error", "--runtime-on-fail=error", "--userconfig=/dev/null"]

    def run(*args, env=environment):
        subprocess.run([*command, *args], cwd=frontend, env=env, check=True, stdout=sys.stderr)

    run("install", "--frozen-lockfile")
    if verify:
        for check in ("lint", "typecheck", "test"):
            run(check)
    timestamp = subprocess.check_output(
        ["git", "show", "-s", "--format=%ct", commit], text=True
    ).strip()
    run(
        "build",
        env={
            **environment,
            "NODE_ENV": "production",
            "NITRO_PRESET": "node-server",
            "SOURCE_DATE_EPOCH": timestamp,
        },
    )
    output = frontend / ".output"
    materialize_output(output)
    # Some traced third-party runtime packages ship their own maps even with Nuxt
    # sourcemaps disabled. Maps are diagnostics, not runtime dependencies.
    for path in output.rglob("*.map"):
        path.unlink()
    files = release.frontend_files(output)
    smoke_output(output, environment)
    if production_e2e:
        # Same pinned browser/OS/fonts as ci.yml; test only the sanitized checkout.
        subprocess.run(
            [
                "docker",
                "--host",
                "unix:///var/run/docker.sock",
                "run",
                "--rm",
                "--init",
                "--ipc=host",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--env",
                "HOME=/tmp",
                "--volume",
                f"{frontend}:/work",
                "--workdir",
                "/work",
                "--volume",
                f"{Path(shutil.which('node')).resolve()}:/usr/local/bin/node:ro",
                "--env",
                "TEST_PRODUCTION=1",
                "--env",
                "CI=true",
                PLAYWRIGHT_IMAGE,
                "node",
                "node_modules/@playwright/test/cli.js",
                "test",
            ],
            check=True,
            stdout=sys.stderr,
            env=environment,
        )
    metadata = {
        "commit": commit,
        "node": release.NODE_VERSION,
        "pnpm": expected_pnpm,
        "platform": "linux-x64",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    (output / release.BUILD_METADATA).write_text(json.dumps(metadata, sort_keys=True, indent=2))
    return output


if __name__ == "__main__":
    release.main(build=True)
