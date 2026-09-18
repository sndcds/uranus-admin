import { test, expect } from '../fixtures/authenticated'
import type { Page } from '@playwright/test'
import { geoArea } from '../fixtures/geo'
import { entityFixture } from '../fixtures/entities'
import { entitySectionSchema } from '../../shared/contracts'
import { statisticsFixture } from '../fixtures/statistics'
import { eventContentFixture } from '../fixtures/event-content'

async function navigate(page: Page, label: string, path: string) {
  await expect(page.getByRole('button', { name: 'Abmelden', exact: true })).toBeEnabled()
  const menu = page.getByRole('button', { name: 'Navigation öffnen' })
  const mobile = await menu.isVisible()
  if (mobile) await menu.click()
  const navigation = mobile
    ? page.getByRole('dialog', { name: 'Mobile Navigation' })
    : page.getByRole('navigation', { name: 'Hauptnavigation' })
  await navigation.getByRole('link', { name: label, exact: true }).click()
  await expect(page).toHaveURL((url) => url.pathname === path)
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.includes('/geo/areas')) return route.continue()
    const section = entitySectionSchema.safeParse(url.pathname.split('/').at(-1))
    if (section.success) {
      const data = entityFixture(section.data)
      const scoped = url.searchParams.has('geo_scope_id')
      data.items[0]!.entity_name = scoped ? 'Im Gebiet Flensburg' : 'Alle Gebiete'
      data.pagination.total = scoped ? 1 : 26
      return route.fulfill({ json: data })
    }
    if (url.pathname.endsWith('/entity-search')) return route.fulfill({ json: { items: [] } })
    if (url.pathname.endsWith('/statistics/entities'))
      return route.fulfill({ json: statisticsFixture(url.searchParams) })
    if (url.pathname.endsWith('/statistics/events/content'))
      return route.fulfill({ json: eventContentFixture() })
    return route.continue()
  })
})

test('global selection, scoped search, local reset, period, navigation, reload and clear', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/events?period=90d')
  await expect(page.getByText('Alle Gebiete', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /Gebiet: Alle/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Gebiet auswählen', exact: true })
  await dialog.getByRole('combobox', { name: 'Administratives Gebiet suchen' }).fill('Flensburg')
  await dialog.getByRole('option').getByRole('button').click()
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('geo_scope_id') === geoArea.id &&
      url.searchParams.get('period') === '90d',
  )
  await expect(page.getByText('Im Gebiet Flensburg', { exact: true })).toBeVisible()
  const search = page.waitForRequest(
    (request) =>
      request.url().includes('/entity-search') &&
      new URL(request.url()).searchParams.get('geo_scope_id') === geoArea.id,
  )
  await page.getByRole('combobox', { name: 'Suche', exact: true }).fill('Konzert')
  await search
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('geo_scope_id') === geoArea.id && !url.searchParams.has('q'),
  )
  await page.getByRole('combobox', { name: 'Erstellt', exact: true }).selectOption('90d')
  await navigate(page, 'Orte & Räume', '/venues')
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('geo_scope_id') === geoArea.id &&
      url.searchParams.get('period') === '90d',
  )
  await expect(page.getByText('Im Gebiet Flensburg', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('Im Gebiet Flensburg', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /Gebiet: Flensburg/ })).toBeVisible()
  await navigate(page, 'Statistiken', '/statistics')
  await expect(page.getByText(/Diese Ansicht ist nicht räumlich eingeschränkt/)).toBeVisible()
  await expect(page).not.toHaveURL(/geo_scope_id/)
  await navigate(page, 'Orte & Räume', '/venues')
  await page.getByRole('combobox', { name: 'Erstellt', exact: true }).selectOption('30d')
  await expect(page).toHaveURL(/geo_scope_id=/)
  await page.getByRole('button', { name: 'Gebiet zurücksetzen', exact: true }).click()
  await expect(page).toHaveURL(
    (url) => !url.searchParams.has('geo_scope_id') && url.searchParams.get('period') === '30d',
  )
  await expect(page.getByText('Alle Gebiete', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  expect(errors).toEqual([])
})

test('logout resets scope, direct URL login restores only the explicit URL', async ({ page }) => {
  await page.goto(`/events?geo_scope_id=${geoArea.id}`)
  await expect(page.getByRole('button', { name: /Gebiet: Flensburg/ })).toBeVisible()
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.getByLabel('Benutzername', { exact: true }).fill('operator')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await navigate(page, 'Veranstaltungen', '/events')
  await expect(page.getByRole('button', { name: /Gebiet: Alle/ })).toBeVisible()
  await expect(page).not.toHaveURL(/geo_scope_id/)
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await page.goto(`/events?geo_scope_id=${geoArea.id}`)
  await expect(page.getByRole('heading', { name: 'Veranstaltungen', exact: true })).toHaveCount(0)
  await page.getByLabel('Benutzername', { exact: true }).fill('operator')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`geo_scope_id=${geoArea.id}`))
  await expect(page.getByRole('button', { name: /Gebiet: Flensburg/ })).toBeVisible()
})

test('unknown scope is removed with a safe warning and provider failure preserves cached scope', async ({
  page,
}) => {
  await page.goto('/venues?geo_scope_id=10000000-0000-4000-8000-000000000099&period=90d')
  await expect(page.getByRole('alert')).toContainText('Gebiet ist nicht verfügbar')
  await expect(page).toHaveURL(
    (url) => !url.searchParams.has('geo_scope_id') && url.searchParams.get('period') === '90d',
  )
  await page.goto(`/venues?geo_scope_id=${geoArea.id}`)
  await page.route('**/api/admin/api/v1/geo/areas/search?*', (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: 'geo_provider_unavailable', message: 'Unavailable' } },
    }),
  )
  await page.getByRole('button', { name: /Gebiet: Flensburg/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Gebiet auswählen', exact: true })
  await dialog.getByRole('combobox').fill('Aarhus')
  await expect(dialog.getByRole('alert')).toContainText('Gespeicherte Gebiete bleiben nutzbar')
  await dialog.getByRole('combobox').press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText('Im Gebiet Flensburg', { exact: true })).toBeVisible()
})
