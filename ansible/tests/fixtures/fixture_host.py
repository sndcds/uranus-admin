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
        event = {"kind": kind, "task": name}
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
        elif name in state["fail_tasks"]:
            result.update(failed=True, msg="Injected local fixture failure", status=503, rc=1)
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
                        and Path(entry["backup"]).read_bytes() != Path(entry["path"]).read_bytes()
                    ):
                        return {
                            "failed": True,
                            "msg": "Recovery contents do not match pre-mutation files",
                        }
                event["backups_match_originals"] = True
            if "name" in args:
                unit = args["name"]
                event.update(unit=unit, state=args.get("state"), enabled=args.get("enabled"))
                if "state" in args:
                    state["services"][unit]["active"] = args["state"] != "stopped"
                if "enabled" in args:
                    state["services"][unit]["unit_file_state"] = (
                        "enabled" if args["enabled"] else "disabled"
                    )
            result["changed"] = True
        elif kind == "uri":
            event["pointer"] = str(Path(state["current"]).resolve())
            result["status"] = 200
        else:
            result.update(rc=0, stdout="Candidate valid")
        state["events"].append(event)
        path.write_text(json.dumps(state))
        return result
