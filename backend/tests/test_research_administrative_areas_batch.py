"""Offline inventory review and sequential operator failure/restart contracts."""

import csv
import json
from collections import Counter
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.research import administrative_areas_batch as batch
from app.research.administrative_areas import load_manifest
from app.research.areas import CITY_EXCEPTIONS, DANISH_RELATIONS, REGIONS
from app.research.catalog import REGION_PREFIX
from tests.test_research_administrative_areas import manifest

ROOT = Path(__file__).resolve().parents[2] / "docs/research/manifests"
DISTRICT_COUNTS = {
    "DE-BB": 14,
    "DE-BW": 35,
    "DE-BY": 71,
    "DE-HE": 21,
    "DE-MV": 6,
    "DE-NI": 37,
    "DE-NW": 31,
    "DE-RP": 24,
    "DE-SH": 11,
    "DE-SL": 6,
    "DE-SN": 10,
    "DE-ST": 11,
    "DE-TH": 17,
}


def test_reviewed_inventory_coverage_and_unique_roles():
    entries = batch.load_batch(ROOT)
    assert len(entries) == 32  # 14 importable states + 13 district batches + 5 regions.
    assert len(list(ROOT.rglob("*.json"))) == len(entries)
    identities = {}
    for relative, item in entries:
        assert item == load_manifest(ROOT / relative)
        assert item.reviewed_on is not None
        assert item.region_code == Path(relative).stem
        assert item.country_codes == [item.region_code[:2]]
        assert item.osm_admin_level == (6 if item.level == "district" else 4)
        assert item.complete == (item.level == "district")
        for identity in item.identities:
            assert identity.osm_id not in identities
            assert identity.osm_id not in CITY_EXCEPTIONS
            assert identity.osm_id not in DANISH_RELATIONS
            identities[identity.osm_id] = (item.level, item.region_code)
    districts = {m.region_code: len(m.identities) for _, m in entries if m.level == "district"}
    assert districts == DISTRICT_COUNTS and sum(districts.values()) == 294
    assert {m.region_code for _, m in entries if m.level == "region"} == {
        "DK-81",
        "DK-82",
        "DK-83",
        "DK-84",
        "DK-85",
    }
    with (ROOT / "reviewed-inventory.csv").open() as handle:
        reviewed = list(csv.DictReader(handle))
    assert Counter(row["level"] for row in reviewed) == {"state": 16, "district": 294, "region": 5}
    assert {row["region_code"] for row in reviewed if row["level"] == "state"} == {
        code for code in REGIONS if code.startswith("DE-")
    }
    imported = {
        int(row["osm_relation_id"]): (row["level"], row["region_code"])
        for row in reviewed
        if row["disposition"] == "import"
    }
    assert identities == imported
    assert len({row["official_key"] for row in reviewed if row["level"] == "district"}) == 294
    for row in reviewed:
        assert int(row["osm_version"]) > 0
        assert row["source_url"].endswith(f"/{row['osm_relation_id']}/{row['osm_version']}")
        if row["level"] == "district":
            assert row["dlt_name"]
            assert REGION_PREFIX[row["official_key"][:2]] == row["region_code"]
    excluded = [r for r in reviewed if r["disposition"] != "import"]
    assert {r["region_code"] for r in excluded} == {"DE-BE", "DE-HH"}
    assert all(int(r["osm_relation_id"]) in CITY_EXCEPTIONS for r in excluded)
    with (ROOT / "excluded-municipalities.csv").open() as handle:
        exclusions = list(csv.DictReader(handle))
    assert {int(r["osm_relation_id"]) for r in exclusions} == set(CITY_EXCEPTIONS)


def write_batch(root):
    for directory, item in [
        ("dk/regions", manifest("region", (103,))),
        ("de/districts", manifest("district", (102,))),
        ("de/states", manifest("state", (101,))),
    ]:
        path = root / directory / (item.region_code + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.model_dump_json())


@pytest.mark.parametrize("apply", [False, True])
async def test_all_plans_precede_sequential_writes(tmp_path, settings, monkeypatch, capsys, apply):
    write_batch(tmp_path)
    run = AsyncMock(return_value={"counts": {}})
    monkeypatch.setattr(batch, "run", run)
    await batch.run_batch(settings, tmp_path, apply=apply)
    assert [(c.args[1].level, c.kwargs["apply"]) for c in run.await_args_list] == [
        (level, mode)
        for mode in ([False, True] if apply else [False])
        for level in ["state", "district", "region"]
    ]
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert reports[0]["manifest"] == "de/states/DE-SH.json"


@pytest.mark.parametrize("failure_call", [2, 5])
async def test_first_failure_stops_and_restart_replans_all(
    tmp_path, settings, monkeypatch, capsys, failure_call
):
    write_batch(tmp_path)
    run = AsyncMock(side_effect=[{}] * (failure_call - 1) + [ValueError("private provider detail")])
    monkeypatch.setattr(batch, "run", run)
    with pytest.raises(batch.BatchFailure) as error:
        await batch.run_batch(settings, tmp_path, apply=True)
    assert error.value.path == "de/districts/DE-SH.json"
    assert error.value.phase == ("plan" if failure_call == 2 else "apply")
    assert run.await_count == failure_call
    assert "private provider detail" not in capsys.readouterr().out
    run = AsyncMock(return_value={})
    monkeypatch.setattr(batch, "run", run)
    await batch.run_batch(settings, tmp_path, apply=True)
    assert [c.kwargs["apply"] for c in run.await_args_list] == [False] * 3 + [True] * 3


async def test_loads_entire_batch_before_any_network_or_write(tmp_path, settings, monkeypatch):
    write_batch(tmp_path)
    (tmp_path / "dk/regions/DK-83.json").write_text("{}")
    run = AsyncMock()
    monkeypatch.setattr(batch, "run", run)
    with pytest.raises(batch.BatchFailure, match="batch failed"):
        await batch.run_batch(settings, tmp_path, apply=True)
    run.assert_not_called()


def test_duplicate_identity_across_manifests_fails(tmp_path):
    write_batch(tmp_path)
    (tmp_path / "de/districts/DE-SH.json").write_text(
        manifest("district", (101,)).model_dump_json()
    )
    with pytest.raises(batch.BatchFailure):
        batch.load_batch(tmp_path)


def test_filename_order_within_each_level_is_stable(tmp_path):
    write_batch(tmp_path)
    (tmp_path / "de/states/DE-BB.json").write_text(
        manifest("state", (104,), region_code="DE-BB").model_dump_json()
    )
    assert [path for path, _ in batch.load_batch(tmp_path)] == [
        "de/states/DE-BB.json",
        "de/states/DE-SH.json",
        "de/districts/DE-SH.json",
        "dk/regions/DK-83.json",
    ]
