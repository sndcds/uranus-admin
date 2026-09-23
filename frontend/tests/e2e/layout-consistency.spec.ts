import { test, expect } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'
import { activityFixture } from '../fixtures/activity'
import { statisticsFixture } from '../fixtures/statistics'
import { graphFixture, graphPath } from '../fixtures/graph'
import { entityFixture, detailFixture } from '../fixtures/entities'
import { inboxFixture } from '../fixtures/inbox'
import { geocodeDetail } from '../fixtures/geocoding'
import { entitySectionSchema } from '../../shared/contracts'

const sections = entitySectionSchema.options
const routes = [
  '/',
  '/activity',
  '/inbox',
  '/findings',
  '/checks',
  '/quality',
  `/geocoding/${geocodeDetail.id}`,
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
  inbox: 'Inbox',
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
const mobileScreenshotNames: Record<string, string> = {
  '/': 'dashboard-mobile.png',
  '/activity': 'activity-mobile.png',
  '/inbox': 'inbox-mobile.png',
  [`/geocoding/${geocodeDetail.id}`]: 'geocoding-detail-mobile.png',
}
for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
]) {
  test(`shared shell and page review at ${viewport.width}px`, async ({ page }, info) => {
    test.setTimeout(180000) // Twenty-one pages plus screenshots in one viewport audit.
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
      if (url.pathname.endsWith('/inbox')) return route.fulfill({ json: inboxFixture })
      if (url.pathname.includes('/geocode/requests/')) return route.fulfill({ json: geocodeDetail })
      if (url.pathname.endsWith('/admins'))
        return route.fulfill({ json: { items: [], admin_timezone: 'Europe/Berlin' } })
      if (url.pathname.endsWith('/assignments')) return route.fulfill({ json: null })
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
      await expect(page.locator('main h2').last()).toBeVisible()
      await expect(
        page.locator('main').getByText('Daten werden geladen …', { exact: true }),
      ).toHaveCount(0)
      if (path.startsWith('/geocoding/'))
        await expect(page.getByRole('heading', { name: geocodeDetail.entity_name })).toBeVisible()
      if (path === '/inbox')
        await expect(
          page.getByRole('heading', { name: inboxFixture.items[0]!.entity_name! }),
        ).toBeVisible()
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
      const label = labels[path === '/' ? '/' : path.split('/')[1]!.split('?')[0]!]
      if (viewport.width < 1024) {
        expect(dimensions.height).toBeLessThanOrEqual(120)
        const mobileHeader = page.locator('[data-mobile-app-header]')
        await expect(mobileHeader).toBeVisible()
        await expect(mobileHeader.getByText('Systemadministrator')).toHaveCount(0)
        await expect(
          mobileHeader.getByRole('button', { name: 'Abmelden', exact: true }),
        ).toHaveCount(0)
        await expect(mobileHeader.getByRole('button', { name: /\+ Datensatz/ })).toHaveCount(0)
        const geoScope = mobileHeader.getByRole('button', { name: /Gebiet: Alle/ })
        await expect(geoScope).toBeVisible()
        expect(
          await geoScope.evaluate(
            (element) =>
              element.getBoundingClientRect().right <= document.documentElement.clientWidth,
          ),
        ).toBe(true)
        if (index === 0) {
          await expect(geoScope).toBeEnabled()
          await geoScope.click()
          await expect(page.getByRole('dialog', { name: 'Gebiet auswählen' })).toBeVisible()
          await page.keyboard.press('Escape')
        }
        await page.getByRole('button', { name: 'Navigation öffnen' }).click()
      } else {
        const desktopHeader = page.locator('[data-desktop-app-header]')
        await expect(desktopHeader).toBeVisible()
        await expect(desktopHeader.getByText('Systemadministrator')).toBeVisible()
        await expect(
          desktopHeader.getByRole('button', { name: 'Abmelden', exact: true }),
        ).toBeVisible()
        await expect(desktopHeader.getByRole('button', { name: /\+ Datensatz/ })).toBeDisabled()
        await expect(desktopHeader.getByText(/Berlin/)).toBeVisible()
      }
      const nav = page
        .getByRole('navigation', { name: 'Hauptnavigation' })
        .filter({ visible: true })
      if (label)
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
        const drawer = page.getByRole('dialog', { name: 'Mobile Navigation' })
        await expect(drawer.getByText('Systemadministrator', { exact: true })).toBeVisible()
        await expect(drawer.getByRole('button', { name: /\+ Datensatz/ })).toBeDisabled()
        await expect(drawer.getByRole('button', { name: 'Abmelden', exact: true })).toBeVisible()
        if (index === 0) {
          await page.screenshot({ path: info.outputPath('navigation-drawer-mobile.png') })
          await page.keyboard.press('Escape')
        } else await page.getByRole('button', { name: 'Navigation schließen' }).click()
        await expect(page.getByRole('button', { name: 'Navigation öffnen' })).toBeFocused()
      }
      const pageHeaderActions = page.locator('[data-page-header-actions]').first()
      if (await pageHeaderActions.isVisible())
        expect(
          await pageHeaderActions.evaluate(
            (element) =>
              element.scrollWidth <= element.clientWidth &&
              element.getBoundingClientRect().right <= innerWidth,
          ),
        ).toBe(true)
      if (path === '/' && viewport.width < 1024) {
        const period = page.getByRole('combobox', { name: 'Zeitraum', exact: true })
        const refresh = page.getByRole('button', { name: 'Zahlen aktualisieren' })
        const [periodBox, refreshBox] = await Promise.all([
          period.boundingBox(),
          refresh.boundingBox(),
        ])
        expect(periodBox).not.toBeNull()
        expect(refreshBox).not.toBeNull()
        expect(Math.abs(periodBox!.y - refreshBox!.y)).toBeLessThan(3)
        const cardHeights = await page
          .locator('#new-records li a')
          .evaluateAll((links) => links.map((link) => link.getBoundingClientRect().height))
        expect(cardHeights.every((height) => height >= 64 && height <= 80)).toBe(true)
        expect(
          await page.locator('[data-dashboard-new-record-label]').evaluateAll((elements) =>
            elements.every((element) => {
              const range = document.createRange()
              range.selectNodeContents(element)
              return range.getClientRects().length === 1
            }),
          ),
        ).toBe(true)
        expect(
          await page
            .locator('#new-records li a')
            .evaluateAll(
              (links) =>
                links.filter((link) => link.getBoundingClientRect().top < innerHeight).length,
            ),
        ).toBeGreaterThan(2)
      }
      const screenshotName = viewport.width === 390 ? mobileScreenshotNames[path] : undefined
      await page.screenshot({
        path: info.outputPath(
          screenshotName ??
            `${index}-${path.split('?')[0]!.replaceAll('/', '_') || 'dashboard'}-${viewport.width}.png`,
        ),
        fullPage: true,
      })
    }
  })
}
