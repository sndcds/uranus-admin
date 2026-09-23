import {
  test,
  expect,
  expectCreateUnavailable,
  expectLogoutAvailable,
} from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'

for (const width of [1440, 820, 390, 360]) {
  test(`operations primitives at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('http://127.0.0.1:3101')
    await expect(
      page.getByRole('heading', { name: 'Operations Center', exact: true }),
    ).toBeVisible()
    const facts = page.getByRole('region', { name: 'Benutzerinformationen', exact: true })
    expect(await facts.locator('dl').evaluate((el) => getComputedStyle(el).display)).toBe('grid')
    expect(
      await facts.locator('dl').evaluate((el) => getComputedStyle(el.parentElement!).paddingTop),
    ).toBe('16px')
    const technical = page.getByRole('region', { name: 'Technische Informationen', exact: true })
    if (width >= 1280)
      expect(await technical.locator('dl').evaluate((el) => getComputedStyle(el).display)).toBe(
        'flex',
      )
    const table = page.getByRole('table', { name: 'Beispiel-Arbeitsliste', exact: true })
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
    for (const button of await page.getByRole('button').all()) {
      expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    const open = page.getByRole('button', { name: 'Details: Hafenbühne' })
    await open.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('status').filter({ hasText: 'Ausgewählt' })).toHaveText(
      'Ausgewählt: Hafenbühne',
    )
    await page.screenshot({ path: info.outputPath(`components-${width}.png`), fullPage: true })
    if (width === 1440) {
      await facts.screenshot({ path: info.outputPath('compact-facts.png') })
      await technical.screenshot({ path: info.outputPath('technical-info.png') })
      await table.screenshot({ path: info.outputPath('dense-table.png') })
    }
    await page.getByText('Tabellenalternative: lokal scrollen').click()
    const scroll = page.getByRole('region', { name: 'Lokal scrollbare Beispiel-Tabelle' })
    await scroll.focus()
    await expect(scroll).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (width < 640)
      expect(await scroll.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
  })
}

test('operations shell retains active navigation, search, disabled creation and drawer focus', async ({
  page,
}, info) => {
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
  expect(await nav.evaluate((el) => getComputedStyle(el.parentElement!).backgroundColor)).not.toBe(
    'rgb(255, 255, 255)',
  )
  for (const link of await nav.getByRole('link').all())
    expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  await page.screenshot({
    path: info.outputPath(mobile ? 'sidebar-mobile.png' : 'sidebar-desktop.png'),
    fullPage: true,
  })
  if (mobile) {
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'Navigation öffnen' })).toBeFocused()
  }
  await page.getByRole('button', { name: 'Globale Suche öffnen' }).filter({ visible: true }).click()
  await expect(page.getByRole('dialog').filter({ visible: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(
    page.getByRole('button', { name: 'Globale Suche öffnen' }).filter({ visible: true }),
  ).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
