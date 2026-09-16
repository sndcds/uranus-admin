# Neue Entitäten

`/statistics` follows the supplied Kulturbytes screenshot: compact period controls, a broad
multi-series timeline, seven metric cards with sparklines, and a recent-record table beside
a distribution donut. Blue users, violet organizations, rose events, green venues, cyan rooms,
amber partner requests and lavender invitations share one presentation map. At desktop widths
all seven cards sit in one row; mobile wraps to two columns and stacks the lower panels. The
existing shell is compact on this route. No identity, author, KPI or chart data is fabricated.

## Verified timestamp contract

Source inspection: local Uranus checkout at `12ec7608d55aed3cf86724ce47d275f9d49e46b2`,
`ddl/*.ddl` and `sql/admin-upsert-invited-org-team-member.sql`. Existing source-timezone
verification remains documented in [source-verification](../../backend/docs/source-verification.md).
No production database inspection or deployment was performed.

| Statistic | Uranus table | Timestamp | Meaning |
| --- | --- | --- | --- |
| Benutzer | `user` | `created_at` | Account row created |
| Organisationen | `organization` | `created_at` | Organization row created |
| Veranstaltungsorte | `venue` | `created_at` | Venue row created |
| Räume | `space` | `created_at` | Space row created |
| Veranstaltungen | `event` | `created_at` | Event row created, never scheduled event time |
| Partneranfragen | `organization_partner_request` | `created_at` | Existing request row created, regardless of later status |
| Teameinladungen | `organization_member_link` | `invited_at` | Latest recorded invitation timestamp, regardless of current joined status |

**Invitations are not an immutable send history.** The verified upsert resets `invited_at` when
reinviting an unjoined member. Each currently stored membership contributes at most once at
its latest invitation time; earlier sends cannot be reconstructed. This limitation is visible
on the page. NULL invitation timestamps are excluded without falling back to `created_at`.
These are statistics of currently retained rows, not an append-only event log: deleted records
are no longer represented. No login, modification, join or finding timestamps are used.

Event dates have a verified `created_at`; images also have `created_at`, which is nullable.
Both remain available in Dashboard/Activity but are deliberately outside this seven-type view
matching the reference. They are not silently mixed into totals, recent records or the donut.
The existing dashboard's `team_memberships` still means row creation, **not** invitation time.
Its six comparable counters equal Statistics totals for the same range and source timezone.
Shared source constants supply both Dashboard and Statistics table definitions. Recent items
reuse Activity's name/context SQL; no speculative creator column or private contact fields.

## API

`GET /api/v1/statistics/entities`

| Parameter | Values / limits |
| --- | --- |
| `period` | `24h` (default), `7d`, `30d`, `90d`, `custom` |
| `interval` | `auto` (default), `15m`, `1h`, `6h`, `1d` |
| `compare` | optional `previous` |
| `from_at`, `to_at` | both offset-aware; only with omitted period or `custom`; positive span, at most 365 days |

Unknown parameters, invalid enums, naive dates, conflicting preset/custom filters and ranges
with more than 500 buckets return 422. The proxy admits only this exact GET route and the five
named query parameters; duplicate parameters and writes are rejected.

Response includes `period`, `from_at`, `to_at`, `timezone`, `interval`, `observed_at`, optional
`previous_from_at`/`previous_to_at`, seven deterministic `series` and up to seven `recent` items.
Each series contains `entity_type`, `label`, `total`, nullable `previous_total`, and aligned
`points: [{start_at, end_at, count}]`. Counts are nonnegative integers; `total = sum(points)`.
Pydantic defines the response and Zod validates identities, all seven series, totals, contiguous
aligned points, comparison bounds, timestamps and trusted internal actions. No `any` payload.

All seven sources are range-filtered once in **one** PostgreSQL UNION query. PostgreSQL
`width_bucket` groups timestamps against bounded ordered bucket boundaries; a LEFT JOIN
with the seven types and boundaries fills zeros. Only boundaries (never domain records) are generated in Python.
A second bounded query retrieves recent names using Activity
projections; enabling comparison adds one aggregate query for the previous totals. Everything
uses the existing read-only, repeatable-read connection, timeout and admin-only router.
No schema migration, domain write, materialized view or new database role.

## Periods and bucket boundaries

| Rolling period | Automatic interval | Usual full/partial bucket count |
| --- | --- | --- |
| 24 hours | 15 minutes | 96–97 |
| 7 × 24 hours | 1 hour | 168–169 |
| 30 × 24 hours | 6 local hours | about 120–122 |
| 90 × 24 hours | 1 local day | about 90–92 |

Custom chooses 15m up to 24h, 1h up to 7d, 6h up to 30d, otherwise 1d. Manual intervals are
bounded at 500. The shared `period_window` retains existing Dashboard/Activity semantics;
new 30d/90d presets extend its rolling-duration behavior. These are not calendar weeks/months.

