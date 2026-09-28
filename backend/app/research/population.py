"""Offline, AGS-exact BKG population import; never changes boundary geometry."""

import argparse
import asyncio
import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.diagnostics import operator_boundary, operator_engine
from app.config import Settings
from app.logging import configure_logging
from app.research.areas import IMPORT_GRANTS, IMPORT_LOCK
from app.research.catalog import REGION_PREFIX, workbook_sheet
from app.storage_preflight import check_grants, check_schema

logger = logging.getLogger("admin.research_population")


@dataclass(frozen=True)
class PopulationEntry:
    ags: str
    name: str
    value: int
    as_of: date
    file_sha256: str


def population_entries(
    path: Path, region: str, offset: int = 0, limit: int = 100
) -> list[PopulationEntry]:
    if region not in REGION_PREFIX.values() or not 0 <= offset <= 20000 or not 1 <= limit <= 100:
        raise ValueError("Invalid population scope or batch bounds")
    cover = workbook_sheet(path, "Deckblatt")
    dates = [
        match[1]
        for row in cover
        for value in row.values()
        if (match := re.fullmatch(r"Verwaltungsgebiete\s+Stand: (31\.12\.[0-9]{4})", value))
    ]
    if len(dates) != 1:
        raise ValueError("Missing population reference date")
    as_of = date(int(dates[0][-4:]), 12, 31)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = workbook_sheet(path, "VGTB_ATT_VG")
    header = rows[0]
    if not {"ADE", "AGS", "GEN", "EWZ", "BEZ", "SN_L"} <= set(header.values()):
        raise ValueError("Missing population columns")
    entries = []
    seen = set()
    for cells in rows[1:]:
        row = {name: cells.get(column, "") for column, name in header.items()}
        if (
            row["ADE"] != "6"
            or row["BEZ"] == "Gemeindefreies Gebiet"
            or REGION_PREFIX.get(row["SN_L"]) != region
        ):
            continue
        ags = row["AGS"]
        if (
            not re.fullmatch(r"[0-9]{8}", ags)
            or not ags.startswith(row["SN_L"])
            or not re.fullmatch(r"[0-9]{1,9}", row["EWZ"])
            or not 1 <= len(row["GEN"]) <= 120
            or ags in seen
        ):
            raise ValueError("Invalid or duplicate population identity")
        seen.add(ags)
        entries.append(PopulationEntry(ags, row["GEN"], int(row["EWZ"]), as_of, digest))
    return sorted(entries, key=lambda entry: entry.ags)[offset : offset + limit]


async def import_population(
    connection: AsyncConnection,
    entries: list[PopulationEntry],
    region: str,
    *,
    apply: bool = False,
) -> dict[str, int]:
    if (
        region not in REGION_PREFIX.values()
        or not 1 <= len(entries) <= 100
        or len({e.ags for e in entries}) != len(entries)
    ):
        raise ValueError("Select a bounded unique population batch")
    counts = dict.fromkeys(("found", "new", "updated", "unchanged", "rejected"), 0)
    counts["found"] = len(entries)
    logger.info("research_population_started", extra={"region": region, "apply": apply})
    async with connection.begin():
        await connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK})
        rows = (
            (
                await connection.execute(
                    text("""SELECT id,municipality_key,population_count,population_date,
                    population_file_sha256 FROM admin.research_area
                    WHERE country_code='DE' AND region_code=:region AND area_type='municipality'
                    AND municipality_key=ANY(:keys)"""),
                    {"region": region, "keys": [entry.ags for entry in entries]},
                )
            )
            .mappings()
            .all()
        )
        accepted = []
        for entry in entries:
            matches = [r for r in rows if r["municipality_key"] == entry.ags]
            if len(matches) != 1 or (
                matches[0]["population_date"] and matches[0]["population_date"] > entry.as_of
            ):
                counts["rejected"] += 1
                continue
            row = matches[0]
            status = (
                "unchanged"
                if row["population_count"] == entry.value
                and row["population_date"] == entry.as_of
                and row["population_file_sha256"] == entry.file_sha256
                else "new"
                if row["population_count"] is None
                else "updated"
            )
            counts[status] += 1
            if status != "unchanged":
                accepted.append({**asdict(entry), "id": row["id"]})
        logger.info("research_population_plan", extra={"region": region, **counts})
        if apply and accepted:
            await connection.execute(
                text("""UPDATE admin.research_area SET population_count=:value,
                    population_date=:as_of,population_source='bkg_vg250_ew',population_name=:name,
                    population_file_sha256=:file_sha256,population_imported_at=now()
                    WHERE id=:id AND municipality_key=:ags"""),
                accepted,
            )
    logger.info("research_population_completed", extra={"region": region, "apply": apply, **counts})
    return counts


async def run(
    settings: Settings, entries: list[PopulationEntry], region: str, apply: bool
) -> dict[str, int]:
    engine = operator_engine(settings)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text("SET TIME ZONE 'UTC'"))
                await operator_boundary(connection)
                await check_schema(connection)
                await check_grants(connection, IMPORT_GRANTS)
            return await import_population(connection, entries, region, apply=apply)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "apply"])
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--region", required=True, choices=sorted(REGION_PREFIX.values()))
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    try:
        entries = population_entries(args.workbook, args.region, args.offset, args.limit)
        settings = Settings()
        configure_logging(settings.log_level)
        counts = asyncio.run(run(settings, entries, args.region, args.mode == "apply"))
        print(json.dumps({"region": args.region, "mode": args.mode, **counts}))
    except KeyboardInterrupt:
        raise SystemExit("Population import interrupted.") from None
    except Exception:
        raise SystemExit(
            "Population import failed; check workbook, schema and operator grants."
        ) from None


if __name__ == "__main__":
    main()
