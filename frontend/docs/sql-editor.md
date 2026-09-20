# Finding SQL Editor

The shared FindingsList opens a dedicated read-only SQL Editor from both the prioritized
work list and `/findings`. AppModal's existing `wide` prop provides `max-w-5xl`, viewport
width minus 2rem and `max-h-[90dvh]` with vertical scrolling. Other modals retain their
existing width. The native dialog preserves focus trapping, Escape and trigger focus return.

Finding context, query, bound parameters, results and rule evaluation follow one vertical
flow. Unsupported and live findings retain **Ansehen**; supported findings expose **SQL
Editor →** and secondary **Details**. FindingDetail links to the same editor instead of
embedding a second diagnostic UI. Resolved findings remain diagnosable; last finding
observation and current diagnostic time are shown separately.

Definitions load only after opening; queries never run automatically. Closing/unmounting
clears local state and invalidates pending definition, execution and clipboard feedback.
Switching findings uses the same revision guard. Copy writes `definition.copy_sql` without
line numbers or markup and shows feedback for 2.5 seconds. Execution still calls
`executeSqlDiagnostic(finding.id)` and sends exactly `{"finding_id":"…"}`.

`sql_diagnostic_available` is the only API addition. Persisted responses derive it from the
existing registry's rule/type/field/key checks, without running SQL. Live findings default
false; older responses without the flag also fall back to false in Zod. Existing API-client
and Nitro response validation share that schema; routes, request allowlists and execution
payloads are unchanged. The flag is presentation metadata, never authorization.

## Highlighting and dependency audit

- Runtime: **prismjs 1.30.0**, MIT; development types: **@types/prismjs 1.26.6**, MIT.
- [Prism tokenization](https://prismjs.com/docs/prism) provides structured tokens. Vue renders
  escaped text spans; no `v-html`, DOM mutation, CDN, eval or CSP exception.
- Only `prism-core` and `prism-sql` are imported. SQL covers the registered PostgreSQL
  statements; an additional token recognizes named SQLAlchemy parameters without confusing
  PostgreSQL `::` casts. No other languages, themes or editor runtime are bundled.
- The highlighter helper is dynamically imported on mounting SqlCodeEditor, after the modal
  opens and its definition arrives. Normal work-list loading does not fetch the highlighter.
- Production measurement: the separate highlighter chunk including the token adapter is
  **11,579 bytes minified / 5,436 bytes gzip**. These are the added highlighting payload,
  not a claim about the whole application bundle delta.
- Vite prebundles the two CommonJS entry points in development to avoid a full-page
  optimizer reload on first opening. This does not preload them in the browser.
- SSR starts with plain SQL; highlighting begins only onMounted. Failed chunk loads leave
  the full SQL readable. Code remains a continuous accessible text block; line numbers are
  separate, aria-hidden and unselectable.
- SqlCodeEditor accepts generic `sql` and `readonly?: true`. A future editable mode can
  extend the component deliberately; this phase has no mutable SQL model or edit event.

The app currently uses a light UI; the code surface uses a fixed dark slate palette.
This change does not add global theme support.

## Validation

Unit tests cover capability-dependent actions, width, lazy loading, escaped structured
highlighting, parameter types, raw Copy SQL, ID-only execution, safe errors/retry, empty
results, resolved/unknown rule evaluation, close/reset and stale definition/execution races.
Existing client/proxy tests reject arbitrary SQL, parameter, recipe and limit overrides.

`tests/e2e/sql-diagnostics.spec.ts` exercises both work-list entry points on desktop and
mobile, native focus behavior, overflow containment, copy, execution and reset. It emits
`sql-editor-modal.png` as a Playwright artifact; fixtures are synthetic, never live data.
Production runs exercise the same flow plus the existing enforcing-CSP regression.

There are no source queries, recipe changes, migrations, grants, database rights or
schema changes in this redesign. Backend changes only enrich the Finding response.

Reviewed production screenshots with synthetic fixtures:
[Desktop](screenshots/sql-editor/desktop.png) · [Mobile](screenshots/sql-editor/mobile.png).

Local checks: frozen install, ESLint, Nuxt typecheck, 382 unit tests and production build.
Backend: Ruff, format check, mypy, 860 tests passed; 703 database integration tests skipped
because no disposable `TEST_DATABASE_URL` was configured. Backend OpenAPI equality passed.
Browser verification uses isolated local ports to avoid another worktree's running servers;
that temporary test configuration is not part of the change.
The affected Chromium suites passed on desktop and mobile: 22 development tests and
24 production tests, including CSP. Development prebundling also covers the first modal
opening without a dependency-optimizer page reload.
