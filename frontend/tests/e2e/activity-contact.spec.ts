import { test, expect } from '../fixtures/authenticated'
import { activityFixture } from '../fixtures/activity'

const userId = '20000000-0000-7000-8000-000000000003'
const orgId = '20000000-0000-7000-8000-000000000004'

test('user contacts and avatars, organization logo spacing and map coordinates', async ({
  page,
}, info) => {
  let avatarMissing = false
  await page.route('**/api/admin/api/v1/dashboard/activity**', (route) => {
    const kind = new URL(route.request().url()).searchParams.get('entity_type')
    const user = kind === 'user'
    const venue = kind === 'venue'
    return route.fulfill({
      json: {
        ...activityFixture,
        items: [
          {
            ...activityFixture.items[0]!,
            entity_type: user ? 'user' : venue ? 'venue' : 'organization',
            entity_key: user ? userId : orgId,
            entity_name: user
              ? 'Beispielbenutzer'
              : venue
                ? 'Ort am Hafen'
                : 'Kulturverein am Hafen',
            organization_id: user ? null : orgId,
            organization_name: user ? null : 'Kulturverein am Hafen',
            status: user ? 'active' : null,
            subtitle: null,
            action: {
              type: 'view',
              route: 'activity',
              entity_type: user ? 'user' : venue ? 'venue' : 'organization',
              entity_key: user ? userId : orgId,
              href: `/activity?entity_key=${user ? userId : orgId}&entity_type=${user ? 'user' : venue ? 'venue' : 'organization'}`,
            },
            email: user ? 'operator@example.invalid' : null,
            image_url: user
              ? `https://api.kulturbytes.de/api/user/${userId}/avatar/128`
              : `https://api.kulturbytes.de/api/image/${orgId}?width=320`,
            address: user ? null : 'Hafenstraße 3, 24937 Flensburg',
            location: user || venue ? null : { latitude: 54.79, longitude: 9.43 },
          },
        ],
        pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
      },
    })
  })
  const requests: string[] = []
  await page.route('https://api.kulturbytes.de/api/**', (route) => {
    requests.push(route.request().url())
    return avatarMissing
      ? route.fulfill({ status: 404, headers: { 'access-control-allow-origin': '*' } })
      : route.fulfill({
          contentType: 'image/svg+xml',
          headers: { 'access-control-allow-origin': '*' },
          body: '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="#f5d0fe"/></svg>',
        })
  })
  await page.goto('/activity?period=7d&entity_type=user')
  await expect(page.getByText('E-Mail: operator@example.invalid')).toBeVisible()
  const avatar = page.getByRole('img', { name: 'Beispielbenutzer' })
  await expect(avatar).toHaveAttribute(
    'src',
    `https://api.kulturbytes.de/api/user/${userId}/avatar/128`,
  )
  await expect(avatar).toHaveJSProperty('naturalWidth', 128)
  await expect(page.getByRole('link', { name: /OpenStreetMap/ })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('activity-user.png'), fullPage: true })
  await page.getByRole('button', { name: 'Bild vergrößern: Beispielbenutzer' }).click()
  await expect(page.getByRole('dialog').getByRole('img')).toHaveAttribute(
    'src',
    `https://api.kulturbytes.de/api/user/${userId}/avatar/512`,
  )
  await page.keyboard.press('Escape')
  avatarMissing = true
  await page.reload()
  await expect(page.getByText('E-Mail: operator@example.invalid')).toBeVisible()
  await expect(page.getByRole('img', { name: 'Beispielbenutzer' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /Markierungen & Notizen/ })).toBeVisible()
  avatarMissing = false
  await page.goto('/activity?period=7d&entity_type=organization')
  await expect(page.getByText('Hafenstraße 3, 24937 Flensburg')).toBeVisible()
  const logo = page.getByRole('button', { name: 'Bild vergrößern: Kulturverein am Hafen' })
  expect(await logo.evaluate((el) => parseFloat(getComputedStyle(el).paddingLeft))).toBeGreaterThan(
    0,
  )
  await expect(logo.getByRole('img')).toHaveJSProperty('naturalWidth', 128)
  const map = page.getByRole('link', { name: /auf OpenStreetMap öffnen/ })
  await expect(map).toHaveAttribute(
    'href',
    'https://www.openstreetmap.org/?mlat=54.79&mlon=9.43#map=17/54.79/9.43',
  )
  await expect(map).toHaveAttribute('rel', 'noopener noreferrer')
  await expect(map).toHaveAttribute('target', '_blank')
  await expect(page.getByText('E-Mail:', { exact: false })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(
    requests.every((url) => /\/avatar\/(128|512)$|\/api\/image\/.+\?width=320$/.test(url)),
  ).toBe(true)
  await page.screenshot({ path: info.outputPath('activity-organization.png'), fullPage: true })
  await page.goto('/activity?period=7d&entity_type=venue')
  const venueImage = page.getByRole('button', { name: 'Bild vergrößern: Ort am Hafen' })
  await expect(venueImage.getByRole('img')).toHaveJSProperty('naturalWidth', 128)
  expect(await venueImage.evaluate((el) => parseFloat(getComputedStyle(el).paddingLeft))).toBe(12)
  await expect(page.getByRole('link', { name: /Markierungen & Notizen/ })).toBeVisible()
})

for (const entityType of ['user', 'team_membership'] as const) {
  test(`email-only ${entityType} uses backend title in Activity`, async ({ page }) => {
    const source = activityFixture.items.find((item) => item.entity_type === entityType)!
    const email = 'no-name@example.org'
    await page.route('**/api/admin/api/v1/dashboard/activity**', (route) =>
      route.fulfill({
        json: {
          ...activityFixture,
          items: [{ ...source, entity_name: email }],
          pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
        },
      }),
    )
    await page.goto(`/activity?entity_type=${entityType}&period=7d`)
    await expect(page.getByRole('heading', { level: 4, name: email, exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: source.entity_key, exact: true })).toHaveCount(0)
  })
}
