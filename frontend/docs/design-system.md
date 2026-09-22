# Admin UI patterns

Activity is the reference: the same function uses the same visual language. Charts,
relationship graphs and workflow editors retain their domain-specific interactions.
Baseline reviewed: `7428b455f68316c2b116798ac1138d70eeeb3d2c`.

## Shell and navigation

One shell for every route: fixed `w-64` desktop sidebar, `lg:pl-64` content offset,
sticky white/translucent header with `min-h-16`, and centered `max-w-7xl` main content
with `p-5 sm:p-8`. No Statistics-specific width, logo, header or login variant.
The Dashboard period selector belongs to its PageHeader and still uses the dashboard
store. There is no second period state. Native graph fullscreen remains independent
of this shell and uses the existing single workspace/SVG/simulation.

The same navigation is used inside the mobile dialog. Keep native dialog focus
handling, Escape, explicit close and focus return to the menu button. Active section
matching includes descendants, excludes prefix collisions, special-cases `/`, and
includes `/spaces/**` under Orte & Räume. Set `aria-current="page"` on the active
section link. Navigation order remains unchanged.

## Typography, spacing and surfaces

- Global application title: h1. PageHeader: h2, `text-2xl font-bold tracking-tight`.
- Major section: SectionHeader, h3 by default, `text-lg font-semibold`; optional h2
  for genuinely independent sections. Minor row titles: `text-sm font-semibold`.
- Regular controls and body text: text-sm; labels, metadata and badges: text-xs.
  Only SVG axes/donut captions may use 10px for chart geometry.
- Page root: `space-y-5`; sections: `space-y-3`; grids: gap-3/4/5 as appropriate.
- `.panel`: rounded-2xl, slate-200 border, white, min-w-0. `.card` adds shadow-soft.
  Controls: rounded-xl; badges: rounded-md/full. Icon tiles can use smaller radii.
- `.data-row`: px-4 sm:px-5, py-3, subtle slate hover. Use divide-y for row lists.

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

`tests/e2e/layout-consistency.spec.ts` visits all nineteen main/list/detail views at
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
