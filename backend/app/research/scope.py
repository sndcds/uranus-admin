"""Run the municipality importer over the explicit Northern DE/Southern DK scope.

The German inventory comes from the operator's BKG catalog. Danish membership is
from Statistics Denmark's NUTS_V1_2007_DK hierarchy (region 083), checked 2026-09-27:
https://www.dst.dk/da/Statistik/dokumentation/nomenklaturer/nuts
Codes are cross-checked against the SOP_KOMKOD classification. Nonmunicipal codes
(including Christiansø, Denmark and foreign/administrative codes) are excluded.
"""

import argparse
import asyncio
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.logging import configure_logging
from app.research.areas import REGIONS, run
from app.research.catalog import CatalogEntry, catalog_entries

# Official code/name and stable OSM relation identity. All available boundaries
# were checked through our own Nominatim on 2026-09-27. R1928466 (Aabenraa) was
# absent there; keep it in the inventory so a missing municipality stays visible.
SYDDANMARK = (
    ("410", "Middelfart", 2178063),
    ("420", "Assens", 2178091),
    ("430", "Faaborg-Midtfyn", 2052179),
    ("440", "Kerteminde", 2171010),
    ("450", "Nyborg", 2077936),
    ("461", "Odense", 2178124),
    ("479", "Svendborg", 2069804),
    ("480", "Nordfyns", 2178137),
    ("482", "Langeland", 2096607),
    ("492", "Ærø", 2096457),
    ("510", "Haderslev", 1927271),
    ("530", "Billund", 1801753),
    ("540", "Sønderborg", 1928254),
    ("550", "Tønder", 1928515),
    ("561", "Esbjerg", 1927177),
    ("563", "Fanø", 1926825),
    ("573", "Varde", 1926826),
    ("575", "Vejen", 1927241),
    ("580", "Aabenraa", 1928466),
    ("607", "Fredericia", 1799261),
    ("621", "Kolding", 1819983),
    ("630", "Vejle", 1618492),
)


@dataclass(frozen=True)
class ScopeEntry:
    region: str
    code: str
    name: str
    osm_id: int | None = None


def inventory(catalog: Path | None, regions: list[str]) -> list[ScopeEntry]:
    selected = set(regions or REGIONS)
    if not selected <= REGIONS.keys():
        raise ValueError("Invalid scope")
    entries: list[ScopeEntry] = []
    if selected - {"DK-83"}:
        if catalog is None:
            raise ValueError("German regions require the BKG catalog")
        german = catalog_entries(catalog)
        if selected - {"DK-83"} - {entry.region_code for entry in german}:
            raise ValueError("Catalog is missing a selected region")
        entries.extend(
            ScopeEntry(entry.region_code, entry.ags, entry.name)
            for entry in german
            if entry.region_code in selected
        )
    if "DK-83" in selected:
        entries.extend(ScopeEntry("DK-83", code, name, osm_id) for code, name, osm_id in SYDDANMARK)
    return sorted(entries, key=lambda entry: (entry.region, entry.code))


async def run_scope(
    settings: Settings,
    entries: list[ScopeEntry],
    *,
    apply: bool,
    offset: int,
    report: Callable[[dict[str, object]], None],
) -> dict[str, dict[str, int]]:
    totals: dict[str, Counter[str]] = {}
    # One municipality per transaction bounds memory even for large coastal
    # boundaries. Earlier committed entries survive an interrupted apply; reruns
    # are idempotent. Every entry uses the same preflight and spatial validation.
    for index, entry in enumerate(entries, offset):
        counts = await run(
            settings,
            entry.region,
            [],
            [entry.osm_id] if entry.osm_id is not None else [],
            apply,
            None
            if entry.osm_id is not None
            else [CatalogEntry(entry.region, entry.code, entry.name)],
        )
        totals.setdefault(entry.region, Counter()).update(counts)
        report(
            {
                "event": "scope_entry",
                "mode": "apply" if apply else "plan",
                "offset": index,
                "region": entry.region,
                "code": entry.code,
                "name": entry.name,
                **counts,
            }
        )
    return {region: dict(counts) for region, counts in totals.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "apply"])
    parser.add_argument("--german-catalog", type=Path)
    parser.add_argument("--region", choices=sorted(REGIONS), action="append", default=[])
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20022)
    args = parser.parse_args()
    if not 0 <= args.offset <= 20022 or not 1 <= args.limit <= 20022:
        parser.error("Use offset 0–20022 and limit 1–20022.")
    try:
        entries = inventory(args.german_catalog, args.region)
        batch = entries[args.offset : args.offset + args.limit]
        if not batch:
            parser.error("No municipalities in the selected range.")
        settings = Settings()
        configure_logging(settings.log_level)

        def report(value: dict[str, object]) -> None:
            print(json.dumps(value, ensure_ascii=False), flush=True)

        report(
            {
                "event": "scope_started",
                "mode": args.mode,
                "inventory": dict(Counter(entry.region for entry in entries)),
                "selected": len(batch),
                "offset": args.offset,
            }
        )
        totals = asyncio.run(
            run_scope(
                settings, batch, apply=args.mode == "apply", offset=args.offset, report=report
            )
        )
        report({"event": "scope_completed", "mode": args.mode, "regions": totals})
    except KeyboardInterrupt:
        raise SystemExit(
            "Scope import interrupted; resume from the last reported offset."
        ) from None
    except Exception:
        raise SystemExit(
            "Scope import failed; check provider, catalog, schema and operator grants. "
            "Earlier applied entries remain; repeat the last reported offset safely."
        ) from None
    if any(counts.get("rejected", 0) for counts in totals.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
