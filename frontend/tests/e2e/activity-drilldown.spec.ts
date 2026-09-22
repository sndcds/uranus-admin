import { test, expect, expectLogoutAvailable } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'
import { activityFixture } from '../fixtures/activity'
import { activityTypes } from '../../app/utils/activity'

const imageUrl =
  'https://api.kulturbytes.de/api/image/20000000-0000-7000-8000-000000000001?width=320'

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
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#f5d0fe"/><circle cx="80" cy="80" r="36" fill="#a21caf"/></svg>',
    }),
  )
  await page.goto('/')
  await expectLogoutAvailable(page)
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
  await expect(row.locator('img')).toHaveJSProperty('naturalWidth', 320)
  await expect(row.getByText('Nächster öffentlicher Termin:', { exact: false })).toBeVisible()
  await expect(row.getByRole('link', { name: /auf kulturbytes.de öffnen/ })).toHaveAttribute(
    'rel',
    'noopener noreferrer',
  )
  await expect(row.getByRole('link', { name: /Markierungen & Notizen/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.screenshot({ path: info.outputPath('rich-activity.png'), fullPage: true })
})

test('image activity loads public thumbnails under a targeted CSP without metadata requests', async ({
  page,
}, info) => {
  test.skip(process.env.TEST_PRODUCTION !== '1', 'Enforced CSP requires the production build')
  const policy =
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://api.kulturbytes.de; connect-src 'self'; object-src 'none'; base-uri 'self'"
  const violations: string[] = []
  const externalRequests: string[] = []
  await page.exposeFunction('recordViolation', (directive: string) => violations.push(directive))
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      void (
        window as typeof window & { recordViolation: (directive: string) => Promise<void> }
      ).recordViolation(event.effectiveDirective)
    })
  })
  page.on('request', (request) => {
    if (request.url().startsWith('https://api.kulturbytes.de'))
      externalRequests.push(request.resourceType())
  })
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue()
    const response = await route.fetch()
    return route.fulfill({
      response,
      headers: { ...response.headers(), 'content-security-policy': policy },
    })
  })
  const item = activityFixture.items.find((item) => item.entity_type === 'image')!
  const thumbnail = `https://api.kulturbytes.de/api/image/${item.entity_key}?width=320`
  await page.route('**/api/admin/auth/session', (route) =>
    route.fulfill({ json: { subject: 'admin:test-only-operator', system_admin: true } }),
  )
  await page.route('**/api/admin/api/v1/dashboard/activity**', (route) =>
    route.fulfill({
      json: {
        ...activityFixture,
        items: [{ ...item, image_url: thumbnail, public_url: null }],
        pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
      },
    }),
  )
  await page.route('https://api.kulturbytes.de/api/image/**', (route) =>
    route.fulfill({
      contentType: 'image/svg+xml',
      headers: { 'access-control-allow-origin': '*' },
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="480"><rect width="320" height="480" fill="#f5d0fe"/></svg>',
    }),
  )
  await page.goto('/activity?entity_type=image&period=7d')
  const row = page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name: item.entity_name }) })
  const image = row.getByRole('img', { name: item.entity_name })
  await expect(image).toBeVisible()
  await expect(image).toHaveAttribute('src', thumbnail)
  await expect(image).toHaveJSProperty('naturalWidth', 320)
  await expect(image).toHaveAttribute('loading', 'lazy')
  await expect(image).toHaveAttribute('decoding', 'async')
  await expect(row.getByRole('link', { name: /Im Admin ansehen/ })).toHaveAttribute(
    'href',
    item.action!.href,
  )
  await expect(row.getByRole('link', { name: /Markierungen & Notizen/ })).toBeVisible()
  await expect(row.getByRole('link', { name: /auf kulturbytes.de öffnen/ })).toHaveCount(0)
  expect(externalRequests).toEqual(['image'])
  const dimensions = await image.boundingBox()
  expect(dimensions!.height / dimensions!.width).toBeCloseTo(1.5, 1)
  const trigger = row.getByRole('button', { name: `Bild vergrößern: ${item.entity_name}` })
  await trigger.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: item.entity_name })
  await expect(dialog).toBeVisible()
  const enlarged = dialog.getByRole('img', { name: item.entity_name })
  await expect(enlarged).toHaveAttribute('src', thumbnail.replace('width=320', 'width=1280'))
  await expect(enlarged).toHaveJSProperty('naturalHeight', 480)
  const enlargedDimensions = await enlarged.boundingBox()
  expect(enlargedDimensions!.height / enlargedDimensions!.width).toBeCloseTo(1.5, 1)
  expect(externalRequests).toEqual(['image', 'image'])
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
  await trigger.click()
  await dialog.getByRole('img').dispatchEvent('error')
  await expect(dialog.getByRole('alert')).toContainText('Das Bild konnte nicht geladen werden')
  await expect(dialog.getByRole('img')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Bildansicht schließen' }).click()
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
  expect(violations).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.screenshot({ path: info.outputPath('image-activity.png'), fullPage: true })
})
