import { test, expect } from '../fixtures/authenticated'
import { graphPath } from '../fixtures/graph'
import { entityFixture } from '../fixtures/entities'
import { inboxFixture } from '../fixtures/inbox'
import { geocodeDetail } from '../fixtures/geocoding'
import { notificationDetail, notificationDeliveryDetail } from '../fixtures/notifications'
import { mockLayoutApi, layoutMark } from '../fixtures/layout'
import { entitySectionSchema } from '../../shared/contracts'

const sections = entitySectionSchema.options
const routes = [
  '/',
  '/activity',
  '/inbox',
  '/findings',
  '/checks',
  '/quality',
  '/geocoding',
  '/queues/partner_requests',
  '/queues/team_invitations',
  '/queues/user_activation',
  '/notifications',
  `/notifications/${notificationDetail.id}`,
  '/notifications/deliveries',
  `/notifications/deliveries/${notificationDeliveryDetail.id}`,
  '/marks',
  `/marks/${layoutMark.id}`,
  '/sql',
  '/statistics?view=event-content',
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
  notifications: 'Benachrichtigungen',
  marks: 'Markierungen',
  sql: 'SQL Console',
  geocoding: 'Standortvorschläge',
  partner_requests: 'Partneranfragen',
  team_invitations: 'Einladungen',
  user_activation: 'Aktivierungen',
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
    test.setTimeout(300000) // Complete route matrix with review screenshots.
    await page.setViewportSize(viewport)
    await page.route('**/api/admin/auth/session', (route) =>
      route.fulfill({ json: { subject: 'admin:layout-fixture', system_admin: true } }),
    )
    await mockLayoutApi(page)
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
      await expect(
        page.locator('main').getByText('Abruf fehlgeschlagen', { exact: true }),
      ).toHaveCount(0)
      await expect(
        page.getByRole('status').filter({ hasText: 'Daten werden geladen' }),
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
      const label =
        labels[
          path === '/'
            ? '/'
            : path.startsWith('/queues/')
              ? path.split('/')[2]!
              : path.split('/')[1]!.split('?')[0]!
        ]
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
        expect(cardHeights.every((height) => height >= 56 && height <= 80)).toBe(true)
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
    await page.context().clearCookies()
    await page.unroute('**/api/admin/auth/session')
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Anmeldung', exact: true })).toBeVisible()
    await expect(page.getByLabel('Benutzername', { exact: true })).toBeEnabled()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`login-${viewport.width}.png`), fullPage: true })
  })
}
