#!/usr/bin/python
"""Offline, fail-closed toolchain inspection and safe archive installation.

Downloads belong to Ansible get_url. Every installed byte is compared to a freshly
hashed, pinned archive; local completion markers are deliberately not trusted.
"""

import hashlib
import os
import platform
import posixpath
import re
import stat
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path("/opt/uranus-admin/toolchain")
SOURCES = {
    "python": "https://github.com/astral-sh/python-build-standalone/releases/download/",
    "uv": "https://github.com/astral-sh/uv/releases/download/",
    "node": "https://nodejs.org/dist/",
    "pnpm": "https://github.com/pnpm/pnpm/releases/download/",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def relative(name):
    p = PurePosixPath(name)
    require(bool(name) and not p.is_absolute() and ".." not in p.parts, "Unsafe archive path")
    return str(p)


def select_packages(catalog, manifest, architecture):
    require(architecture == catalog["architecture"] == "x86_64", "Unsupported architecture")
    selected, directories = {}, set()
    for pin in catalog["packages"]:
        tool, version = pin["tool"], pin["version"]
        require(tool in SOURCES and re.fullmatch(r"\d+\.\d+\.\d+", version), "Invalid version pin")
        require(
            re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) and len(set(pin["sha256"])) > 1,
            "Missing/invalid SHA256 pin",
        )
        require(
            pin["url"].startswith(SOURCES[tool])
            and version in pin["url"]
            and not any(c in pin["url"] for c in ("?", "#", "@"))
            and "/latest/" not in pin["url"],
            "Invalid official download URL",
        )
        directory = pin["directory"]
        require(
            re.fullmatch(r"[a-z0-9.-]+", directory)
            and directory.startswith(tool + "-")
            and directory not in directories,
            "Invalid/duplicate installation directory",
        )
        directories.add(directory)
        relative(pin["binary"])
        if pin["prefix"]:
            require("/" not in pin["prefix"] and relative(pin["prefix"]) != ".", "Invalid prefix")
        require(
            pin["selector"] == (".".join(version.split(".")[:2]) if tool == "python" else version),
            "Selector/version mismatch",
        )
        matches = manifest.get(tool) == pin["selector"]
        if tool == "python":
            matches = matches and catalog["python_series"].get(pin["selector"]) == directory
        if matches:
            require(tool not in selected, "Ambiguous toolchain pin")
            selected[tool] = pin
    require(set(selected) == set(SOURCES), "Release requires an unreviewed toolchain version")
    return selected


