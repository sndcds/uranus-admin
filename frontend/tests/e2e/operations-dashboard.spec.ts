import { test, expect } from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'
import { operationsSummary, operationsFindings } from '../fixtures/operations-dashboard'

for (const [name, width, height] of [
  ['desktop', 1440, 1000],
  ['tablet', 1024, 768],
  ['mobile', 390, 844],
  ['small-mobile', 360, 800],
] as const) {
  test(`operations dashboard ${name}`, async ({ page }, info) => {
    // Both projects exercise this layout, including touch behavior in mobile.
    await page.setViewportSize({ width, height })
    await page.clock.setFixedTime(new Date('2026-09-23T10:05:00Z'))
    await mockLayoutApi(page)
    const requests: URL[] = []
    await page.route('**/api/admin/api/v1/dashboard/summary**', (route) =>
      route.fulfill({
        json: {
          ...operationsSummary,
          period: new URL(route.request().url()).searchParams.get('period') ?? '24h',
        },
      }),
    )
    await page.route('**/api/admin/api/v1/findings**', (route) => {
      const url = new URL(route.request().url())
      requests.push(url)
      return route.fulfill({
        json: {
          ...operationsFindings,
          items: operationsFindings.items.filter(
            (item) =>
              !url.searchParams.get('severity') ||
              item.severity === url.searchParams.get('severity'),
          ),
        },
      })
    })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible()
    await expect(page.locator('#new-records li')).toHaveCount(9)
    await expect(page.getByRole('link', { name: /^Räume: 0/ })).toBeVisible()
    await expect(page.locator('#attention h4')).toHaveCount(4)
    const worklist = page.getByRole('table', { name: 'Priorisierte Befunde' })
    await expect(worklist.locator('tbody tr')).toHaveCount(4)
    const quality = page.getByRole('region', { name: 'Datenqualitätsübersicht' })
    await expect(quality).toContainText('929 Befunde')
    await expect(quality.getByRole('listitem')).toHaveCount(5)
    await expect(page.locator('#open-queues li')).toHaveCount(3)
    const technical = page.getByRole('region', { name: 'Technische Informationen' })
    await expect(technical).toContainText('Letzter erfolgreicher Abruf')
    await expect(technical).toContainText('Client-Abrufzeit')
    await expect(technical).toContainText('Europe/Berlin')
    await expect(page.getByRole('combobox', { name: 'Schweregrad', exact: true })).not.toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const incomingBoxes = await page
      .locator('#new-records li a')
      .evaluateAll((links) => links.map((link) => link.getBoundingClientRect().height))
    expect(incomingBoxes.every((height) => height >= 44 && height <= 80)).toBe(true)
    // Synthetic, reproducible review artifacts; only write tracked screenshots explicitly.
    await page.screenshot({
      path:
        process.env.UPDATE_DASHBOARD_SCREENSHOTS === '1' && info.project.name === 'desktop'
          ? `docs/screenshots/operations-dashboard/${name}.png`
          : info.outputPath(`${name}.png`),
      fullPage: true,
    })
    const advanced = page.locator('summary').filter({ hasText: 'Erweiterte Filter' })
    await advanced.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('combobox', { name: 'Schweregrad', exact: true })).toBeVisible()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('combobox', { name: 'Schweregrad', exact: true })).not.toBeVisible()
    await expect(worklist.locator('summary')).toHaveCount(0)
    await expect(worklist.getByRole('button')).toHaveCount(1)
    await expect(worklist.getByRole('button', { name: 'SQL Editor für Hafenbühne' })).toBeVisible()
    await expect(worklist.getByRole('link', { name: 'Markierungen & Notizen' })).toHaveCount(0)
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: 'Fehler', exact: true }).click()
    await expect(worklist.locator('tbody tr')).toHaveCount(2)
    expect(requests.at(-1)!.searchParams.get('active_only')).toBe('true')
    expect(requests.at(-1)!.searchParams.get('page_size')).toBe('4')
    expect(requests.at(-1)!.searchParams.get('severity')).toBe('error')
    await page.getByRole('combobox', { name: 'Zeitraum', exact: true }).selectOption('7d')
    await expect(page).toHaveURL(/period=7d/)
    await page.getByRole('button', { name: 'Zahlen aktualisieren' }).click()
    await expect(page.getByRole('button', { name: 'Zahlen aktualisieren' })).toBeEnabled()
  })
}
