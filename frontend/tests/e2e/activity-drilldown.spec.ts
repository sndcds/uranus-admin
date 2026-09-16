import { test, expect } from '@playwright/test'
import { summary, findings } from '../fixtures/api'
import { activityFixture } from '../fixtures/activity'
import { activityTypes } from '../../app/utils/activity'

const imageUrl =
  'https://api.kulturbytes.de/api/image/20000000-0000-7000-8000-000000000001?width=160&ratio=1%3A1'

test('all nine metric links preserve periods and support keyboard drill-down', async ({
  page,
}, info) => {
  await page.route('**/api/admin/auth/session', (route) =>
    route.fulfill({ json: { subject: 'admin:test-only-operator', system_admin: true } }),
  )
  await page.route('**/api/admin/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/summary'))
      return route.fulfill({
        json: { ...summary, period: url.searchParams.get('period') ?? '24h' },
      })
    if (url.pathname.endsWith('/activity'))
      return route.fulfill({
        json: {
          ...activityFixture,
          items: [
            {
              ...activityFixture.items[0]!,
              entity_type: 'event',
              image_url: imageUrl,
              public_url:
                'https://kulturbytes.de/de/veranstaltung/20000000-0000-7000-8000-000000000002/20000000-0000-7000-8000-000000000001',
              subtitle: 'Nächster öffentlicher Termin: 16.09.2026 · 19:00 (Europe/Berlin)',
              address: null,
            },
          ],
          pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
        },
      })
    return route.fulfill({ json: findings })
  })
  await page.route('https://api.kulturbytes.de/api/image/**', (route) =>
    route.fulfill({
      contentType: 'image/svg+xml',
      headers: { 'access-control-allow-origin': '*' },
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160"><rect width="160" height="160" fill="#f5d0fe"/><circle cx="80" cy="80" r="36" fill="#a21caf"/></svg>',
    }),
  )
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Abmelden', exact: true })).toBeVisible()
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  for (const period of ['24h', 'today', '7d']) {
    await page.getByLabel('Zeitraum', { exact: true }).selectOption(period)
    const links = page.locator('#new-records li a')
    await expect(links).toHaveCount(9)
    for (const [type, presentation] of Object.entries(activityTypes)) {
      const link = links.filter({ hasText: presentation.plural })
      await expect(link).toHaveAttribute('href', `/activity?period=${period}&entity_type=${type}`)
    }
  }
  await page.locator('#new-records').screenshot({ path: info.outputPath('new-records.png') })
  const link = page.locator('#new-records li a').filter({ hasText: 'Veranstaltungen' })
  await link.focus()
  await expect(link).toBeFocused()
  expect(await link.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe('none')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/period=7d&entity_type=event/)
  await expect(page.getByRole('heading', { name: 'Neue Veranstaltungen' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Objektart', exact: true })).toHaveValue('event')
  await expect(page.getByRole('combobox', { name: 'Zeitraum', exact: true })).toHaveValue('7d')
  const row = page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name: 'Lesung am Hafen' }) })
  await expect(row.locator('img')).toBeVisible()
  await expect(row.locator('img')).toHaveJSProperty('naturalWidth', 160)
  await expect(row.getByText('Nächster öffentlicher Termin:', { exact: false })).toBeVisible()
  await expect(row.getByRole('link', { name: /auf kulturbytes.de öffnen/ })).toHaveAttribute(
    'rel',
    'noopener noreferrer',
  )
  await expect(row.getByRole('link', { name: /Markierungen & Notizen/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.screenshot({ path: info.outputPath('rich-activity.png'), fullPage: true })
})
