"""Offline relevance policy tests: synthetic scores, no embedding/model requests."""

import json
from pathlib import Path

import pytest

from app.research.semantic_limits import semantic_relevance_threshold


@pytest.mark.parametrize(
    "scores,expected_threshold,survivors",
    [
        ([0.275, 0.231, 0.174, 0.103, 0.058], 0.11, [0.275, 0.231, 0.174]),
        ([0.20, 0.12, 0.10], 0.10, [0.20, 0.12, 0.10]),
        ([0.09, 0.08], 0.10, []),
        ([0.9, 0.35], 0.36, [0.9]),
        ([0.15, 0.15, 0.15], 0.10, [0.15, 0.15, 0.15]),
        ([0.099999999, 0.100000001], 0.10, [0.100000001]),
        ([-0.2, 0.0], 0.10, []),
        ([], None, []),
    ],
)
def test_threshold(scores, expected_threshold, survivors):
    original = scores.copy()
    threshold = semantic_relevance_threshold(scores)
    if expected_threshold is None:
        assert threshold is None
    else:
        assert threshold == pytest.approx(expected_threshold)
    assert scores == original
    assert semantic_relevance_threshold(list(reversed(scores))) == threshold
    assert [s for s in scores if threshold is not None and s >= threshold] == survivors


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("position", [0, 1])
def test_nonfinite_score_fails_closed(invalid, position):
    scores = [0.3]
    scores.insert(position, invalid)
    with pytest.raises(ValueError, match="^invalid_semantic_relevance_score$"):
        semantic_relevance_threshold(scores)


CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "semantic_relevance_cases.json").read_text()
)


def test_offline_corpus_coverage():
    cases = CORPUS["cases"]
    assert 20 <= len(cases) <= 30
    assert len({case["query"] for case in cases}) == len(cases)
    assert CORPUS["score_source"] == "synthetic_final_context_valid_scores"
    for case in cases:
        assert {c["relevance"] for c in case["candidates"]} == {
            "clearly_relevant",
            "borderline",
            "irrelevant",
        }
        assert all(c["review_reason"] for c in case["candidates"])


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["id"])
def test_offline_review_expectations(case):
    candidates = case["candidates"]
    threshold = semantic_relevance_threshold([c["score"] for c in candidates])
    assert threshold == pytest.approx(case["expected_threshold"])
    assert threshold is not None
    assert [c["label"] for c in candidates if c["score"] >= threshold] == case["expected_kept"]
