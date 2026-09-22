# AGENTS.md

## Project overview

`uranus-admin` is the independent administration, data-quality and operations system
for Kulturbytes/Uranus. It reads Uranus domain data and owns separate admin workflow
and authentication state. Admin authentication does not confer Uranus write access.

Implemented features include persisted quality findings/reviews, independent administrator
assignments and a deduplicated admin inbox, record marks and notes, activity, entity
lists/details, operational queues, statistics, a bounded D3
relationship graph, asynchronous URL checks, and organization email notifications
with delivery history and manual retries. Domain creation/editing is unavailable.
Global administrative Geo Scope uses cached boundaries and authoritative Uranus points.
Nominatim location suggestions are stored separately in admin and are never authoritative.
Never write Uranus organization/venue points directly or automatically accept a suggestion.

Prefer current code, migration metadata and CI over historical implementation notes.
Recheck these facts when changing the corresponding subsystem; never present an open
branch, planned feature or synthetic fixture as a deployed source contract.

## Architecture and repository layout

Browser → same-origin Nuxt/Nitro proxy → FastAPI → separate source/admin connections.
Standalone workers share the backend services and durable PostgreSQL admin state.

| Location                                                          | Responsibility                                                       |
| ----------------------------------------------------------------- | -------------------------------------------------------------------- |
| `backend/app/main.py`, `backend/app/config.py`                    | FastAPI composition, lifecycle, validated settings                   |
| `backend/app/api/`, `backend/app/schemas/`                        | HTTP endpoints and Pydantic request/response contracts               |
| `backend/app/repositories/`, `backend/app/services/`              | Explicit SQL projections and business rules                          |
| `backend/app/auth/`                                               | Independent accounts, sessions, authorization, operator CLI          |
| `backend/app/database.py`, `backend/app/admin_database.py`        | Source reader and restricted admin runtime                           |
| `backend/app/admin_tables.py`, `backend/app/storage_preflight.py` | Admin metadata, head/grant checks                                    |
| `backend/migrations/versions/`                                    | Alembic revisions for admin only                                     |
| `backend/tests/`                                                  | Unit, API, PostgreSQL/PostGIS and role-boundary tests                |
| `frontend/app/`                                                   | Nuxt 4/Vue 3 pages, components, Pinia stores, middleware, API client |
| `frontend/server/`, `frontend/shared/`                            | Nitro allowlisted proxy, Zod contracts and safe errors               |
| `frontend/tests/`                                                 | Vitest unit tests, Playwright E2E, synthetic fixtures                |
| `.github/workflows/`                                              | CI and security gates                                                |

Start with [README.md](README.md), [backend/README.md](backend/README.md) and
[frontend/README.md](frontend/README.md). Detailed contracts and operations live in
[backend/docs/contracts.md](backend/docs/contracts.md),
[backend/docs/development.md](backend/docs/development.md) and `frontend/docs/`.
There is no root `docs/` directory.

## Database boundaries

| Setting                              | Provisioned role      | Allowed purpose                                                                    |
| ------------------------------------ | --------------------- | ---------------------------------------------------------------------------------- |
| `DATABASE_URL`                       | `uranus_reader`       | SELECT-only Uranus source access; no domain DML or DDL                             |
| `ADMIN_DATABASE_URL`                 | `admin_user`          | Explicit minimal DML on admin workflow/session tables; no DDL or Uranus writes     |
| `ADMIN_MIGRATION_DATABASE_URL`       | `admin_migrator`      | Alembic owner and DDL in `admin` only; never runtime credentials                   |
| `ADMIN_AUTH_MANAGEMENT_DATABASE_URL` | `admin_auth_operator` | Separate operator connection for account/grant management and bounded auth cleanup |

The auth operator uses the same `admin` schema, not a separate identity database.
Runtime checks inspect effective privileges of the connected role; role names alone
do not establish safety. All backend connections use PostgreSQL through asyncpg.

**NEVER write directly to the `uranus` schema from application code or migrations.**
Forbidden operations include `INSERT INTO uranus.*`, `UPDATE uranus.*`,
`DELETE FROM uranus.*`, `ALTER TABLE uranus.*` and `CREATE INDEX` on Uranus tables.
Source transactions use READ ONLY / REPEATABLE READ and UTC session time; preserve
these settings and database-enforced least privilege.

Any future domain write requires an explicitly verified, authorized Uranus API write
contract with per-operation authorization. NEVER introduce service-token shortcuts,
direct SQL mutation, impersonation or shared signing secrets. The disabled create UI
MUST NOT be enabled by a browser capability flag.

