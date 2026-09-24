import { test, expect, expectLogoutAvailable } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'

test('dashboard separates period metrics from inventory and labels stale periods honestly', async ({
  page,
}) => {
  let release: () => void = () => {}
  const delayed = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (!url.pathname.endsWith('/summary')) return route.fulfill({ json: findings })
    const period = url.searchParams.get('period') ?? '24h'
    if (period === '7d') await delayed
    return route.fulfill({
      json: {
        ...summary,
        period,
        urgent_findings: 44,
        quality: {
          ...summary.quality,
          total: 298,
          errors: 178,
          warnings: 86,
          info: 34,
          mode: 'persisted',
        },
        new_records: {
          ...summary.new_records,
          total: period === '7d' ? 83 : 51,
          organizations: 2,
          events: 7,
          event_dates: period === '7d' ? 62 : 30,
          images: 12,
        },
      },
    })
  })
  await page.goto('/')
  const incoming = page.locator('#new-records')
  const attention = page.locator('#attention')
  await expect(incoming).toContainText('51 neue Datensätze · Letzte 24 Stunden')
  expect(
    await incoming.evaluate(
      (el) =>
        !!(
          el.compareDocumentPosition(document.querySelector('#attention')!) &
          Node.DOCUMENT_POSITION_FOLLOWING
        ),
    ),
  ).toBe(true)
  await expect(attention).toContainText('unabhängig vom gewählten Zeitraum')
  await expect(attention).toContainText('178 Fehler · 86 Warnungen · 34 Hinweise')
  await expect(attention.getByRole('link', { name: 'Dringend öffnen' })).toHaveAttribute(
    'href',
    '/findings?mode=persisted&active_only=true',
  )
  await expect(attention).toContainText('gesamte Arbeitsliste öffnen')
  await page.getByLabel('Zeitraum', { exact: true }).selectOption('7d')
  await expect(page.getByRole('status').filter({ hasText: 'Die sichtbaren Zahlen' })).toBeVisible()
  await expect(incoming).toContainText('51 neue Datensätze · Letzte 24 Stunden')
  await expect(incoming).toHaveAttribute('aria-busy', 'true')
  release()
  await expect(incoming).toContainText('83 neue Datensätze · Letzte 7 Tage')
  await expect(page.getByText('Die sichtbaren Zahlen', { exact: false })).toHaveCount(0)
  await expect(attention).toContainText('44')
  for (const [name, kind] of [
    ['Organisationen', 'organization'],
    ['Veranstaltungen', 'event'],
    ['Bilder', 'image'],
  ]) {
    const link = incoming.getByRole('link', { name: new RegExp(`^${name}:`) })
    await expect(link).toHaveAttribute('href', `/activity?period=7d&entity_type=${kind}`)
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('findings keep URL filters, page totals, badges, page size and empty/error states', async ({
  page,
}, info) => {
  let empty = false
  let unavailable = false
  let releaseFindings: () => void = () => {}
  const firstResponse = new Promise<void>((resolve) => {
    releaseFindings = resolve
  })
  await page.route('**/api/admin/api/v1/findings**', async (route) => {
    await firstResponse
    const url = new URL(route.request().url())
    if (unavailable)
      return route.fulfill({
        status: 503,
        json: { error: { code: 'admin_storage_unconfigured', message: 'not configured' } },
      })
    return route.fulfill({
      json: {
        ...findings,
        mode: 'persisted',
        items: empty ? [] : findings.items,
        pagination: {
          page: Number(url.searchParams.get('page') ?? 1),
          page_size: Number(url.searchParams.get('page_size') ?? 25),
          total: empty ? 0 : 298,
          pages: empty ? 0 : 12,
        },
      },
    })
  })
  await page.goto(
    '/findings?mode=persisted&severity=warning&entity_type=venue&rule=venue_missing_geolocation&status=open&page_size=25',
  )
  await expect(page.getByRole('form', { name: 'Filter' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Schweregrad', exact: true })).toHaveValue(
    'warning',
  )
  await expect(page.getByRole('combobox', { name: 'Objektart', exact: true })).toHaveValue('venue')
  await expect(page.getByRole('status').filter({ hasText: 'Daten werden geladen' })).toBeVisible()
  releaseFindings()
  const results = page.getByRole('region', { name: 'Ergebnisübersicht' })
  await expect(results).toContainText('298 Befunde insgesamt')
  await expect(results).toContainText('Auf dieser Seite: 1 Einträge')
  for (const label of ['0 Fehler', '1 Warnungen', '0 Hinweise', '· auf dieser Seite']) {
    await expect(results.getByText(label, { exact: true })).toBeVisible()
  }
  const row = page.getByRole('table', { name: 'Priorisierte Befunde' }).locator('tbody tr')
  await expect(row.getByText('Warnung', { exact: true })).toBeVisible()
  await expect(row.getByText('Ort', { exact: true })).toBeVisible()
  await expect(row.getByRole('link', { name: 'Markierungen & Notizen' })).toHaveCount(0)
  await expect(row.getByRole('button', { name: /^Befund bearbeiten:/ })).toHaveCount(1)
  await expect(page.getByText('Seite 1 von 12')).toBeVisible()
  await page.getByRole('button', { name: 'Weiter', exact: true }).click()
  await expect(page).toHaveURL(/page=2/)
  await page.getByLabel('Einträge pro Seite').selectOption('50')
  await expect(page).toHaveURL(/page_size=50/)
  await expect(page).toHaveURL(/page=1/)
  await expect(page.getByRole('combobox', { name: 'Befundstatus', exact: true })).toHaveValue(
    'open',
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('unified-findings.png'), fullPage: true })
  empty = true
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
  await expect(page.getByText('Keine Befunde für diese Auswahl.', { exact: false })).toBeVisible()
  unavailable = true
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Erneut versuchen' })).toBeVisible()
  await page.goto('/findings?page=0')
  await expect(page.getByRole('alert')).toContainText('ungültige Filter')
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(page).toHaveURL(/\/findings$/)
})

test('check history shares pagination, empty states and readable result badges', async ({
  page,
}, info) => {
  await page.route('**/api/admin/api/v1/check-runs**', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: '10000000-0000-4000-8000-000000000001',
            started_at: '2026-09-14T12:00:00Z',
            finished_at: '2026-09-14T12:01:00Z',
            status: 'success',
            rule_count: 22,
            finding_count: 298,
            error_message: null,
            rule_results: {},
          },
        ],
        pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
      },
    }),
  )
  await page.goto('/checks')
  await expect(page.getByRole('heading', { name: 'Prüfläufe' })).toBeVisible()
  await expect(page.getByText('1 Prüfläufe insgesamt')).toBeVisible()
  await expect(page.getByText('Erfolgreich', { exact: true })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Prüflaufhistorie' })).toContainText('22 Regeln')
  await expect(page.getByRole('table', { name: 'Prüflaufhistorie' })).toContainText('298 Befunde')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('checks.png'), fullPage: true })
  await expect(
    page
      .getByRole('navigation', { name: 'Seitennavigation' })
      .getByRole('button', { name: 'Weiter' }),
  ).toBeDisabled()
})

