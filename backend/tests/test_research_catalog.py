"""Offline workbook contract and AGS-pinned provider discovery."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from app.errors import APIError
from app.research.areas import boundary
from app.research.catalog import CatalogEntry, load_catalog, workbook_entries
from tests.test_research_areas import row


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
