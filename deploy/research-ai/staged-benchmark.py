"""Run the explicitly approved pilot stages with persisted plans and smoke exports."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("model", choices=("e5-small", "e5-base", "jina-v3"))
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
wrapper = Path(__file__).with_name("run-indexer.py")
base = [sys.executable, str(wrapper)]
model_args = ["--model", args.model]
if args.model == "jina-v3":
    model_args.append("--noncommercial-jina")
root = args.output / args.model
root.mkdir(parents=True, exist_ok=False, mode=0o700)
for stage, limit in [("10", ["--limit", "10"]), ("100", ["--limit", "100"]), ("full", [])]:
    for command in ("plan", "sync"):
        output = root / (command + "-" + stage)
        subprocess.run(
            base + [command] + model_args + limit + ["--output", str(output)], check=True
        )
        report = json.loads((output / "run.json").read_text())
        if command == "plan" and (report["events_selected"] == 0 or report["events_total"] > 10000):
            raise SystemExit("Unexpected source counts; stopped before writes")
    # Query smoke for every stage verifies actual retrieval and unique public event IDs.
    output = root / ("benchmark-" + stage)
    subprocess.run(
        base
        + ["benchmark"]
        + model_args
        + limit
        + [
            "--questions",
            "../docs/research-ai/event-retrieval-benchmark.json",
            "--output",
            str(output),
        ],
        check=True,
    )
    rows = json.loads((output / "results.json").read_text())
    for query in {r["query_id"] for r in rows}:
        hits = [r for r in rows if r["query_id"] == query]
        if len(hits) != 10 or len({r["entity_id"] for r in hits}) != 10:
            raise SystemExit("Smoke retrieval did not produce ten distinct events")
    print(json.dumps({"stage_complete": stage, "model": args.model}), flush=True)
output = root / "reconcile-repeat"
subprocess.run(base + ["reconcile"] + model_args + ["--output", str(output)], check=True)
report = json.loads((output / "run.json").read_text())
if report["new"] or report["updated"] or report["metadata_updated"] or report["deleted"]:
    raise SystemExit("Repeat reconciliation was not unchanged")
