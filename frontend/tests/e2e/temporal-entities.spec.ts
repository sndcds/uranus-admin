import { test, expect } from '../fixtures/authenticated'
import { entityFixture } from '../fixtures/entities'

for (const section of ['events', 'organizations', 'venues', 'spaces'] as const) {
  test(`${section} temporal filtering applies to list, autocomplete and history`, async ({
    page,
  }) => {
    const fixture = entityFixture(section),
      item = fixture.items[0]!
    const org = item.entity_key
    const requests: URL[] = []
    await page.route('**/api/admin/api/v1/**', (route) => {
      const url = new URL(route.request().url())
      requests.push(url)
      const temporal = url.searchParams.get('temporal')
      const label =
        temporal === 'upcoming'
          ? 'Upcoming fixture'
          : temporal === 'past'
            ? 'Past fixture'
            : 'All fixtures'
      if (url.pathname.endsWith('/entity-search'))
        return route.fulfill({
          json: {
            items: [
              {
                entity_type: item.entity_type,
                entity_key: item.entity_key,
                label,
                subtitle: null,
                status: item.status,
                action: item.action,
              },
            ],
          },
        })
      return route.fulfill({
        json: {
          ...fixture,
          items: [{ ...item, entity_name: label }],
          pagination: { ...fixture.pagination, page: Number(url.searchParams.get('page') || 1) },
        },
      })
    })
    await page.goto(`/${section}?organization_id=${org}&page=2`)
    await expect(page.getByText('All fixtures', { exact: true })).toBeVisible()
    await expect(page.getByLabel('Organisation UUID', { exact: true })).toHaveCount(0)
    const temporal = page.getByRole('combobox', { name: 'Zeitraum', exact: true })
    await temporal.selectOption({ label: 'Mit bevorstehenden Terminen' })
    await expect(page).toHaveURL(
      (url) =>
        url.searchParams.get('temporal') === 'upcoming' &&
        url.searchParams.get('page') === '1' &&
        url.searchParams.get('organization_id') === org,
    )
    await expect(page.getByText('Upcoming fixture', { exact: true })).toBeVisible()
    await expect(page.getByText('Zeitraum: Mit bevorstehenden Terminen')).toBeVisible()
    const search = page.getByRole('combobox', { name: 'Suche', exact: true })
    await search.fill('hacks')
    await expect(page.getByRole('option', { name: /Upcoming fixture/ })).toBeVisible()
    expect(
      requests.some(
        (url) =>
          url.pathname.endsWith('/entity-search') &&
          url.searchParams.get('temporal') === 'upcoming' &&
          url.searchParams.get('organization_id') === org,
      ),
    ).toBe(true)
    await search.press('Enter')
    await expect(page).toHaveURL(
      (url) =>
        url.searchParams.get('q') === 'hacks' &&
        url.searchParams.get('temporal') === 'upcoming' &&
        url.searchParams.get('page') === '1',
    )
    await page.getByRole('link', { name: 'Weiter', exact: true }).click()
    await expect(page).toHaveURL(
      (url) =>
        url.searchParams.get('page') === '2' &&
        url.searchParams.get('q') === 'hacks' &&
        url.searchParams.get('temporal') === 'upcoming',
    )
    await page.reload()
    await expect(temporal).toHaveValue('upcoming')
    await expect(search).toHaveValue('hacks')
    await temporal.selectOption({ label: 'Mit vergangenen Terminen' })
    await expect(page.getByText('Past fixture', { exact: true })).toBeVisible()
    await expect(page).toHaveURL(
      (url) => url.searchParams.get('page') === '1' && url.searchParams.get('temporal') === 'past',
    )
    await page.goBack()
    await expect(temporal).toHaveValue('upcoming')
    await page.goForward()
    await expect(temporal).toHaveValue('past')
    await search.focus()
    await expect(page.getByRole('option', { name: /Past fixture/ })).toBeVisible()
    await search.press('Escape')
    await temporal.selectOption({ label: 'Alle' })
    await expect(page).toHaveURL(
      (url) => !url.searchParams.has('temporal') && url.searchParams.get('organization_id') === org,
    )
    await expect(page.getByText('All fixtures', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

for (const section of ['users', 'images'] as const) {
  test(`${section} has no temporal or organization UUID input`, async ({ page }) => {
    await page.route('**/api/admin/api/v1/**', (route) =>
      route.fulfill({ json: entityFixture(section) }),
    )
    await page.goto(`/${section}`)
    await expect(page.getByText(`Fixture ${section}`, { exact: true })).toBeVisible()
    await expect(page.getByRole('combobox', { name: 'Suche', exact: true })).toBeVisible()
    await expect(page.getByRole('combobox', { name: 'Zeitraum', exact: true })).toHaveCount(0)
    await expect(page.getByLabel('Organisation UUID', { exact: true })).toHaveCount(0)
  })
}
