# Shared SQL workspace

Finding SQL Editor/Diagnostics and SQL / Datenherkunft/Provenance use the same
`SqlWorkspace`/`SqlWorkspaceModal`, `SqlQueryPanel`, `SqlCodeEditor`, `SqlParameterTable`,
`SqlResultTable`, `SqlJsonResult` and `SqlReadonlyNotice`. `SqlSourceTabs` selects one
provenance query at a time. The former vertical finding card and stacked provenance
code boxes are replaced; both existing controllers retain their execution contracts.
FindingDetail continues to link to the editor, with no second inline SQL renderer.

## Layout and mockup

The SQL-only AppModal variant is `max-w-5xl`, viewport width/height minus 2rem,
with a database icon, subtitle and native close control. At desktop widths its grid is
`260px minmax(0, 1fr)`: finding/source context and navigation on the left, then SQL,
parameters, results, and optional rule evaluation/postprocessing on the right. The
read-only notice sits at the bottom left. The dark slate editor has numbered lines,
fuchsia keywords, a 280px minimum height and a 480px maximum height; longer content
scrolls. On desktop the right pane scrolls independently so the context and notice remain
visible. Copy and fuchsia execution actions sit above it. Other modals retain their
normal size and padding.

Below the desktop breakpoint the order is header, context, navigation, query,
parameters, result/evaluation, notice. Long code and tables scroll inside their own
containers; they do not widen the dialog. The native dialog retains Escape, focus
trapping and focus return. Source tabs support arrows, Home and End. Line numbers are
hidden from assistive technology and excluded from text selection.

The reference mockup determines layout and placement. The existing design system's
1024px maximum width, fonts, buttons and badges are retained. The actual registered
recipe determines columns and rows: no invented organization joins or sample results
are added to application behavior. Separate Python rule evaluation remains visible
below the result. Provenance adds its source selector and postprocessing.

Finding navigation exposes details, the rule explanation, a link to existing marks
and notes, and known observation/review/resolution timestamps. Unknown dates stay
unknown. “In neuem Tab öffnen” links to the authenticated, filtered `/findings` page
with an encoded finding identity in the fragment. Only a supported finding returned
by that list can open; the fragment never contains SQL, parameters or results.
Provenance context exposes the view, source, endpoint, actual filters and metadata.
Results are retained per visited source until the workspace closes.

## Formatting, copying and registered execution

