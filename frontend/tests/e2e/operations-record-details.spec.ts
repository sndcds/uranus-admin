import { test, expect } from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'
import { placeDetailFixture, identityDetailFixture } from '../fixtures/entities'
import { eventDetailFixture } from '../fixtures/event-detail'
import { enforceProductionCsp } from '../fixtures/record-csp'
import type { EntityDetail, EntitySection } from '../../shared/contracts'

const examples: [EntitySection, string, () => EntityDetail][] = [
  ['venues', 'venue', () => placeDetailFixture('venues')],
  ['organizations', 'organization', () => placeDetailFixture('organizations')],
  ['spaces', 'space', () => placeDetailFixture('spaces')],
  ['users', 'user', () => identityDetailFixture('users')],
  ['images', 'image', () => identityDetailFixture('images')],
  ['events', 'event', eventDetailFixture],
]
for (const viewport of [
  { width: 1440, height: 1000, name: 'desktop' },
  { width: 1024, height: 768, name: 'tablet' },
  { width: 390, height: 844, name: 'mobile' },
  { width: 360, height: 800, name: 'small-mobile' },
]) {
  test(`operations record details: ${viewport.name}`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit four-viewport matrix')
    await page.setViewportSize(viewport)
    await enforceProductionCsp(page)
    await mockLayoutApi(page)
    for (const [section, name, fixture] of examples) {
      const data = fixture()
      // Small, complete synthetic examples for review; existing detail tests cover pagination.
      if (section === 'organizations') {
        data.related.items = [data.related.items[0]!]
        data.item.facts.events = 1
        data.item.facts.venues = data.item.facts.memberships = 0
      } else if (section === 'users') {
        data.related.items = [data.related.items[0]!, data.related.items[13]!]
        data.item.facts.memberships = 1
      } else if (section === 'images') {
        data.related.items = [
          data.related.items[0]!,
          data.related.items[9]!,
          data.related.items[18]!,
        ]
        data.item.facts.image_links = 3
      }
      data.related.pagination = {
        page: 1,
        page_size: 25,
        pages: 1,
        total: data.related.items.length,
      }
      await page.route(`**/api/admin/api/v1/${section}/${data.item.entity_key}{,?*}`, (route) =>
        route.fulfill({ json: data }),
      )
      await page.goto(`/${section}/${data.item.entity_key}`)
      const main = page.locator('#main-content')
      const hero = main.locator('[data-entity-hero]')
      await expect(main.getByRole('heading', { level: 2 })).toHaveText(data.item.entity_name)
      await expect(hero).toHaveClass(/operations-panel/)
      await expect(hero.getByRole('link', { name: 'Zur Liste', exact: true })).toHaveAttribute(
        'href',
        `/${section}`,
      )
      await expect(hero.getByRole('link', { name: 'Beziehungen', exact: true })).toHaveCount(
        section === 'images' ? 0 : 1,
      )
      await expect(hero.getByRole('link', { name: /^Markierungen & Notizen/ })).toHaveClass(
        /button/,
      )
      if (data.item.public_url)
        await expect(hero.locator('a.button-primary')).toHaveText('Auf kulturbytes.de öffnen')
      const relations = main.getByRole('region', { name: 'Verknüpfte Datensätze', exact: true })
      await expect(relations).toHaveClass(/section-table/)
      await expect(relations).toContainText(
        `${data.related.items.length} auf dieser Seite von ${data.related.pagination.total} insgesamt`,
      )
      const open = relations.getByRole('link', { name: /^Öffnen:/ }).first()
      await expect(open).toHaveText('Öffnen')
      await expect(open).toHaveClass(/button button-compact/)
      await expect(open).toHaveAttribute(
        'href',
        data.related.items.find((item) => item.action)!.action!.href,
      )
      await open.focus()
      await expect(open).toBeFocused()
      await page.keyboard.press('Tab')
      await page.keyboard.press('Shift+Tab')
      await expect(open).toBeFocused()
      await expect(main).not.toContainText('Im Admin ansehen')
      const workflow = main.getByRole('region', { name: 'Qualität & Arbeitsstand' })
      await expect(workflow.locator('dt')).toHaveText(['Gespeicherte Befunde', 'Markierungen'])
      await expect(workflow.getByRole('link', { name: 'Befunde öffnen' })).toHaveClass(/button/)
      await expect(main.getByRole('region', { name: 'Verlauf', exact: true })).toHaveClass(
        /timeline-compact/,
      )
      await expect(main.getByRole('region', { name: 'Technische Informationen' })).toContainText(
        data.item.entity_key,
      )
      if (['venues', 'organizations', 'users', 'images'].includes(section)) {
        const grid = main.locator('[data-record-info-grid]')
        const columns = await grid.evaluate(
          (el) => getComputedStyle(el).gridTemplateColumns.split(' ').length,
        )
        expect(columns).toBe(viewport.width >= 640 ? 2 : 1)
      }
      const controls = await hero
        .locator('a, button')
        .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().height))
      expect(controls.every((height) => height >= 44)).toBe(true)
      expect(await open.evaluate((el) => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(
        44,
      )
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      // Wait for lazy previews before recording a complete review artifact.
      for (const img of await main.locator('img').all()) {
        await img.scrollIntoViewIfNeeded()
        await expect(img).toHaveJSProperty('complete', true)
        await expect
          .poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth))
          .toBeGreaterThan(0)
      }
      await page.evaluate(() => {
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
        window.scrollTo(0, 0)
      })
      await page.screenshot({
        path: info.outputPath(`${name}-${viewport.name}.png`),
        fullPage: true,
      })
      if (section === 'events' && viewport.name === 'desktop')
        await relations.screenshot({ path: info.outputPath('relations-desktop.png') })
    }
  })
}