## Source-data rules

- Use explicit source columns, bound values and fixed application-owned identifiers.
  Do not add `SELECT *` domain projections or ORM reflection of Uranus tables.
- Verify schema, joins, ownership and timestamp meaning before extending a query.
  `backend/app/source_schema_verify.py` performs read-only catalog verification;
  run `uv run python -m app.source_schema_verify --json` from `backend/` with an
  authorized reader when live verification is needed. Fixtures are not live evidence.
- Use `entity_key` (including composite keys); `entity_id` is a legacy nullable UUID
  alias. Admin actor subjects (`admin:<UUID>`) are not Uranus user IDs.
- Missing timestamps stay unknown. Invitation time is not membership join time;
  activation status is not login history. Do not guess public links or relationships.
- Preserve effective venue/space inheritance in `backend/app/repositories/location.py`
  and temporal semantics in `backend/app/repositories/temporal.py`.
- Preserve PostGIS coordinate/SRID contracts and existing location projection helpers.
  New spatial queries should use appropriate existing indexes and server-side filtering;
  required source indexes belong in Uranus-owned migrations, never automatic admin DDL.

## Admin persistence and migrations

Admin owns check runs, findings/reviews and append-only finding events, record marks/events, URL observations,
notification intents/deliveries/items, accounts, grants, sessions and login buckets.
The authoritative table definitions are in `backend/app/admin_tables.py`.

- `admin_migrator` owns admin tables. `admin_user` MUST NOT own tables, inherit the
  owner role or acquire schema CREATE. Grants are explicit operator provisioning,
  not runtime self-repair or blanket default privileges.
- Use `RUNTIME_GRANTS` in `backend/app/storage_preflight.py` as the current required
  grant set, including SELECT on `admin.alembic_version`.
- Runtime has SELECT-only access to `auth_account` and `auth_system_admin`. Account/grant changes
  belong to `app.auth.manage`; operator cleanup uses `app.auth.maintenance`.
- No runtime DELETE grants are currently required. Operator retention deletes only
  explicitly authorized auth data. Preserve append-only `finding_event`, `assignment_event`,
  `record_mark_event` and `notification_delivery_item` records, mark/assignment versions and
  immutable sent history.
- NEVER rewrite a migration already shipped. Add a revision, preserve existing data,
  and describe any unavoidable loss. Revisions use frozen definitions, not imports
  of mutable application table metadata.
- Always inspect the current Alembic head before adding a migration. Do not pin
  operational instructions to an old numbered revision.
- `backend/migrations/env.py` limits metadata comparison and version storage to
  `admin`. Migration commands bootstrap a missing schema as the connected migrator;
  this first run requires database CREATE, which can be revoked afterward. Existing
  schema ownership and grants are preserved; roles/grants remain operator provisioning.
  Migrations require the explicit
  `ADMIN_MIGRATION_DATABASE_URL`; NEVER fall back to `DATABASE_URL` or runtime access.
- The API and workers NEVER auto-migrate or grant privileges.

From `backend/`, with an explicitly selected migration target and migrator access:

