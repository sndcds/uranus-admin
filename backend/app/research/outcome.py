"""Execution output without the transport envelope; assembled into HTTP at the API edge."""

from dataclasses import dataclass
from datetime import datetime

from app.schemas.research_execution import (
    ExecutionDiagnostics,
    ExecutionProvenance,
    ExecutionResult,
    ResolvedField,
)


@dataclass(frozen=True, slots=True)
class ResearchExecutionOutcome:
    resolution: list[ResolvedField]
    result: ExecutionResult
    execution: ExecutionProvenance
    observed_at: datetime
    diagnostics: ExecutionDiagnostics
