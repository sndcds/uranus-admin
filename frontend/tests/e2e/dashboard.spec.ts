import { test, expect } from '@playwright/test'
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

test('locked access and unavailable backend have honest errors', async ({ page }) => {
  await page.route('**/api/admin/api/v1/**', (route) =>
    route.fulfill({
      status: 401,
      json: { error: { code: 'authentication_required', message: 'required' } },
    }),
  )
  await page.goto('/')
  await expect(page.getByText('Zugang erforderlich').first()).toBeVisible()
  await expect(page.getByText('Lokaler Entwicklungszugang', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Nicht verfügbar', { exact: true }).first()).toBeVisible()
  await page.unroute('**/api/admin/api/v1/**')
  await page.route('**/api/admin/api/v1/**', (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: 'unavailable', message: 'private-details' } },
    }),
  )
  await page.getByRole('button', { name: 'Erneut versuchen' }).first().click()
  await expect(
    page.getByText('Die Admin-API ist derzeit nicht bereit. Bitte später erneut versuchen.'),
  ).toBeVisible()
  await expect(page.getByText('private-details')).toHaveCount(0)
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
