import { test, expect } from '../fixtures/authenticated'
import { entityFixture } from '../fixtures/entities'

for (const [status, badge, day] of [
  ['draft', 'Entwurf', '21.09.2026'],
  ['review', 'In Prüfung', '21.09.2026'],
  ['released', 'Veröffentlicht', '21.09.2026'],
] as const) {
  test(`events show the next ${status} date and preserve public-link boundaries`, async ({
    page,
  }) => {
    const fixture = entityFixture('events')
    const item = fixture.items[0]!
    const prefix = status === 'released' ? 'Nächster öffentlicher Termin' : 'Nächster Termin'
    const subtitle = `${prefix}: ${day} · 18:00 (Europe/Berlin)`
    const notice = 'Dieser noch unveröffentlichte Event findet schon in 3 Tagen statt.'
    const publicUrl = `https://kulturbytes.de/de/veranstaltung/${item.entity_key}/019954ea-0000-7000-8000-000000000001`
    await page.route('**/api/admin/api/v1/events?**', (route) => {
      const url = new URL(route.request().url())
      expect(url.searchParams.get('status')).toBe(status)
      expect(url.searchParams.get('period')).toBe('90d')
      expect(url.searchParams.get('temporal')).toBe('upcoming')
      expect(url.searchParams.get('page')).toBe('1')
      return route.fulfill({
        json: {
          ...fixture,
          observed_at: '2026-09-18T10:00:00Z',
          items: [
            {
              ...item,
              status,
              subtitle,
              notice: status === 'released' ? null : notice,
              public_url: status === 'released' ? publicUrl : null,
              facts: { ...item.facts, event_dates: 3 },
            },
          ],
          pagination: { page: 1, page_size: 25, total: 1, pages: 1 },
        },
      })
    })
    await page.goto(`/events?period=90d&status=${status}&temporal=upcoming&page=1`)
    const row = page
      .locator('li')
      .filter({ has: page.getByRole('heading', { name: item.entity_name }) })
    await expect(row.getByText(badge, { exact: true })).toBeVisible()
    await expect(row.getByText(subtitle, { exact: true })).toBeVisible()
    await expect(row.getByText(subtitle, { exact: true })).toHaveCount(1)
    await expect(row).toContainText(day)
    await expect(row).toContainText('18:00')
    await expect(row).toContainText('Termine: 3')
    await expect(row.locator('time')).toHaveAttribute('datetime', item.created_at!)
    const publicLink = row.getByRole('link', { name: /auf kulturbytes.de öffnen/ })
    if (status === 'released') {
      await expect(row.getByRole('status')).toHaveCount(0)
      await expect(row).not.toContainText(notice)
      await expect(publicLink).toBeVisible()
      await expect(publicLink).toHaveAttribute('href', publicUrl)
    } else {
      await expect(row.getByRole('status')).toHaveText(notice)
      await expect(row.getByRole('status')).toBeVisible()
      await expect(publicLink).toHaveCount(0)
      await expect(row).not.toContainText('öffentlicher Termin')
    }
  })
}