```sh
uv run alembic heads
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

## Authentication and authorization

[Authentication contract](backend/docs/authentication.md): independent accounts in
`admin.auth_account` use Argon2id; `admin.auth_system_admin` separately grants global
access. There is no Uranus login/status lookup, JWT bridge, SSO or shared signing key.

Sessions are server-side: the database stores token digests, with revocation,
credential-version, absolute expiry, idle expiry and current grant checks. Passwords
and session values MUST NOT enter response bodies, URLs, logs, Pinia or SSR payloads.
Browser session values are transmitted only through the intended HttpOnly cookie.
Production/staging use `__Host-admin_session`, Secure, SameSite=Strict, Path=/,
without Domain; development/test use the local `admin_session` cookie.

All `/api/v1` routes and `/auth/session` require `get_current_admin`. State-changing
admin routes MUST preserve this authorization and typed, bounded request contracts.
Login and cookie-authenticated writes require exact `AUTH_PUBLIC_ORIGIN` validation
and `X-Admin-CSRF: 1`; preserve logout's equivalent cookie/no-credential checks.
Bearer sessions follow the existing non-cookie CSRF path; never invent a bypass.
Dev auth requires explicit opt-in and is limited to development/test.

Preserve login rate limits, body limits, hash concurrency limits and trusted ingress
handling. Nitro validates the socket peer before accepting configured `X-Real-IP`;
NEVER trust arbitrary forwarded headers or configure wildcard trusted proxy peers.
401 clears local protected data; 403 means denied authorization, not automatic logout.

## Backend conventions and timezones

- Python 3.13, FastAPI, Pydantic v2, async SQLAlchemy Core and existing parameterized
  SQL patterns. Keep endpoints thin and reuse repositories/services.
- Bound input lengths, result pages, graph expansion and network work. Batch related
  data; avoid N+1 queries. Existing quality scans load bulk snapshots: do not assume
  all reporting paths stream or add per-entity fetches to them.
- Preserve deterministic ordering, tie-breakers, pagination and consistent source
  snapshots. Do not substitute an empty successful result for an infrastructure error.
- Use `APIError` and the shared safe error envelope/codes. NEVER return raw driver,
  SMTP or provider errors, SQL, tracebacks or validation secrets in HTTP responses.
- Use aware UTC clocks and timezone-aware admin timestamps; never the server's
  implicit local timezone. Reuse period/temporal helpers instead of naive datetime logic.
- `URANUS_TIMESTAMP_TIMEZONE` interprets naive source timestamps (current default UTC).
  `ADMIN_TIMEZONE` defines admin calendar periods and notification daily quotas.
  `EVENT_TIMEZONE` interprets event date/time fields; both local defaults are Europe/Berlin.
  `today` is a local calendar period; `24h`/`7d` are rolling periods. Preserve DST behavior.
- Event-list upcoming/past filters use effective ends; quality/activity notification
  start checks use start semantics. These are intentionally different questions.

## Quality, workers and background jobs

Quality rules are deterministic and identities stable across runs. Preserve rule,
entity and field identity, evidence and coverage. Only a successful covering check
may resolve findings; failed/partial runs are not evidence of clean data. Human review
does not directly mutate source data or provide a manual resolved shortcut.
Quality rules MUST match current Uranus DDL. Secret source columns MUST NOT be
returned as values; token-presence checks project only non-sensitive booleans.

Run these standalone entry points from `backend/` (all support `--once`):

```sh
uv run python -m app.check_worker --once
uv run python -m app.url_check_worker --once
uv run python -m app.notification_worker --once
```

- `check_worker`: consumes durable check runs enqueued with HTTP 202; worker IDs,
  leases and supervised heartbeats fence completion. Expired crashed runs fail;
  a new check is an explicit new run.
- `url_check_worker`: discovers source URLs, stores observations in admin, applies
  TTLs, leases and bounded concurrency. Reachability is separate from deterministic
  URL syntax rules and NEVER runs in ordinary list requests.
- `notification_worker`: plans durable deliveries, claims leases, revalidates current
  eligibility, then sends outside the admin transaction and records fenced outcomes.
- Preserve idempotency, claim ownership and audit history. NEVER use detached
  fire-and-forget HTTP tasks or mark crashed/lost-lease work successful.
- Keep admin transactions/locks short around external work; NEVER send SMTP or perform
  external HTTP inside an admin write transaction. The existing URL worker holds a
  read-only source snapshot across its bounded batch; do not mistake it for a write lock.
- Keep entry points suitable for supervised services/timers. Monitor queue age and
  worker health separately from API readiness. Auth cleanup is an explicit bounded
  operator command: `uv run python -m app.auth.maintenance cleanup`.

## Notifications and external network access

[Notification contract](backend/docs/notifications.md): organization notification JSON
is source read-only. Detection, delivery state and history belong to admin. Missing
or incompatible source capability suppresses delivery; NEVER repair the source schema.

- `NOTIFICATIONS_DELIVERY_ENABLED` defaults false. Automatic dry runs detect without
  creating deliveries; an explicit manual retry can queue while sending stays disabled.
- External quality mail requires the explicit `EXTERNAL_POLICY` in
  `backend/app/services/notifications/policy.py`, current source evidence and eligible
  persisted open findings. Technical/internal rules MUST NOT become mail automatically.
- Keep user-facing recommendations separate from internal diagnostic messages. Recipient
  actions use verified user-facing Kulturbytes routes from `KULTURBYTES_APP_PUBLIC_BASE_URL`,
  never system-admin-only routes. Preserve DE/DA/EN localization and escaped rendering.
- Manual retry is allowed only for an eligible permanent failure: create a new delivery
  linked by `retry_of_delivery_id`, revalidate original items and enforce the active
  successor constraint. NEVER reset the historical row or send SMTP in the retry endpoint.
- Preserve immutable sent/composed audit content and normal bounded automatic retry
  semantics. SMTP is at-least-once around acceptance versus database commit; do not
  promise exactly-once delivery or fabricate provider success.
- SMTP host and public service origins come from trusted settings, not request fields.
  Authenticated SMTP requires STARTTLS with verified certificates. Plaintext is allowed
  only for an unauthenticated explicit loopback relay under `backend/app/smtp_policy.py`;
  DNS resolving a remote-looking name to loopback is not sufficient.
- The URL checker intentionally reads untrusted source URLs. Preserve HTTP(S)/port
  validation, rejection of credentials/sensitive query keys, public-IP checks on every
  connection and redirect, and numeric-IP pinning with original TLS hostname verification.
  Current limits: 20 seconds total, 256 KiB body, five redirects. No environment proxies,
  forwarded credentials, unrestricted fetch endpoint or persisted raw response bodies.

## Frontend conventions and global preferences

- Nuxt 4, Vue 3, Pinia, strict TypeScript and Zod. Use
  `frontend/app/utils/admin-api.ts`; validate responses at runtime, not by type assertion.
  ESLint forbids explicit `any`; do not silence it to bypass a contract.
- Import Zod through `frontend/shared/zod.ts` (`#shared/zod` in app code). Its `jitless`
  bootstrap is required for CSP. NEVER opt into Zod compilation or add `unsafe-eval`.
