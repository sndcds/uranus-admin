import { test, expect } from '../fixtures/authenticated'
import { statisticsFixture } from '../fixtures/statistics'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/admin/auth/session', (route) =>
    route.fulfill({ json: { subject: 'admin:statistics-test', system_admin: true } }),
  )
  await page.route('**/api/admin/api/v1/statistics/entities**', (route) =>
    route.fulfill({ json: statisticsFixture(new URL(route.request().url()).searchParams) }),
  )
})

test('presets, named series, crosshair, comparison, links and responsive layout', async ({
  page,
}, info) => {
  if (info.project.name === 'desktop') await page.setViewportSize({ width: 1536, height: 1024 })
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/statistics')
  await expect(page.getByRole('heading', { name: 'Neue Entitäten', exact: true })).toBeVisible()
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  await expect(page.locator('.statistics-metric')).toHaveCount(7)
  await expect(page.getByRole('button', { name: '24 Stunden', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByRole('combobox', { name: 'Intervall' })).toContainText('15 Minuten')
  await page.screenshot({ path: info.outputPath('statistics-24h.png'), fullPage: true })
  await page.getByRole('button', { name: '7 Tage', exact: true }).click()
  await expect(page).toHaveURL(/period=7d/)
  await expect(page.getByRole('combobox', { name: 'Intervall' })).toContainText('Stündlich')
  await page.getByRole('switch').check()
  await expect(page.locator('.statistics-comparison')).toHaveCount(7)
  const chart = page.getByRole('img', { name: 'Neue Entitäten im Zeitverlauf', exact: true })
  await chart.focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.locator('.statistics-tooltip')).toContainText('Veranstaltungen')
  await page.keyboard.press('Escape')
  await page
    .locator('.statistics-legend')
    .getByRole('button', { name: 'Benutzer', exact: true })
    .click()
  await expect(page.locator('.statistics-series')).toHaveCount(6)
  await page
    .locator('.statistics-legend')
    .getByRole('button', { name: 'Benutzer', exact: true })
    .click()
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  const link = page.getByRole('link', { name: 'Alle neuen Entitäten anzeigen' })
  await expect(link).toHaveAttribute('href', /creation_basis=statistics/)
  await expect(link).toHaveAttribute('href', /from_at=/)
  await expect(page.locator('.statistics-recent tbody tr')).toHaveCount(7)
  await expect(page.getByRole('link', { name: 'Jazz im Hof 2027', exact: true })).toHaveAttribute(
    'href',
    '/events/20000000-0000-4000-8000-000000000003',
  )
  await page.getByRole('heading', { name: 'Neue Entitäten im Zeitverlauf' }).click()
  await page.mouse.move(0, 0)
  await page.screenshot({ path: info.outputPath('statistics-7d.png'), fullPage: true })
  await page.getByRole('button', { name: '30 Tage', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Intervall' })).toContainText('6 Stunden')
  await page.goBack()
  await expect(page.getByRole('button', { name: '7 Tage', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  if (info.project.name === 'mobile')
    await page.getByRole('button', { name: 'Navigation öffnen' }).click()
  await page.getByRole('link', { name: 'Statistiken', exact: true }).click()
  await expect(page).toHaveURL(/\/statistics$/)
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  await expect(page.getByRole('button', { name: '24 Stunden', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  expect(errors).toEqual([])
})

test('custom calendar range, manual intervals, refresh and text alternative', async ({ page }) => {
  await page.route('**/api/admin/api/v1/statistics/entities**', (route) =>
    route.fulfill({
      json: {
        ...statisticsFixture(new URL(route.request().url()).searchParams),
        timezone: 'America/New_York',
      },
    }),
  )
  await page.goto('/statistics')
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  await page.getByRole('button', { name: 'Benutzerdefiniert' }).click()
  await page.getByLabel('Von', { exact: true }).fill('2026-09-14')
  await page.getByLabel('Bis einschließlich').fill('2026-09-15')
  await page.getByRole('button', { name: 'Zeitraum anwenden' }).click()
  await expect(page).toHaveURL(/period=custom/)
  expect(new URL(page.url()).searchParams.get('from_at')).toBe('2026-09-14T04:00:00.000Z')
  expect(new URL(page.url()).searchParams.get('to_at')).toBe('2026-09-16T04:00:00.000Z')
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  await page.getByRole('combobox', { name: 'Intervall' }).selectOption('6h')
  await expect(page).toHaveURL(/interval=6h/)
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  const request = page.waitForRequest((r) => r.url().includes('/statistics/entities'))
  await page.getByRole('button', { name: 'Zahlen aktualisieren' }).click()
  await request
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  await page.getByText(/Daten als Tabelle/).click()
  await expect(page.locator('.statistics-data-table table')).toBeVisible()
})

test('loading, empty, error and retry are explicit without invented zero metrics', async ({
  page,
}) => {
  await page.route('**/api/admin/api/v1/statistics/entities**', async (route) => {
    const data = statisticsFixture()
    data.series = data.series.map((s) => ({
      ...s,
      total: 0,
      points: s.points.map((p) => ({ ...p, count: 0 })),
    }))
    data.recent = []
    await route.fulfill({ json: data })
  })
  await page.goto('/statistics')
  await expect(page.getByText('Keine neuen Entitäten in diesem Zeitraum.').first()).toBeVisible()
  await expect(page.locator('.statistics-distribution svg')).toHaveCount(0)
  await page.route('**/api/admin/api/v1/statistics/entities**', (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: 'database_unavailable', message: 'Unavailable' } },
    }),
  )
  await page.getByRole('button', { name: 'Zahlen aktualisieren' }).click()
  await expect(page.getByRole('alert')).toContainText('Abruf fehlgeschlagen')
  await expect(page.locator('.statistics-metric')).toHaveCount(0)
  await page.route('**/api/admin/api/v1/statistics/entities**', (route) =>
    route.fulfill({ json: statisticsFixture() }),
  )
  await page.getByRole('button', { name: 'Erneut versuchen' }).click()
  await expect(page.locator('.statistics-metric')).toHaveCount(7)
})

test('late responses cannot overwrite a newer period or restore data after access loss', async ({
  page,
}) => {
  let release!: () => void
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/admin/api/v1/statistics/entities**', async (route) => {
    const query = new URL(route.request().url()).searchParams
    if (query.get('period') === '7d') await held
    await route.fulfill({ json: statisticsFixture(query) }).catch(() => {})
  })
  await page.goto('/statistics')
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  await page.getByRole('button', { name: '7 Tage', exact: true }).click()
  await expect(page.locator('.statistics-page [role="status"]')).toContainText('geladen')
  await page.getByRole('button', { name: '30 Tage', exact: true }).click()
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  release()
  await expect(page.getByRole('combobox', { name: 'Intervall' })).toContainText('6 Stunden')
  await page.route('**/api/admin/api/v1/statistics/entities**', (route) =>
    route.fulfill({
      status: 401,
      json: { error: { code: 'authentication_required', message: 'Unauthorized' } },
    }),
  )
  await page.getByRole('button', { name: 'Zahlen aktualisieren' }).click()
  await expect(page).toHaveURL(/\/login\?redirect=/)
  await expect(page.getByRole('button', { name: 'Anmelden', exact: true })).toBeVisible()
  await expect(page.locator('.statistics-series')).toHaveCount(0)
})
