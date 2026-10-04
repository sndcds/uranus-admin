# Persistent administrative boundaries

`app.research.administrative_areas` is an explicit operator tool for **district**,
**state** and **region** boundaries in `admin.research_area`. It never runs during
deployment, migration, API startup, queries or worker startup. No Uranus source
data is written. `app.research.areas` and `app.research.scope` continue to own
municipalities; `municipality` and `country` remain unsupported here.

The Research storage hierarchy is:

- Germany: `state` → `district` → `municipality`, with independent cities remaining
  municipality entities instead of duplicate districts.
- Denmark: `region` → `municipality`. There is no Danish district layer.

This describes Research storage, not equivalent administrative systems. In
particular, **Region Syddanmark is `region`, never `state`**.

## Reviewed inventory and the city-state limit

[The manifest inventory](manifests/README.md) lists every exact manifest path and
batch count. Review date: **2026-10-04**. There are:

- **14 importable German state manifests**; all **16** state identities are reviewed.
- **13 German district manifests**, containing **294 distinct rural-district
  identities**, cross-checked against the Deutscher Landkreistag inventory.
- **5 Danish region manifests**, one for each of DK-81 through DK-85.

**Berlin (R62422) and Hamburg (R62782) cannot also be persisted as states under
this model.** Those exact state relations are already protected municipality
identities in `areas.CITY_EXCEPTIONS`. `UNIQUE(osm_type, osm_id)`, municipality
exclusion and the prohibition on reclassification make 16 simultaneously stored
German states impossible without a separately authorized model change. They are
recorded in [reviewed-inventory.csv](manifests/reviewed-inventory.csv) as
`municipality_identity_excluded`, with versioned OSM evidence, and deliberately
have no executable state manifest. No substitute or guessed identity is used.
Bremen's distinct state relation R62718 is importable; its two city relations
R62559 and R62658 remain municipalities.

[excluded-municipalities.csv](manifests/excluded-municipalities.csv) records all
107 existing German city exceptions, including Flensburg, Kiel, Lübeck,
Neumünster, Berlin and Hamburg, with municipality keys and verified OSM versions.
The district set includes Region Hannover, StädteRegion Aachen and Regionalverband
Saarbrücken as district-role associations listed by the DLT, not as municipalities.

For each district manifest, `complete=true` means **complete reviewed rural-district
inventory for that Bundesland; municipality-role independent cities excluded by
the persistent model**. It does not mean every `admin_level=6` object, a partition
covering independent cities, or a complete catalog of all possible administrative
roles. City states have no rural-district manifests. Each state/region manifest
has `complete=false`: it is a single identity, not the country's entire inventory.

These flags and `parent_area_id` describe reviewed scope; they do not persist
hierarchy or establish execution-time completeness for zero-event grouping.
Do not substitute this rural-only inventory for an exhaustive operator catalog.

## Manifest and authority

The closed `PersistentManifest` extends
`app.research.administrative_import.Manifest`. A file contains 1–100 unique OSM
**relation** identities (positive signed bigint), one level, one country and one
reviewed region. File size remains limited to 64 KiB. No name searches, first-hit
selection or discovery occurs during plan/apply.

The explicit supported combinations are:

| Expected semantic level | Exact country codes | Reviewed region code                            |
| ----------------------- | ------------------- | ----------------------------------------------- |
| `state`                 | `["DE"]`            | The state's supported DE subdivision code       |
| `district`              | `["DE"]`            | The containing Bundesland's DE subdivision code |
| `region`                | `["DK"]`            | `DK-81`, `DK-82`, `DK-83`, `DK-84` or `DK-85`   |

`osm_admin_level` remains mandatory reviewed metadata (2–12). Checked-in state and
Danish region relations currently have raw level 4; district relations have raw
level 6. These observed values are **not classification rules**. `reviewed_on` is
present in every checked-in manifest; older operator manifests may omit that
advisory date and retain their existing `inventory_source` review provenance.

Only the configured private `ResearchGeocoderClient` supplies current names,
country, administrative roles and boundary geometry. Each lookup uses its existing
authenticated, bounded 8 MiB boundary transport. The importer continues to call
`resolved_boundary(place, manifest.level)`, requires the exact relation identity
and country, and rejects any municipality role. Known German municipality
exceptions are also rejected before lookup. An existing row with another
`area_type` always fails closed, even if provider metadata now claims another role.

For states **and regions**, an available Geocoder `ISO-3166-2` official code must
match `region_code`. The current Geocoder contract does not expose all storage
metadata: raw OSM admin level and district-to-state membership remain explicitly
reviewed manifest assertions. A missing official subdivision code is not fabricated.
Neither `region_code`, names nor a raw OSM tag can replace the Geocoder's semantic
role validation. No German-level assumption is applied to Denmark.

## Validation and persistence

Plan and apply use the same lookup, geometry, classification and overlap pipeline.
Network calls finish before each database transaction. Polygons must be closed and
bounded, with at most 500,000 points per boundary and 32 MiB geometry JSON per
manifest. PostGIS rejects empty/invalid geometry; there is no simplification or
repair. Inventory review confirms identities and tags, not production Geocoder
availability, role metadata or the size/topology of its current geometries. A
failed lookup, transport limit, topology check or role check blocks that manifest.

