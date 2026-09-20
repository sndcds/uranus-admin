import { test, expect } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'

test('dashboard, responsive navigation, filtering, pagination and detail', async ({
  page,
}, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (/hydration/i.test(message.text())) errors.push(message.text())
  })
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/summary'))
      return route.fulfill({
        json: { ...summary, period: url.searchParams.get('period') ?? '24h' },
      })
    const current = Number(url.searchParams.get('page') ?? '1')
    return route.fulfill({
      json: { ...findings, pagination: { page: current, page_size: 10, total: 21, pages: 3 } },
    })
  })
  await page.goto('/')
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  await page.getByLabel('Zeitraum', { exact: true }).selectOption('today')
  await expect(page.getByLabel('Zeitraum', { exact: true })).toHaveValue('today')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await page.screenshot({ path: testInfo.outputPath('dashboard.png'), fullPage: true })
  if (testInfo.project.name === 'mobile') {
    await page.getByRole('button', { name: 'Navigation öffnen' }).click()
    await expect(page.getByRole('dialog', { name: 'Mobile Navigation' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'Navigation öffnen' })).toBeFocused()
    await page.getByRole('button', { name: 'Navigation öffnen' }).click()
    await page.getByRole('dialog').getByRole('link', { name: 'Arbeitsliste' }).click()
  } else
    await page
      .getByRole('navigation', { name: 'Hauptnavigation' })
      .getByRole('link', { name: 'Arbeitsliste' })
      .click()
  await expect(page).toHaveURL(/\/findings/)
  await page.getByRole('combobox', { name: 'Schweregrad', exact: true }).selectOption('warning')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/severity=warning/)
  await page.getByRole('button', { name: 'Weiter', exact: true }).click()
  await expect(page).toHaveURL(/page=2/)
  await page.getByRole('combobox', { name: 'Schweregrad', exact: true }).selectOption('error')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/page=1/)
  await page.getByRole('button', { name: 'Befund zu Test-Hafenbühne ansehen' }).click()
  await expect(page.getByRole('dialog', { name: 'Test-Hafenbühne' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(
    page.getByRole('button', { name: 'Befund zu Test-Hafenbühne ansehen' }),
  ).toBeFocused()
  await page.screenshot({ path: testInfo.outputPath('findings.png'), fullPage: true })
  expect(errors).toEqual([])
})

test('unavailable backend has an honest error without logging out', async ({ page }) => {
  await page.route('**/api/admin/api/v1/**', (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: 'unavailable', message: 'private-details' } },
    }),
  )
  await page.goto('/')
  await expect(
    page
      .getByText('Die Admin-API ist derzeit nicht bereit. Bitte später erneut versuchen.')
      .first(),
  ).toBeVisible()
  await expect(page.getByText('private-details')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Abmelden', exact: true })).toBeVisible()
})

test('real Nitro proxy denies absent auth, unknown routes and write methods', async ({
  request,
}) => {
  expect((await request.get('/api/admin/api/v1/findings')).status()).toBe(401)
  expect((await request.get('/api/admin/anything')).status()).toBe(404)
  expect((await request.post('/api/admin/api/v1/findings')).status()).toBe(405)
  const response = await request.get('/api/admin/api/v1/findings')
  expect(response.headers()['cache-control']).toContain('no-store')
})

test('dashboard active worklist total and links exclude resolved history', async ({ page }) => {
  const base = findings.items[0]!
  const rows = [
    {
      ...base,
      id: 'resolved-high',
      entity_name: 'Behobener Spitzenbefund',
      status: 'resolved',
      severity: 'error',
      priority_score: 99999,
    },
    {
      ...base,
      id: 'open-low',
      entity_name: 'Aktiver Fehler',
      status: 'open',
      severity: 'error',
      priority_score: 1000,
    },
    {
      ...base,
      id: 'exception-low',
      entity_name: 'Aktive Ausnahme',
      status: 'exception',
      severity: 'warning',
      priority_score: 900,
    },
  ]
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/summary'))
      return route.fulfill({
        json: {
          ...summary,
          quality: { ...summary.quality, mode: 'persisted', total: 2, errors: 1, warnings: 1 },
        },
      })
    const active = url.searchParams.get('active_only') === 'true'
    const severity = url.searchParams.get('severity')
    const selected = rows.filter(
      (row) => (!active || row.status !== 'resolved') && (!severity || row.severity === severity),
    )
    return route.fulfill({
      json: {
        ...findings,
        mode: 'persisted',
        items: selected.slice(0, Number(url.searchParams.get('page_size') ?? 50)),
        pagination: { page: 1, page_size: 4, total: selected.length, pages: 1 },
      },
    })
  })
  await page.goto('/?period=24h')
  await expect(page.getByText('Aktiver Fehler', { exact: true })).toBeVisible()
  await expect(page.getByText('Aktive Ausnahme', { exact: true })).toBeVisible()
  await expect(page.getByText('Behobener Spitzenbefund')).toHaveCount(0)
  const all = page.getByRole('link', { name: 'Alle 2 Befunde anzeigen' })
  await expect(all).toHaveAttribute('href', /active_only=true/)
  await expect(page.getByRole('region', { name: 'Datenqualitätsübersicht' })).toContainText(
    '2 Befunde',
  )
  await expect(page.getByRole('link', { name: /Dringend/ })).toHaveAttribute(
    'href',
    /active_only=true/,
  )
  await all.click()
  await expect(page).toHaveURL(/active_only=true/)
  await expect(page.getByText('Behobener Spitzenbefund')).toHaveCount(0)
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Alle 2 Befunde anzeigen' })).toBeVisible()
  await page.getByRole('button', { name: 'Fehler', exact: true }).click()
  const errors = page.getByRole('link', { name: 'Alle 1 Befunde anzeigen' })
  await expect(errors).toHaveAttribute('href', /active_only=true/)
  await expect(errors).toHaveAttribute('href', /severity=error/)
  await expect(page.getByText('Behobener Spitzenbefund')).toHaveCount(0)
  await expect(page.getByText('Aktive Ausnahme', { exact: true })).toHaveCount(0)
  await errors.click()
  await expect(page).toHaveURL(/severity=error/)
  await expect(page.getByText('Aktiver Fehler', { exact: true })).toBeVisible()
  await page.goto('/findings')
  await expect(page.getByText('Behobener Spitzenbefund', { exact: true })).toBeVisible()
})
