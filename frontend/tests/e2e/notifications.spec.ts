import { test, expect } from '../fixtures/authenticated'
import {
  notification,
  notificationPage,
  notificationDeliveryPage,
  notificationDetail,
  notificationDeliveryDetail,
  notificationPreview,
  notificationGuidance,
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
  await page.getByRole('link', { name: 'Temporär fehlgeschlagen · recipient@example.test' }).click()
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
    await expect(page.frameLocator('iframe').getByRole('link')).toHaveAttribute(
      'href',
      notification.payload.external_action_url!,
    )
    const html = await page.locator('iframe').getAttribute('srcdoc')
    expect(html).not.toContain('https://admin.kulturbytes.de')
    expect(html).not.toContain('/findings')
    await page.getByRole('button', { name: 'Text', exact: true }).click()
    await expect(page.locator('pre[lang]')).toContainText('Kulturverein')
    await expect(page.locator('pre[lang]')).toContainText(notification.payload.external_action_url!)
    await page.route(`**/api/admin/api/v1/notifications/${notification.id}/preview?**`, (route) =>
      route.fulfill({ json: notificationPreview(locale, false) }),
    )
    await page.getByRole('button', { name: 'Vorschau laden' }).click()
    await expect(page.locator('pre[lang]')).toContainText(notificationGuidance[locale])
    await page.getByRole('button', { name: 'HTML', exact: true }).click()
    await expect(page.frameLocator('iframe').getByText(notificationGuidance[locale])).toBeVisible()
    await expect(page.frameLocator('iframe').getByRole('link')).toHaveCount(0)
    expect(await page.locator('iframe').getAttribute('srcdoc')).not.toContain(
      'https://admin.kulturbytes.de',
    )
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

test('failure KPI, delivery list and confirmed retry preserve the old history', async ({
  page,
}) => {
  const old = {
    ...notificationDeliveryDetail,
    status: 'permanent_failure',
    last_error: 'smtp_553',
    attempt_count: 2,
  }
  const nextId = '10000000-0000-4000-8000-000000000099'
  const next = {
    ...old,
    id: nextId,
    retry_of_delivery_id: old.id,
    status: 'queued',
    attempt_count: 0,
    last_error: null,
  }
  await page.route('**/api/admin/api/v1/notifications?**', (route) =>
    route.fulfill({
      json: {
        ...notificationPage,
        summary: {
          ...notificationPage.summary,
          failed: 2,
          permanent_failed: 2,
          temporary_failed: 0,
        },
      },
    }),
  )
  await page.route('**/api/admin/api/v1/notification-deliveries?**', (route) =>
    route.fulfill({
      json: {
        ...notificationDeliveryPage,
        items: [{ ...old, organization_name: 'Kulturverein', created_at: old.queued_at }],
      },
    }),
  )
  await page.route(`**/api/admin/api/v1/notification-deliveries/${old.id}`, (route) =>
    route.fulfill({ json: old }),
  )
  await page.route(`**/api/admin/api/v1/notification-deliveries/${nextId}`, (route) =>
    route.fulfill({ json: next }),
  )
  let posts = 0
  await page.route(`**/api/admin/api/v1/notification-deliveries/${old.id}/retry`, (route) => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().postData()).toBeNull()
    expect(route.request().headers()['x-admin-csrf']).toBe('1')
    posts++
    return route.fulfill({
      status: 201,
      json: { delivery_id: nextId, retry_of_delivery_id: old.id, status: 'queued' },
    })
  })
  await page.goto('/notifications')
  await page.getByRole('link', { name: 'Dauerhaft fehlgeschlagen', exact: true }).click()
  await expect(page).toHaveURL(/notifications\/deliveries\?status=permanent_failure/)
  await expect(page.getByRole('heading', { name: 'E-Mail-Versände', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Status', exact: true })).toHaveValue(
    'permanent_failure',
  )
  await page.getByRole('link', { name: old.subject! }).click()
  await expect(page.getByText('Der automatische Versand wurde beendet.')).toBeVisible()
  await expect(page.getByText('smtp_553', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Erneut versuchen', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Erneut versuchen?' })).toBeVisible()
  await page.getByRole('button', { name: 'Versand erneut einreihen' }).click()
  await expect(page).toHaveURL(`/notifications/deliveries/${nextId}`)
  await expect(page.getByText(/Neuer Versand wurde eingereiht/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Vorheriger Versand' })).toHaveAttribute(
    'href',
    `/notifications/deliveries/${old.id}`,
  )
  await expect(page.getByRole('button', { name: 'Erneut versuchen', exact: true })).toHaveCount(0)
  expect(posts).toBe(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

for (const status of ['failed', 'sent'] as const)
  test(`${status} delivery has no manual retry`, async ({ page }) => {
    await page.route(
      `**/api/admin/api/v1/notification-deliveries/${notificationDeliveryDetail.id}`,
      (route) => route.fulfill({ json: { ...notificationDeliveryDetail, status } }),
    )
    await page.goto(`/notifications/deliveries/${notificationDeliveryDetail.id}`)
    await expect(page.getByText('recipient@example.test', { exact: false })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Erneut versuchen', exact: true })).toHaveCount(0)
    if (status === 'failed')
      await expect(page.getByText(/Automatischer neuer Versuch:/)).toBeVisible()
  })

test('retry proxy denies anonymous and cross-origin writes without forwarding overrides', async ({
  request,
  context,
}) => {
  const url = `/api/admin/api/v1/notification-deliveries/${notificationDeliveryDetail.id}/retry`
  expect((await request.post(url)).status()).toBe(401)
  // The page fixture has a real session; the separate request fixture is anonymous.
  // APIRequestContext does not apply Chromium's secure-loopback cookie exception.
  const cookie = (await context.cookies()).find((item) => item.name.endsWith('admin_session'))!
  const authenticated = { Cookie: `${cookie.name}=${cookie.value}` }
  expect((await request.post(url, { headers: authenticated })).status()).toBe(403)
  expect(
    (
      await request.post(url, {
        headers: { ...authenticated, Origin: 'http://evil.test', 'X-Admin-CSRF': '1' },
      })
    ).status(),
  ).toBe(403)
  expect(
    (
      await request.post(url, {
        headers: { ...authenticated, Origin: 'http://127.0.0.1:3100', 'X-Admin-CSRF': '1' },
        data: { recipient: 'other@example.test' },
      })
    ).status(),
  ).toBe(422)
})

test('delivery routes keep unauthenticated SSR and client content private', async ({
  request,
  browser,
}) => {
  for (const path of [
    '/notifications/deliveries',
    `/notifications/deliveries/${notificationDeliveryDetail.id}`,
  ]) {
    const response = await request.get(path)
    expect(await response.text()).not.toContain('recipient@example.test')
    const context = await browser.newContext()
    const page = await context.newPage()
    await page.goto(path)
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole('button', { name: 'Erneut versuchen', exact: true })).toHaveCount(0)
    await context.close()
  }
})
