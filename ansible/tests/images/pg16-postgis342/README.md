# PostgreSQL 16.15 + PostGIS 3.4.2 CI Fixture for Kulturbytes Admin

This directory provides an **audited, reproducible PostgreSQL/PostGIS test image** for
Kulturbytes Admin's Ansible and SQL Console security tests. It reproduces the reviewed
**PostgreSQL 16.15 / PostGIS 3.4.2** stack without connecting to production data and is
intended only for disposable local/CI verification.

It is useful for contributors working on PostgreSQL privilege boundaries, PostGIS function
policies, SQL Console hardening, reproducible deployment checks and compatibility audits.

Related documentation:
[Kulturbytes Admin deployment](../../../README.md).

## Scope and safety

This disposable CI image reproduces the versions documented in `ansible/README.md`.
No production connection or production catalog was used. It contains normal Ubuntu
packages and initializes a fresh database; no PUBLIC function ACLs are pre-hardened.
The fixed password is a public synthetic test credential. Never use this image for deployment.

## Reproducible inputs

The combined image is built locally and in CI, not published to a container registry.
Its local image ID is not a portable registry manifest digest. The immutable inputs are:

- Ubuntu 24.04 amd64 base:
  `ubuntu@sha256:496754492fb28b4d3049432f2ca787449331e23fb14f0dd3fffea86bf5a93eb4`.
- Bootstrap CA bundle only, copied from the already reviewed CI image:
  `postgis/postgis@sha256:44126d872ac91993766c341e369c539e8196614321765d36a6f1bab0419a5fa5`.
  No PostgreSQL/PostGIS binaries or SQL come from this second image.
