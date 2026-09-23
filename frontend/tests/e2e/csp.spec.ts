import { test, expect } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'
import { statisticsFixture } from '../fixtures/statistics'
import { graphFixture, graphPath } from '../fixtures/graph'
import { globalSearchFixture } from '../fixtures/search'

test('production schemas work under an enforced CSP without unsafe-eval', async ({ page }) => {
  test.skip(process.env.TEST_PRODUCTION !== '1', 'Requires the production client build')
  const policy =
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'"
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.addInitScript(() => {
    const state = window as typeof window & { cspViolations: string[] }
    state.cspViolations = []
    document.addEventListener('securitypolicyviolation', (event) => {
      state.cspViolations.push(`${event.effectiveDirective}: ${event.blockedURI}`)
    })
  })
  // Enforce via the HTML response header, before any client module executes.
  // This changes only the test response, never the live proxy configuration.
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue()
    const response = await route.fetch()
    await route.fulfill({
      response,
      headers: { ...response.headers(), 'content-security-policy': policy },
    })
  })
  await page.route('**/api/admin/api/v1/**', (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith('/summary') ? summary : findings,
    }),
  )
  const response = await page.goto('/')
  expect(response?.headers()['content-security-policy']).toBe(policy)
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  expect(
    await page.evaluate(
      () => (window as typeof window & { cspViolations: string[] }).cspViolations,
    ),
  ).toEqual([])
  // Exercise a separate route and client-side filter/record-link interactions too.
  await page.goto('/findings')
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  await page.getByRole('combobox', { name: 'Schweregrad', exact: true }).selectOption('warning')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/severity=warning/)
  await page
    .getByRole('table')
    .getByRole('button', { name: /^Befund bearbeiten:/ })
    .click()
  await expect(page.getByRole('dialog', { name: 'Test-Hafenbühne' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.route('**/api/admin/api/v1/graph?**', (route) => route.fulfill({ json: graphFixture }))
  await page.goto(graphPath)
  await expect(page.locator('.graph-node')).toHaveCount(12)
  await page.getByRole('button', { name: 'Vergrößern', exact: true }).click()
  await page.route('**/api/admin/api/v1/statistics/entities**', (route) =>
    route.fulfill({ json: statisticsFixture() }),
  )
  await page.goto('/statistics')
  await expect(page.locator('.statistics-series')).toHaveCount(7)
  await page.locator('.statistics-legend button').first().click()
  await expect(page.locator('.statistics-series')).toHaveCount(6)
  await page.route('**/api/admin/api/v1/search?**', (route) => {
    const query = new URL(route.request().url()).searchParams.get('q') || ''
    return route.fulfill({ json: globalSearchFixture(query) })
  })
  await page.getByRole('button', { name: 'Globale Suche öffnen' }).filter({ visible: true }).click()
  const palette = page.getByRole('dialog', { name: 'Kulturbytes durchsuchen' })
  await palette.getByRole('combobox').fill('person@example.org')
  await expect(palette.getByRole('option', { name: /person@example.org/ })).toBeVisible()
  await page.keyboard.press('Escape')
  expect(errors).toEqual([])
  expect(
    await page.evaluate(
      () => (window as typeof window & { cspViolations: string[] }).cspViolations,
    ),
  ).toEqual([])
})
