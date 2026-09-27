"""Synthetic operator review fixtures; no source, model, network or database access."""

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.research.vector_benchmark import quality_metrics

SCRIPT = Path(__file__).resolve().parents[2] / "deploy/research-ai/review-benchmark.py"
spec = importlib.util.spec_from_file_location("review_benchmark", SCRIPT)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def row(**changes):
    return {
        "query_id": "q1",
        "query": "Sprachkurse",
        "model": "MODEL_HIDDEN",
        "rank": 1,
        "entity_id": "event1",
        "event_title": "Sprachkurs",
        "chunk_kind": "content",
        "review_excerpt": "Dänisch lernen – gemeinsam",
        "score": 0.987654321,
        "manual_relevance": "",
        **changes,
    }


def write_results(tmp_path, rows=None):
    directory = tmp_path / "inputs"
    path = directory / "model" / "results.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(rows if rows is not None else [row()]), encoding="utf-8")
    return directory, path


def test_pool_unique_pairs_blind_fields_and_stable_order():
    rows = [row(), row(model="second"), row(entity_id="event2", rank=2), row(query_id="q2")]
    pooled = review.pool(rows)
    assert len(pooled) == 3
    assert {(r["query_id"], r["entity_id"]) for r in pooled} == {
        ("q1", "event1"),
        ("q1", "event2"),
        ("q2", "event1"),
    }
    assert all(
        set(r)
        == {"query_id", "query", "entity_id", "event_title", "chunk_kinds", "review_excerpts"}
        for r in pooled
    )
    assert pooled[0]["review_excerpts"] == [row()["review_excerpt"]]
    assert review.pool(list(reversed(rows))) == pooled == review.pool(rows)
    changed = [{**r, "model": r["model"] + "changed", "score": 0.1} for r in rows]
    assert review.pool(changed) == pooled


def test_pool_keeps_all_winning_excerpts_without_model_prefix():
    rows = [
        row(review_excerpt="passage: Dänisch lernen"),
        row(model="second", review_excerpt="Dänisch lernen"),
        row(model="third", chunk_kind="tickets", review_excerpt="Tickets: kostenlos"),
    ]
    item = review.pool(rows)[0]
    assert item["review_excerpts"] == ["Dänisch lernen", "Tickets: kostenlos"]
    assert item["chunk_kinds"] == ["content", "tickets"]


def test_existing_grades_apply_to_every_model_and_unjudged_stays_empty():
    rows = [row(manual_relevance="2"), row(model="second"), row(entity_id="event2", rank=2)]
    grades = review.existing_grades(rows)
    assert grades == {("q1", "event1"): 2}
    judged = review.apply_grades(rows, grades)
    assert [r["manual_relevance"] for r in judged] == [2, 2, ""]
    assert rows[1]["manual_relevance"] == ""
    assert quality_metrics(judged) is None
    assert review.apply_grades([row()], {})[0]["manual_relevance"] == ""
    assert review.apply_grades([row(manual_relevance=0)], {})[0]["manual_relevance"] == 0


@pytest.mark.parametrize("grade", [True, False, 1.0, 1.5, -1, 3, "2.1", " 2", "s", [], {}])
def test_invalid_grades_rejected_at_every_entrypoint(grade):
    with pytest.raises(ValueError, match="grade"):
        review.validate_rows([row(manual_relevance=grade)])
    with pytest.raises(ValueError, match="grade"):
        review.existing_grades([row(manual_relevance=grade)])
    with pytest.raises(ValueError, match="grade"):
        review.apply_grades([row()], {("q1", "event1"): grade})


@pytest.mark.parametrize("grade", [None, ""])
def test_blank_grade_is_unjudged(grade):
    assert review.existing_grades([row(manual_relevance=grade)]) == {}
    with pytest.raises(ValueError, match="grade"):
        review.apply_grades([row()], {("q1", "event1"): grade})


