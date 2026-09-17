from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.repositories.quality_sources import SOURCE_QUERIES, Sources
from app.schemas.finding import FindingFilters
from app.services.checks import persisted_counts, persisted_page, run_check
from app.services.quality.core import evaluate_core
from app.services.quality.engine import scan
from tests.conftest import uid

RULE = "postal_code_whitespace"
NOW = datetime(2026, 9, 17, 12, tzinfo=UTC)


@pytest.mark.parametrize("kind", ["organization", "venue"])
@pytest.mark.parametrize(
    "postal_code,expected",
    [
        (None, False),
        ("", False),
        ("24937", False),
        ("8000", False),
        ("SW1A 1AA", False),
        ("24 937", False),
        ("24\t937", False),
        (" 24937", True),
        ("24937 ", True),
        (" 24937 ", True),
        ("\t24937", True),
        ("24937\n", True),
        ("\r\n24937\t", True),
        (" SW1A 1AA ", True),
        (" 24\t937 ", True),
        (" \t\n", True),
        ("\u00a024937\u00a0", True),
    ],
)
def test_postal_code_contract(settings, kind, postal_code, expected):
    sources = Sources({kind: [] for kind in SOURCE_QUERIES})
    row = {"uuid": uid(20), "name": "Postal code owner", "postal_code": postal_code}
    sources.rows[kind] = [row]
    result = evaluate_core(RULE, sources, settings, NOW)
    assert result.covered == {(kind, str(uid(20)))}
    assert len(result.findings) == int(expected)
    assert row["postal_code"] == postal_code
    if expected:
        finding = result.findings[0]
        assert finding.id == f"{RULE}:{kind}:{uid(20)}:postal_code"
        assert finding.rule == RULE and finding.entity_type == kind
        assert finding.entity_key == str(uid(20))
        assert finding.field == "postal_code" and finding.severity == "warning"
        assert finding.entity_name == row["name"]
        assert finding.message == "Postleitzahl enthält führende oder abschließende Leerzeichen."
        assert finding.metadata["reason"] == "leading_or_trailing_whitespace"
        assert set(finding.metadata) == {"reason", "source_fingerprint"}
        assert finding.address.postal_code is None
        section = "venues" if kind == "venue" else "organizations"
        assert finding.action.href == f"/{section}/{uid(20)}"


@pytest.mark.integration
@pytest.mark.parametrize("kind,key", [("organization", 10), ("venue", 20)])
async def test_postal_code_persistence_resolution_and_failed_runs(
    admin_store, db_connection, settings, now, monkeypatch, kind, key
):
    source_update = text(f"UPDATE uranus.{kind} SET postal_code=:value WHERE uuid=:key")
    await db_connection.execute(source_update, {"value": "24937 ", "key": uid(key)})
    filters = FindingFilters(rule=RULE)
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    page = await persisted_page(admin_store, filters, now)
    # Existing events and dates referencing this owner must not multiply the finding.
    assert page.pagination.total == 1
    item = page.items[0]
    assert item.status == "open" and item.entity_type == kind
    assert item.entity_key == str(uid(key)) and item.severity == "warning"
    assert "published_soon" in item.priority_reasons
    counts, _ = await persisted_counts(admin_store)
    assert counts.rule_counts[RULE] == 1
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    assert (await persisted_page(admin_store, filters, now)).pagination.total == 1

    await db_connection.execute(source_update, {"value": "24937", "key": uid(key)})

    async def failed(*args):
        raise RuntimeError("Synthetic source scan failure")

    async def incomplete(*args):
        return (await scan(*args))[:-1]

    async def unsuccessful_rule(*args):
        results = await scan(*args)
        results[-1].success = False
        return results

    for replacement in (failed, incomplete, unsuccessful_rule):
        with monkeypatch.context() as patch:
            patch.setattr("app.services.checks.scan", replacement)
            assert (await run_check(db_connection, admin_store, settings)).status == "failed"
        assert (await persisted_page(admin_store, filters, now)).items[0].status == "open"
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    resolved = (await persisted_page(admin_store, filters, now)).items[0]
    assert resolved.id == item.id and resolved.status == "resolved" and resolved.resolved_at
    assert resolved.first_seen_at == item.first_seen_at
    counts, _ = await persisted_counts(admin_store)
    assert counts.rule_counts[RULE] == 0
