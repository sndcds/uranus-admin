"""Offline workbook contract and AGS-pinned provider discovery."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.errors import APIError
from app.research.areas import CITY_EXCEPTIONS, boundary, import_boundaries
from app.research.catalog import CatalogEntry, load_catalog, workbook_entries
from tests.test_research_areas import POLYGON, provider, row


def workbook(path: Path, rows: str) -> None:
    with ZipFile(path, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            ><sheets><sheet name="VGTB_VZ_GEM" r:id="r1"/></sheets></workbook>""",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="r1" Target="worksheets/sheet7.xml"/></Relationships>',
        )
        z.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
        )
        header = ["AGS_G", "GEN_G", "BEZ_G", "ARS_L"]
        cells = "".join(
            f'<c r="{col}1" t="inlineStr"><is><t>{val}</t></is></c>'
            for col, val in zip("ABCD", header, strict=True)
        )
        z.writestr(
            "xl/worksheets/sheet7.xml",
            f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row>{cells}</row>{rows}</sheetData></worksheet>',
        )


def line(ags, name, kind, region):
    return (
        "<row>"
        + "".join(
            f'<c r="{col}2" t="inlineStr"><is><t>{value}</t></is></c>'
            for col, value in zip("ABCD", [ags, name, kind, region], strict=True)
        )
        + "</row>"
    )


def test_bkg_scope_excludes_nonmunicipalities(tmp_path):
    path = tmp_path / "fixture.xlsx"
    workbook(
        path,
        line("01001000", "Flensburg", "Stadt", "01")
        + line("03999999", "Forest", "Gemeindefreies Gebiet", "03")
        + line("17999999", "Outside", "Gemeinde", "17"),
    )
    assert workbook_entries(path) == [CatalogEntry("DE-SH", "01001000", "Flensburg")]


def test_duplicate_or_invalid_identity_fails_closed(tmp_path):
    path = tmp_path / "fixture.xlsx"
    workbook(path, line("1001000", "Broken AGS", "Stadt", "01"))
    with pytest.raises(ValueError):
        workbook_entries(path)
    workbook(path, line("01001000", "Flensburg", "Stadt", "01") * 2)
    with pytest.raises(ValueError):
        workbook_entries(path)


