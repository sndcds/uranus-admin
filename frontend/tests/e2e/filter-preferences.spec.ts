import { test, expect } from '../fixtures/authenticated'
import type { Page } from '@playwright/test'
import { entityFixture } from '../fixtures/entities'
import { entitySectionSchema } from '../../shared/contracts'
import { summary, findings } from '../fixtures/api'
import { activityFixture } from '../fixtures/activity'
import { statisticsFixture } from '../fixtures/statistics'

async function navigate(page: Page, label: string) {
  const menu = page.getByRole('button', { name: 'Navigation öffnen' })
  if (await menu.isVisible()) {
    await menu.click()
    await page
      .getByRole('dialog', { name: 'Mobile Navigation' })
      .getByRole('link', { name: label, exact: true })
      .click()
  } else
    await page
      .getByRole('navigation', { name: 'Hauptnavigation' })
      .getByRole('link', { name: label, exact: true })
      .click()
}
test.beforeEach(async ({ page }) => {
  await page.route('**/api/admin/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    const section = entitySectionSchema.safeParse(url.pathname.split('/').at(-1))
    if (section.success) return route.fulfill({ json: entityFixture(section.data) })
    if (url.pathname.endsWith('/summary'))
      return route.fulfill({
        json: { ...summary, period: url.searchParams.get('period') ?? '24h' },
      })
    if (url.pathname.endsWith('/statistics/entities'))
      return route.fulfill({ json: statisticsFixture(url.searchParams) })
    if (url.pathname.endsWith('/activity')) return route.fulfill({ json: activityFixture })
    if (url.pathname.endsWith('/entity-search')) return route.fulfill({ json: { items: [] } })
    return route.fulfill({ json: findings })
  })
})
test('entity memory, URL priority, history and scoped reset survive SPA navigation', async ({
  page,
}) => {
  await page.goto('/events')
  const status = page.getByRole('combobox', { name: 'Status', exact: true })
  const temporal = page.getByRole('combobox', { name: 'Terminlage', exact: true })
  await expect(page.getByText('Fixture events', { exact: true })).toBeVisible()
  await status.selectOption('released')
  await temporal.selectOption('upcoming')
  await expect(page).toHaveURL(/status=released/)
  await navigate(page, 'Benutzer & Teams')
  await expect(page.getByText('Fixture users', { exact: true })).toBeVisible()
  await status.selectOption('active')
  await page.getByRole('combobox', { name: 'Suche', exact: true }).fill('max@example.org')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/status=active/)
  await navigate(page, 'Veranstaltungen')
  await expect(status).toHaveValue('released')
  await expect(temporal).toHaveValue('upcoming')
  await expect(page).toHaveURL(/temporal=upcoming/)
  await status.selectOption('draft')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/status=draft/)
  await page.goBack()
  await expect(status).toHaveValue('released')
  await page.goForward()
  await expect(status).toHaveValue('draft')
  await navigate(page, 'Benutzer & Teams')
  await navigate(page, 'Veranstaltungen')
  await expect(status).toHaveValue('draft')
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(status).toHaveValue('')
  await expect(temporal).toHaveValue('')
  await navigate(page, 'Benutzer & Teams')
  await expect(status).toHaveValue('active')
  await expect(page.getByRole('combobox', { name: 'Suche', exact: true })).toHaveValue(
    'max@example.org',
  )
  expect(
    await page.evaluate(() =>
      JSON.stringify({
        local: { ...localStorage },
        session: { ...sessionStorage },
        cookies: document.cookie,
      }),
    ),
  ).not.toContain('max@example.org')
  await page.reload()
  await expect(status).toHaveValue('active')
  await navigate(page, 'Veranstaltungen')
  await expect(status).toHaveValue('')
})
test('shared periods cross pages, preserve unsupported preferences and keep custom local', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (/hydration/i.test(message.text())) errors.push(message.text())
  })
  await page.goto('/')
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  await page.getByLabel('Zeitraum', { exact: true }).selectOption('7d')
  await expect(page).toHaveURL(/period=7d/)
  await navigate(page, 'Aktivität')
  await expect(page.getByRole('combobox', { name: 'Zeitraum', exact: true })).toHaveValue('7d')
  await navigate(page, 'Statistiken')
  await expect(page.getByRole('button', { name: 'Letzte 7 Tage', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: 'Letzte 90 Tage', exact: true }).click()
  await expect(page).toHaveURL(/period=90d/)
  await page.getByRole('switch').check()
  await page.getByRole('combobox', { name: 'Intervall', exact: true }).selectOption('1d')
  await expect(page).toHaveURL(/interval=1d/)
  await navigate(page, 'Übersicht')
  await expect(page.getByLabel('Zeitraum', { exact: true })).toHaveValue('24h')
  await navigate(page, 'Statistiken')
  await expect(page.getByRole('button', { name: 'Letzte 90 Tage', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByRole('switch')).toBeChecked()
  await expect(page.getByRole('combobox', { name: 'Intervall', exact: true })).toHaveValue('1d')
  await navigate(page, 'Aktivität')
  await page.getByRole('combobox', { name: 'Zeitraum', exact: true }).selectOption('unknown')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/timestamp_state=unknown/)
  await navigate(page, 'Statistiken')
  await expect(page.getByRole('button', { name: 'Letzte 90 Tage', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  expect(errors).toEqual([])
})
