# Remaining issues: implementation audit

Baseline: main at `8fea79e1d42019799202026d2f1d62263b146a86`.
No live production connection, migration, service or reverse-proxy change was performed.

## #9 — persisted runs and finding history: complete in this PR

Already present: durable queued/running/success/failed jobs, fenced worker leases,
first/last seen timestamps, retained resolved rows, idempotent finding identity,
and failed/incomplete/uncovered-scan resolution guards (`tests/test_checks.py`).
Missing: dashboard access to the last successful run. Added separate latest-run
and last-success summaries, deterministic tie ordering and current-stock UI.
Failed runs never masquerade as successful; no-run/live states remain honest.
Tests: `test_dashboard.py`, `dashboard-check-status.test.ts`; existing persistence,
resolution and worker tests remain unchanged.

## #13 — live source inconsistencies: progress, remains open

Repository/schema-fixture review already exists in `source-verification.md`.
Added `python -m app.source_schema_verify --json` for an operator to verify the
actual catalog: scope/default/CHECK values, space-feature types/FKs, partner
constraints/status, membership/permission pair uniqueness/FKs, timestamp types.
Tests demonstrate read-only queries and sanitized failures.
**Actual authoritative live verification: not performed.** Storage timezone requires
operator confirmation independent of column type. No new rule relies on an unverified
inconsistency. Do not close #13 until a reviewed live report exists.

## #15 — domain sections/create flow: progress, remains open

Added all six list/detail pairs: events, venues, spaces, organizations, users and
images. Navigation is enabled; Activity/Findings/Graph canonical targets lead to
real detail pages. SQL search/filter/count/page ordering is bounded and parameterized.
Related records are paginated. Views include safe previews, addresses/geolocation,
statuses, safe user email/avatar and typed source facts/counts; workflow links reuse
marks, exact finding filters and graph. No join/login timestamp is inferred.
Unsupported image contexts count as links but only verified organization/venue/event
contexts yield related entity links. Domain reads remain read-only.
Tests: `test_entities.py`, `entities.test.ts`, `entities.spec.ts`, proxy tests.

**Remaining:** create/edit workflows need explicitly delegated Uranus API credentials
and authorization. Independent admin sessions cannot authenticate to Uranus JWT and
organization permission endpoints. No token bridge or SQL-write substitute was
invented. The create control explains the missing setup and remains disabled.
Verified endpoint evidence and the required adapter contract are in `contracts.md`.
Do not close #15 on read-only pages alone. Editing and further per-entity filters
remain follow-up work.

## #11 — stable cursor API: complete in this PR

Offset API and page-number UI remain compatible. Activity adds validated opaque
cursors with UTC created time/type/key, or type/key only for unknown timestamps.
The original time window survives subsequent requests. Persisted findings use the
same effective priority score/ID order as offset. Scopes bind endpoints and filters;
mixed page/cursor and live-finding cursors fail with 422. Page size remains 1–100.
Tests: `test_cursors.py` covers ties, mixed types, inserted rows, unchanged originals,
unknown timestamps, invalid encoding/types/endpoints/scopes and size boundaries.
Changing existing ordering fields is not a multi-request snapshot; this limitation
is documented.

## #12 — asynchronous safe reachability: complete in this PR

`url_syntax` stays local. A separate optional PostgreSQL-backed worker discovers
source URLs in bounded pages, claims observations with leases, performs bounded
async network checks and persists attempts/successes/status. No GET/core scan waits
for HTTP. Every DNS answer must be public; numeric-IP dialing prevents re-resolution
while preserving Host and verified TLS identity. Redirects are revalidated.
Tests cover private/metadata/loopback/link-local/IPv6/transition ranges, mixed DNS,
rebinding, private redirects, loops/limits, body/time limits, DNS/TLS errors, 200,
301, 403 and 429 without Internet access. Persistence tests cover expiry, fencing,
URL changes, concurrent claims, TTL, repeat-failure warnings, human state and exact
field resolution. Only successful checks resolve; 403/429 remain inconclusive.
Migration 0007, SIU grants and worker operation are documented in `development.md`.

## Preserved boundaries

- Source reads use DATABASE_URL in read-only transactions.
- ADMIN_DATABASE_URL stores metadata only; account/grant restrictions and append-only
  record-mark history remain unchanged.
- DDL stays migration-only; migration 0007 never alters Uranus.
- No production credential, source secret or response body is returned or logged.
- Proxy paths/methods/queries stay explicit; dev auth remains non-production.
- CodeQL, dependency review and functional CI gates remain enabled.

## Acceptance-criterion checklist

### #9

- [x] Persisted runs — existing check worker/storage.
- [x] Last successful run available to dashboard — added here.
- [x] Failed runs visible — existing checks page, now also dashboard.
- [x] Real first_seen_at — existing persistence.
- [x] Real last_seen_at — existing persistence.
- [x] Resolved findings retain history — existing persistence.
- [x] Failed runs cannot resolve findings — existing guarded coverage.
- [x] Repeat scans do not duplicate findings — existing stable identity.

### #11

- [x] Activity cursor API.
- [x] Deterministic unique tie-breaker.
- [x] Persisted findings cursor API.
- [x] Inserts-between-requests tests.
- [x] Identical-timestamp tests.
- [x] Invalid-cursor validation errors.

### #12

- [x] Syntax stays separate.
- [x] Private/internal IP blocking.
- [x] DNS-resolved private-target blocking.
- [x] Redirect revalidation.
- [x] Request timeouts.
- [x] Redirect limit.
- [x] Bounded response size.
- [x] 403/429 are inconclusive.
- [x] Persisted last attempt and success.
- [x] SSRF-focused tests.

### #13

- [ ] Authoritative live venue scope/default verification.
- [ ] Authoritative live space-feature identifier verification.
- [ ] Authoritative live partner constraints verification.
- [ ] Authoritative live membership/permission uniqueness verification.
- [ ] Timestamp storage semantics confirmed by operator.
- [ ] Confirmed live results documented.
- [ ] Live evidence available for all affected quality-rule decisions.

The new command supplies the catalog evidence mechanism, not the missing live evidence.

### #15

- [x] Veranstaltungen navigation available.
- [x] Orte & Räume navigation available.
- [x] Organisationen navigation available.
- [x] Benutzer & Teams navigation available.
- [x] Bilder navigation available.
- [x] Real routes for each section.
- [x] Paginated lists.
- [x] Search and organization/status filters where supplied by the source projection.
- [x] Entity detail views.
- [x] Findings link to canonical supported entity details.
- [x] Marks link to canonical supported entity details.
- [ ] Working `+ Datensatz` workflow — authorization prerequisite unresolved.
- [ ] Authorized Uranus API write integration — no write operation enabled.
- [x] Read-only Uranus PostgreSQL boundary.
- [x] Explicit safe response fields.
- [x] Backend tests.
- [x] Frontend lint.
- [x] Frontend typecheck.
- [x] Frontend unit tests.
- [x] Nuxt production build.
- [x] Playwright domain workflows (desktop/mobile).

Checked entries describe this branch, not deployment or issue closure. Create/edit
and richer entity-specific management remain tracked in #15.
