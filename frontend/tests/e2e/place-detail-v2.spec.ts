import { test, expect } from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'
import { placeDetailFixture, placeSections } from '../fixtures/entities'
import { enforceProductionCsp } from '../fixtures/record-csp'

for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
]) {
  for (const section of placeSections) {
    test(`${section} record v2 at ${viewport.width}px`, async ({ page }, info) => {
      await page.setViewportSize(viewport)
      const violations: string[] = []
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.exposeFunction('recordCspViolation', (directive: string) =>
        violations.push(directive),
      )
      await page.addInitScript(() =>
        document.addEventListener('securitypolicyviolation', (event) => {
          void (
            window as unknown as { recordCspViolation: (value: string) => Promise<void> }
          ).recordCspViolation(event.violatedDirective)
        }),
      )
      await enforceProductionCsp(page)
      await mockLayoutApi(page)
      const data = placeDetailFixture(section)
      const response = await page.goto(`/${section}/${data.item.entity_key}`)
      if (process.env.TEST_PRODUCTION === '1')
        expect(response?.headers()['content-security-policy']).toContain(
          "script-src 'self' 'unsafe-inline';",
        )
      const main = page.locator('#main-content')
      const hero = main.locator('[data-entity-hero]')
      await expect(main.getByRole('heading', { level: 2 })).toHaveText(data.item.entity_name)
      await expect(
        main.getByRole('heading', { name: data.item.entity_name, exact: true }),
      ).toHaveCount(1)
      await expect(hero.locator('li')).toHaveCount(0)
      await expect(hero).not.toContainText(data.item.entity_key)
      await expect(hero.getByRole('link', { name: 'Zur Liste', exact: true })).toHaveAttribute(
        'href',
        `/${section}`,
      )
      const actions = hero.getByRole('group', { name: 'Datensatzaktionen' })
      const graph = actions.getByRole('link', { name: 'Beziehungen', exact: true })
      await expect(graph).toHaveAttribute(
        'href',
        `/graph?root_type=${data.item.entity_type}&root_key=${data.item.entity_key}&depth=2`,
      )
      const marks = actions.getByRole('link', {
        name: `Markierungen & Notizen zu ${data.item.entity_name}`,
        exact: true,
      })
      const markHref = new URL((await marks.getAttribute('href'))!, 'http://127.0.0.1:3100')
      expect(markHref.pathname).toBe('/marks')
      expect(markHref.searchParams.get('entity_type')).toBe(data.item.entity_type)
      expect(markHref.searchParams.get('entity_key')).toBe(data.item.entity_key)
      const relations = main.getByRole('region', { name: 'Verknüpfte Datensätze', exact: true })
      await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(
        data.related.items.length,
      )
      await expect(relations).toContainText(
        `${data.related.items.length} auf dieser Seite von ${data.related.pagination.total} insgesamt`,
      )
      await expect(main.getByRole('heading', { name: 'Verlauf', exact: true })).toBeVisible()
      const technical = main.getByRole('region', { name: 'Technische Informationen', exact: true })
      await expect(technical.getByText(data.item.entity_key, { exact: true })).toBeVisible()
      const headings = await main.locator('h3').allTextContents()
      expect(headings.slice(-4)).toEqual([
        'Verknüpfte Datensätze',
        'Qualität & Arbeitsstand',
        'Verlauf',
        'Technische Informationen',
      ])
      if (section === 'organizations') {
        const facts = main.getByRole('region', { name: 'Auf einen Blick' })
        await expect(facts.locator('dt')).toHaveText([
          'Veranstaltungen',
          'Orte',
          'Teammitgliedschaften',
        ])
        await expect(facts.locator('dd.font-semibold')).toHaveText(['26', '1', '1'])
        await expect(facts).toContainText('Einschließlich Einladungen')
        await expect(hero).toContainText('Flensburg')
        await expect(hero.getByText(data.item.entity_name, { exact: true })).toHaveCount(1)
        await expect(main.getByRole('link', { name: /auf OpenStreetMap öffnen/ })).toHaveAttribute(
          'href',
          /^https:\/\/www.openstreetmap.org\//,
        )
      }
      if (section === 'venues') {
        const facts = main.getByRole('region', { name: 'Auf einen Blick' })
        await expect(facts.locator('dt')).toHaveText(['Räume insgesamt'])
        await expect(facts.locator('dd')).toHaveText(['1'])
        await expect(hero).toContainText(`Organisation: ${data.item.organization_name}`)
        const publicLink = actions.getByRole('link', {
          name: `${data.item.entity_name} auf kulturbytes.de öffnen (neuer Tab)`,
          exact: true,
        })
        await expect(publicLink).toHaveAttribute('href', data.item.public_url!)
        await expect(publicLink).toHaveClass(/button-primary/)
        await expect(publicLink).toHaveAttribute('target', '_blank')
        await expect(publicLink).toHaveAttribute('rel', 'noopener noreferrer')
        await expect(publicLink).toHaveAttribute('referrerpolicy', 'no-referrer')
        // Current source projection supplies coordinates only for organizations.
        await expect(main.getByRole('link', { name: /auf OpenStreetMap öffnen/ })).toHaveCount(0)
      } else await expect(actions.locator('.button-primary')).toHaveCount(0)
      if (section !== 'spaces') {
        await expect(main.getByRole('region', { name: 'Adresse', exact: true })).toContainText(
          data.item.address!,
        )
        await expect(hero).not.toContainText(data.item.address!)
      } else {
        await expect(hero.locator('dt')).toHaveText(['Zugehöriger Ort', 'Organisation'])
        await expect(
          hero.getByRole('link', { name: data.item.facts.venue_name!, exact: true }),
        ).toHaveAttribute('href', data.related.items[0]!.action!.href)
        await expect(hero).toContainText(data.item.organization_name!)
        await expect(main.getByRole('region', { name: 'Adresse', exact: true })).toHaveCount(0)
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      if (viewport.width < 640) {
        for (const link of await hero.locator('a').all()) {
          const bounds = await link.boundingBox()
          expect(bounds!.height).toBeGreaterThanOrEqual(44)
        }
      }
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({
        path: info.outputPath(`${section}-detail-v2-${viewport.width}.png`),
        fullPage: true,
      })
      await graph.click()
      await expect(page).toHaveURL(
        new RegExp(
          `/graph\\?root_type=${data.item.entity_type}&root_key=${data.item.entity_key}&depth=2`,
        ),
      )
      expect(errors).toEqual([])
      expect(violations).toEqual([])
    })
  }
}

test('organization relations remain globally paginated, preserve context and keep independent counts visible', async ({
  page,
}) => {
  await mockLayoutApi(page)
  const data = placeDetailFixture('organizations')
  await page.goto(`/organizations/${data.item.entity_key}?context=retained`)
  const relations = page.getByRole('region', { name: 'Verknüpfte Datensätze', exact: true })
  await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(25)
  await expect(relations).toContainText('25 auf dieser Seite von 28 insgesamt')
  await expect(relations).toContainText('Weitere verknüpfte Datensätze stehen auf anderen Seiten.')
  for (const name of ['Veranstaltungen', 'Orte', 'Team', 'Partner', 'Medien'])
    await expect(page.getByRole('region', { name, exact: true })).toHaveCount(0)
  await relations.getByRole('link', { name: 'Weiter', exact: true }).click()
  await expect(page).toHaveURL(/context=retained&related_page=2/)
  await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(3)
  await expect(relations).toContainText('3 auf dieser Seite von 28 insgesamt')
  await expect(
    page.getByRole('region', { name: 'Auf einen Blick' }).locator('dd.font-semibold'),
  ).toHaveText(['26', '1', '1'])
  await relations.getByRole('link', { name: 'Zurück', exact: true }).click()
  await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(25)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('missing venue data stays unknown without empty address boxes or invented external links', async ({
  page,
}) => {
  await mockLayoutApi(page)
  const data = placeDetailFixture('venues')
  data.item.facts.spaces = null
  data.item.address = data.item.public_url = null
  await page.route(`**/api/admin/api/v1/venues/${data.item.entity_key}**`, (route) =>
    route.fulfill({ json: data }),
  )
  await page.goto(`/venues/${data.item.entity_key}`)
  await expect(page.getByRole('region', { name: 'Auf einen Blick' })).toContainText(
    'Nicht verfügbar',
  )
  await expect(page.getByRole('region', { name: 'Adresse', exact: true })).toHaveCount(0)
  await expect(page.locator('[data-entity-hero] a[target="_blank"]')).toHaveCount(0)
})
