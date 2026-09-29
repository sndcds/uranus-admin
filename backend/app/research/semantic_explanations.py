"""Deterministic presentation of validated evidence; never query-generated prose."""

from app.research.chunk_kinds import Kind
from app.research.semantic_contracts import EvidenceChunk, SemanticHit
from app.schemas.research import SemanticEvidence, SemanticExplanation

ASPECTS: dict[Kind, tuple[str, str]] = {
    "content": ("Inhalt", "Der Inhalt passt zur Suchanfrage."),
    "participation": (
        "Teilnahme & Mitmachen",
        "Die Angaben zur Teilnahme oder zum Mitmachen passen zur Suchanfrage.",
    ),
    "accessibility": (
        "Barrierefreiheit",
        "Die Angaben zur Barrierefreiheit passen zur Suchanfrage.",
    ),
    "tickets": (
        "Tickets & Anmeldung",
        "Die Ticket- oder Anmeldeinformationen passen zur Suchanfrage.",
    ),
    "additional": (
        "Weitere Informationen",
        "Zusätzliche öffentliche Informationen passen zur Suchanfrage.",
    ),
    "facilities": (
        "Ausstattung & Nutzung",
        "Die Angaben zur Ausstattung oder Nutzung des Ortes passen zur Suchanfrage.",
    ),
    "location_context": ("Ort & Umgebung", "Der Orts- und Umgebungskontext passt zur Suchanfrage."),
    "activities": ("Aktivitäten", "Die beschriebenen Aktivitäten passen zur Suchanfrage."),
    "categories": ("Kategorien", "Die Kategorien passen zur Suchanfrage."),
}


def evidence(chunk: EvidenceChunk) -> SemanticEvidence:
    return SemanticEvidence(
        kind=chunk.chunk_kind, label=ASPECTS[chunk.chunk_kind][0], text=chunk.chunk_text
    )


def explain(hit: SemanticHit) -> SemanticExplanation:
    """Call only after authoritative eligibility and evidence context validation."""
    label, reason = ASPECTS[hit.winning_chunk.chunk_kind]
    return SemanticExplanation(
        score=hit.score,
        matched_aspect=hit.winning_chunk.chunk_kind,
        matched_aspect_label=label,
        reason=reason,
        evidence=evidence(hit.winning_chunk),
        supporting_evidence=[evidence(chunk) for chunk in hit.supporting_chunks],
    )
