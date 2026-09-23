# Admin UI patterns

Activity is the reference: the same function uses the same visual language. Charts,
relationship graphs and workflow editors retain their domain-specific interactions.
Baseline reviewed: `7428b455f68316c2b116798ac1138d70eeeb3d2c`.

## Shell and navigation

One shell for every route: fixed `w-64` desktop sidebar, `lg:pl-64` content offset,
sticky white/translucent header, and centered `max-w-7xl` main content. Mobile uses
`p-4` and `space-y-4`; `sm` and larger retain `p-8` and `space-y-5`. No
Statistics-specific width, logo, header or login variant.
The Dashboard period selector belongs to its PageHeader and still uses the dashboard
store. There is no second period state. Native graph fullscreen remains independent
of this shell and uses the existing single workspace/SVG/simulation.

Below `lg`, the sticky header has two stable rows: a 56px navigation/title row and one
compact Geo Scope row. It does not show the timestamp, administrator role, logout or
the unavailable create explanation. Role, the disabled create state and logout live in
the account/action section at the bottom of the mobile drawer. The desktop header keeps
its timestamp and account actions. Do not duplicate mobile account actions between the
header and drawer. Long area names truncate inside the available width.

The same navigation is used inside the mobile dialog. Keep native dialog focus
handling, Escape, explicit close and focus return to the menu button. Active section
matching includes descendants, excludes prefix collisions, special-cases `/`, and
includes `/spaces/**` under Orte & Räume. Set `aria-current="page"` on the active
section link. Navigation labels and targets come from `adminNavigationItems` in `utils/navigation.ts`.

## Typography, spacing and surfaces

- Global application title: h1. PageHeader: h2, `text-2xl font-bold tracking-tight`.
- Major section: SectionHeader, h3 by default, `text-lg font-semibold`; optional h2
  for genuinely independent sections. Minor row titles: `text-sm font-semibold`.
- Regular controls and body text: text-sm; labels, metadata and badges: text-xs.
  Only SVG axes/donut captions may use 10px for chart geometry.
- Page root: `space-y-4 sm:space-y-5`; sections: `space-y-3`; grids: gap-3/4/5 as appropriate.
- `.panel`: rounded-2xl, slate-200 border, white, min-w-0. `.card` adds shadow-soft.
  Controls: rounded-xl; badges: rounded-md/full. Icon tiles can use smaller radii.
- `.data-row`: px-4 sm:px-5, py-3, subtle slate hover. Use divide-y for row lists.
- Interactive mobile controls should provide an approximately 44px touch target. Do not
  make every action full-width: related primary controls may share a row, while labels
  stay unbroken and secondary actions remain visually subordinate.

## Shared inventory

| Component / primitive         | Responsibility                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------ |
| PageHeader                    | Page heading, description, optional badge slot and actions                     |
| SectionHeader                 | Section heading, description, optional metadata and actions                    |
| FilterBar / FilterForm        | Form surface/grid and domain-specific validated filters                        |
| RequestState                  | Shared loading, error, stale data and retry behavior                           |
| InlineAlert                   | Info/success status or warning/error alert; explicit role override when needed |
| ResultSummary                 | Real totals, visible-page counts, observation time; never extrapolate a page   |
| DataListShell                 | Single bordered surface, optionally semantic ul/section                        |
| PaginationBar                 | Server-page information, URL links or events, unavailable directions disabled  |
| EmptyState                    | Compact explanatory dashed-border empty result                                 |
| StatusBadge / EntityTypeBadge | Text plus tone, never color-only meaning                                       |
| DetailFacts                   | Definition grid; null omitted, zero/false retained, source text escaped        |
| `.button` / `.button-primary` | Shared control geometry, states and focus                                      |
| `.input` / `.label`           | Shared search/date/text/select/textarea presentation                           |
| `.admin-table`                | Readable table header/cells/row hover and canonical links                      |

