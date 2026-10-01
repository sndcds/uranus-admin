"""Internal semantic execution bounds and relevance policy; no public request controls.

Matches the existing event-index scan budget (10,000 events), versus 576 public
events in the documented September 2026 audit. A complete UUID match-any list
costs about 400 KiB, comfortably within InternalHTTP's 2 MiB request budget.
"""

from math import isfinite

MAX_ELIGIBLE_EVENTS = 10_000

# Initial policy based on the reported weak-tail score series, not universal
# similarity calibration. See docs/semantic-relevance.md and the offline corpus.
SEMANTIC_ABSOLUTE_MIN_SCORE = 0.10
SEMANTIC_RELATIVE_MIN_RATIO = 0.40


def semantic_relevance_threshold(scores: list[float]) -> float | None:
    """Threshold final context-valid scores, without rounding or input mutation.

    Invalid scores fail closed; they must never produce an accepted selection.
    An absolute floor above the best score intentionally permits zero results.
    """
    if not scores:
        return None
    if any(not isfinite(score) for score in scores):
        raise ValueError("invalid_semantic_relevance_score")
    return max(SEMANTIC_ABSOLUTE_MIN_SCORE, max(scores) * SEMANTIC_RELATIVE_MIN_RATIO)
