import { test, expect } from '@playwright/test'
import { entityFixture, detailFixture } from '../fixtures/entities'
import { entitySectionSchema } from '../../shared/contracts'
for (const section of entitySectionSchema.options) {
  test(`${section} list, detail and workflow links`, async ({ page }) => {
    const fixture = entityFixture(section)
    await page.route('**/api/admin/api/v1/**', (route) => {
      const path = new URL(route.request().url()).pathname
      return route.fulfill({
        json: path.includes(`/${section}/`) ? detailFixture(section) : fixture,
      })
    })
    await page.goto(`/${section}`)
    await expect(page.getByText(`Fixture ${section}`, { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: /\+ Datensatz/ })).toBeDisabled()
    await page
      .getByRole('link', { name: `Im Admin ansehen: Fixture ${section}`, exact: true })
      .click()
    await expect(page).toHaveURL(new RegExp(`/${section}/${fixture.items[0]!.entity_key}`))
    await expect(
      page.getByRole('heading', { level: 2, name: `Fixture ${section}`, exact: true }),
    ).toHaveText(`Fixture ${section}`)
    await expect(page.getByRole('link', { name: 'Befunde zu diesem Datensatz' })).toHaveAttribute(
      'href',
      /entity_key=/,
    )
    await expect(
      page.getByRole('link', { name: `Markierungen & Notizen zu Fixture ${section}` }),
    ).toBeVisible()
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
      await expect(page.getByRole('link', { name: 'Beziehungen anzeigen' })).toHaveAttribute(
        'href',
        /root_key=/,
      )
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
  })
}