GraphFilters keeps its search dropdown and models but uses the same panel, controls,
spacing and Tailwind breakpoints. Statistics presets use normal buttons with
aria-pressed; selected presets use button-primary. Their compare switch is a labeled
native checkbox with role=switch. No separate button/select CSS system remains.

On phones, `PageHeader` is intentionally ordered as title/description, primary page
actions, then SQL/data provenance. Its action region uses the available width and wraps
as a group instead of competing with the title. Dashboard keeps period and refresh in
one primary row (the select grows; refresh may use its icon-only accessible label at the
narrowest width), with provenance on a quieter row below. From `sm` upward, the existing
side-by-side heading/actions layout remains.

## Page patterns

**List:** PageHeader → FilterBar → RequestState → ResultSummary → DataListShell /
EmptyState → PaginationBar. Findings, Activity, entity lists, Marks and Queues retain
URL-based filtering, server pagination and their own row semantics.

**Detail:** PageHeader with list/findings actions → RequestState → entity summary
with record actions → DetailFacts → EntityTimeline → SectionHeader/ResultSummary → related records
→ pagination. Entity details
reuse ActivityRow's already-safe preview, canonical links, public links, thumbnails,
marks and graph links. A second nearly identical row component would add duplication;
no universal row with a growing prop list is introduced.

Workflow details may place `AssignmentEditor` after the immutable facts and review form. The
editor keeps assignee, status and Berlin due date together, reports stale-version conflicts in
place and uses the normal button/input styles. Loading failure and an empty admin roster are
distinct single-alert states. Inbox rows use existing badges and list shells; they do not
introduce a second card/list system.

The geocoding detail follows the same detail hierarchy: PageHeader, entity/source panel,
DetailFacts, candidate comparison, AssignmentEditor and retry workflow. Its candidate map is a
client-only Leaflet raster map built from the already validated candidate coordinates. All points
fit with 48px padding and a maximum initial zoom of 16; “Alle Kandidaten zeigen” restores the
comparison after panning or selection. Numbered native 44px buttons synchronize with `.data-row`
selection, aria-pressed/current and row focus. The selected marker has a contrasting ring and
higher stacking order. List “Auf Karte zeigen” recenters even an already-selected candidate.

