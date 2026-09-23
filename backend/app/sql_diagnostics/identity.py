"""Resolve canonical live identities only against the fixed diagnostic registry."""

from urllib.parse import quote, unquote

from app.errors import APIError
from app.sql_diagnostics.models import StoredFinding
from app.sql_diagnostics.registry import parameters_for


def live_finding(identity: str) -> StoredFinding:
    parts = identity.split(":")
    if len(parts) != 4:
        raise APIError(422, "diagnostic_invalid_finding", "Invalid finding identity.")
    rule, kind, key, field = (unquote(part) for part in parts)
    if identity != ":".join(quote(part, safe="") for part in (rule, kind, key, field)):
        raise APIError(422, "diagnostic_invalid_finding", "Invalid finding identity.")
    # The ID selects a registered recipe and typed UUID parameters, never SQL or
    # identifiers. A live request makes no claim about stored or observed evidence.
    finding = StoredFinding(identity, rule, kind, key, field, None)
    parameters_for(finding)
    return finding


def diagnostic_available(finding: StoredFinding) -> bool:
    try:
        parameters_for(finding)
    except APIError:
        return False
    return True
