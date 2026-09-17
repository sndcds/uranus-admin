import { test, expect } from '../fixtures/authenticated'
import { eventContentFixture } from '../fixtures/event-content'
import { statisticsFixture } from '../fixtures/statistics'

test('event content shares periods, filters rankings, compares and restores URL history on every viewport', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (/hydration|violates.*security policy/i.test(message.text())) errors.push(message.text())
  })
  await page.route('**/api/admin/api/v1/statistics/**', (route) => {
    const url = new URL(route.request().url())
    return route.fulfill({
      json: url.pathname.endsWith('/events/content')
        ? eventContentFixture(url.searchParams)
        : statisticsFixture(url.searchParams),
    })
  })
  await page.goto('/statistics')
  await expect(page.getByRole('button', { name: 'Letzte 24 Stunden', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Neueste Entitäten', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Event-Inhalte', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Event-Inhalte', exact: true })).toBeVisible()
  const period = page.getByRole('combobox', { name: 'Zeitraum', exact: true })
  const status = page.getByRole('combobox', { name: 'Status', exact: true })
  await period.selectOption('30d')
  await expect(page).toHaveURL(/period=30d/)
  await status.selectOption('released')
  await expect(page.getByRole('region', { name: 'Events erstellt', exact: true })).toContainText(
    '8',
  )
  for (const title of ['Top 10 Kategorien', 'Top 10 Genres', 'Top 10 Event-Typen']) {
    const panel = page.getByRole('region', { name: title, exact: true })
    await expect(panel).toBeVisible()
    await expect(panel).toContainText('6 Events · 75 %')
  }
  await expect(page.getByText(/nicht zwingend zu 100 %/)).toBeVisible()
  await page.getByRole('switch', { name: 'Zeitraum vergleichen' }).check()
  await expect(page.getByRole('region', { name: 'Top 10 Genres', exact: true })).toContainText(
    'Rang ↑ 2',
  )
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('view') === 'event-content' &&
      url.searchParams.get('period') === '30d' &&
      url.searchParams.get('status') === 'released' &&
      url.searchParams.get('compare') === 'previous',
  )
  await page.screenshot({ path: test.info().outputPath('event-content.png'), fullPage: true })
  await page.reload()
  await expect(period).toHaveValue('30d')
  await expect(status).toHaveValue('released')
  await expect(page.getByRole('switch')).toBeChecked()
  await period.selectOption('7d')
  await expect(page).toHaveURL(/period=7d/)
  await page.goBack()
  await expect(period).toHaveValue('30d')
  await page.goForward()
  await expect(period).toHaveValue('7d')
  await period.selectOption('all')
  await expect(page.getByRole('switch')).toBeDisabled()
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('period') === 'all' && !url.searchParams.has('compare'),
  )
  await status.selectOption('cancelled')
  await expect(
    page.getByText('Keine Events im gewählten Erstellungszeitraum.', { exact: true }),
  ).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Erstellung', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Letzte 7 Tage', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByLabel('Intervall', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