The existing dependency audit found Prism but no SQL formatter. The workspace uses
[sql-formatter 15.8.2](https://github.com/sql-formatter-org/sql-formatter), MIT, with its
PostgreSQL dialect and `formatDialect` entry point (other dialects are tree-shaken).

```text
server sql      → PostgreSQL formatter → plain text → Prism SQL tokens → display
server copy_sql → PostgreSQL formatter → plain text → clipboard
finding ID / existing provenance parameters → unchanged API execution method
```

`SQL kopieren` **copies formatted `copy_sql`**, preserving the server's literal and
parameter binding choices. It never copies display SQL in place of that contract,
HTML or line numbers. Clipboard feedback expires after 2.5 seconds. Only local
component state caches a formatted copy for a stable input; close clears it.

Formatting uses four spaces, separate SELECT columns, uppercase keywords and a
110-character expression-width target. FROM, JOIN, WHERE, GROUP BY, HAVING, ORDER BY
and LIMIT begin their own lines. ON and multiline AND/OR are indented; CTEs, CASE,
EXISTS and subqueries use the library's PostgreSQL layout. Long identifiers, literals
and URLs remain intact, so the width target is deliberately not a hard wrap.

Before:

```sql
SELECT uuid,event_uuid,start_date FROM uranus.event_date WHERE uuid = :entity_key LIMIT :diagnostic_limit
```

After:

```sql
SELECT
    uuid,
    event_uuid,
    start_date
FROM uranus.event_date
WHERE uuid = :entity_key
LIMIT :diagnostic_limit;
```

The library's PostgreSQL lexer verifies tokens before/after formatting, including
named binds, `::` casts, quoted identifiers, dollar strings and nested comments.
Small whitespace-only layout adjustments use lexer positions, never replacements
inside literals. PostgreSQL's newline-sensitive adjacent string literals are guarded.
Unsupported syntax, token changes, excessive input or failed optional imports retain
readable original text. The formatter is never called by execution handlers.

`executeSqlDiagnostic(finding.id)` still sends exactly `{"finding_id":"…"}`.
Provenance still calls `executeProvenance(view, source.id, definition.parameters)`.
No automatic execution, new endpoint, free SQL console, WSS, grants, recipes,
backend schemas, auth, CSRF, CSP or source connections are changed. Existing
capability-dependent list actions and resolved-finding diagnostics are preserved.

## Parameters and results

Both workspaces use Name/Typ/Wert parameter tables, including UUID, Integer, Boolean,
Date, DateTime, String, NULL and structured JSON parameters where provenance supplies
them. NULL has a compact chip and long values wrap within the table.

Results show row count, elapsed time and observation time. The compact semantic table
has a sticky header, horizontal scrolling, NULL/boolean chips and truncated cells
with their full value in a title tooltip. The JSON toggle shows exactly the received
rows in a dark surface using **Prism's JSON grammar**, separately from SQL.
CSV is generated from received columns and rows only, with quoted fields, CRLF and
UTF-8 BOM. Potential spreadsheet formulas in source strings are prefixed with an
apostrophe; numeric negatives remain numeric. There is no export request or endpoint.
Documentary sources omit execution and explain that no result can be requested.

## Loading, highlighting and bundle

- Highlighter: **prismjs 1.30.0**, MIT; types **@types/prismjs 1.26.6**.
- Vue renders escaped token text: no `v-html`, DOM mutation, eval or CSP exception.
- Formatter and SQL/JSON grammars load dynamically on demand; closed dialogs do not
  initialize them. SSR initially renders readable plain text. Watchers run only for
  changed input, and revision guards discard stale work.
- Vite prebundles the optional libraries in development to avoid a first-open optimizer
  reload. This does not make them eager browser imports in the production build.
- Production comparison against fresh main `e7a48b30bcbd1ddd6629c43474edd93b40a9ecfa`:
  all emitted client JavaScript totals **725,644 → 810,978 bytes** minified and
  **268,147 → 292,553 bytes** gzip (delta **24,406 bytes gzip**). CSS totals
  **45,971 → 48,830 bytes**. Gzip is summed per emitted file; these totals are not
  the initial page payload.
- The lazy PostgreSQL formatter chunk is **69,876 bytes minified / 19,495 bytes gzip**.
  The remainder includes shared UI, JSON grammar and changed chunk boundaries.

## Verification and screenshots

Unit coverage includes the exact formatting example, JOIN/CTE/CASE/EXISTS, casts,
parameters, quoted names, literals/URLs, comments, all registry fixtures, safe fallback,
formatted copying, execution payloads, source isolation, tab keyboard navigation,
JSON/CSV, errors, resolved/unsupported findings, reset and stale responses.

Playwright covers both entry points and provenance views on desktop and mobile,
checks the two-column geometry, SQL → parameters → result order, new-tab navigation,
focus behavior, overflow, copy, JSON/CSV and production CSP. Screenshot fixtures are
synthetic and do not establish a live source schema or deployed behavior.

- Finding: [Desktop](screenshots/sql-editor/desktop.png) · [Mobile](screenshots/sql-editor/mobile.png)
- Provenance: [Desktop](screenshots/sql-provenance/desktop.png) · [Mobile](screenshots/sql-provenance/mobile.png)

No migrations, grants or worker deployment steps are required. Backend/database
integration tests are outside this frontend-only change; browser mocks do not replace
them. This PR is not a deployment.

Validated locally: frozen dependency install, ESLint, Nuxt typecheck, 402 unit tests,
production build, 14 targeted development Chromium tests, and the complete production
Chromium suite (216 passed, none skipped), including CSP and shared desktop/mobile
layout checks. Documentation formatting, relative links and `git diff --check` pass.

## Phase 3

Readonly, CodeMirror und `/sql` teilen `SqlWorkspace`, `SqlQueryPanel` und die
visuelle Definition `app/components/sql/sql-theme.css`. CodeMirror übernimmt die
bestehenden Prism-Tokens über Decorations; Layoutmapping in `sql-codemirror.ts`.
Die registrierte Ausführung bleibt erhalten; der Bearbeitungsmodus verwendet den
separaten Console-WebSocket ohne Befundbewertung.
[Runtime-Vertrag und Verifikation](../../backend/docs/sql-console-runtime.md).

### Reproduzierbare visuelle Tests

Die Produktions-E2E-Tests laufen in CI im per Digest gepinnten offiziellen
Playwright-Image aus [ci.yml](../../.github/workflows/ci.yml). Browser, Linux und
Systemschriften müssen bei Referenzbildern und Vergleichen übereinstimmen. Ein
lokaler Linux-Host kann andere UI-Schriften verwenden, obwohl das SQL-Panel bereits
pixelgleich ist. Anwendungsschriften und Vergleichstoleranzen bleiben unverändert.

Nach `pnpm install --frozen-lockfile` und `pnpm build` im Verzeichnis `frontend/`:

```sh
docker run --rm --init --ipc=host \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/work" --workdir /work \
  --volume "$(command -v node):/usr/local/bin/node:ro" \
  --env TEST_PRODUCTION=1 \
  mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27 \
  node node_modules/@playwright/test/cli.js test
```

Für eine beabsichtigte Aktualisierung am Ende des Befehls
`tests/e2e/sql-console.spec.ts --update-snapshots` ergänzen, die Bilder prüfen und
danach ohne Update erneut testen. Bei einem Playwright-Upgrade müssen Paketversion,
Image und Referenzbilder gemeinsam geprüft werden. Readonly und CodeMirror teilen
weiterhin **ein** SQL-Panel-Referenzbild. CI sichert bei Fehlern Screenshots, Diffs
und Traces aus `test-results/` für sieben Tage; alle Daten stammen aus Test-Fixtures.

Der Linux-Befehl bindet Node **22.22.3** vom Host ein (in CI durch `setup-node`
installiert), damit Build und E2E dieselbe Node-Version verwenden; das Image
enthält sonst Node 24. Der Build verwendet pnpm **12.3.4**. Browser und Schriften
kommen weiterhin ausschließlich aus dem gepinnten Playwright-**1.63.0**-Image.

Die ursprünglichen Fehler wurden in dieser Ubuntu-24.04-Schriftumgebung mit exakt
**7.783** abweichenden Pixeln für `/sql` und **10.928** für den Readonly-Dialog
reproduziert. Expected/Actual/Diff zeigten die abweichende System-Fallback-Schrift
der umgebenden UI; das isolierte SQL-Panel bestand bereits unverändert. Weder
Gutter, Zeilenhöhe, Badge, Scrollbars noch Viewport, Status oder CSP waren die Ursache.
Commit `7c8ee64` korrigierte die sechs betroffenen Workspace-Referenzen
(`sql-console`, `sql-results`, `sql-error`, `sql-running-cancel`, `finding-readonly`,
`finding-editable`); `sql-theme-parity` blieb unverändert.

Die Tests warten auf geladene Fonts, CodeMirror-Inhalt/Token und den jeweils
erwarteten Status. Playwright verlangt anschließend stabile aufeinanderfolgende
Bilder. Native Carets, Animationen und der von CodeMirror gezeichnete Cursor werden
nur während der Aufnahme ausgeblendet; Fokus, Selektion und Theme bleiben unverändert.
Keine pauschalen Sleeps. Die Toleranz bleibt **0.001**; Tokenfarben, Typografie,
Hintergrund und Gutter-/Textgeometrie werden weiterhin zusätzlich exakt verglichen.