def test_conflicting_grades_titles_and_query_text_fail():
    for changes, message in [
        ({"manual_relevance": 0}, "conflicting_relevance_grade"),
        ({"event_title": "different"}, "conflicting_event_title"),
        ({"query": "different"}, "conflicting_query_text"),
    ]:
        with pytest.raises(ValueError, match=message):
            review.pool([row(manual_relevance=2), row(model="second", **changes)])
    with pytest.raises(ValueError, match="conflicting"):
        review.apply_grades([row(manual_relevance=0)], {("q1", "event1"): 2})


def test_missing_excerpt_clearly_rejected(tmp_path):
    old = row()
    del old["review_excerpt"]
    directory, _ = write_results(tmp_path, [old])
    with pytest.raises(ValueError, match="missing_review_excerpt: rerun benchmark"):
        review.load_rows(directory)


@pytest.mark.parametrize(
    "changes",
    [
        {"review_excerpt": ""},
        {"review_excerpt": "x" * 1201},
        {"query": "x" * 501},
        {"event_title": {}},
        {"entity_id": 123},
        {"rank": True},
        {"rank": 1.5},
        {"rank": "1"},
        {"rank": 11},
        {"score": float("inf")},
        {"score": 10**400},
        {"score": True},
        {"chunk_kind": "MODEL_HIDDEN"},
        {"review_excerpt": "\ud800"},
    ],
)
def test_invalid_fields_rejected(changes):
    with pytest.raises(ValueError):
        review.validate_rows([row(**changes)])


def test_duplicate_or_gapped_rankings_rejected():
    for rows in ([row(), row()], [row(rank=2)], [row(), row(rank=2)]):
        with pytest.raises(ValueError, match="ranking"):
            review.pool(rows)


def test_safe_json_and_bounds(tmp_path, monkeypatch):
    directory, path = write_results(tmp_path, [row(internal_note="NOT_EXPORTED")])
    assert "internal_note" not in review.load_rows(directory)[0]
    original = path.read_bytes()
    for value in (b"{", b"null", b"{}", b"[1]", b"[NaN]", b'[{"a":1,"a":2}]', b"\xff"):
        path.write_bytes(value)
        with pytest.raises(ValueError):
            review.load_rows(directory)
    path.write_bytes(original)
    with pytest.raises(ValueError, match="file_limit"):
        review.read_json(path, limit=1)
    with pytest.raises(ValueError, match="invalid_results_file"):
        review.validate_rows([row()] * (review.MAX_ROWS + 1))
    second = directory / "second" / "results.json"
    second.parent.mkdir()
    second.write_bytes(original)
    monkeypatch.setattr(review, "MAX_INPUT_BYTES", len(original) + 1)
    with pytest.raises(ValueError, match="file_limit"):
        review.load_rows(directory)
    monkeypatch.setattr(review, "MAX_RESULTS_FILES", 1)
    with pytest.raises(ValueError, match="bounded_model_results"):
        review.load_rows(directory)
    monkeypatch.setattr(review, "MAX_DIRECTORY_ENTRIES", 1)
    with pytest.raises(ValueError, match="directory_limit"):
        review.load_rows(directory)


def test_resume_requires_same_results_and_consistent_grades(tmp_path):
    rows = [row(), row(model="second")]
    path = tmp_path / "pooled-results.json"
    assert review.load_existing_output(path, rows) == {}
    review.atomic_write(path, review.apply_grades(rows, {("q1", "event1"): 2}))
    assert review.load_existing_output(path, list(reversed(rows))) == {("q1", "event1"): 2}
    with pytest.raises(ValueError, match="conflicting_existing_judgment"):
        review.load_existing_output(path, [row(manual_relevance=0), row(model="second")])
    for changed in (
        [row()],
        [row(query="changed"), row(model="second")],
        [row(review_excerpt="changed"), row(model="second")],
    ):
        with pytest.raises(ValueError, match="does_not_match"):
            review.load_existing_output(path, changed)
    review.atomic_write(path, [row(manual_relevance=True)])
    with pytest.raises(ValueError, match="grade"):
        review.load_existing_output(path, [row()])


