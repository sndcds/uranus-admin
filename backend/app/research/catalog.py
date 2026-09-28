"""Offline BKG VG250 municipality names/AGS to bounded Nominatim discovery input.

Coordinates, formulas and geometry are never imported from the workbook.
"""

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

REGION_PREFIX = {
    "01": "DE-SH",
    "02": "DE-HH",
    "03": "DE-NI",
    "04": "DE-HB",
    "05": "DE-NW",
    "06": "DE-HE",
    "07": "DE-RP",
    "08": "DE-BW",
    "09": "DE-BY",
    "10": "DE-SL",
    "11": "DE-BE",
    "12": "DE-BB",
    "13": "DE-MV",
    "14": "DE-SN",
    "15": "DE-ST",
    "16": "DE-TH",
}
MAX_CATALOG_ENTRIES = 20000
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


@dataclass(frozen=True)
class CatalogEntry:
    region_code: str
    ags: str
    name: str


def workbook_sheet(path: Path, sheet: str) -> list[dict[str, str]]:
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Workbook is too large")
    with ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > 128 * 1024 * 1024:
            raise ValueError("Expanded workbook is too large")
        sheets = ET.fromstring(archive.read("xl/workbook.xml")).findall("s:sheets/s:sheet", NS)
        selected = [s for s in sheets if s.attrib.get("name") == sheet]
        if len(selected) != 1:
            raise ValueError("Expected BKG sheet")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(
            r.attrib["Target"] for r in relationships if r.attrib["Id"] == selected[0].attrib[REL]
        )
        if not re.fullmatch(r"worksheets/sheet[0-9]+\.xml", target):
            raise ValueError("Unexpected sheet relationship")
        strings = [
            "".join(t.text or "" for t in item.iter("{" + NS["s"] + "}t"))
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", NS)
        ]
        rows = ET.fromstring(archive.read("xl/" + target)).findall("s:sheetData/s:row", NS)
        if not rows or len(rows) > 20000:
            raise ValueError("Invalid municipality sheet size")

        def values(row: ET.Element) -> dict[str, str]:
            result = {}
            for cell in row.findall("s:c", NS):
                if cell.find("s:f", NS) is not None:
                    raise ValueError("Formulas are not supported")
                key = re.sub("[0-9]", "", cell.attrib["r"])
                raw = cell.findtext("s:v", default="", namespaces=NS)
                if cell.attrib.get("t") == "s":
                    raw = strings[int(raw)]
                elif cell.attrib.get("t") == "inlineStr":
                    raw = "".join(t.text or "" for t in cell.findall("s:is/s:t", NS))
                result[key] = raw
            return result

        return [values(row) for row in rows]


def workbook_entries(path: Path) -> list[CatalogEntry]:
    rows = workbook_sheet(path, "VGTB_VZ_GEM")
    header = rows[0]
    required = {"AGS_G", "GEN_G", "BEZ_G", "ARS_L"}
    if not required <= set(header.values()):
        raise ValueError("Missing BKG municipality columns")
    result = []
    seen = set()
    for row in rows[1:]:
        cells = row
        data = {name: cells.get(column, "") for column, name in header.items()}
        prefix = data["ARS_L"]
        if prefix not in REGION_PREFIX or data["BEZ_G"] == "Gemeindefreies Gebiet":
            continue
        ags, name = data["AGS_G"], data["GEN_G"]
        if (
            not re.fullmatch(r"[0-9]{8}", ags)
            or not ags.startswith(prefix)
            or not 1 <= len(name) <= 120
            or ags in seen
        ):
            raise ValueError("Invalid or duplicate municipality identity")
        seen.add(ags)
        result.append(CatalogEntry(REGION_PREFIX[prefix], ags, name))
    return sorted(result, key=lambda entry: entry.ags)


def catalog_entries(path: Path) -> list[CatalogEntry]:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Invalid catalog size")
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["region_code", "ags", "name"]:
            raise ValueError("Invalid catalog columns")
        entries = []
        seen = set()
        for row in reader:
            ags = row["ags"]
            if (
                not re.fullmatch(r"[0-9]{8}", ags)
                or REGION_PREFIX.get(ags[:2]) != row["region_code"]
                or not 1 <= len(row["name"]) <= 120
                or ags in seen
            ):
                raise ValueError("Invalid catalog identity")
            seen.add(ags)
            entries.append(CatalogEntry(REGION_PREFIX[ags[:2]], ags, row["name"]))
            if len(entries) > MAX_CATALOG_ENTRIES:
                raise ValueError("Too many catalog entries")
    return sorted(entries, key=lambda entry: entry.ags)


def load_catalog(path: Path, region: str, offset: int, limit: int) -> list[CatalogEntry]:
    if not 0 <= offset <= MAX_CATALOG_ENTRIES or not 1 <= limit <= 100:
        raise ValueError("Invalid catalog batch bounds")
    return [entry for entry in catalog_entries(path) if entry.region_code == region][
        offset : offset + limit
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        entries = workbook_entries(args.workbook)
        with args.output.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["region_code", "ags", "name"])
            writer.writeheader()
            writer.writerows(vars(entry) for entry in entries)
        print(
            json.dumps(
                {
                    "municipalities": len(entries),
                    "regions": dict(Counter(e.region_code for e in entries)),
                }
            )
        )
    except Exception:
        raise SystemExit(
            "Catalog conversion failed; check BKG workbook and unused output path."
        ) from None


if __name__ == "__main__":
    main()