- Signed [Ubuntu archive snapshot](https://snapshot.ubuntu.com/ubuntu/20260915T000000Z/),
  suites `noble`, `noble-updates`, `noble-security`, components `main`, `universe`.
  All dependency resolution uses this fixed snapshot. APT verifies the Ubuntu archive
  signatures/package checksums; TLS verification stays enabled.
  Index and package downloads retry transient failures up to five times. Any failed
  index download stops the build before package installation. A persistent snapshot
  outage fails this matrix job; the other pinned stacks continue independently.
- `postgresql-16` and `postgresql-client-16`: **16.15-0ubuntu0.24.04.1**.
- `postgresql-16-postgis-3` and `postgresql-16-postgis-3-scripts`:
  **3.4.2+dfsg-1ubuntu3**.

Upstream package descriptions:
[PostgreSQL](https://packages.ubuntu.com/noble-updates/postgresql-16),
[PostGIS](https://packages.ubuntu.com/noble/postgresql-16-postgis-3).
The dated archive and explicit package versions, not these moving package pages,
are the build inputs. The Dockerfile never upgrades to whatever version is newest.

## Audit result and comparison

The existing `audit_sql_console_functions.py` emitted a candidate from a fresh
`template0` database with only `CREATE EXTENSION postgis`. The candidate was reviewed
before manual integration into Contract v4 / Function Policy v2. The helper does not
write the contract. The separately read complete canonical function inventories were
compared by signature, definition hash, volatility, language, C library and membership.

| Catalog                                         | PostgreSQL 16.15 / PostGIS 3.4.2 | PostgreSQL 16.4 / PostGIS 3.4.3 |
| ----------------------------------------------- | -------------------------------: | ------------------------------: |
| Core functions                                  |                             3294 |                            3294 |
| plpgsql functions                               |                                3 |                               3 |
| PostGIS functions                               |                              776 |                             777 |
| PostGIS IMMUTABLE / STABLE / VOLATILE           |                    684 / 13 / 79 |                   685 / 13 / 79 |
| Restricted PostGIS signatures                   |                               95 |                              95 |
| Restricted core signatures                      |                              153 |                             153 |
| Planned PUBLIC EXECUTE removals, core + PostGIS |                          96 + 95 |                         96 + 95 |

Differences in the two actual package installations:

- 3.4.2 has no `public._st_concavehull(public.geometry)` helper.
- `public.st_concavehull(public.geometry, double precision, boolean)` is an IMMUTABLE,
  invoker C function using `$libdir/postgis-3`, entry point `ST_ConcaveHull`, in 3.4.2.
  The older-GEOS Debian 3.4.3 build instead uses an IMMUTABLE plpgsql implementation
  and the additional helper. This is a package/build difference as well as a version
  comparison; it must not be generalized to every 3.4.2/3.4.3 package.
- `_postgis_deprecate(text, text, text)` differs only in its embedded version literal.
- `postgis_scripts_build_date()` returns `2024-04-01 07:18:37` instead of
  `2024-09-11 18:11:28`.
- `postgis_scripts_installed()` embeds `3.4.2 c19ce56` instead of `3.4.3 e365945`.
- All other common canonical function entries are identical. All restricted signatures,
  their definition hashes, original PUBLIC EXECUTE and privileged grantees are identical.
  All 4,073 common functions also have identical complete initial EXECUTE ACLs (including
  safe functions), not just identical restricted ACLs.
  All 95 restricted PostGIS functions initially have PUBLIC EXECUTE. The core's existing
  privileged grantees, including `pg_monitor`, are unchanged.
- PostGIS extension membership and C-library paths for common functions are unchanged,
  except the documented ConcaveHull language/library difference. Extension/function
  owners must still be privileged installation roles, never either console role;
  PostGIS must be in `public`, plpgsql in `pg_catalog`.
- Core and plpgsql fingerprints from PostgreSQL **16.15** were actually compared with
  **16.4** and are identical. The complete catalogs remain in each selected snapshot;
  there is no fallback to a different snapshot's core.

Exact catalog SHA256:

```text
core:    98b7eaf0df1b98afcf460672ef9815ec817fbd5a6b86a584107b7fb3da6d42ba
plpgsql: eaecbad5556ae377254217e7de0a3240a654ae64fb8eed32567283566e9044fd
postgis: f327f881827c95e7f25db1735333ff5f9a4ae6edfaaf3841a9bcff2147a406d8
```

PostGIS metadata fingerprints (identical in all three reviewed combinations):

```text
public.geography_columns: f75cb1e255c3e24140755d41aea9550021e7a08f488889a86fd5d44cfe7a9f8e
public.geometry_columns:  0e8e63ec2b3febb07a3e9d7cbe749855127d3e38f4ecb1ec013263ca2a94ac23
public.spatial_ref_sys:   62e9e170cf6007859468869b1f414131ba20b0f35cd68d6502af63a0b676ddd6
```

These are exact build fingerprints, not a promise that every installation labelled
3.4.2 has identical SQL definitions. A different package build, added function, changed
extension membership or definition still fails closed. No build-date normalization or
version wildcard was introduced.

## Reproduce locally

From the repository root, with Docker and uv:

```sh
docker build -t uranus-console-production-test:local ansible/tests/images/pg16-postgis342
docker run --detach --name console-production-audit \
  --publish 127.0.0.1:55842:5432 uranus-console-production-test:local
docker exec console-production-audit pg_isready -h 127.0.0.1 -U postgres
# Wait for readiness before the following commands.
docker exec console-production-audit createdb -U postgres -T template0 function_audit_test
docker exec console-production-audit psql -U postgres -d function_audit_test \
  -c 'CREATE EXTENSION postgis'
ANSIBLE_TEST_DATABASE_URL=postgresql://postgres:local-fixture-only@127.0.0.1:55842/function_audit_test \
  uv run --no-project --python 3.13 --with-requirements ansible/requirements-test.txt \
  python ansible/tests/audit_sql_console_functions.py > /tmp/sql-console-342-candidate.json
ANSIBLE_TEST_EXPECTED_STACK=160015/3.4.2 \
ANSIBLE_TEST_DATABASE_URL=postgresql://postgres:local-fixture-only@127.0.0.1:55842/uranus_ansible_test \
  uv run --no-project --python 3.13 --with-requirements ansible/requirements-test.txt \
  python -m unittest discover -s ansible/tests -v
docker rm --force --volumes console-production-audit
```

The `psql` command above prepares only the disposable audit fixture. Compatible
production provisioning is entirely Ansible-managed and needs no manual `psql` step.
The production-baseline preflight regression asserts real server version `160015`,
exact extversion and fingerprints, the normal-installation EXECUTE/TEMP plan, both
console roles' lack of restricted EXECUTE/TEMP, and a second apply with no changes.
The same suite runs against the two existing pinned compatibility images.
