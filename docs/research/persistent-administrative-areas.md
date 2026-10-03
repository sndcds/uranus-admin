# Persistent administrative boundaries

`app.research.administrative_areas` is an explicit operator tool for **district**
and **state** boundaries in `admin.research_area`. It does not run on deployment,
API startup, queries or worker timers. `app.research.areas` and `app.research.scope`
remain unchanged municipality-only workflows. No Uranus source data is written.

## Manifest and authority

The closed `PersistentManifest` extends the existing
`app.research.administrative_import.Manifest`. It accepts 1–100 unique OSM
**relation** identities (positive signed bigint), one country and one reviewed
region per batch. File size is limited to 64 KiB. No names/search queries are
accepted as import identities. `municipality`, `country` and generic `region`
imports are rejected; future levels require explicit validation/storage work.

The current Geocoder supplies administrative roles, country, names, identity and
boundary geometry. Each lookup goes exclusively through `ResearchGeocoderClient`
with its existing authenticated, bounded 8 MiB boundary transport. The importer
calls `resolved_boundary(candidate, manifest.level)` and checks the requested
identity and country. Municipality-role places (including dual-role city states
and kreisfreie Städte) are rejected even if the Geocoder also lists `district` or
`state`. Existing rows with a different `area_type` are never reclassified.

Two additional reviewed manifest fields are required because the current Geocoder
contract does not expose the corresponding non-null storage fields:

- `region_code`: an existing supported ISO subdivision, such as `DE-SH`;
- `osm_admin_level`: the reviewed OSM tag value, 2–12.

These values are operator-supplied metadata, **not classification inputs**.
No name or raw OSM-level mapping determines the administrative level. An available
Geocoder state code in the `ISO-3166-2` scheme must agree with `region_code`.
The operator must review region membership and the raw tag; the importer cannot
independently verify fields absent from the service contract. No German-level
assumption is applied to Denmark.

`inventory_source`, `complete` and `parent_area_id` describe the reviewed manifest;
they do not create persistent hierarchy/completeness assertions. This importer
does not replace the separate complete operator catalog used for zero-event
inventory/grouping. Do not feed the rural-only example to a catalog claiming to
contain every administrative district role, including municipal dual roles.

## Validation and persistence

Plan and apply share the same lookup, geometry validation, database classification
and overlap pipeline. All network calls finish before the database transaction.
Polygons must be closed and bounded, at most 500,000 points per boundary and
32 MiB geometry JSON per batch. PostGIS then rejects empty/invalid geometry;
there is no simplification or automatic repair.

Plan uses a read-only repeatable-read transaction and never inserts scratch rows
or refreshes timestamps. Both modes use the existing importer advisory lock.
Apply additionally serializes table writers while allowing readers; lock and
statement timeouts are 10 seconds. Any failure rolls back the entire batch.

Positive-area overlap is checked only at the **same stored level**, both within
the final batch and against rows outside the batch. Shared edges/points are valid.
State/district/municipality containment is valid. When replacing multiple rows,
overlap checks use their new geometries, not obsolete versions of the same IDs.

The upsert uses `UNIQUE (osm_type, osm_id)` and additionally guards the existing
level. UUID and `created_at` survive updates. Geometry is stored as EPSG:4326
MultiPolygon; centroid uses `ST_PointOnSurface`. Names, country, region, OSM
metadata and `source='osm'` are retained. `retrieved_at` refreshes on every apply;
`updated_at` changes only for changed data. `municipality_key` and all population
fields are null. No rows are deleted when omitted from later manifests.

Existing expected-level resolution finds persisted district/state rows without
resolver changes, even when municipality display names mention the same district.

## Schleswig-Holstein examples

- [State manifest](manifests/sh-state.json): Schleswig-Holstein only; not a complete
  inventory of German states (`complete=false`).
- [District manifest](manifests/sh-districts.json): the eleven rural districts,
  explicitly excluding Flensburg, Kiel, Lübeck and Neumünster. Those remain
  municipalities under the existing importer.

