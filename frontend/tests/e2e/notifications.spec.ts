import { test, expect } from '../fixtures/authenticated'
import {
  notification,
  notificationPage,
  notificationDetail,
  notificationDeliveryDetail,
  notificationPreview,
} from '../fixtures/notifications'
test.beforeEach(async ({ page }) => {
  await page.route('**/api/admin/api/v1/notifications?**', (route) =>
    route.fulfill({ json: notificationPage }),
  )
  await page.route(`**/api/admin/api/v1/notifications/${notification.id}`, (route) =>
    route.fulfill({ json: notificationDetail }),
  )
  await page.route(
    `**/api/admin/api/v1/notification-deliveries/${notificationDeliveryDetail.id}`,
    (route) => route.fulfill({ json: notificationDeliveryDetail }),
  )
  await page.route(`**/api/admin/api/v1/notifications/${notification.id}/preview?**`, (route) => {
    const locale = new URL(route.request().url()).searchParams.get('locale') as 'de' | 'da' | 'en'
    return route.fulfill({ json: notificationPreview(locale) })
  })
})
test('list, filters, dry run, detail and delivery history', async ({ page }) => {
  await page.goto('/notifications')
  await expect(page.getByRole('heading', { name: 'Benachrichtigungen', exact: true })).toBeVisible()
  await expect(page.getByText('E-Mail-Versand ist deaktiviert (Dry Run).')).toBeVisible()
  await page.getByRole('combobox', { name: 'Status', exact: true }).selectOption('active')
  const request = page.waitForRequest(
    (r) => r.url().includes('/notifications?') && r.url().includes('status=active'),
  )
  await page.getByRole('button', { name: 'Filter anwenden' }).click()
  await request
  await page.getByRole('link', { name: 'Kulturabend', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Versandhistorie' })).toBeVisible()
  await page.getByRole('link', { name: 'Fehlgeschlagen · recipient@example.test' }).click()
  await expect(page.getByRole('heading', { name: 'E-Mail-Versand' })).toBeVisible()
  await expect(page.getByText('smtp_451')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
for (const locale of ['de', 'da', 'en'] as const)
  test(`preview ${locale} under CSP`, async ({ page }) => {
    await page.route('**/notifications/*', async (route) => {
      if (route.request().resourceType() !== 'document') return route.fallback()
      const response = await route.fetch()
      await route.fulfill({
        response,
        headers: {
          ...response.headers(),
          'content-security-policy':
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'",
        },
      })
    })
    await page.goto(`/notifications/${notification.id}`)
    await page.getByLabel('Sprache').selectOption(locale)
    await page.getByRole('button', { name: 'Vorschau laden' }).click()
    await expect(
      page.getByRole('heading', { name: notificationPreview(locale).subject }),
    ).toBeVisible()
    await expect(
      page.frameLocator('iframe').getByText(notificationPreview(locale).subject),
    ).toBeVisible()
    await expect(page.locator('iframe')).toHaveAttribute('sandbox', '')
    await page.getByRole('button', { name: 'Text', exact: true }).click()
    await expect(page.locator('pre[lang]')).toContainText('Kulturverein')
  })
test('anonymous deep links and SSR disclose no protected content', async ({ request, browser }) => {
  const response = await request.get(`/notifications/${notification.id}`)
  expect(await response.text()).not.toContain('recipient@example.test')
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto(`/notifications/${notification.id}`)
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByText('Versandhistorie')).toHaveCount(0)
  await context.close()
})
test('navigation for an authenticated administrator', async ({ page, isMobile }) => {
  await page.goto('/notifications')
  if (isMobile) await page.getByRole('button', { name: 'Navigation öffnen' }).click()
  await expect(
    page.getByRole('link', { name: 'Benachrichtigungen', exact: true }).filter({ visible: true }),
  ).toHaveAttribute('aria-current', 'page')
})
