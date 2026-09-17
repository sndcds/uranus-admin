import { test, expect } from '@playwright/test'
import { summary, findings } from '../fixtures/api'
import { activityFixture } from '../fixtures/activity'
import { statisticsFixture } from '../fixtures/statistics'
import { graphFixture, graphPath } from '../fixtures/graph'
import { entityFixture, detailFixture } from '../fixtures/entities'
import { entitySectionSchema } from '../../shared/contracts'

const sections = entitySectionSchema.options
const routes = [
  '/',
  '/activity',
  '/findings',
  '/checks',
  '/quality',
  graphPath,
  '/statistics',
  ...sections.flatMap((section) => [
    `/${section}`,
    `/${section}/${entityFixture(section).items[0]!.entity_key}`,
  ]),
]
const labels: Record<string, string> = {
  '/': 'Übersicht',
  activity: 'Aktivität',
  findings: 'Arbeitsliste',
  checks: 'Prüfläufe',
  quality: 'Datenqualität',
  graph: 'Beziehungsgraph',
  statistics: 'Statistiken',
  events: 'Veranstaltungen',
  venues: 'Orte & Räume',
  spaces: 'Orte & Räume',
  organizations: 'Organisationen',
  users: 'Benutzer & Teams',
  images: 'Bilder',
}
for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
]) {
  test(`shared shell and page review at ${viewport.width}px`, async ({ page }, info) => {
    test.setTimeout(120000) // Nineteen pages in one viewport audit, not a longer interaction timeout.
    await page.setViewportSize(viewport)
    await page.route('**/api/admin/auth/session', (route) =>
      route.fulfill({ json: { subject: 'admin:layout-fixture', system_admin: true } }),
    )
    await page.route('https://api.kulturbytes.de/**', (route) =>
      route.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="#e2e8f0"/></svg>',
      }),
    )
    await page.route('**/api/admin/api/v1/**', (route) => {
      const url = new URL(route.request().url())
      const section = sections.find((section) => url.pathname.includes(`/api/v1/${section}`))
      if (section)
        return route.fulfill({
          json: url.pathname.endsWith(section) ? entityFixture(section) : detailFixture(section),
        })
      if (url.pathname.endsWith('/summary')) return route.fulfill({ json: summary })
      if (url.pathname.includes('/statistics/'))
        return route.fulfill({ json: statisticsFixture(url.searchParams) })
      if (url.pathname.endsWith('/activity')) return route.fulfill({ json: activityFixture })
      if (url.pathname.endsWith('/graph')) return route.fulfill({ json: graphFixture })
      if (url.pathname.endsWith('/check-runs'))
        return route.fulfill({
          json: { items: [], pagination: { page: 1, page_size: 50, total: 0, pages: 0 } },
        })
      return route.fulfill({ json: findings })
    })
    let shell: { x: number; width: number; height: number } | undefined
    for (const [index, path] of routes.entries()) {
      await page.goto(path)
      await expect(page.getByRole('button', { name: 'Abmelden', exact: true })).toBeVisible()
      await expect(page.locator('main h2').last()).toBeVisible()
      await expect(
        page.locator('main').getByText('Daten werden geladen …', { exact: true }),
      ).toHaveCount(0)
      const dimensions = await page.evaluate(() => {
        const main = document.querySelector('main')!.getBoundingClientRect()
        const header = document.querySelector('div.min-h-screen > header')!.getBoundingClientRect()
        return { x: main.x, width: main.width, height: header.height }
      })
      if (!shell) shell = dimensions
      expect(dimensions).toEqual(shell)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      const label = labels[path === '/' ? '/' : path.split('/')[1]!.split('?')[0]!]!
      if (viewport.width < 1024)
        await page.getByRole('button', { name: 'Navigation öffnen' }).click()
      const nav = page
        .getByRole('navigation', { name: 'Hauptnavigation' })
        .filter({ visible: true })
      await expect(nav.getByRole('link', { name: label, exact: true })).toHaveAttribute(
        'aria-current',
        'page',
      )
      if (viewport.width >= 1024)
        expect(
          await page
            .locator('aside')
            .filter({ has: page.getByRole('navigation', { name: 'Hauptnavigation' }) })
            .evaluate((el) => el.getBoundingClientRect().width),
        ).toBe(256)
      else {
        if (index === 0)
          await page.screenshot({ path: info.outputPath(`navigation-${viewport.width}.png`) })
        await page.getByRole('button', { name: 'Navigation schließen' }).click()
        await expect(page.getByRole('button', { name: 'Navigation öffnen' })).toBeFocused()
      }
      await page.screenshot({
        path: info.outputPath(
          `${index}-${path.split('?')[0]!.replaceAll('/', '_') || 'dashboard'}-${viewport.width}.png`,
        ),
        fullPage: true,
      })
    }
  })
}