The map has a real 320px height on phones and 420px from `sm`; ResizeObserver invalidates its
size. Pan, pinch, keyboard arrows/+/- and 44px zoom controls are available; scroll-wheel zoom
is off to preserve page scrolling. The complete candidate list always follows the map. On tile,
initialization or timeout failure an InlineAlert replaces the map surface, with no automatic retry.
OSM and configured provider attribution remain visible outside the clipped map canvas. Provider
text is escaped, never HTML. No coordinate mutation or client geocoding exists. Tile configuration,
privacy and exact `img-src` allowance are documented in the [README](../README.md#geocoding-karte-konfigurieren).

**Analytics:** PageHeader → period/interval controls → RequestState → chart surface →
metric controls → supporting recent records/distribution → accessible data table.
Tables have captions and a local overflow container. Recent records remain a table:
it compares four concise columns and uses the same global table style as the chart's
text alternative. Invitation semantics do not fit an unmodified ActivityRow.

**Graph:** PageHeader → GraphFilters → optional settings/InlineAlert → GraphWorkspace.
The graph's initial exploratory illustration, viewport sizing, node positions,
fullscreen toolbar, pan/zoom/fit, collapsible details and legend remain specialized.

## Entity presentation and routing

`utils/entityPresentation.ts` owns shared singular/plural labels, icons, badge tones
and chart colors. Activity re-exports its existing API; Statistics derives its series
presentation; Graph retains contrast-appropriate fill/border variants. Invitations
are explicitly distinct from memberships. User-section title “Benutzer & Teams” is
navigation context, not a second entity name. Existing status helpers keep workflow
and source statuses separate.

Backend Action.href remains authoritative. Statistics only adds creation_basis to
an actual `/activity` path using URL parsing. Canonical detail and queue hrefs remain
unchanged; never append `&...` to a bare detail path.

## Loading, errors, responsiveness and accessibility

Use RequestState once for a request failure; do not repeat a second generic error.
Chart skeletons use slate-100/rounded-2xl and are aria-hidden. Use EmptyState for
zero/empty results; absence of data must not be displayed as invented zero counts.
Keep domain warnings and stale-period notices explicit.

Use Tailwind sm/md/lg/xl layouts, min-w-0, wrapped actions and readable titles.
Wide real tables scroll inside their container, never the whole page. Charts keep
ResizeObserver and accessible keyboard/text alternatives. Global focus-visible also
covers textareas. Decorative icons remain hidden from assistive technology; controls
retain labels, pressed/expanded state and native keyboard behavior.

Card/list grids fall back to one column before `sm` unless their content is demonstrably
short enough for two columns. Dashboard “Neu eingegangen” rows use a compact 64–80px
icon/label/value/arrow pattern, become two columns at `sm` and three at `md`, and never
split German labels inside words. Page-level horizontal scrolling is not allowed;
genuinely wide tables keep their local overflow containers.

## Page audit and remaining deliberate special cases

The pre-change audit examined the shell, width/padding/gaps, heading hierarchy,
surfaces, controls, filters, summaries, pagination, request/empty states and responsive
CSS. Entity route wrappers share the audited EntityListPage/EntityDetailPage.

| Pages                     | Initial drift                                                       | Result                                                                                                        |
| ------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Dashboard                 | Inconsistent section headings, small tile radii, custom stale alert | SectionHeader, standard tiles/alert, period control in page header; period vs inventory semantics retained    |
| Activity                  | Reference; page gap differed from Dashboard                         | Common page gap; grouping, images, public links, unknown timestamps retained                                  |
| Findings                  | Custom invalid-query alert                                          | InlineAlert; existing FilterForm, summary, rows and pagination retained                                       |
| Checks                    | Already shared list structure                                       | Common page spacing; polling, status and pagination retained                                                  |
| Quality                   | Bespoke geolocation card/header                                     | Standard panel and SectionHeader; real aggregate counts retained                                              |
| Graph                     | Manual page header, custom small filters and details                | PageHeader badge, global controls/panels/readable metadata; graph/fullscreen stays specialized                |
| Statistics                | Separate shell and 573-line parallel CSS design system              | Shared shell, surfaces, buttons/inputs, tables, empty/error states; CSS limited to plot geometry and tooltips |
| Events list/detail        | Shared list, ad-hoc definition grid                                 | Standard spacing, shared DetailFacts and semantic preview list                                                |
| Venues list/detail        | Same shared list/detail drift                                       | Same shared pattern; canonical actions retained                                                               |
| Spaces list/detail        | Missing active parent navigation                                    | Orte & Räume active; same shared patterns                                                                     |
| Organizations list/detail | Same shared list/detail drift                                       | Same shared patterns; related-record semantics unchanged                                                      |
| Users list/detail         | Same shared list/detail drift                                       | Same shared patterns; no changed identity/invitation semantics                                                |
| Images list/detail        | Same shared list/detail drift                                       | Same shared patterns; natural-ratio preview/modal unchanged                                                   |
| Marks list/detail         | Existing editor/history-specific layout                             | Common page spacing; editor and append-only history interaction retained                                      |
| Queue kinds               | Already shared shell with domain-specific state                     | Common spacing; business differences retained                                                                 |

Deliberate special cases: graph SVG labels/forces and fullscreen geometry; chart
axes, crosshair/tooltip, sparkline and donut geometry; mark/review editors and image
modal. These are interaction surfaces, not route-specific global design systems.
There is no new PageContainer width override, UI dependency or backend contract.

## Verification / screenshots

`tests/e2e/layout-consistency.spec.ts` visits all twenty-one main/list/detail views at
1440×1000, 1024×768 and 390×844, checks shell dimensions, active section and overflow,
and writes full-page screenshots plus mobile navigation screenshots to Playwright
output. Existing suites cover filtering, pagination, auth loss, charts, graph
fullscreen and workflow actions. The screenshots are review artifacts, not brittle
pixel snapshots. Unit tests cover the new primitives, navigation boundaries, shared
presentation and Statistics canonical-link handling.

### Reviewed examples

These screenshots use deterministic test fixtures and the production build, with no
live user or production data. Desktop examples use 1440×1000; responsive examples
use 1024×768 and 390×844. Full-page captures may be taller than the viewport.

- [Dashboard](screenshots/ui-consistency/dashboard.png)
- [Activity reference](screenshots/ui-consistency/activity.png)
- [Statistics](screenshots/ui-consistency/statistics.png)
- [Graph](screenshots/ui-consistency/graph.png)
- [Entity list](screenshots/ui-consistency/event-list.png)
- [Entity detail](screenshots/ui-consistency/event-detail.png)
- [Tablet Statistics](screenshots/ui-consistency/statistics-tablet.png)
- [Mobile Statistics](screenshots/ui-consistency/statistics-mobile.png)
- [Mobile navigation](screenshots/ui-consistency/mobile-navigation.png)

### Geocoding map review

[Desktop](screenshots/geocoding-map-desktop.png) and [mobile](screenshots/geocoding-map-mobile.png)
show the production build with synthetic local tiles and candidates. The geocoding Playwright
suite writes fresh full-page captures and checks marker/list synchronization, responsive bounds,
visible tiles and the failure alternative. These images verify layout, not geographic correctness.

## Command Palette

`GlobalSearchPalette` uses the existing native `AppModal` workspace dialog. Desktop
adds one compact search trigger with Ctrl/⌘ K; mobile adds a 44px search icon beside
the app title, preserving the two-row mobile shell. No extra header row or UI library.
The palette keeps a fixed responsive workspace height: `min(38rem, 100dvh - 2rem)`
on desktop, `100dvh - 1rem` below 640px. Its nonshrinking header and flexing, internally
scrolling results keep the dialog's size and position stable across navigation, debounce,
loading, result counts and errors. Mobile includes safe-area padding, no horizontal
overflow and 44px minimum result targets. These styles belong only to the search palette;
other `AppModal` consumers keep their existing layout.

The labelled search input is a combobox controlling one listbox with labelled groups;
active options use aria-selected, aria-activedescendant and a visible ring. Arrows move
selection, Enter follows the selected canonical Action.href, Escape closes. Native
dialog semantics provide aria-modal, Tab focus containment and return to the previous
focus target. Opening focuses search, even when Ctrl+K / Cmd+K began in an input.

Local navigation appears first from the shared sidebar definition. Entity labels,
plural group labels and icons reuse `entityPresentation.ts`. Long labels truncate and
subtitles/emails wrap. Loading uses an absolute input spinner with reduced-motion support
and a polite live status in reserved header space; errors use that same space. The header
also identifies the query of the retained successful results. Neither loading nor errors
add result rows or replace the previous results. Typing preserves selection by identity
and never scrolls to an option; only arrow keys do. Input focus survives result replacement.
The palette is systemwide and says so next to the search input. See
[data-page search semantics](data-pages.md#globale-suche-und-kontextbezogene-suche)
for fields/ranking, limits and memory-only privacy behavior.

Palette review captures (synthetic fixtures):
[desktop initial](screenshots/search-palette-desktop-initial.png),
[desktop revalidation](screenshots/search-palette-desktop-loading.png),
[desktop results](screenshots/search-palette-desktop-results.png),
[mobile initial](screenshots/search-palette-mobile-initial.png),
[mobile results](screenshots/search-palette-mobile-results.png).
The global-search Playwright suite measures dialog height/top and header position across
these states, checks internal scrolling, and runs the same workflow under production CSP.
