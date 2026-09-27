"""Synthetic BKG workbook, no live files or network required."""

from datetime import date
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest

from app.research.population import population_entries


def workbook(path, entries, cover="Verwaltungsgebiete\nStand: 31.12.2024"):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    def sheet(rows):
        return (
            f'<worksheet xmlns="{ns}"><sheetData>'
            + "".join(
                "<row>"
                + "".join(
                    f'<c r="{chr(65 + i)}1" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                    for i, value in enumerate(row)
                )
                + "</row>"
                for row in rows
            )
            + "</sheetData></worksheet>"
        )

    with ZipFile(path, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Deckblatt" r:id="r1"/>'
            '<sheet name="VGTB_ATT_VG" r:id="r2"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="r2" Target="worksheets/sheet2.xml"/></Relationships>',
        )
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}"/>')
        z.writestr("xl/worksheets/sheet1.xml", sheet([[cover]]))
        z.writestr(
            "xl/worksheets/sheet2.xml",
            sheet([["ADE", "AGS", "GEN", "EWZ", "BEZ", "SN_L"], *entries]),
        )


def test_population_uses_only_municipality_level_and_exact_date(tmp_path):
    path = tmp_path / "population.xlsx"
    workbook(
        path,
        [
            ["4", "01001", "Flensburg", "99", "Kreisfreie Stadt", "01"],
            ["6", "01001000", "Flensburg", "99", "Stadt", "01"],
            ["6", "03999000", "Forest", "0", "Gemeindefreies Gebiet", "03"],
        ],
    )
    entries = population_entries(path, "DE-SH")
    assert len(entries) == 1
    assert entries[0].value == 99 and entries[0].ags == "01001000"
    assert entries[0].as_of == date(2024, 12, 31)
    assert len(entries[0].file_sha256) == 64
    assert population_entries(path, "DE-NI") == []
    with pytest.raises(ValueError):
        population_entries(path, "DK-83")


@pytest.mark.parametrize("value", ["-1", "12.5", "", "unknown"])
def test_missing_or_invalid_population_is_not_zero(tmp_path, value):
    path = tmp_path / "population.xlsx"
    workbook(path, [["6", "01001000", "Flensburg", value, "Stadt", "01"]])
    with pytest.raises(ValueError):
        population_entries(path, "DE-SH")


def test_ambiguous_date_and_duplicate_identity_fail(tmp_path):
    path = tmp_path / "population.xlsx"
    row = ["6", "01001000", "Flensburg", "99", "Stadt", "01"]
    workbook(path, [row], "Stand unknown")
    with pytest.raises(ValueError):
        population_entries(path, "DE-SH")
    workbook(path, [row, row])
    with pytest.raises(ValueError):
        population_entries(path, "DE-SH")