class Toolchain:
    def __init__(
        self,
        root,
        catalog,
        manifest,
        architecture,
        uid=0,
        gid=0,
        anchor=Path("/opt"),
        runtime_user=None,
    ):
        self.root, self.catalog = Path(root), catalog
        self.selected = select_packages(catalog, manifest, architecture)
        self.uid, self.gid, self.anchor = uid, gid, Path(anchor)
        self.runtime_user = runtime_user
        self.known = {p["directory"]: p for p in catalog["packages"]}

    def metadata(self, path, kind, mode=None):
        info = path.lstat()
        require(
            info.st_uid == self.uid and info.st_gid == self.gid,
            f"Wrong owner: {path}; expected {self.uid}:{self.gid}, "
            f"found {info.st_uid}:{info.st_gid}. No automatic adoption or ownership repair.",
        )
        valid = {"dir": stat.S_ISDIR, "file": stat.S_ISREG, "link": stat.S_ISLNK}[kind]
        require(valid(info.st_mode), f"Wrong file type or symlink: {path}")
        if kind != "link":
            require(not info.st_mode & 0o022, f"Writable managed path: {path}")
            if mode is not None:
                require(stat.S_IMODE(info.st_mode) == mode, f"Wrong permissions: {path}")
        if kind == "file":
            require(info.st_nlink == 1, f"Unexpected hard link: {path}")

    def parents(self):
        require(self.root.is_relative_to(self.anchor) and self.root != self.anchor, "Unsafe root")
        nearest = None
        for path in reversed([self.root, *self.root.parents]):
            if path != self.anchor and not path.is_relative_to(self.anchor):
                continue
            if path.exists() or path.is_symlink():
                self.metadata(path, "dir")
                nearest = path
        require(
            nearest is not None
            and os.access(nearest, os.W_OK)
            and nearest.stat().st_mode & 0o200
            and not os.statvfs(nearest).f_flag & os.ST_RDONLY,
            "Toolchain target not writable",
        )

    def archive(self, pin):
        return self.root / "archives" / (pin["directory"] + ".tar")

    def model(self, pin):
        archive = self.archive(pin)
        self.metadata(archive, "file", 0o644)
        with archive.open("rb") as stream:
            require(sha256(stream) == pin["sha256"], f"Archive SHA256 mismatch: {archive}")
        tree = {}
        with tarfile.open(archive) as source:
            members = source.getmembers()
            require(
                len(members) <= 30000 and sum(m.size for m in members) <= 2 * 1024**3,
                "Archive exceeds bounds",
            )
            for member in members:
                name = relative(member.name)
                prefix = pin["prefix"]
                if prefix:
                    if name == prefix and member.isdir():
                        continue
                    require(name.startswith(prefix + "/"), "Unexpected archive prefix")
                    name = name[len(prefix) + 1 :]
                require(name != "." and name not in tree, "Duplicate archive member")
                if member.isdir():
                    record = {"kind": "dir", "mode": 0o755}
                elif member.issym():
                    require(not posixpath.isabs(member.linkname), "Absolute archive symlink")
                    target = posixpath.normpath(
                        posixpath.join(posixpath.dirname(name), member.linkname)
                    )
                    relative(target)
                    record = {"kind": "link", "target": member.linkname, "resolved": target}
                elif member.isfile() or member.islnk():
                    if member.islnk():
                        relative(member.linkname)
                        target = source.getmember(member.linkname)
                        require(target.isfile(), "Hardlink must target a regular archive member")
                    with source.extractfile(member) as stream:
                        digest = sha256(stream)
                    record = {
                        "kind": "file",
                        "mode": 0o755 if member.mode & 0o111 else 0o644,
                        "sha256": digest,
                        "member": member.name,
                    }
                else:
                    raise ValueError("Unsupported archive member type")
                tree[name] = record
        # Archives such as python-build-standalone omit directory entries.
        for name in list(tree):
            for parent in PurePosixPath(name).parents:
                if str(parent) != ".":
                    tree.setdefault(str(parent), {"kind": "dir", "mode": 0o755})
        for name, record in tree.items():
            for parent in PurePosixPath(name).parents:
                if str(parent) != ".":
                    require(tree[str(parent)]["kind"] == "dir", "Archive traverses a symlink")
            if record["kind"] == "link":
                target, seen = record["resolved"], {name}
                while True:
                    require(target in tree and target not in seen, "Dangling/cyclic archive link")
                    seen.add(target)
                    if tree[target]["kind"] != "link":
                        break
                    target = tree[target]["resolved"]
        require(tree.get(pin["binary"], {}).get("kind") == "file", "Binary must be a regular file")
        require(tree[pin["binary"]]["mode"] == 0o755, "Binary must be executable")
        return tree

    def verify_tree(self, directory, tree):
        self.metadata(directory, "dir", 0o755)
        actual = set()
        for parent, dirs, files in os.walk(directory, followlinks=False):
            for name in dirs + files:
                path = Path(parent) / name
                rel = str(path.relative_to(directory))
                require(rel in tree, f"Unexpected installed file: {path}")
                record = tree[rel]
                self.metadata(path, record["kind"], record.get("mode"))
                if record["kind"] == "file":
                    with path.open("rb") as stream:
                        require(
                            sha256(stream) == record["sha256"], f"Installed hash mismatch: {path}"
                        )
                elif record["kind"] == "link":
                    require(os.readlink(path) == record["target"], f"Unexpected symlink: {path}")
                actual.add(rel)
        require(actual == set(tree), f"Incomplete installation: {directory}")

    def verify_version(self, pin):
        binary = self.root / pin["directory"] / pin["binary"]
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "XDG_CONFIG_HOME": "/nonexistent",
            "PYTHONDONTWRITEBYTECODE": "1",
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_NO_ENV_FILE": "1",
        }
        options = (
            {"user": self.runtime_user, "group": self.runtime_user, "extra_groups": []}
            if self.runtime_user
            else {}
        )
        result = subprocess.run(
            [str(binary), "--version"],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            **options,
        )
        expected = {"python": "Python ", "uv": "uv ", "node": "v", "pnpm": ""}[pin["tool"]] + pin[
            "version"
        ]
        # uv's version includes the official build commit and date.
        valid = result.stdout.strip() == expected
        if pin["tool"] == "uv":
            valid = result.stdout.strip() == expected + " (x86_64-unknown-linux-gnu)" or bool(
                re.fullmatch(
                    re.escape(expected) + r"( \([0-9a-f]+ \d{4}-\d{2}-\d{2}\))?",
                    result.stdout.strip(),
                )
            )
        require(result.returncode == 0 and valid, f"Wrong {pin['tool']} version")

    def inspect(self):
        self.parents()
        if self.root.exists():
            self.metadata(self.root, "dir", 0o755)
            require(
                set(p.name for p in self.root.iterdir()) <= set(self.known) | {"archives"},
                "Unknown toolchain installation or unfinished staging directory",
            )
            archives = self.root / "archives"
            if archives.exists() or archives.is_symlink():
                self.metadata(archives, "dir", 0o755)
                names = {name + ".tar": pin for name, pin in self.known.items()}
                for file in archives.iterdir():
                    require(file.name in names, "Unknown archive in toolchain")
                    self.model(names[file.name])
            # Verify all retained installations, including versions used by older releases.
            for name, pin in self.known.items():
                directory = self.root / name
                if directory.exists() or directory.is_symlink():
                    self.verify_tree(directory, self.model(pin))
                    self.verify_version(pin)
        return [
            pin for pin in self.selected.values() if not (self.root / pin["directory"]).exists()
        ]

    def install(self):
        missing = self.inspect()
        # Validate every archive before starting any extraction.
        models = {p["directory"]: self.model(p) for p in missing}
        for pin in missing:
            tree = models[pin["directory"]]
            staging = self.root / (".staging-" + pin["directory"])
            staging.mkdir(
                mode=0o700
            )  # Failure leaves evidence; never automatic cleanup/replacement.
            for name, record in sorted(
                tree.items(), key=lambda item: len(PurePosixPath(item[0]).parts)
            ):
                if record["kind"] == "dir":
                    (staging / name).mkdir(mode=0o755)
                    (staging / name).chmod(0o755)
            with tarfile.open(self.archive(pin)) as source:
                for name, record in tree.items():
                    path = staging / name
                    if record["kind"] == "file":
                        with source.extractfile(record["member"]) as src, path.open("xb") as dst:
                            while data := src.read(1024 * 1024):
                                dst.write(data)
                        path.chmod(record["mode"])
                    elif record["kind"] == "link":
                        path.symlink_to(record["target"])
            staging.chmod(0o755)
            self.verify_tree(staging, tree)
            staging.rename(self.root / pin["directory"])
            self.verify_version(pin)
        self.inspect()
        return bool(missing)

    def paths(self):
        return {
            tool: str(self.root / pin["directory"] / pin["binary"])
            for tool, pin in self.selected.items()
        }


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "catalog": {"type": "dict", "required": True},
            "manifest": {"type": "dict", "required": True},
            "state": {"choices": ["inspect", "install"], "default": "inspect"},
        },
        supports_check_mode=True,
    )
    try:
        chain = Toolchain(
            ROOT,
            module.params["catalog"],
            module.params["manifest"],
            platform.machine(),
            runtime_user="oklab",
        )
        missing = chain.inspect()
        changed = False
        if module.params["state"] == "install" and not module.check_mode:
            changed = chain.install()
            missing = []
        module.exit_json(
            changed=changed,
            missing=missing,
            paths=chain.paths(),
            plan=[f"{p['tool']} {p['version']} missing -> would install" for p in missing],
        )
    except (ValueError, OSError, KeyError, tarfile.TarError, subprocess.SubprocessError) as exc:
        module.fail_json(msg=f"Toolchain safety check failed: {exc}")


if __name__ == "__main__":
    main()