Bucket boundaries align to local :00/:15/:30/:45, whole hours, 00/06/12/18 or local midnight.
First and last buckets are **clipped** to the exact request range `[from_at,to_at)`, so no
outside records enter totals. Partial bucket counts are not extrapolated. Hourly steps advance
on the UTC timeline, preserving the two different instants during the repeated fall-back hour.
Daily/six-hour steps follow the admin calendar, allowing 23/25-hour days. API timestamps are
UTC instants; axis/tooltip/table labels use the response's IANA timezone, including zone names
for ambiguous hourly labels. Source-naive timestamps use `URANUS_TIMESTAMP_TIMEZONE`, exactly
as Dashboard/Activity; missing configuration fails closed with 503.

Date-only custom controls represent inclusive selected calendar days in the server's admin
zone, converted to an exclusive next-midnight boundary. The browser's timezone is not used.
The comparison ends at current `from_at` and spans the exact same elapsed duration. It appears
in metric cards, avoiding fourteen overlapping chart lines. Percentage change is calculated
only with positive prior totals; a zero prior total displays `+N neu` or `±0`.

## Interaction, accessibility and routing

Vue owns markup, filters and request state. Modular D3 `scaleTime`, `scaleLinear`, `line`, `area`,
`pie`, `arc` and `bisector` compute responsive geometry; no extra chart framework or CDN.
Timeline lines connect discrete zero-filled counts linearly; Y starts at zero with integer ticks.
Sparklines and donut share the exact current response. Legend and card buttons expose
`aria-pressed`, keyboard focus and named colors/icons. Hover/focus highlights a series.
The chart supports pointer/touch inspection and keyboard arrows/Home/End/Escape; tooltips show
all visible series for a bucket. A text table exposes every bucket independently of hover.
Zero totals have explicit empty states; deselecting every series explains how to restore them.
`ResizeObserver` follows container dimensions and disconnects on unmount. No chart animation.

The URL owns period, manual interval, comparison and custom boundaries. Back/Forward restores
them; request generations discard older results and clear old data on changes/access loss or
unmount. Loading, 401/403/503 failures and retry reuse `RequestState`; failures never become
zero metrics. Refresh is manual. The normal admin authentication/CSRF/session boundary and CSP
remain unchanged, including no `unsafe-eval` requirement. D3 is loaded with the Statistics page.

The recent list and “Alle neuen Entitäten anzeigen” link preserve the exact range and
`creation_basis=statistics` in Activity. That opt-in mode uses the same seven sources and
invitation time; default Activity retains record creation semantics. Row drilldowns retain
existing validated Action targets plus the same explicit statistics basis. The displayed
organization is context, never an inferred author.

## Performance follow-ups

The inspected source DDL contains no time indexes on these seven `created_at`/`invited_at`
columns. The UTC aggregation path compares the timestamp column directly to converted bounds
so ordinary B-tree timestamp indexes can be used if added by Uranus maintainers. Other source
zones preserve the established expression conversion semantics. The query returns at most
3,500 count rows (seven × 500) and seven recent rows, but missing source indexes may still require
full source-table scans on large datasets. A production `<1s` latency is not claimed: inspect EXPLAIN on
a representative anonymized snapshot before adding source indexes or designing preaggregation.
No index or other DDL is applied to Uranus by this feature.

## Verification

See the PR for final command results. Coverage includes preset/manual/custom ranges, clipped
half-open bounds, source timezone conversion, spring/fall DST, zeros, invitation-vs-membership
semantics and dashboard consistency; admin rejection and exact proxy allowlisting; contract
validation, D3 shapes, resize/disposal, comparison edge cases and calendar-date conversion;
desktop/mobile filters, URL history, tooltip/legend, recent links, empty/failure/retry/access
loss and stale requests. Production CSP coverage exercises the Statistics route and toggles.
Screenshots use synthetic fixtures only.

### Local verification, 2026-09-16

- Backend: frozen `uv sync --locked`, Ruff lint/format, strict mypy; **344 tests passed**
  with a separate disposable PostgreSQL/PostGIS test database. No skipped DB tests.
- Frontend: frozen pnpm install, ESLint, Nuxt typecheck, **136 unit tests passed** and
  production build passed.
- Complete development Playwright suite: **60 passed**, four production-only cases skipped.
- Complete production Playwright suite: **64 passed**, including CSP without `unsafe-eval`.
- After guarding custom dates until the server timezone is known, rebuilt and reran all
  Statistics/CSP desktop/mobile cases: **10 passed**, including custom dates in
  `America/New_York` with the browser still in another zone.
- `git diff --check` passed. Screenshots were visually inspected against the reference;
  desktop captures use 1536 × 1024, mobile uses 390 × 844 with full-page capture.

[Desktop, 24 hours](screenshots/statistics-desktop-24h.png) ·
[Desktop, 7 days with comparison](screenshots/statistics-desktop-7d.png) ·
[Mobile](screenshots/statistics-mobile.png)
