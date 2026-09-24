import { test, expect } from '../fixtures/authenticated'
import { activityFixture } from '../fixtures/activity'
import { detailFixture, entityFixture, timelineFixture } from '../fixtures/entities'
import { globalSearchFixture } from '../fixtures/search'

for (const [scope, label] of [
  ['shared', 'Eigener Ort'],
  ['organization', 'Provisorischer Ort (nicht eigener Ort)'],
] as const) {
  test(`${scope}: identity, activity, relations and both searches remain readable and keyboard accessible`, async ({
    page,
  }) => {
    const venue = { ...entityFixture('venues').items[0]!, venue_scope: scope }
    const requests: string[] = []
    await page.route('**/api/admin/api/v1/**', (route) => {
      const url = new URL(route.request().url())
      requests.push(url.pathname)
      if (url.pathname.endsWith('/timeline'))
        return route.fulfill({ json: timelineFixture('venue') })
      if (url.pathname.endsWith('/entity-search'))
        return route.fulfill({
          json: {
            items: [
              {
                entity_type: 'venue',
                entity_key: venue.entity_key,
                label: venue.entity_name,
                subtitle: 'Flensburg',
                status: null,
                venue_scope: scope,
                action: venue.action,
              },
            ],
          },
        })
      if (url.pathname.endsWith('/search')) {
        const result = globalSearchFixture('Kühlhaus')
        result.groups = result.groups.filter((group) => group.entity_type === 'venue')
        result.groups[0]!.items[0]!.venue_scope = scope
        return route.fulfill({ json: result })
      }
      if (url.pathname.endsWith('/activity'))
        return route.fulfill({ json: { ...activityFixture, items: [venue] } })
      if (url.pathname.includes('/organizations/')) {
        const detail = detailFixture('organizations')
        detail.related = {
          items: [venue],
          pagination: { page: 1, pages: 1, page_size: 25, total: 1 },
        }
        return route.fulfill({ json: detail })
      }
      if (url.pathname.includes('/venues/'))
        return route.fulfill({ json: { ...detailFixture('venues'), item: venue } })
      return route.fulfill({ json: { ...entityFixture('venues'), items: [venue] } })
    })
    const noOverflow = async () =>
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
    await page.goto('/venues')
    const row = page.locator('[data-collection-row]')
    await expect(row.locator('[data-venue-scope]')).toHaveText(label)
    for (const width of [1440, 390, 360]) {
      await page.setViewportSize({ width, height: 844 })
      await noOverflow()
      await expect(row.locator('[data-venue-scope]')).toBeVisible()
    }
    const search = page.getByRole('combobox', { name: 'Suche', exact: true })
    await search.fill('Venue')
    const option = page.getByRole('option')
    await expect(option.locator('[data-venue-scope]')).toHaveText(label)
    await noOverflow()
    expect(requests.filter((path) => path.endsWith('/entity-search'))).toHaveLength(1)
    await search.press('ArrowDown')
    await search.press('Enter')
    await expect(page.locator('[data-entity-hero] [data-venue-scope]')).toHaveText(label)
    await noOverflow()
    await page.goto('/activity')
    await expect(page.locator('main [data-venue-scope]')).toHaveText(label)
    await noOverflow()
    await page.goto(`/organizations/${venue.entity_key}`)
    await expect(page.locator('[data-entity-hero] [data-venue-scope]')).toHaveCount(0)
    await expect(page.locator('[data-record-relations] [data-venue-scope]')).toHaveText(label)
    await noOverflow()
    await page
      .getByRole('button', { name: 'Globale Suche öffnen' })
      .filter({ visible: true })
      .click()
    const dialog = page.getByRole('dialog', { name: 'Kulturbytes durchsuchen' })
    const input = dialog.getByRole('combobox')
    await input.fill('Kühlhaus')
    await expect(dialog.getByRole('option').locator('[data-venue-scope]')).toHaveText(label)
    expect(requests.filter((path) => path.endsWith('/search'))).toHaveLength(1)
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await noOverflow()
    await input.press('Enter')
    await expect(dialog).not.toBeVisible()
    await expect(page).toHaveURL(`/venues/${venue.entity_key}`)
  })
}
