import { test, expect } from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'
import { collectionFixture } from '../fixtures/collections'
import { activityFixture } from '../fixtures/activity'
import { entitySectionSchema } from '../../shared/contracts'

const sizes = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'tablet', width: 1024, height: 768 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'small-mobile', width: 360, height: 800 },
]
for (const size of sizes) {
  test(`collections and chronological activity at ${size.name}`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit four-viewport matrix')
    await page.setViewportSize(size)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await mockLayoutApi(page)
    for (const section of entitySectionSchema.options) {
      const fixture = collectionFixture(section)
      await page.route(`**/api/admin/api/v1/${section}?**`, (route) =>
        route.fulfill({ json: fixture }),
      )
      await page.route(`**/api/admin/api/v1/${section}`, (route) =>
        route.fulfill({ json: fixture }),
      )
      await page.goto(`/${section}`)
      const rows = page.locator('[data-collection-row]')
      await expect(rows).toHaveCount(3)
      await expect(
        rows.first().getByRole('heading', { name: fixture.items[0]!.entity_name, exact: true }),
      ).toBeVisible()
      await expect(page.getByRole('region', { name: 'Technische Informationen' })).toContainText(
        '25',
      )
      await expect(page.getByRole('region', { name: 'Ergebnisübersicht' })).toContainText(
        '28 Datensätze insgesamt',
      )
      await expect(page.getByRole('combobox', { name: 'Terminlage', exact: true })).toHaveCount(
        ['users', 'images'].includes(section) ? 0 : 1,
      )
      await expect(page.getByRole('combobox', { name: 'Status', exact: true })).toHaveCount(
        ['events', 'users'].includes(section) ? 1 : 0,
      )
      await expect(rows.first().getByRole('link', { name: /^Öffnen:/ })).toHaveAttribute(
        'href',
        fixture.items[0]!.action!.href,
      )
      await expect(rows.first().getByRole('link', { name: /Markierungen & Notizen/ })).toBeVisible()
      await expect(rows.first().getByRole('link', { name: 'Beziehungen' })).toHaveCount(
        section === 'images' ? 0 : 1,
      )
      if (section === 'events') {
        await expect(rows.first()).toContainText('Veröffentlicht')
        await expect(rows.first()).toContainText('Standardort')
        await expect(
          rows.first().getByRole('link', { name: /auf kulturbytes.de/ }),
        ).toHaveAttribute('rel', 'noopener noreferrer')
      }
      if (section === 'users' || section === 'organizations')
        await expect(rows.first()).toContainText('einschließlich Einladungen')
      if (section === 'users')
        await expect(
          rows.nth(1).getByText(fixture.items[1]!.entity_name, { exact: true }),
        ).toHaveCount(1)
      if (section === 'spaces')
        await expect(rows.first()).toContainText('Kulturhaus an der alten Hafenpromenade')
      if (section === 'images') await expect(rows.first()).toContainText('Ohne Verknüpfung')
      if (section !== 'spaces')
        await expect(rows.first().getByRole('img')).toHaveJSProperty('naturalWidth', 1280)
      await expect(page.locator('.collection-header')).toBeVisible({ visible: size.width > 1100 })
      await expect(page.locator('.collection-header > span')).toHaveText(
        section === 'spaces'
          ? ['Datensatz', 'Kontext', 'Status / Erstellt']
          : ['Datensatz', 'Kontext', 'Fakten', 'Status / Erstellt'],
      )
      const controls = await rows
        .first()
        .locator('a, button')
        .evaluateAll((elements) => elements.map((el) => el.getBoundingClientRect().height))
      expect(controls.every((height) => height >= 44)).toBe(true)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({
        path: info.outputPath(`${section}-${size.name}.png`),
        fullPage: true,
      })
    }
    await page.route('**/api/admin/api/v1/dashboard/activity**', (route) =>
      route.fulfill({
        json: {
          ...activityFixture,
          items: activityFixture.items.map((item) => ({
            ...item,
            image_url: ['event', 'event_date', 'organization', 'venue', 'image'].includes(
              item.entity_type,
            )
              ? `https://api.kulturbytes.de/api/image/${item.entity_key}?width=320&type=png`
              : null,
          })),
        },
      }),
    )
    await page.goto('/activity?period=7d')
    await expect(page.getByRole('heading', { name: 'Heute', exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Zusammenfassung der Aktivität' })).toContainText(
      'Objektarten auf dieser Seite',
    )
    await expect(page.getByRole('region', { name: 'Technische Informationen' })).toContainText(
      'Europe/Berlin',
    )
    await expect(page.getByRole('textbox', { name: 'Organisation (UUID)' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    for (const thumbnail of await page.locator('.activity-row-dense img').all()) {
      await thumbnail.scrollIntoViewIfNeeded()
      await expect(thumbnail).toHaveJSProperty('naturalWidth', 1280)
    }
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: info.outputPath(`activity-${size.name}.png`), fullPage: true })
  })
}

for (const kind of ['activity', 'events'] as const) {
  test(`${kind} retains same-query data, marks stale failures and clears denied data`, async ({
    page,
  }) => {
    await mockLayoutApi(page)
    const endpoint = kind === 'activity' ? 'dashboard/activity' : 'events'
    const fixture = kind === 'activity' ? activityFixture : collectionFixture('events')
    let response = 200
    let release: (() => void) | undefined
    let pause = false
    await page.route(`**/api/admin/api/v1/${endpoint}**`, async (route) => {
      if (pause)
        await new Promise<void>((resolve) => {
          release = resolve
        })
      await route.fulfill(
        response === 200
          ? { json: fixture }
          : {
              status: response,
              json: { error: { code: 'unavailable', message: 'Synthetic error' } },
            },
      )
    })
    await page.goto(`/${kind}`)
    const title = page.getByRole('heading', { name: fixture.items[0]!.entity_name, exact: true })
    await expect(title).toBeVisible()
    response = 503
    pause = true
    await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
    await expect(page.getByText('Daten werden aktualisiert …', { exact: true })).toBeVisible()
    await expect(title).toBeVisible()
    await expect.poll(() => !!release).toBe(true)
    release!()
    await expect(page.getByRole('alert')).toContainText('Abruf fehlgeschlagen')
    await expect(title).toBeVisible()
    await expect(page.getByRole('alert')).toContainText('Die angezeigten Daten sind veraltet.')
    response = 403
    pause = false
    await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
    await expect(title).toHaveCount(0)
    await expect(page.getByRole('alert')).toContainText('Keine Berechtigung')
  })
}
