import { test, expect } from '../fixtures/authenticated'
import type { Page } from '@playwright/test'
import { geoArea } from '../fixtures/geo'
import { activityFixture } from '../fixtures/activity'
import { findings, summary } from '../fixtures/api'
import { statisticsFixture } from '../fixtures/statistics'
import { eventContentFixture } from '../fixtures/event-content'
import { graphFixture } from '../fixtures/graph'
import { isSpatialType } from '../../app/utils/geo'

async function navigate(page: Page, label: string) {
  const mobile = page.getByRole('button', { name: 'Navigation öffnen' })
  if (await mobile.isVisible()) await mobile.click()
  await page
    .getByRole('navigation', { name: 'Hauptnavigation' })
    .getByRole('link', { name: label, exact: false })
    .click()
}

test('geo context spans analytics; global metrics and complete graph relationships stay explicit', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const seen = new Set<string>()
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace('/api/admin/api/v1/', '')
    const scoped = url.searchParams.get('geo_scope_id') === geoArea.id
    if (scoped) seen.add(path)
    if (path === 'dashboard/activity') {
      const data = structuredClone(activityFixture)
      data.items = scoped
        ? data.items.filter((item) => isSpatialType(item.entity_type)).slice(0, 5)
        : data.items
      data.pagination = { page: 1, page_size: 50, total: data.items.length, pages: 1 }
      return route.fulfill({ json: data })
    }
    if (path === 'findings') {
      const inside = {
        ...findings.items[0]!,
        id: 'inside',
        rule: 'venue_invalid_postal_code',
        field: 'postal_code',
        entity_name: 'Befund im Gebiet',
        message: 'Postleitzahl prüfen.',
      }
      const outside = { ...inside, id: 'outside', entity_name: 'Befund außerhalb' }
      const items = scoped ? [inside] : [inside, outside]
      return route.fulfill({
        json: {
          ...findings,
          items,
          pagination: { page: 1, page_size: 50, pages: 1, total: items.length },
        },
      })
    }
    if (path === 'dashboard/summary')
      return route.fulfill({
        json: {
          ...summary,
          period: url.searchParams.get('period') ?? '24h',
          geo_scope_id: scoped ? geoArea.id : null,
          scoped_new_records_total: scoped ? 5 : null,
          global_new_records_total: scoped ? 7 : null,
          new_record_scopes: {
            organizations: 'geo',
            venues: 'geo',
            spaces: 'geo',
            events: 'geo',
            event_dates: 'geo',
            users: 'global',
            images: 'global',
            team_memberships: 'global',
            partner_requests: 'global',
          },
        },
      })
    if (path === 'statistics/entities') {
      const data = statisticsFixture(url.searchParams)
      for (const series of data.series)
        series.scope = scoped && isSpatialType(series.entity_type) ? 'geo' : 'global'
      if (scoped) data.recent = data.recent.filter((item) => isSpatialType(item.entity_type))
      return route.fulfill({ json: data })
    }
    if (path === 'statistics/events/content') {
      const data = eventContentFixture(url.searchParams)
      if (scoped) data.categories.items[0]!.name = 'Kategorie im Gebiet'
      return route.fulfill({ json: data })
    }
    if (path === 'graph/search') {
      const inside = { ...graphFixture.nodes[0]!, label: 'Organisation im Gebiet' }
      const outside = { ...graphFixture.nodes[4]!, label: 'Root außerhalb' }
      return route.fulfill({ json: { items: scoped ? [inside] : [inside, outside] } })
    }
    if (path === 'graph') {
      expect(url.searchParams.has('geo_scope_id')).toBe(false)
      return route.fulfill({ json: graphFixture })
    }
    return route.continue()
  })
  await page.goto('/activity?period=7d')
  await page.getByRole('button', { name: /Gebiet: Alle/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Gebiet auswählen', exact: true })
  await dialog.getByRole('combobox').fill('Flensburg')
  await dialog.getByRole('option').getByRole('button').click()
  await expect(page).toHaveURL(new RegExp(`geo_scope_id=${geoArea.id}`))
  await expect(page.getByText(/Nicht räumlich zuordenbare Aktivität/)).toBeVisible()
  await expect(page.getByText('Testkonto', { exact: true })).toHaveCount(0)
  await expect(page.locator('select').first().locator('option[value="user"]')).toHaveCount(0)
  await navigate(page, 'Arbeitsliste')
  await expect(page.getByText('Befund im Gebiet', { exact: true })).toBeVisible()
  await expect(page.getByText('Befund außerhalb', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(page).toHaveURL(/geo_scope_id=/)
  await navigate(page, 'Statistiken')
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('period') === '7d' && url.searchParams.has('geo_scope_id'),
  )
  await expect(page.getByText(/Systemweite Kennzahlen sind gekennzeichnet/)).toBeVisible()
  await expect(
    page.locator('.statistics-metric').filter({ hasText: 'Systemweit' }).first(),
  ).toBeVisible()
  await expect(
    page.locator('.statistics-metric').filter({ hasText: 'Gebiet' }).first(),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Letzte 30 Tage', exact: true }).click()
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('period') === '30d' && url.searchParams.has('geo_scope_id'),
  )
  await page.getByRole('button', { name: 'Event-Inhalte', exact: true }).click()
  await expect(page.getByText('1. Kategorie im Gebiet', { exact: true }).first()).toBeVisible()
  await expect(page.getByText(/Rankings und Anteile beziehen sich/)).toBeVisible()
  await navigate(page, 'Beziehungsgraph')
  await page.getByLabel('Nach Name, E-Mail oder UUID suchen', { exact: true }).fill('Organisation')
  await expect(
    page.getByRole('button', { name: 'Organisation im Gebiet Organisation', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: /Root außerhalb/ })).toHaveCount(0)
  await expect(
    page.getByLabel('Entitätstypen', { exact: true }).locator('option[value="user"]'),
  ).toBeDisabled()
  await page
    .getByRole('button', { name: 'Organisation im Gebiet Organisation', exact: true })
    .click()
  await expect(page.locator('.graph-node')).toHaveCount(12)
  await expect(
    page.locator('.graph-node').filter({ hasText: 'St. Marien-Kirche Rendsburg' }),
  ).toBeVisible()
  await expect(page.getByText(/Der Graph zeigt vollständige Beziehungen/)).toBeVisible()
  await navigate(page, 'Übersicht')
  await expect(page.getByText(/Systemweit zusätzlich: 7/)).toBeVisible()
  await expect(page.getByText(/neue Datensätze im Gebiet/)).toBeVisible()
  await expect(page).not.toHaveURL(/[?&]page=/)
  await page.getByRole('button', { name: 'Gebiet zurücksetzen', exact: true }).click()
  await expect(page).not.toHaveURL(/geo_scope_id/)
  await navigate(page, 'Arbeitsliste')
  await expect(page.getByText('Befund außerhalb', { exact: true })).toBeVisible()
  expect([...seen]).toEqual(
    expect.arrayContaining([
      'dashboard/activity',
      'findings',
      'dashboard/summary',
      'statistics/entities',
      'statistics/events/content',
      'graph/search',
    ]),
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(errors).toEqual([])
})