Plan uses a read-only repeatable-read transaction: no scratch rows or timestamp
refresh. Both modes retain the importer advisory lock. Apply also serializes table
writers while allowing readers; statement and lock timeouts remain 10 seconds.
Each manifest commits atomically or rolls back in full.

Positive-area overlaps are rejected only at the **same stored level**:
`district/district`, `state/state`, `region/region`. Shared edges/points are valid.
Municipality/district, district/state and municipality/region containment are valid,
including Danish municipalities inside regions. Updated batch geometries replace
old versions for the overlap comparison. No geographic coverage is inferred.

Upserts preserve UUID and `created_at`, EPSG:4326 MultiPolygon geometry and
`ST_PointOnSurface` centroids. `retrieved_at` refreshes on apply; `updated_at`
changes only for changed data. Municipality keys and population fields stay null
on these nonmunicipal rows. Existing expected-level resolution supports all three
levels and excludes wrong-level matches before ranking/limiting.

## Migration and privileges

The audited main baseline is `cf9985ac48fa2a0ed89282ba2ba3f00c862c25ef`, with
Alembic head **0019**. Its `research_area_type` constraint already permits
`region`, `district`, `municipality` and `state`. **No new migration is needed**;
no shipped revision is changed. Use the regular migration workflow to reach the
current deployed code's head before invoking the importer.

No new grants are required. The auth operator connection from
`ADMIN_AUTH_MANAGEMENT_DATABASE_URL` needs SELECT on `admin.alembic_version` and
SELECT/INSERT/UPDATE on `admin.research_area`. Existing operator boundary,
schema-head and grant checks run before imports. Runtime SELECT-only access stays
unchanged. Provision the Geocoder key in protected `runtime.env`.

## Production plan and apply

The batch CLI reads only `de/states/*.json`, `de/districts/*.json` and
`dk/regions/*.json` under the supplied root, in that order, sorted by filename
within each group. CSV/README files are advisory evidence, never import authority.
The root may contain a reviewed subset, but must contain at least one manifest;
there is a 64-manifest limit. Directory scope, filename/region and repeated OSM
identities across files are checked before any network/database work.

Plan **all** intended manifests first:

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
  python -m app.research.administrative_areas_batch \
  plan /var/lib/uranus-admin/current/docs/research/manifests
'
```

Review each JSON report's manifest path, identities, names, levels and
new/updated/unchanged counts. Only after that review, apply:

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
  python -m app.research.administrative_areas_batch \
  apply /var/lib/uranus-admin/current/docs/research/manifests
'
```

Apply first repeats a read-only plan of **every** manifest, then applies each
sequentially with full live revalidation. No parallel writes or giant transaction
are used. Planning checks against the current stored rows, not a simulated final
state of other manifests; cross-manifest same-level conflicts are caught when
applying against preceding commits. A plan is not a frozen geometry snapshot or
an approval token bypassing checks.

The first failure stops execution and reports `failed_manifest` and `phase`, with
no provider/driver details, geometry or credentials. Previously committed
manifests remain applied; the failed transaction rolls back. Correct the cause,
plan the entire intended set again, review it, then restart apply from the root.
Already-applied unchanged identities retain UUIDs and are reported as unchanged.

Individual imports remain available, for example from `backend/` with the same
operator environment:

```sh
python -m app.research.administrative_areas plan ../docs/research/manifests/de/districts/DE-SH.json
python -m app.research.administrative_areas apply ../docs/research/manifests/de/districts/DE-SH.json
```

The old `sh-state.json` and `sh-districts.json` examples have moved into the
country/level directories; there are no duplicate executable SH inventories.

## Post-import verification

Run these read-only queries through an authorized admin reader/operator:

```sql
SELECT area_type, country_code, count(*)
FROM admin.research_area
GROUP BY area_type, country_code
ORDER BY country_code, area_type;

SELECT name, area_type, country_code, region_code, osm_admin_level
FROM admin.research_area
WHERE area_type IN ('state','district','region')
ORDER BY country_code, area_type, region_code, name;

SELECT osm_id, name, area_type, country_code, region_code, osm_admin_level
FROM admin.research_area
WHERE osm_type = 'R' AND osm_id IN (51529, 27014, 27019, 1319978)
ORDER BY osm_id;
```

Expect Schleswig-Holstein R51529 → `state`, Schleswig-Flensburg R27014 →
`district`, Nordfriesland R27019 → `district`, and Region Syddanmark R1319978 →
`region`. Source names may include the prefix `Kreis`. After successful application
of the full checked-in set to otherwise empty nonmunicipal storage, expect
DE/state=14, DE/district=294 and DK/region=5. Counts may include previously stored
areas because the importer never synchronizes by deletion.

## Rollback and regression coverage

Removing a manifest or omitting an identity **does not delete any row**. Cleanup
must be a separate explicit future operator action. There is no destructive sync,
automatic rollback of earlier successful manifests or source mutation.

Regression cases cover country/level validation, Danish region persistence,
municipality conflicts/containment, same-level overlap, read-only plans, idempotence,
batch ordering/failure/restart and offline manifest evidence. PostGIS v12 cases
exercise persisted state/district/region resolution, outside-state execution and
wrong-level exclusion for the requested German queries and a Danish Syddanmark
example. Their Planner responses are fixtures: they do not prove live Planner
language support. Tests are added but **not executed**, per the task instruction.
No production import, deployment, Docker run or CI wait is part of this change.