def test_atomic_private_write_failure_preserves_old_file(tmp_path, monkeypatch):
    path = tmp_path / "pooled-results.json"
    review.atomic_write(path, [row()])
    original = path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600

    def fail(*args):
        raise OSError("synthetic_failure")

    monkeypatch.setattr(review.os, "replace", fail)
    with pytest.raises(OSError):
        review.atomic_write(path, [row(manual_relevance=2)])
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
    monkeypatch.setattr(review, "MAX_INPUT_BYTES", 1)
    with pytest.raises(ValueError, match="judgments_file_limit"):
        review.atomic_write(path, [row()])
    assert path.read_bytes() == original


def test_symlinks_and_special_files_rejected(tmp_path):
    directory, path = write_results(tmp_path)
    target = tmp_path / "target.json"
    target.write_text("[]")
    link = tmp_path / "output.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        review.atomic_write(link, [row()])
    with pytest.raises(ValueError, match="symlink"):
        review.load_existing_output(link, [row()])
    assert target.read_text() == "[]" and link.is_symlink()
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        review.load_rows(directory)
    parent_link = tmp_path / "linked"
    parent_link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        review.atomic_write(parent_link / "new.json", [])
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="file_limit"):
        review.read_json(fifo)


def test_prompt_is_blind_and_terminal_safe(monkeypatch, capsys):
    item = review.pool([row(review_excerpt="passage: Dänisch\nlernen\x1b\u202e")])[0]
    monkeypatch.setattr(sys, "stdin", io.StringIO("invalid\n2\n"))
    assert review.prompt(item, 1, 1) == "2"
    output = capsys.readouterr().out
    assert "Sprachkurse" in output and "Sprachkurs" in output and "Dänisch" in output
    assert all(
        hidden not in output
        for hidden in ("MODEL_HIDDEN", "0.987654321", "passage:", "rank", "score", "\x1b", "\u202e")
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("x" * 100))
    with pytest.raises(ValueError, match="answer_limit"):
        review.prompt(item, 1, 1)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert review.prompt(item, 1, 1) == "q"


def test_cli_skip_quit_resume_and_evaluate(tmp_path):
    directory, first = write_results(tmp_path, [row(), row(rank=2, entity_id="event2")])
    second = directory / "second" / "results.json"
    second.parent.mkdir()
    second.write_text(json.dumps([row(model="second")]))
    originals = (first.read_bytes(), second.read_bytes())
    output = tmp_path / "pooled-results.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "--results-dir",
        str(directory),
        "--output",
        str(output),
    ]
    skipped = subprocess.run(command, input="s\nq\n", text=True, capture_output=True, check=True)
    assert "MODEL_HIDDEN" not in skipped.stdout and "0.987654321" not in skipped.stdout
    rows = json.loads(output.read_text())
    assert all(r["manual_relevance"] == "" for r in rows)
    subprocess.run(command, input="2\nq\n", text=True, capture_output=True, check=True)
    assert len(review.existing_grades(json.loads(output.read_text()))) == 1
    resumed = subprocess.run(command, input="0\n", text=True, capture_output=True, check=True)
    assert "1 noch unbewertet" in resumed.stdout
    rows = json.loads(output.read_text())
    assert len(review.existing_grades(rows)) == 2
    metrics = quality_metrics(rows)
    assert "MODEL_HIDDEN:ndcg_at_10" in metrics and "second:ndcg_at_10" in metrics
    result = subprocess.run(
        [sys.executable, "-m", "app.research.vector_index", "evaluate", "--judgments", str(output)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == metrics
    assert (first.read_bytes(), second.read_bytes()) == originals
    rejected = subprocess.run(command[:-1] + [str(first)], input="", text=True, capture_output=True)
    assert rejected.returncode == 1 and "output_must_not_replace_input" in rejected.stderr
    assert first.read_bytes() == originals[0]
