"""Mask internal taxonomy choices only at the public response boundary."""

from app.schemas.research_execution import ExecutionResult


def public_execution_result(result: ExecutionResult) -> ExecutionResult:
    """Mask taxonomy choice IDs only at the HTTP edge, never in domain resolution."""
    if result.kind != "needs_clarification" or result.reason != "ambiguous":
        return result
    return result.model_copy(
        update={
            "candidates": [
                choice.model_copy(update={"id": f"choice-{i}"})
                if choice.entity_type in {"event_type", "genre"}
                else choice
                for i, choice in enumerate(result.candidates)
            ]
        }
    )
