import { test, expect } from '../fixtures/authenticated'
import type { Page } from '@playwright/test'
import { entityFixture } from '../fixtures/entities'
import { entitySectionSchema } from '../../shared/contracts'

async function navigate(page: Page, label: string) {
  const menu = page.getByRole('button', { name: 'Navigation öffnen' })
  if (await menu.isVisible()) {
    await menu.click()
    await page
      .getByRole('dialog', { name: 'Mobile Navigation' })
      .getByRole('link', { name: label, exact: true })
      .click()
  } else {
    await page
      .getByRole('navigation', { name: 'Hauptnavigation' })
      .getByRole('link', { name: label, exact: true })
      .click()
  }
}

test('created period combines with Terminlage, status, search, pagination and history', async ({
  page,
}) => {
  const fixture = entityFixture('events'),
    item = fixture.items[0]!
  const requests: URL[] = []
  await page.route('**/api/admin/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    requests.push(url)
    const selected =
      url.searchParams.get('period') === '7d' &&
      url.searchParams.get('temporal') === 'upcoming' &&
      url.searchParams.get('status') === 'released'
    const label = selected ? 'Recent released future event' : 'Unfiltered event'
    if (url.pathname.endsWith('/entity-search'))
      return route.fulfill({
        json: {
          items: [
            {
              entity_type: 'event',
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
  await page.goto('/events')
  await expect(page.getByText('Unfiltered event', { exact: true })).toBeVisible()
  const created = page.getByRole('combobox', { name: 'Erstellt', exact: true })
  await expect(created).toHaveValue('')
  await created.selectOption('7d')
  // Period changes apply immediately and reload the form from the committed URL.
  // Wait for that result before editing the next, not-yet-applied filter.
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('period') === '7d' && url.searchParams.get('page') === '1',
  )
  await expect(page.getByRole('region', { name: 'Ergebnisübersicht' })).toContainText(
    'Erstellt: Letzte 7 Tage',
  )
  await page.getByRole('combobox', { name: 'Status', exact: true }).selectOption('released')
  await page.getByRole('combobox', { name: 'Terminlage', exact: true }).selectOption('upcoming')
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('period') === '7d' &&
      url.searchParams.get('status') === 'released' &&
      url.searchParams.get('temporal') === 'upcoming',
  )
  await expect(page.getByText('Recent released future event', { exact: true })).toBeVisible()
  const search = page.getByRole('combobox', { name: 'Suche', exact: true })
  await search.fill('recent')
  await expect(page.getByRole('option', { name: /Recent released future event/ })).toBeVisible()
  expect(
    requests.some(
      (url) =>
        url.pathname.endsWith('/entity-search') &&
        url.searchParams.get('period') === '7d' &&
        url.searchParams.get('temporal') === 'upcoming' &&
        url.searchParams.get('status') === 'released' &&
        url.searchParams.get('q') === 'recent',
    ),
  ).toBe(true)
  await search.press('Enter')
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('q') === 'recent' &&
      url.searchParams.get('period') === '7d' &&
      url.searchParams.get('temporal') === 'upcoming' &&
      url.searchParams.get('status') === 'released' &&
      url.searchParams.get('page') === '1',
  )
  await page.getByRole('link', { name: 'Weiter', exact: true }).click()
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('page') === '2' &&
      url.searchParams.get('period') === '7d' &&
      url.searchParams.get('q') === 'recent' &&
      url.searchParams.get('status') === 'released' &&
      url.searchParams.get('temporal') === 'upcoming',
  )
  await page.reload()
  await expect(created).toHaveValue('7d')
  await expect(page.getByText('Recent released future event', { exact: true })).toBeVisible()
  await created.selectOption('30d')
  await expect(page).toHaveURL(/period=30d/)
  await page.goBack()
  await expect(created).toHaveValue('7d')
  await page.goForward()
  await expect(created).toHaveValue('30d')
  await created.selectOption('')
  await expect(page).toHaveURL(
    (url) => !url.searchParams.has('period') && url.searchParams.get('temporal') === 'upcoming',
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('entity periods inherit conscious shared choices and preserve their own selection or All', async ({
  page,
}) => {
  await page.route('**/api/admin/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    const section = entitySectionSchema.safeParse(url.pathname.split('/').at(-1))
    return route.fulfill({ json: section.success ? entityFixture(section.data) : { items: [] } })
  })
  const created = page.getByRole('combobox', { name: 'Erstellt', exact: true })
  await page.goto('/events')
  await expect(page.getByText('Fixture events', { exact: true })).toBeVisible()
  await expect(created).toHaveValue('')
  await created.selectOption('7d')
  await expect(page).toHaveURL(/period=7d/)
  await navigate(page, 'Orte & Räume')
  await expect(page.getByText('Fixture venues', { exact: true })).toBeVisible()
  await expect(created).toHaveValue('7d')
  await created.selectOption('30d')
  await expect(page).toHaveURL(/period=30d/)
  await navigate(page, 'Veranstaltungen')
  await expect(created).toHaveValue('7d')
  await expect(page).toHaveURL(/period=7d/)
  await navigate(page, 'Bilder')
  await expect(page.getByText('Fixture images', { exact: true })).toBeVisible()
  await expect(created).toHaveValue('30d')
  await expect(page.getByRole('combobox', { name: 'Terminlage', exact: true })).toHaveCount(0)
  await created.selectOption('')
  await expect(page).toHaveURL((url) => !url.searchParams.has('period'))
  await navigate(page, 'Veranstaltungen')
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(created).toHaveValue('')
  await navigate(page, 'Orte & Räume')
  await expect(created).toHaveValue('30d')
  await navigate(page, 'Bilder')
  await expect(created).toHaveValue('')
  await navigate(page, 'Organisationen')
  await expect(page.getByText('Fixture organizations', { exact: true })).toBeVisible()
  await expect(created).toHaveValue('30d')
})
