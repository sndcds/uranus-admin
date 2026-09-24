import { test, expect, expectCreateUnavailable } from '../fixtures/authenticated'
import { entityFixture, detailFixture, timelineFixture } from '../fixtures/entities'
import { entitySections } from '../../app/utils/entities'
import { entitySectionSchema } from '../../shared/contracts'
for (const section of entitySectionSchema.options) {
  test(`${section} list, detail and workflow links`, async ({ page }) => {
    const fixture = entityFixture(section)
    await page.route('**/api/admin/api/v1/**', (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/timeline'))
        return route.fulfill({ json: timelineFixture(entitySections[section].type) })
      return route.fulfill({
        json: path.includes(`/${section}/`) ? detailFixture(section) : fixture,
      })
    })
    await page.goto(`/${section}`)
    await expect(page.getByText(`Fixture ${section}`, { exact: true })).toBeVisible()
    await expectCreateUnavailable(page)
    await page.getByRole('link', { name: `Öffnen: Fixture ${section}`, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/${section}/${fixture.items[0]!.entity_key}`))
    await expect(
      page.getByRole('heading', { level: 2, name: `Fixture ${section}`, exact: true }),
    ).toHaveText(`Fixture ${section}`)
    await expect(
      page.getByRole('link', {
        name: 'Befunde öffnen',
      }),
    ).toHaveAttribute('href', /entity_key=/)
    await expect(
      page.getByRole('link', { name: `Markierungen & Notizen zu Fixture ${section}` }),
    ).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Verlauf' })).toBeVisible()
    await expect(page.getByText('Beschreibung fehlt.')).toBeVisible()
    if (section === 'events') {
      await expect(page.getByText('Standardort', { exact: true })).toBeVisible()
      await expect(page.getByText('Standardraum', { exact: true })).toBeVisible()
    }
    if (section === 'users') {
      await expect(
        page.getByText('Eingeladen: 02.02.2026 13:00 (Europe/Berlin)', { exact: true }),
      ).toBeVisible()
      await expect(page.locator('time[datetime="2026-01-01T00:00:00Z"]')).toHaveAttribute(
        'aria-label',
        /Erstellt am 01.01.2026/,
      )
      await expect(page.getByText('Eingeladen', { exact: true })).toBeVisible()
    }
    if (section !== 'images')
      await expect(
        page.getByRole('link', {
          name: 'Beziehungen',
        }),
      ).toHaveAttribute('href', /root_key=/)
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    await page.getByRole('link', { name: 'Details öffnen: Qualitätsproblem erkannt' }).click()
    await expect(page).toHaveURL(/\/findings\?.*entity_key=/)
  })
}

for (const section of entitySectionSchema.options) {
  test(`${section} contextual autocomplete, apply and URL pagination`, async ({ page }) => {
    const fixture = entityFixture(section)
    const item = fixture.items[0]!
    const label = section === 'users' ? 'Max Mustermann' : `Search ${section}`
    const subtitle = section === 'users' ? '@max · max@example.org' : 'Flensburg'
    const requests: URL[] = []
    await page.route('**/api/admin/api/v1/**', (route) => {
      const url = new URL(route.request().url())
      requests.push(url)
      if (url.pathname.endsWith('/entity-search')) {
        expect(url.searchParams.get('entity_type')).toBe(item.entity_type)
        return route.fulfill({
          json: {
            items: [
              {
                entity_type: item.entity_type,
                entity_key: item.entity_key,
                label,
                subtitle,
                status: item.status,
                action: item.action,
              },
            ],
          },
        })
      }
      if (url.pathname.includes(`/${section}/`))
        return route.fulfill({ json: detailFixture(section) })
      return route.fulfill({
        json: {
          ...fixture,
          items: [
            {
              ...item,
              entity_name: url.searchParams.has('q') ? 'Filtered result' : item.entity_name,
            },
          ],
          pagination: { ...fixture.pagination, page: Number(url.searchParams.get('page') || 1) },
        },
      })
    })
    await page.goto(`/${section}`)
    await expect(page.getByText(`Fixture ${section}`, { exact: true })).toBeVisible()
    const search = page.getByRole('combobox', { name: 'Suche', exact: true })
    await search.fill('max')
    const option = page.getByRole('option', { name: new RegExp(label) })
    await expect(option).toBeVisible()
    await expect(option).toContainText(subtitle)
    await expect(page).toHaveURL(new RegExp(`/${section}$`))
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await option.click()
    await expect(page).toHaveURL(new RegExp(`/${section}/${item.entity_key}$`))
    await page.goto(`/${section}?page=2`)
    await expect(search).toBeVisible()
    await expect(page.getByText('Seite 2 von 2', { exact: false })).toBeVisible()
    await search.fill('max@example.org')
    await expect(option).toBeVisible()
    await search.press('Enter')
    await expect(page).toHaveURL(
      (url) =>
        url.pathname === `/${section}` &&
        url.searchParams.get('q') === 'max@example.org' &&
        url.searchParams.get('page') === '1',
    )
    await expect(page.getByText('Filtered result', { exact: true })).toBeVisible()
    await page.getByRole('link', { name: 'Weiter' }).click()
    await expect(page).toHaveURL(
      (url) =>
        url.searchParams.get('q') === 'max@example.org' && url.searchParams.get('page') === '2',
    )
    await expect(search).toHaveValue('max@example.org')
    await page.reload()
    await expect(search).toHaveValue('max@example.org')
    expect(
      requests.some(
        (url) =>
          url.pathname.endsWith(`/${section}`) &&
          url.searchParams.get('q') === 'max@example.org' &&
          url.searchParams.get('page') === '2',
      ),
    ).toBe(true)
  })
}

test('email-only user titles in list, autocomplete, detail and memberships', async ({ page }) => {
  const email = 'no-name@example.org'
  const fixture = entityFixture('users')
  const item = { ...fixture.items[0]!, entity_name: email, email }
  item.facts = { ...item.facts, username: null }
  const detail = detailFixture('users')
  await page.route('**/api/admin/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/timeline')) return route.fulfill({ json: timelineFixture('user') })
    if (path.endsWith('/entity-search'))
      return route.fulfill({
        json: {
          items: [
            {
              entity_type: 'user',
              entity_key: item.entity_key,
              label: email,
              subtitle: null,
              status: item.status,
              action: item.action,
            },
          ],
        },
      })
    if (path.includes('/users/'))
      return route.fulfill({
        json: {
          ...detail,
          item,
          related: {
            ...detail.related,
            items: detail.related.items.map((related) => ({ ...related, entity_name: email })),
          },
        },
      })
    return route.fulfill({ json: { ...fixture, items: [item] } })
  })
  await page.goto('/users')
  await expect(page.getByRole('heading', { level: 3, name: email, exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: 'Suche', exact: true }).fill(email)
  const option = page.getByRole('option', { name: `${email} Benutzer`, exact: true })
  await expect(option.locator('.font-medium')).toHaveText(email)
  await option.click()
  await expect(page.getByRole('heading', { level: 2, name: email, exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { level: 3, name: email, exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 4, name: email, exact: true })).toHaveCount(1)
  await expect(page.locator('[data-entity-hero]').getByText(email, { exact: true })).toHaveCount(1)
  await expect(page.getByText(item.entity_key, { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: item.entity_key, exact: true })).toHaveCount(0)
})
