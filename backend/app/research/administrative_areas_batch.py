"""Sequential operator import of checked-in DE states/districts and DK regions.

All manifests are loaded before any network/database work. Apply first plans the
entire set, then revalidates and commits each manifest independently. No discovery
of OSM identities, automatic cleanup, parallel writes or cross-manifest transaction.
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.research.administrative_areas import PersistentManifest, load_manifest, run

GROUPS = (
    ("de/states", "DE", "state"),
    ("de/districts", "DE", "district"),
    ("dk/regions", "DK", "region"),
)
MAX_MANIFESTS = 64


class BatchFailure(ValueError):
    def __init__(self, path: str, phase: str) -> None:
        self.path = path
        self.phase = phase
        super().__init__("Administrative area batch failed")


def load_batch(root: Path) -> list[tuple[str, PersistentManifest]]:
    items: list[tuple[str, PersistentManifest]] = []
    identities: set[int] = set()
    if not root.is_dir():
        raise BatchFailure(".", "load")
    for directory, country, level in GROUPS:
        for path in sorted((root / directory).glob("*.json")):
            relative = path.relative_to(root).as_posix()
            try:
                if (
                    len(items) >= MAX_MANIFESTS
                    or path.resolve().parent != (root / directory).resolve()
                ):
                    raise ValueError("Manifest count/path exceeds batch bounds")
                manifest = load_manifest(path)
                if manifest.level != level or manifest.country_codes != [country]:
                    raise ValueError("Manifest directory does not match scope")
                if path.stem != manifest.region_code:
                    raise ValueError("Manifest filename does not match region")
                incoming = {item.osm_id for item in manifest.identities}
                if identities & incoming:
                    raise ValueError("Repeated OSM identity across manifests")
                identities.update(incoming)
                items.append((relative, manifest))
            except Exception:
                raise BatchFailure(relative, "load") from None
    if not items:
        raise BatchFailure(".", "load")
    return items


async def run_batch(settings: Settings, root: Path, *, apply: bool) -> None:
    items = load_batch(root)
    # Preflight ALL manifests before the first write. Individual apply still
    # revalidates against live state, including earlier committed manifests.
    for phase in ("plan", "apply") if apply else ("plan",):
        for path, manifest in items:
            try:
                report = await run(settings, manifest, apply=phase == "apply")
            except Exception:
                raise BatchFailure(path, phase) from None
            print(json.dumps({"manifest": path, **report}, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "apply"])
    parser.add_argument("manifest_root", type=Path)
    args = parser.parse_args()
    try:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        asyncio.run(run_batch(settings, args.manifest_root, apply=args.mode == "apply"))
    except BatchFailure as exc:
        print(json.dumps({"failed_manifest": exc.path, "phase": exc.phase}), flush=True)
        raise SystemExit(
            "Administrative area batch stopped. Earlier applied manifests remain committed; "
            "review the failed manifest, then plan the entire set again before restarting."
        ) from None
    except Exception:
        raise SystemExit(
            "Administrative area batch failed; check operator configuration."
        ) from None


if __name__ == "__main__":
    main()