- Reuse `PageHeader`, `FilterBar`, `RequestState`, `ResultSummary`, `DataListShell`,
  `EmptyState`, `PaginationBar` and shared entity pages. Follow
  [design-system guidance](frontend/docs/design-system.md) and
  [data-page semantics](frontend/docs/data-pages.md); avoid duplicate page patterns.
- Global auth middleware validates before protected SSR/client rendering; `/login` is
  public with a separate layout. Preserve safe internal return targets and prevent
  protected-content flashes. Discard stale responses after filter/auth changes.
- Escape source/user content. NEVER use `v-html` for untrusted content. Notification
  HTML previews use the existing opaque sandboxed iframe and restrictive preview CSP.
- `frontend/app/stores/filter-preferences.ts` and `usePreferenceQuery` implement
  URL > session store > default precedence. Explicit URLs/history are authoritative;
  preserve each page's existing merge/restore behavior and validation of preferences.
- Shared period choices flow across supported pages, with page-specific fallback and
  entity overrides. Custom windows/unknown timestamps MUST NOT silently overwrite them.
  Preferences are in-memory Pinia state; do not add localStorage/sessionStorage.
  Logout/session loss resets preferences and protected data.

## API contracts and frontend proxy

Frontend-used API changes MUST update all affected layers together:
Pydantic schemas and FastAPI routes; `frontend/shared/contracts.ts` and errors;
`frontend/app/utils/admin-api.ts`; `frontend/server/utils/admin-proxy.ts`;
`frontend/docs/openapi.json`; backend/unit/E2E fixtures and contract tests.

Nitro's `frontend/server/api/admin/[...path].ts` is a catch-all file backed by explicit
route, method and query allowlists, not a generic forwarding capability. New routes
MUST be allowlisted explicitly, with validated identifiers and typed write bodies.
NEVER add wildcard forwarding, arbitrary paths/hosts/methods/SQL identifiers, duplicate
query parameters or arbitrary query passthrough. Preserve fixed upstream origin,
10-second proxy timeout, redirect rejection, selective credential/header forwarding,
safe errors and `private, no-store` responses.

## Testing, CI and generated files

Inspect relevant regression tests before changing behavior. Add focused tests for
changed behavior and REQUIRED security-boundary regressions; run affected tests during
development and the relevant full gates before opening a PR.

Backend (from repository root):

```sh
cd backend
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
```

Integration tests require a disposable PostgreSQL/PostGIS database via
`TEST_DATABASE_URL`, with a name ending in `_test` and no pre-existing `uranus` schema.
Fixtures create/drop schemas and roles. NEVER use production, disable these safeguards,
or substitute SQLite. Without the variable, local integration tests skip; CI fails.
Report skips explicitly. CI uses PostgreSQL 17/PostGIS 3.5 from a pinned image.

