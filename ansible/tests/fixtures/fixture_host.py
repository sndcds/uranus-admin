"""Test-only host adapter: records actions in a temporary JSON file; no host services/HTTP."""

import json
from pathlib import Path

from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        path = Path(task_vars["fixture_state"])
        state = json.loads(path.read_text())
        args = dict(self._task.args)
        kind = args.pop("kind")
        name = self._task.name
        event = {
            "kind": kind,
            "task": name,
            "maintenance_active": Path(state["marker"]).is_file(),
            "public_maintenance": Path(state["marker"]).is_file()
            and state["loaded_maintenance_capable"],
            "maintenance_files_ready": all(
                (Path(state["maintenance"]) / f).is_file()
                for f in [
                    "maintenance.html",
                    "assets/lottie.min.js",
                    "assets/maintenance.json",
                    "assets/maintenance.js",
                ]
            ),
        }
        result = {"changed": False}
        if kind == "command" and args.get("argv", [""])[0] == "systemctl":
            unit = args["argv"][2]
            previous = state["services"][unit]
            result["stdout"] = (
                "LoadState=loaded\nActiveState="
                + ("active" if previous["active"] else "inactive")
                + "\nUnitFileState="
                + previous["unit_file_state"]
            )
            result["rc"] = 0
            event["unit"] = unit
        elif kind == "command" and args.get("argv", [""])[0] == "/usr/bin/pgrep":
            result.update(rc=0, stdout_lines=["12345"])
        elif name in state["fail_tasks"]:
            result.update(failed=True, msg="Injected local fixture failure", status=502, rc=1)
        elif kind == "systemd":
            manifests = list(Path(state["config_dir"]).glob("recovery/*/attempt-*/manifest.json"))
            if not manifests:
                return {"failed": True, "msg": "Service mutation before recovery preparation"}
            event["snapshot_prepared"] = True
            if not any(e["kind"] == "systemd" for e in state["events"]):
                metadata = json.loads(manifests[-1].read_text())
                for entry in metadata["files"]:
                    if (
                        entry["exists"]
                        and Path(entry["backup"]).read_text() != state["originals"][entry["path"]]
                    ):
                        return {
                            "failed": True,
                            "msg": "Recovery contents do not match pre-mutation files",
                        }
                event["backups_match_originals"] = True
            if "name" in args:
                unit = args["name"]
                event.update(unit=unit, state=args.get("state"), enabled=args.get("enabled"))
                if unit == "nginx.service" and args.get("state") == "reloaded":
                    state["loaded_maintenance_capable"] = (
                        "error_page 503 =503 /__maintenance.html;"
                        in Path(state["nginx_site"]).read_text()
                    )
                if "state" in args:
                    state["services"][unit]["active"] = args["state"] != "stopped"
                if "enabled" in args:
                    state["services"][unit]["unit_file_state"] = (
                        "enabled" if args["enabled"] else "disabled"
                    )
            result["changed"] = True
        elif kind == "uri":
            event["pointer"] = str(Path(state["current"]).resolve())
            result["status"] = (
                503 if args["url"].startswith("https://") and event["public_maintenance"] else 200
            )
            if result["status"] == 503:
                result.update(
                    content=(Path(state["maintenance"]) / "maintenance.html").read_text(),
                    retry_after=str(task_vars["ua_maintenance_retry_after"]),
                    cache_control="no-store",
                )
        else:
            result.update(rc=0, stdout="Candidate valid")
        state["events"].append(event)
        path.write_text(json.dumps(state))
        return result
