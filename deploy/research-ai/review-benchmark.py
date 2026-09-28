#!/usr/bin/env python3
"""Model-blind, resumable manual review of */results.json benchmark exports.

Only the standard library is needed. Run one reviewer in an operator-owned directory.
The output retains model rows for vector_index evaluate; the prompt never shows them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 8_000_000  # Also the evaluate CLI's output-file limit.
MAX_RESULTS_FILES = 20
MAX_DIRECTORY_ENTRIES = 1000
MAX_ROWS = 20_000
VALID_GRADES = {"0", "1", "2"}
TEXT_LIMITS = {
    "query_id": 50,
    "query": 500,
    "model": 200,
    "entity_id": 100,
    "event_title": 4000,
    "chunk_kind": 32,
    "review_excerpt": 1200,
}
CHUNK_KINDS = {"content", "participation", "accessibility", "tickets", "additional"}


def grade_value(raw: object) -> int | None:
    if raw is None or raw == "":
        return None
    if type(raw) not in (str, int) or str(raw) not in VALID_GRADES:
        raise ValueError("invalid_relevance_grade")
    return int(str(raw))


def no_symlinks(path: Path) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("symlink_not_allowed")


def read_json(path: Path, limit: int = MAX_INPUT_BYTES) -> tuple[object, int]:
    no_symlinks(path)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("results_file_limit")
        data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError("results_file_limit")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError("nonfinite_json_number")

    try:
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant
        ), len(data)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_results_json") from exc


def validate_rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        raise ValueError("invalid_results_file")
    rows = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("invalid_result_row")
        if "review_excerpt" not in row:
            raise ValueError("missing_review_excerpt: rerun benchmark in a fresh directory")
        for key, limit in TEXT_LIMITS.items():
            text = row.get(key)
            if not isinstance(text, str) or not text.strip() or len(text) > limit:
                raise ValueError("invalid_result_text")
            # Reject lone surrogates before terminal output or UTF-8 persistence.
            try:
                text.encode("utf-8")
            except UnicodeError as exc:
                raise ValueError("invalid_result_text") from exc
        if row["chunk_kind"] not in CHUNK_KINDS:
            raise ValueError("invalid_chunk_kind")
        if type(row.get("rank")) is not int or not 1 <= row["rank"] <= 10:
            raise ValueError("invalid_result_rank")
        if "manual_relevance" not in row:
            raise ValueError("missing_relevance_grade")
        grade_value(row["manual_relevance"])
        # Preserve only benchmark columns, never arbitrary payload/notes.
        checked = {key: row[key] for key in (*TEXT_LIMITS, "rank", "manual_relevance")}
        for key in ("score", "query_latency_seconds"):
            if key in row:
                number = row[key]
                if (
                    type(number) not in (int, float)
                    or abs(number) > 1e308
                    or not math.isfinite(number)
                ):
                    raise ValueError("invalid_result_number")
                checked[key] = number
        for key in ("language", "event_language"):
            if key in row:
                if row[key] is not None and (not isinstance(row[key], str) or len(row[key]) > 50):
                    raise ValueError("invalid_result_language")
                checked[key] = row[key]
        rows.append(checked)
    return rows


def load_rows(results_dir: Path) -> list[dict[str, Any]]:
    no_symlinks(results_dir)
    paths = []
    # Bound directory traversal as well as file count and aggregate input bytes.
    with os.scandir(results_dir) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_DIRECTORY_ENTRIES:
                raise ValueError("results_directory_limit")
            if entry.is_symlink():
                raise ValueError("symlink_not_allowed")
            candidate = Path(entry.path) / "results.json"
            if entry.is_dir(follow_symlinks=False) and (
                candidate.exists() or candidate.is_symlink()
            ):
                paths.append(candidate)
                if len(paths) > MAX_RESULTS_FILES:
                    raise ValueError("expected_bounded_model_results")
    if not paths:
        raise ValueError("expected_bounded_model_results")
    rows: list[dict[str, Any]] = []
    remaining = MAX_INPUT_BYTES
    for path in sorted(paths):
        value, size = read_json(path, remaining)
        remaining -= size
        rows.extend(validate_rows(value))
        if len(rows) > MAX_ROWS:
            raise ValueError("results_row_limit")
    if not rows:
        raise ValueError("empty_results")
    return rows


def existing_grades(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    grades: dict[tuple[str, str], int] = {}
    for row in rows:
        grade = grade_value(row.get("manual_relevance"))
        if grade is not None:
            key = (row["query_id"], row["entity_id"])
            if grades.setdefault(key, grade) != grade:
                raise ValueError("conflicting_relevance_grade")
    return grades


def load_existing_output(path: Path, rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    grades = existing_grades(rows)
    no_symlinks(path)
    if not path.exists():
        return grades
    value, _ = read_json(path)
    previous = validate_rows(value)

    def snapshot(items: list[dict[str, Any]]) -> list[str]:
        return sorted(
            json.dumps({k: v for k, v in row.items() if k != "manual_relevance"}, sort_keys=True)
            for row in items
        )

    if snapshot(previous) != snapshot(rows):
        raise ValueError("existing_review_does_not_match_results")
    for key, grade in existing_grades(previous).items():
        if grades.setdefault(key, grade) != grade:
            raise ValueError("conflicting_existing_judgment")
    return grades


def stable_pool_order(query_id: str, entity_id: str) -> str:
    return hashlib.sha256(json.dumps([query_id, entity_id]).encode()).hexdigest()


def pool(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = validate_rows(rows)
    existing_grades(rows)  # Conflicts must fail even before the first prompt.
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    query_text: dict[str, str] = {}
    titles: dict[str, str] = {}
    rankings: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        qid, entity_id = row["query_id"], row["entity_id"]
        if query_text.setdefault(qid, row["query"]) != row["query"]:
            raise ValueError("conflicting_query_text")
        if titles.setdefault(entity_id, row["event_title"]) != row["event_title"]:
            raise ValueError("conflicting_event_title")
        grouped[(qid, entity_id)].append(row)
        rankings[(row["model"], qid)].append(row)
    for items in rankings.values():
        if sorted(r["rank"] for r in items) != list(range(1, len(items) + 1)) or len(
            {r["entity_id"] for r in items}
        ) != len(items):
            raise ValueError("invalid_result_ranking")
    pooled = [
        {
            "query_id": qid,
            "query": query_text[qid],
            "entity_id": entity_id,
            "event_title": titles[entity_id],
            "chunk_kinds": sorted({r["chunk_kind"] for r in items}),
            # E5's transport prefix would disclose model family. Export stays exact.
            "review_excerpts": sorted(
                {r["review_excerpt"].removeprefix("passage: ") for r in items}
            ),
        }
        for (qid, entity_id), items in grouped.items()
    ]
    return sorted(
        pooled, key=lambda r: (r["query_id"], stable_pool_order(r["query_id"], r["entity_id"]))
    )


def apply_grades(
    rows: list[dict[str, Any]], grades: dict[tuple[str, str], int]
) -> list[dict[str, Any]]:
    merged = existing_grades(rows)
    for key, raw in grades.items():
        grade = grade_value(raw)
        if grade is None:
            raise ValueError("invalid_relevance_grade")
        if merged.setdefault(key, grade) != grade:
            raise ValueError("conflicting_relevance_grade")
    return [
        {**row, "manual_relevance": merged.get((row["query_id"], row["entity_id"]), "")}
        for row in rows
    ]


def atomic_write(path: Path, value: object) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    if len(payload) > MAX_INPUT_BYTES:
        raise ValueError("judgments_file_limit")
    no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=".review-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        no_symlinks(path)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def terminal_text(value: str) -> str:
    return "".join(
        " " if c.isspace() else c
        for c in value
        if c.isspace() or not unicodedata.category(c).startswith("C")
    )


def prompt(item: dict[str, Any], index: int, total: int) -> str:
    print("\n" + "=" * 72)
    print(f"Bewertung {index}/{total}")
    print("Query: " + terminal_text(item["query"]))
    print("Event: " + terminal_text(item["event_title"]))
    print("Gefundene Bereiche: " + ", ".join(item["chunk_kinds"]))
    print("\nTextausschnitte:")
    for excerpt in item["review_excerpts"]:
        print("- " + terminal_text(excerpt))
    print("\n2 = klar relevant; 1 = teilweise relevant; 0 = irrelevant")
    print("s = überspringen; q = speichern und beenden")
    while True:
        print("Bewertung: ", end="", flush=True)
        answer = sys.stdin.readline(32)
        if not answer:  # EOF, like q, preserves all completed judgments.
            return "q"
        if len(answer) == 32:
            raise ValueError("review_answer_limit")
        answer = answer.strip().lower()
        if answer in VALID_GRADES | {"s", "q"}:
            return answer
        print("Bitte 0, 1, 2, s oder q eingeben.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if (
        args.output.name == "results.json"
        and args.output.parent.parent.resolve() == args.results_dir.resolve()
    ):
        raise ValueError("output_must_not_replace_input")
    rows = load_rows(args.results_dir)
    items = pool(rows)
    grades = load_existing_output(args.output, rows)
    # Validate output capacity/permissions before accepting any human work.
    atomic_write(args.output, apply_grades(rows, grades))
    pending = [item for item in items if (item["query_id"], item["entity_id"]) not in grades]
    print(f"{len(items)} eindeutige Query/Event-Paare, {len(pending)} noch unbewertet.")
    print("Modellnamen, Ränge und Scores bleiben während der Bewertung verborgen.")
    try:
        for offset, item in enumerate(pending, 1):
            answer = prompt(item, offset, len(pending))
            if answer == "q":
                break
            if answer == "s":
                continue
            grades[(item["query_id"], item["entity_id"])] = int(answer)
            atomic_write(args.output, apply_grades(rows, grades))
    except KeyboardInterrupt:
        pass
    atomic_write(args.output, apply_grades(rows, grades))
    # Do not print paths, which can themselves contain model names.
    print(f"Gespeichert. Bewertet: {len(grades)}/{len(items)}; offen: {len(items) - len(grades)}")
    if len(grades) < len(items):
        print("Denselben Befehl erneut starten, um die Bewertung fortzusetzen.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        # OS exceptions can contain model directory names; don't echo them.
        print(str(exc) if isinstance(exc, ValueError) else "review_file_error", file=sys.stderr)
        raise SystemExit(1) from None