Frontend (from repository root; use Node engines and pnpm from `frontend/package.json`):

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install --with-deps chromium
pnpm test:e2e
TEST_PRODUCTION=1 pnpm test:e2e
```

Production E2E requires the build and includes CSP coverage. Playwright uses controlled
fixtures and a local auth server; it does not establish production/backend integration.

- `.github/workflows/ci.yml` (`CI`): `lint`, `typecheck`, `tests`, `frontend` including
  production Chromium E2E. Current pins: Python 3.13.15, uv 0.12.5, Node 22.22.3;
  pnpm 12.3.4 is declared in the frontend manifest.
- `.github/workflows/security.yml` (`Security`): CodeQL for Python and JS/TS;
  PR Dependency review blocks high/critical vulnerabilities.
- `.github/workflows/deployment-checks.yml` (`Deployment checks`): local Ansible safety,
  syntax, proxy and isolated PostgreSQL privilege tests; never deploys to production.
  See `ansible/README.md` for the reviewed dry-run/apply gates. Do not claim CI
  configuration establishes branch-protection settings.
- Regenerate `frontend/docs/openapi.json` from FastAPI `create_app(...).openapi()` in
  an explicit development/test configuration without loading secrets. Do not hand-fake
  it; `backend/tests/test_auth.py::test_openapi` checks exact structural equality.
- After notification renderer changes, run
  `uv run python -m tests.generate_notification_previews` from `backend/`, then
  `pnpm exec prettier --write tests/fixtures/notification-previews.json` from `frontend/`.
- Update lockfiles using uv/pnpm only when dependencies change. Do not hand-edit
  generated `.nuxt`/`.output` content or commit build/test artifacts.
- Documentation-only changes need `git diff --check`, path/link verification and any
  applicable documentation formatter. No Markdown-specific CI linter is configured;
  frontend Prettier is available. A full application suite is unnecessary for AGENTS-only edits.

## Security invariants and logging

**MUST** preserve source read-only access, least privilege, bound SQL, input validation,
central auth/Origin/CSRF checks, escaping and worker claim/idempotency guarantees.
Add regression tests when modifying those boundaries.

**NEVER** expose secrets; weaken CSP for unrelated fixes; add `unsafe-eval` or wildcard
CORS; disable TLS verification; trust source HTML; allow unbounded network requests;
bypass system-admin checks; rewrite shipped revisions; or mutate Uranus directly.

Use `backend/app/logging.py` structured events and safe fixed error categories. Log
IDs rather than recipient/address PII. No passwords, tokens, cookies, DSNs, raw request
bodies, query strings or provider response text. NEVER stringify SMTP exceptions:
they can contain credentials and recipient data. Keep SQL parameter/access-log
suppression and production debug/OpenAPI restrictions. Examples use placeholders only.

## Deployment considerations

1. Coordinate API/worker downtime when a schema change requires it; inspect current
   heads and provisioning instructions. Provision schema/roles, migrate first as
   `admin_migrator`, then apply explicit runtime grants and verify migration state.
2. Deploy compatible backend/frontend builds and restart affected API/worker services
   or timers. Runtime environments MUST NOT contain migrator/operator credentials.
3. Use HTTPS for the public admin origin, exact `AUTH_PUBLIC_ORIGIN`, and loopback or
   encrypted authenticated transport between Nitro and FastAPI. Configure trusted
   ingress peers explicitly. Do not invent or modify live service names/configuration.
4. Check `/health` for process liveness (no DB access) and `/ready` for source connectivity,
   configured admin role boundary, exact current migration head and required grants.
   The source-only exception is explicit development/test with dev auth and no admin DSN.
   Readiness does not prove source-schema completeness, SMTP delivery or worker liveness.
5. Verify worker progress separately. Before enabling mail, verify source notification
   capability, previews, recipient routes, SMTP policy and quotas. SMTP is not a readiness
   blocker. Existing permanent failures are not automatically retriggered by deployment.

## Git and pull-request workflow

Start from freshly fetched `main` and record its SHA. Inspect `git status` and all
applicable `AGENTS.md` files first; preserve unrelated work, using an isolated worktree
when needed. Create a focused branch, inspect the existing architecture, implement
only the requested behavior, update contracts/docs and run relevant validation.
Document follow-ups separately; avoid opportunistic subsystem rewrites.

Recent history uses Conventional Commit prefixes, e.g. `feat(notifications): ...`,
`fix(security): ...`, `test(...): ...`, `docs: ...`; follow that convention without
inventing an enforced commit policy. Open a PR against `main` with the concrete
problem/result, validation (including skips), and migration/grant/deployment impact.
**Do not merge unless explicitly asked.**

## Definition of done

- Requested behavior and scope are complete; no unrelated changes or secrets.
- Database/auth/network boundaries and audit history remain intact.
- Relevant tests pass; limitations and unavailable integration checks are disclosed.
- Pydantic/Zod/proxy/OpenAPI/fixtures/docs agree where affected.
- Migration, grant and worker deployment requirements are reviewable where applicable.
- `git diff --check` passes; final diff is reviewed; PR is ready for review, not merged.
