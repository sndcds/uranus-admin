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


def test_complete_inventory_and_selective_regions(tmp_path):
    from collections import Counter

    from app.research.catalog import REGION_PREFIX

    path = tmp_path / "national.csv"
    path.write_text(
        "region_code,ags,name\n"
        + "".join(f"{region},{prefix}999999,Fixture\n" for prefix, region in REGION_PREFIX.items())
    )
    entries = scope.inventory(path, [])
    assert len(entries) == 16 + 98
    assert {entry.region for entry in entries} == scope.REGIONS.keys()
    assert entries == sorted(entries, key=lambda entry: (entry.region, entry.code))
    danish = scope.inventory(None, ["DK-81", "DK-82", "DK-83", "DK-84", "DK-85"])
    assert Counter(e.region for e in danish) == {
        "DK-81": 11,
        "DK-82": 19,
        "DK-83": 22,
        "DK-84": 29,
        "DK-85": 17,
    }
    assert len({e.code for e in danish}) == len({e.osm_id for e in danish}) == 98
    assert {e.code for e in danish}.isdisjoint({"100", "411", "997", "998", "999", "956", "11"})
    assert scope.inventory(path, ["DK-81", "DE-BY", "DE-BY"]) == [
        e for e in entries if e.region in {"DK-81", "DE-BY"}
    ]
    with pytest.raises(ValueError):
        scope.inventory(path, ["DK-86"])


@pytest.mark.parametrize("mode", ["plan", "apply"])
def test_cli_resume_offset_and_limit(monkeypatch, mode):
    run = AsyncMock(return_value={})
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(scope, "run_scope", run)
    monkeypatch.setattr(scope, "configure_logging", lambda _: None)
    monkeypatch.setattr(
        "sys.argv", ["scope", mode, "--region", "DK-84", "--offset", "7", "--limit", "3"]
    )
    scope.main()
    assert run.call_args.args[1] == scope.inventory(None, ["DK-84"])[7:10]
    assert run.call_args.kwargs["offset"] == 7
    assert run.call_args.kwargs["apply"] is (mode == "apply")


@pytest.mark.parametrize(
    "option,value",
    [("--offset", "-1"), ("--offset", "20099"), ("--limit", "0"), ("--limit", "20099")],
)
def test_cli_bounds(monkeypatch, option, value):
    monkeypatch.setattr("sys.argv", ["scope", "plan", "--region", "DK-81", option, value])
    with pytest.raises(SystemExit) as error:
        scope.main()
    assert error.value.code == 2


def test_cli_without_regions_dispatches_entire_national_inventory(tmp_path, monkeypatch):
    from app.research.catalog import REGION_PREFIX

    path = tmp_path / "national.csv"
    path.write_text(
        "region_code,ags,name\n"
        + "".join(f"{region},{prefix}999999,Fixture\n" for prefix, region in REGION_PREFIX.items())
    )
    run = AsyncMock(return_value={})
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(scope, "run_scope", run)
    monkeypatch.setattr(scope, "configure_logging", lambda _: None)
    monkeypatch.setattr("sys.argv", ["scope", "plan", "--german-catalog", str(path)])
    scope.main()
    assert run.call_args.args[1] == scope.inventory(path, [])
    assert len(run.call_args.args[1]) == 114


def test_maximum_catalog_plus_danish_inventory_is_not_truncated(tmp_path):
    path = tmp_path / "large.csv"
    path.write_text(
        "region_code,ags,name\n" + "".join(f"DE-BY,09{i:06},Fixture\n" for i in range(20000))
    )
    entries = scope.inventory(path, ["DE-BY", "DK-81", "DK-82", "DK-83", "DK-84", "DK-85"])
    assert len(entries) == scope.MAX_SCOPE_ENTRIES == 20098
    assert entries[-1].region == "DK-85"
    with path.open("a") as stream:
        stream.write("DE-BY,09200000,Overflow\n")
    with pytest.raises(ValueError, match="Too many catalog entries"):
        scope.inventory(path, ["DE-BY"])


def test_danish_membership_matches_official_98_municipal_codes():
    # Statistics Denmark NUTS_V1_2007_DK, excluding the nonmunicipality 411.
    official = {
        "DK-81": "773 787 810 813 820 825 840 846 849 851 860",
        "DK-82": "615 657 661 665 671 706 707 710 727 730 740 741 746 751 756 760 766 779 791",
        "DK-83": (
            "410 420 430 440 450 461 479 480 482 492 510 530 540 550 "
            "561 563 573 575 580 607 621 630"
        ),
        "DK-84": (
            "101 147 151 153 155 157 159 161 163 165 167 169 173 175 183 185 "
            "187 190 201 210 217 219 223 230 240 250 260 270 400"
        ),
        "DK-85": "253 259 265 269 306 316 320 326 329 330 336 340 350 360 370 376 390",
    }
    for region, codes in official.items():
        assert {e.code for e in scope.inventory(None, [region])} == set(codes.split())