test('quality has honest aggregate counts, bounded dashboard rules and a full rule list', async ({
  page,
}, info) => {
  const rules = [
    'venue_missing_geolocation',
    'event_date_without_location',
    'event_date_space_venue_mismatch',
    'event_without_dates',
    'event_without_location',
    'image_orphaned_upload',
  ]
  await page.route('**/api/admin/api/v1/**', (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith('/summary')
        ? { ...summary, quality: { ...summary.quality, rules, mode: 'persisted' } }
        : findings,
    }),
  )
  await page.goto('/')
  const preview = page.getByRole('region', { name: 'Datenqualitätsübersicht' })
  await expect(
    preview.getByRole('list', { name: 'Qualitätsregeln' }).getByRole('listitem'),
  ).toHaveCount(5)
  await expectLogoutAvailable(page)
  await expect(page.getByRole('region', { name: 'Admin-Anmeldung' })).toHaveCount(0)
  await expect(page.locator('#open-queues li')).toHaveCount(3)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('dashboard.png'), fullPage: true })
  await preview.getByRole('link', { name: 'Alle Regeln anzeigen' }).click()
  await expect(page).toHaveURL(/\/quality$/)
  const aggregate = page.getByRole('region', { name: 'Qualitätsstatus' })
  await expect(aggregate.locator('dl > div').filter({ hasText: 'Befunde' })).toContainText('2')
  await expect(aggregate.locator('dl > div').filter({ hasText: 'Warnungen' })).toContainText('2')
  await expect(aggregate).not.toContainText('Auf dieser Seite')
  const list = page.getByRole('list', { name: 'Qualitätsregeln' })
  await expect(list.getByRole('listitem')).toHaveCount(5)
  const geoRule = page.locator('[data-quality-rule=venue_missing_geolocation]')
  await expect(geoRule).toHaveCount(1)
  await expect(geoRule.getByRole('link')).toHaveAttribute(
    'href',
    '/findings?rule=venue_missing_geolocation&entity_type=venue&status=open',
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('quality.png'), fullPage: true })
  await geoRule.getByRole('link').click()
  await expect(page).toHaveURL(/rule=venue_missing_geolocation&entity_type=venue&status=open/)
  await expect(page.getByRole('heading', { name: 'Test-Hafenbühne' })).toBeVisible()
  // The same surfaces must also fit between mobile and desktop breakpoints.
  await page.setViewportSize({ width: 820, height: 1180 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('findings-tablet.png'), fullPage: true })
})
