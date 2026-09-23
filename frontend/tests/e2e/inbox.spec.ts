import { test, expect } from '../fixtures/authenticated'
import { unassignedFindingInboxFixture } from '../fixtures/inbox'
import { findings } from '../fixtures/api'

test('unassigned event-date findings render and link to the matching finding filter', async ({
  page,
}) => {
  await page.route('**/api/admin/api/v1/inbox?*', (route) =>
    route.fulfill({ json: unassignedFindingInboxFixture }),
  )
  await page.route('**/api/admin/api/v1/findings?*', (route) =>
    route.fulfill({
      json: { ...findings, items: [], pagination: { page: 1, page_size: 50, total: 0, pages: 0 } },
    }),
  )
  await page.goto('/inbox')
  await expect(page.getByRole('heading', { name: 'Testtermin' })).toBeVisible()
  await expect(page.getByText('Das Enddatum liegt vor dem Startdatum.')).toBeVisible()
  await expect(page.getByText('Abruf fehlgeschlagen')).toHaveCount(0)
  const link = page.getByRole('link', { name: 'Befund ansehen' })
  await expect(link).toHaveAttribute('href', unassignedFindingInboxFixture.items[0]!.href)
  await link.click()
  await expect(page).toHaveURL(/\/findings\?entity_key=.*&rule=event_date_end_before_start$/)
})
