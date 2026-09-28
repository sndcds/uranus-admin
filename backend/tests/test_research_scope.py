"""Explicit regional inventory and restartable, bounded operator dispatch."""

from unittest.mock import AsyncMock

import pytest

from app.errors import APIError
from app.research import scope
from app.research.catalog import CatalogEntry


def test_danish_inventory_contains_only_syddanmark_municipalities():
    entries = scope.inventory(None, ["DK-83"])
    assert len(entries) == 22
    assert len({entry.osm_id for entry in entries}) == 22
    assert {entry.region for entry in entries} == {"DK-83"}
    assert {entry.code for entry in entries}.isdisjoint({"100", "411", "997", "956", "11"})
    assert next(entry for entry in entries if entry.code == "580").osm_id == 1928466
    assert next(entry for entry in entries if entry.code == "540").name == "Sønderborg"


def test_german_inventory_requires_complete_selected_regions(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text("region_code,ags,name\nDE-SH,01001000,Flensburg\nDE-HH,02000000,Hamburg\n")
    assert scope.inventory(path, ["DE-SH"]) == [scope.ScopeEntry("DE-SH", "01001000", "Flensburg")]
    with pytest.raises(ValueError):
        scope.inventory(path, [])
    with pytest.raises(ValueError):
        scope.inventory(None, ["DE-SH"])
    with pytest.raises(ValueError):
        scope.inventory(path, ["DE-BY"])


@pytest.mark.parametrize("apply", [False, True])
async def test_plan_and_apply_share_validation_and_report_rejections(settings, monkeypatch, apply):
    counts = {"found": 1, "new": 1, "updated": 0, "unchanged": 0, "rejected": 0}
    rejected = {**counts, "new": 0, "rejected": 1}
    run = AsyncMock(side_effect=[counts, rejected])
    monkeypatch.setattr(scope, "run", run)
    events = []
    entries = [
        scope.ScopeEntry("DE-SH", "01001000", "Flensburg"),
        scope.ScopeEntry("DK-83", "580", "Aabenraa", 1928466),
    ]
    totals = await scope.run_scope(settings, entries, apply=apply, offset=7, report=events.append)
    assert [event["offset"] for event in events] == [7, 8]
    assert totals == {"DE-SH": counts, "DK-83": rejected}
    assert run.call_args_list[0].args == (
        settings,
        "DE-SH",
        [],
        [],
        apply,
        [CatalogEntry("DE-SH", "01001000", "Flensburg")],
    )
    assert run.call_args_list[1].args == (settings, "DK-83", [], [1928466], apply, None)
    assert events[1]["rejected"] == 1


async def test_outage_stops_scope_without_success_or_later_mutations(settings, monkeypatch):
    error = APIError(503, "geo_provider_unavailable", "Geo provider is unavailable.")
    run = AsyncMock(side_effect=error)
    monkeypatch.setattr(scope, "run", run)
    events = []
    with pytest.raises(APIError):
        await scope.run_scope(
            settings, scope.inventory(None, ["DK-83"]), apply=True, offset=0, report=events.append
        )
    assert run.await_count == 1 and events == []
