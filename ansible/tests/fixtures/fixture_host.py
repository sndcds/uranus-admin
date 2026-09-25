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
            previous = state["services"].get(unit)
            if name in state["fail_tasks"]:
                result.update(rc=1, stdout="", failed=True, msg="Injected local fixture failure")
                state["events"].append(event)
                path.write_text(json.dumps(state))
                return result
            if args["argv"][1] in {"is-enabled", "is-active"}:
                value = (
                    (
                        previous["unit_file_state"]
                        if args["argv"][1] == "is-enabled"
                        else "active"
                        if previous["active"]
                        else "inactive"
                    )
                    if previous
                    else "not-found"
                )
                result.update(rc=0 if value in {"enabled", "active"} else 1, stdout=value)
                event.update(unit=unit, operation=args["argv"][1])
                state["events"].append(event)
                path.write_text(json.dumps(state))
                return result
            if previous is None:
                result.update(
                    rc=4, stdout="LoadState=not-found\nActiveState=inactive\nUnitFileState="
                )
                if "--value" in args["argv"]:
                    result["stdout"] = "not-found"
                state["events"].append(event)
                path.write_text(json.dumps(state))
                return result
            result["stdout"] = (
                "LoadState=loaded\nActiveState="
                + ("active" if previous["active"] else "inactive")
                + "\nUnitFileState="
                + previous["unit_file_state"]
            )
            if "--value" in args["argv"]:
                result["stdout"] = "loaded"
            result["rc"] = 0
            event["unit"] = unit
        elif kind == "command" and args.get("argv", [""])[0] == "/usr/bin/pgrep":
            result.update(rc=0, stdout_lines=["12345"])
        elif name in state["fail_tasks"] and not (
            name == "Check public HTTP 503 maintenance content and headers"
            and state["maintenance_responses"]
        ):
            result.update(failed=True, msg="Injected local fixture failure", status=502, rc=1)
        elif kind == "service_facts":
            result["ansible_facts"] = {
                "services": {
                    name: {"state": "running" if values["active"] else "stopped"}
                    for name, values in state["services"].items()
                }
            }
        elif kind == "systemd":
            manifests = list(Path(state["config_dir"]).glob("recovery/*/attempt-*/manifest.json"))
            if not manifests:
                return {"failed": True, "msg": "Service mutation before recovery preparation"}
            event["snapshot_prepared"] = True
            if args.get("daemon_reload"):
                for unit in state.get("app_units", []):
                    if (Path(state["unit_dir"]) / unit).is_file():
                        state["services"].setdefault(
                            unit,
                            {
                                "active": False,
                                "unit_file_state": "static"
                                if unit
                                in {
                                    "uranus-admin-notification-worker.service",
                                    "uranus-admin-geocode-worker.service",
                                }
                                else "disabled",
                            },
                        )
                    elif unit in state["services"] and not state["services"][unit]["active"]:
                        state["services"].pop(unit)
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
                    capable = (
                        Path(state["nginx_site"]).is_file()
                        and "error_page 503 =503 /__maintenance.html;"
                        in Path(state["nginx_site"]).read_text()
                    )
                    if name == "Reload nginx for maintenance activation":
                        # Reload returns before old workers finish using their old config.
                        state["pending_maintenance_capable"] = capable
                    else:
                        state["loaded_maintenance_capable"] = capable
                if "state" in args:
                    state["services"][unit]["active"] = args["state"] != "stopped"
                if "enabled" in args:
                    state["services"][unit]["unit_file_state"] = (
                        "enabled" if args["enabled"] else "disabled"
                    )
            result["changed"] = True
        elif kind == "wait_for":
            state["loaded_maintenance_capable"] = state.pop("pending_maintenance_capable")
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
            if name == "Check public HTTP 503 maintenance content and headers":
                responses = state["maintenance_responses"]
                if responses:
                    index = state.get("maintenance_response_index", 0)
                    result.update(responses[min(index, len(responses) - 1)])
                    state["maintenance_response_index"] = index + 1
                event["response_status"] = result["status"]
                # Match uri failure for an unexpected status; failed_when also checks content.
                result["failed"] = result["status"] != args["status_code"]
        else:
            result.update(rc=0, stdout="Candidate valid")
        state["events"].append(event)
        path.write_text(json.dumps(state))
        return result