def test_catalog_batches_and_exact_prefix(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(
        "region_code,ags,name\nDE-SH,01001000,Flensburg\nDE-SH,01002000,Kiel\nDE-HH,02000000,Hamburg\n"
    )
    assert load_catalog(path, "DE-SH", 1, 1) == [CatalogEntry("DE-SH", "01002000", "Kiel")]
    with pytest.raises(ValueError):
        load_catalog(path, "DE-SH", 0, 101)
    path.write_text("region_code,ags,name\nDE-SH,02000000,Hamburg\n")
    with pytest.raises(ValueError):
        load_catalog(path, "DE-SH", 0, 1)


def test_lookup_revalidates_official_identity(settings):
    data = row(extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": "01999000"})
    assert boundary(data, settings, "DE-SH", "01999000")
    with pytest.raises(APIError):
        boundary(data, settings, "DE-SH", "01999001")


VERIFIED_CASES = [
    ("DE-SH", "01057001", "Ascheberg (Holstein)", 310405),
    ("DE-SH", "01057004", "Behrensdorf (Ostsee)", 288915),
    ("DE-SH", "01057030", "Hohwacht (Ostsee)", 288939),
    ("DE-SH", "01061044", "Horst (Holstein)", 447194),
    ("DE-NI", "03151040", "Wittingen", 1392804),
    ("DE-NI", "03354026", "Wustrow (Wendland)", 1821905),
    ("DE-NI", "03357019", "Hamersen", 1079013),
    ("DE-NI", "03358001", "Ahlden (Aller)", 1808860),
]


@pytest.fixture
def classification(monkeypatch):
    # Exercise real discovery, HTTP lookup and boundary validation without a DB.
    # PostGIS classification is covered by test_research_areas integration tests.
    classify = AsyncMock(return_value=("new", {}))
    monkeypatch.setattr("app.research.areas.classify", classify)
    return classify


def municipality_lookup(region, ags, name, identity):
    # Synthetic contract data; not evidence of a live lookup.
    data = row(
        osm_id=identity,
        name=name,
        category="boundary",
        address={"country_code": "de", "ISO3166-2-lvl4": region},
        extratags={"admin_level": "8", "de:amtlicher_gemeindeschluessel": ags},
    )
    del data["class"]
    return data


@pytest.mark.parametrize("region,ags,name,identity", VERIFIED_CASES)
@pytest.mark.parametrize("shape", ["Polygon", "MultiPolygon"])
async def test_verified_municipality_uses_lookup_without_search(
    settings, classification, region, ags, name, identity, shape
):
    data = municipality_lookup(region, ags, name, identity)
    if shape == "MultiPolygon":
        data["geojson"] = {"type": shape, "coordinates": [POLYGON["coordinates"]]}
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/lookup"
        assert dict(request.url.params) == {
            "format": "jsonv2",
            "osm_ids": f"R{identity}",
            "polygon_geojson": "1",
            "addressdetails": "1",
            "extratags": "1",
        }
        return httpx.Response(200, json=[data])

    counts = await import_boundaries(
        MagicMock(spec=AsyncConnection),
        provider(settings, handler=handler),
        region,
        [],
        [],
        catalog=[CatalogEntry(region, ags, name)],
    )
    assert counts == dict(found=1, new=1, updated=0, unchanged=0, rejected=0)
    assert len(requests) == 1
    classification.assert_awaited_once()
    item = classification.call_args.args[1]
    assert (item.osm_id, item.municipality_key, item.osm_admin_level) == (identity, ags, 8)
    assert item.region_code == region
    assert identity not in CITY_EXCEPTIONS


@pytest.mark.parametrize("region,ags,name,identity", VERIFIED_CASES)
@pytest.mark.parametrize(
    "changes",
    [
        {"extratags": {"admin_level": "8", "de:amtlicher_gemeindeschluessel": "01999000"}},
        {"extratags": {"de:amtlicher_gemeindeschluessel": None}},
        {"address": {"ISO3166-2-lvl4": "DE-BY"}},
        {"address": {"country_code": "dk"}},
        {"extratags": {"admin_level": "6"}},
        {"osm_type": "way"},
        {"osm_id": 999999},
        {"category": "place"},
        {"type": "city"},
        {"geojson": None},
        {"geojson": {"type": "Point", "coordinates": [9, 54]}},
        {"geojson": {"type": "Polygon", "coordinates": [[[9, 54], [10, 54], [10, 55]]]}},
    ],
)
async def test_verified_municipality_rejects_invalid_lookup(
    settings, classification, region, ags, name, identity, changes
):
    data = municipality_lookup(region, ags, name, identity)
    # Change one tag at a time to test each validation independently.
    if "extratags" in changes:
        data["extratags"].update(changes["extratags"])
    elif "address" in changes:
        data["address"].update(changes["address"])
    else:
        data.update(changes)
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/lookup"
        assert request.url.params["osm_ids"] == f"R{identity}"
        return httpx.Response(200, json=[data])

    counts = await import_boundaries(
        MagicMock(spec=AsyncConnection),
        provider(settings, handler=handler),
        region,
        [],
        [],
        catalog=[CatalogEntry(region, ags, name)],
    )
    assert counts == dict(found=1, new=0, updated=0, unchanged=0, rejected=1)
    assert len(requests) == 1
    classification.assert_not_awaited()


@pytest.mark.parametrize(
    "region,region_name,ags,name",
    [
        ("DE-SH", "Schleswig-Holstein", "01999000", "Ascheberg (Holstein)"),
        ("DE-SH", "Schleswig-Holstein", "01057002", "Ascheberg (Holstein)"),
        ("DE-NI", "Niedersachsen", "03999000", "Wittingen"),
        ("DE-NI", "Niedersachsen", "03151041", "Wittingen"),
    ],
)
async def test_unmapped_municipality_keeps_name_discovery(
    settings, classification, region, region_name, ags, name
):
    # Even the same name as a mapped municipality must not select its relation.
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/search":
            assert request.url.params["countrycodes"] == "de"
            if len(requests) == 1:
                assert request.url.params["q"] == f"{name}, {region_name}, Deutschland"
                return httpx.Response(200, json=[])
            assert request.url.params["q"] == name
        else:
            assert request.url.path == "/lookup"
            assert request.url.params["osm_ids"] == "R101"
        return httpx.Response(200, json=[municipality_lookup(region, ags, name, 101)])

    counts = await import_boundaries(
        MagicMock(spec=AsyncConnection),
        provider(settings, handler=handler),
        region,
        [],
        [],
        catalog=[CatalogEntry(region, ags, name)],
    )
    assert counts == dict(found=1, new=1, updated=0, unchanged=0, rejected=0)
    assert [r.url.path for r in requests] == ["/search", "/search", "/lookup"]
    classification.assert_awaited_once()


@pytest.mark.parametrize(
    "region,entry",
    [
        ("DK-81", CatalogEntry("DK-81", "01057001", "Ascheberg (Holstein)")),
        ("DE-NI", CatalogEntry("DE-NI", "01057001", "Ascheberg (Holstein)")),
        ("DE-SH", CatalogEntry("DE-SH", "01057001 ", "Ascheberg (Holstein)")),
        ("DK-81", CatalogEntry("DK-81", "03151040", "Wittingen")),
        ("DE-SH", CatalogEntry("DE-SH", "03151040", "Wittingen")),
        ("DE-NI", CatalogEntry("DE-NI", "03151040 ", "Wittingen")),
    ],
)
async def test_mapping_cannot_bypass_german_catalog_identity(settings, region, entry):
    def forbidden(_):
        pytest.fail("Invalid catalog entries must not call the provider")

    with pytest.raises(APIError) as error:
        await import_boundaries(
            MagicMock(spec=AsyncConnection),
            provider(settings, handler=forbidden),
            region,
            [],
            [],
            catalog=[entry],
        )
    assert error.value.code == "invalid_input"


EXPECTED_PREFIXES = dict(
    zip(
        [f"{i:02}" for i in range(1, 17)],
        [
            "DE-SH",
            "DE-HH",
            "DE-NI",
            "DE-HB",
            "DE-NW",
            "DE-HE",
            "DE-RP",
            "DE-BW",
            "DE-BY",
            "DE-SL",
            "DE-BE",
            "DE-BB",
            "DE-MV",
            "DE-SN",
            "DE-ST",
            "DE-TH",
        ],
        strict=True,
    )
)


def test_all_official_state_prefixes_and_workbook(tmp_path):
    from app.research.catalog import REGION_PREFIX

    assert REGION_PREFIX == EXPECTED_PREFIXES
    path = tmp_path / "all.xlsx"
    workbook(
        path,
        "".join(
            line(prefix + "999999", region, "Gemeinde", prefix)
            for prefix, region in EXPECTED_PREFIXES.items()
        ),
    )
    assert workbook_entries(path) == [
        CatalogEntry(region, prefix + "999999", region)
        for prefix, region in EXPECTED_PREFIXES.items()
    ]


@pytest.mark.parametrize(
    "ags,region",
    [
        ("1234567", "DE-BB"),
        ("123456789", "DE-BB"),
        ("１２３４５６７８", "DE-BB"),
        ("09999999", "DE-BW"),
        ("17999999", "DE-XX"),
    ],
)
def test_national_catalog_rejects_bad_ags_or_region(tmp_path, ags, region):
    path = tmp_path / "catalog.csv"
    path.write_text(f"region_code,ags,name\n{region},{ags},Fixture\n")
    with pytest.raises(ValueError):
        load_catalog(path, region, 0, 1)