Identities were checked against the [OSM boundary inventory](https://wiki.openstreetmap.org/w/index.php?title=Schleswig-Holstein&oldid=2323471)
and the public OSM relation metadata API on 2026-10-04. These are administrative
boundary relations, including maritime areas, not the alternate landmass relations.
This authoring-time review introduces no public OSM/Nominatim runtime dependency.
Re-review before applying; live boundary availability/classification still comes
from the configured private Research Geocoder.

| Name                  | OSM relation | Reviewed relation version | Raw admin level |
| --------------------- | ------------ | ------------------------- | --------------- |
| Schleswig-Holstein    | 51529        | 311                       | 4               |
| Dithmarschen          | 27028        | 142                       | 6               |
| Herzogtum Lauenburg   | 62703        | 136                       | 6               |
| Nordfriesland         | 27019        | 135                       | 6               |
| Ostholstein           | 27025        | 175                       | 6               |
| Pinneberg             | 62408        | 108                       | 6               |
| Plön                  | 27026        | 99                        | 6               |
| Rendsburg-Eckernförde | 27017        | 183                       | 6               |
| Schleswig-Flensburg   | 27014        | 132                       | 6               |
| Segeberg              | 62733        | 121                       | 6               |
| Steinburg             | 27016        | 116                       | 6               |
| Stormarn              | 62546        | 125                       | 6               |

## Migration and operator commands

Migration **0019** is required: the previous `research_area_type` check allowed
region/district/municipality but not state. This additive migration only widens
that check; it does not import or reclassify data. Its downgrade refuses while
state rows remain, without deleting them. Apply through the existing migration
workflow using the migrator, never the runtime or operator connection.

No new grants are needed. The existing auth operator connection from
`ADMIN_AUTH_MANAGEMENT_DATABASE_URL` requires SELECT on `admin.alembic_version`
and SELECT/INSERT/UPDATE on `admin.research_area`. Existing operator boundary,
schema-head and grant checks run first. Runtime SELECT-only area access remains
unchanged. Provision the Geocoder key separately in protected `runtime.env`.

Copy/review the example into an operator-owned path. Plan:

```sh
sudo bash -lc '
set +x
set -e
set -a
source /etc/uranus-admin/operator.env
source /etc/uranus-admin/runtime.env
set +a

cd /var/lib/uranus-admin/current/backend

runuser -u oklab -- \
  /usr/local/bin/uv run \
  --no-cache --no-sync --offline --no-python-downloads --no-env-file \
  python -m app.research.administrative_areas \
  plan /path/to/sh-districts.json
'
```

Review the bounded JSON report (identity/name/level/status and counts), then apply:

```sh
sudo bash -lc '
set +x
set -e
set -a
source /etc/uranus-admin/operator.env
source /etc/uranus-admin/runtime.env
set +a

cd /var/lib/uranus-admin/current/backend

runuser -u oklab -- \
  /usr/local/bin/uv run \
  --no-cache --no-sync --offline --no-python-downloads --no-env-file \
  python -m app.research.administrative_areas \
  apply /path/to/sh-districts.json
'
```

Use `/path/to/sh-state.json` for the state; either order is valid. Apply repeats all
validation against current service/database state; a plan is not a frozen geometry
snapshot or a token bypassing revalidation. Errors never print provider/SQL details,
credentials or geometry. No deployment, import or migration is automatic.

## Regression coverage

`backend/tests/test_research_administrative_areas.py` covers manifest bounds,
expected roles, municipality exclusion, state codes, missing/invalid boundaries,
plan/no-write, idempotent apply, identity conflicts, atomic overlap rejection,
hierarchical containment, level-aware resolver lookup and guarded migration SQL.
Database cases use the existing disposable PostGIS fixture; ordinary transport
cases use a mocked Geocoder. Tests were added but not run for this change, as
requested. No Docker or CI waiting is needed by the operator workflow.
