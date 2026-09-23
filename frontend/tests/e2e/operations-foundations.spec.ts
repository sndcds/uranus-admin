import {
  test,
  expect,
  expectCreateUnavailable,
  expectLogoutAvailable,
} from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'

const viewports = [
  { width: 1440, height: 1000 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
]

for (const viewport of viewports) {
  const { width } = viewport
  test(`operations primitives at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize(viewport)
    await page.goto('http://127.0.0.1:3101')
    await expect(
      page.getByRole('heading', { name: 'Operations Center', exact: true }),
    ).toBeVisible()
    const facts = page.getByRole('region', { name: 'Benutzerinformationen', exact: true })
    expect(await facts.locator('dl').evaluate((el) => getComputedStyle(el).display)).toBe('grid')
    const header = page.locator('main > header')
    await expect(header.getByRole('link', { name: 'Arbeitsliste ansehen' })).toBeVisible()
    expect(await header.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    const technical = page.getByRole('region', { name: 'Technische Informationen', exact: true })
    if (width >= 1280)
      expect(await technical.locator('dl').evaluate((el) => getComputedStyle(el).display)).toBe(
        'flex',
      )
    const table = page.getByRole('table', { name: 'Beispiel-Arbeitsliste', exact: true })
    const list = page.getByRole('list', { name: 'Dichte Beispiel-Liste' })
    await expect(list.getByRole('listitem')).toHaveCount(3)
    for (const row of await list.getByRole('listitem').all()) {
      expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(44)
      expect((await row.boundingBox())!.height).toBeLessThanOrEqual(56)
    }
    const timeline = page.getByRole('region', { name: 'Verlauf', exact: true })
    await expect(timeline.getByText('Qualitätsproblem erkannt', { exact: true })).toBeVisible()
    await expect(timeline.locator('time')).toHaveAttribute('datetime', '2026-02-03T10:15:00Z')
    await expect(table.getByRole('rowheader')).toHaveCount(3)
    await expect(table.getByRole('columnheader', { name: 'Status', exact: true })).toHaveCount(1)
    await expect(table.getByRole('button')).toHaveCount(3)
    if (width >= 640) {
      for (const row of await table.locator('tbody tr').all()) {
        expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(44)
        expect((await row.boundingBox())!.height).toBeLessThanOrEqual(56)
      }
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    for (const control of await page.locator('button, a').filter({ visible: true }).all()) {
      expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    const open = page.getByRole('button', { name: 'Details: Hafenbühne' })
    await open.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('status').filter({ hasText: 'Ausgewählt' })).toHaveText(
      'Ausgewählt: Hafenbühne',
    )
    const updateReview =
      process.env.UPDATE_FOUNDATION_SCREENSHOTS === '1' && info.project.name === 'desktop'
    await page.screenshot({
      path: updateReview
        ? `docs/screenshots/operations-foundations/components-${width}.png`
        : info.outputPath(`components-${width}.png`),
      fullPage: true,
    })
    for (const [name, locator] of [
      ['page-header', header],
      ['compact-facts', facts.locator('dl')],
      ['operations-panel', facts],
      ['technical-info', technical],
      ['dense-table', table],
      ['dense-list', list],
      ['compact-timeline', timeline],
      ['compact-empty', page.getByRole('region', { name: 'Verknüpfte Datensätze', exact: true })],
    ] as const)
      await locator.screenshot({
        path:
          updateReview &&
          width === 1440 &&
          [
            'compact-facts',
            'technical-info',
            'dense-table',
            'dense-list',
            'compact-timeline',
          ].includes(name)
            ? `docs/screenshots/operations-foundations/${name}.png`
            : info.outputPath(`${name}-${width}.png`),
      })
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: info.outputPath(`viewport-${width}.png`) })
    await page.getByText('Tabellenalternative: lokal scrollen').click()
    const scroll = page.getByRole('region', { name: 'Lokal scrollbare Beispiel-Tabelle' })
    await scroll.focus()
    await expect(scroll).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (width < 640)
      expect(await scroll.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
  })
}

for (const viewport of viewports) {
  test(`operations shell at ${viewport.width}px retains navigation, search and drawer focus`, async ({
    page,
  }, info) => {
    await page.setViewportSize(viewport)
    await mockLayoutApi(page)
    await page.goto('/users')
    await expectCreateUnavailable(page)
    if ((page.viewportSize()?.width ?? 1440) >= 1024) {
      await expect(
        page.getByRole('button', { name: /\+ Datensatz/ }).filter({ visible: true }),
      ).toContainText('Nur Lesen')
      const provenance = page.getByRole('button', { name: 'SQL / Datenherkunft', exact: true })
      expect((await provenance.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    await expectLogoutAvailable(page)
    const mobile = (page.viewportSize()?.width ?? 1440) < 1024
    if (mobile) await page.getByRole('button', { name: 'Navigation öffnen' }).click()
    const nav = page.getByRole('navigation', { name: 'Hauptnavigation' }).filter({ visible: true })
    await expect(nav.getByRole('link', { name: 'Benutzer & Teams', exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(
      await nav.evaluate((el) => getComputedStyle(el.parentElement!).backgroundColor),
    ).not.toBe('rgb(255, 255, 255)')
    for (const link of await nav.getByRole('link').all())
      expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    const current = nav.getByRole('link', { name: 'Benutzer & Teams', exact: true })
    await current.focus()
    await page.keyboard.press('Tab')
    const next = nav.getByRole('link', { name: 'Bilder', exact: true })
    await expect(next).toBeFocused()
    expect(await next.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe('none')
    await page.screenshot({
      path: info.outputPath(`sidebar-${viewport.width}.png`),
    })
    if (mobile) {
      await page.keyboard.press('Escape')
      await expect(page.getByRole('button', { name: 'Navigation öffnen' })).toBeFocused()
    }
    await page
      .getByRole('button', { name: 'Globale Suche öffnen' })
      .filter({ visible: true })
      .click()
    await expect(page.getByRole('dialog').filter({ visible: true })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(
      page.getByRole('button', { name: 'Globale Suche öffnen' }).filter({ visible: true }),
    ).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
