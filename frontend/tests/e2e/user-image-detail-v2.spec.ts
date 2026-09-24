import { test, expect } from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'
import { identityDetailFixture, identitySections } from '../fixtures/entities'
import { enforceProductionCsp } from '../fixtures/record-csp'

for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
]) {
  for (const section of identitySections) {
    test(`${section} record v2 at ${viewport.width}px`, async ({ page }, info) => {
      await page.setViewportSize(viewport)
      const violations: string[] = [],
        errors: string[] = []
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
      const data = identityDetailFixture(section)
      const response = await page.goto(`/${section}/${data.item.entity_key}?context=retained`)
      if (process.env.TEST_PRODUCTION === '1')
        expect(response?.headers()['content-security-policy']).toContain(
          "script-src 'self' 'unsafe-inline';",
        )
      const main = page.locator('#main-content'),
        hero = main.locator('[data-entity-hero]')
      await expect(main.getByRole('heading', { level: 2 })).toHaveText(data.item.entity_name)
      await expect(hero.getByText(data.item.entity_name, { exact: true })).toHaveCount(1)
      await expect(hero.locator('li')).toHaveCount(0)
      await expect(hero).not.toContainText(data.item.entity_key)
      await expect(hero.getByRole('link', { name: 'Zur Liste', exact: true })).toHaveAttribute(
        'href',
        `/${section}`,
      )
      const marks = hero.getByRole('link', {
        name: `Markierungen & Notizen zu ${data.item.entity_name}`,
        exact: true,
      })
      await expect(marks).toHaveAttribute(
        'href',
        `/marks?entity_type=${data.item.entity_type}&entity_key=${data.item.entity_key}&status=all`,
      )
      await expect(hero.locator('a[target="_blank"]')).toHaveCount(0)
      const relations = main.getByRole('region', { name: 'Verknüpfte Datensätze', exact: true })
      await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(25)
      await expect(relations).toContainText(
        `25 auf dieser Seite von ${data.related.pagination.total} insgesamt`,
      )
      await expect(
        main.getByRole('region', { name: 'Qualität & Arbeitsstand' }).locator('dd'),
      ).toHaveText(['2 Ohne behobene', '1 Einschließlich erledigter'])
      await expect(main.getByRole('heading', { name: 'Verlauf', exact: true })).toBeVisible()
      await expect(main.getByRole('region', { name: 'Technische Informationen' })).toContainText(
        data.item.entity_key,
      )
      expect((await main.locator('h3').allTextContents()).slice(-4)).toEqual([
        'Verknüpfte Datensätze',
        'Qualität & Arbeitsstand',
        'Verlauf',
        'Technische Informationen',
      ])
      if (section === 'users') {
        await expect(hero).toContainText('Aktiv')
        await expect(hero).toContainText(data.item.email!)
        await expect(hero).toContainText(data.item.facts.username!)
        await expect(hero.locator('img')).toHaveAttribute('alt', data.item.entity_name)
        await expect(main.getByRole('region', { name: 'Teamkontext' })).toContainText(
          'Einschließlich Einladungen',
        )
        await expect(
          main.getByRole('region', { name: 'Teamkontext' }).locator('dd.font-semibold'),
        ).toHaveText('13 Einschließlich Einladungen')
        await expect(relations.getByText('Eingeladen', { exact: true }).first()).toBeVisible()
        await expect(relations.getByText('Beigetreten', { exact: true }).first()).toBeVisible()
      } else {
        const preview = main.locator('[data-record-preview] img')
        await expect(preview).toHaveAttribute('src', data.item.image_url!.replace('320', '1280'))
        await expect(preview).toHaveAttribute('alt', data.item.entity_name)
        await expect(preview).toHaveAttribute('referrerpolicy', 'no-referrer')
        await expect(preview).toHaveAttribute('crossorigin', 'anonymous')
        await expect
          .poll(() => preview.evaluate((img: HTMLImageElement) => img.naturalWidth))
          .toBeGreaterThan(0)
        expect((await preview.boundingBox())!.width).toBeGreaterThan(200)
        await expect(
          main.getByRole('region', { name: 'Bildinformationen' }).locator('dd'),
        ).toHaveText(['27', 'Nein'])
        const trigger = main.getByRole('button', {
          name: `Bild vergrößern: ${data.item.entity_name}`,
          exact: true,
        })
        await trigger.click()
        await expect(page.getByRole('dialog', { name: data.item.entity_name })).toBeVisible()
        await page.keyboard.press('Escape')
        await expect(trigger).toBeFocused()
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({
        path: info.outputPath(`${section}-${viewport.width}.png`),
        fullPage: true,
      })
      await relations.getByRole('link', { name: 'Weiter', exact: true }).click()
      await expect(page).toHaveURL(/context=retained&related_page=2/)
      await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(
        section === 'users' ? 1 : 2,
      )
      await expect(relations).toContainText(
        `${section === 'users' ? 1 : 2} auf dieser Seite von ${data.related.pagination.total} insgesamt`,
      )
      if (section === 'users') {
        await hero.getByRole('link', { name: 'Beziehungen', exact: true }).click()
        await expect(page).toHaveURL(
          new RegExp(`/graph\\?root_type=user&root_key=${data.item.entity_key}`),
        )
      } else {
        await marks.click()
        await expect(page).toHaveURL(/\/marks\?entity_type=image/)
      }
      expect(errors).toEqual([])
      expect(violations).toEqual([])
    })
  }
}

test('image failure leaves readable fallback without retries', async ({ page }) => {
  await mockLayoutApi(page)
  let requests = 0
  await page.route('https://api.kulturbytes.de/api/image/**', (route) => {
    requests++
    return route.abort()
  })
  const data = identityDetailFixture('images')
  await page.goto(`/images/${data.item.entity_key}`)
  const preview = page.locator('[data-record-preview]')
  await expect(preview).toContainText('Bildvorschau konnte nicht geladen werden.')
  await expect(preview.locator('img, button')).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 2 })).toHaveText(data.item.entity_name)
  expect(requests).toBe(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

for (const dimensions of [
  { width: 300, height: 1200 },
  { width: 1800, height: 300 },
]) {
  test(`image ratio ${dimensions.width}x${dimensions.height} and long plain title`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    await mockLayoutApi(page)
    await page.route('https://api.kulturbytes.de/api/image/**', (route) =>
      route.fulfill({
        contentType: 'image/svg+xml',
        headers: { 'access-control-allow-origin': '*' },
        body: `<svg xmlns="http://www.w3.org/2000/svg" width="${dimensions.width}" height="${dimensions.height}"><rect width="100%" height="100%" fill="#86198f"/></svg>`,
      }),
    )
    const data = identityDetailFixture('images')
    data.item.entity_name = '**Plaintext** <img> ' + 'LangerAlttext'.repeat(20)
    data.related.items = []
    await page.route(`**/api/admin/api/v1/images/${data.item.entity_key}**`, (route) =>
      route.fulfill({ json: data }),
    )
    await page.goto(`/images/${data.item.entity_key}`)
    await expect(page.getByRole('heading', { level: 2 })).toHaveText(data.item.entity_name)
    const preview = page.locator('[data-record-preview] img')
    await expect
      .poll(() => preview.evaluate((img: HTMLImageElement) => img.naturalWidth))
      .toBe(dimensions.width)
    const bounds = (await preview.boundingBox())!
    expect(bounds.width / bounds.height).toBeCloseTo(dimensions.width / dimensions.height, 1)
    expect(bounds.height).toBeLessThanOrEqual(440)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

for (const width of [1440, 390]) {
  test(`compact synthetic review screenshots at ${width}px`, async ({ page }, info) => {
    await enforceProductionCsp(page)
    await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 })
    await mockLayoutApi(page)
    for (const section of identitySections) {
      const data = identityDetailFixture(section)
      data.related.items =
        section === 'users'
          ? [data.related.items[0]!, data.related.items[13]!]
          : [data.related.items[0]!, data.related.items[9]!, data.related.items[18]!]
      data.related.pagination = {
        page: 1,
        page_size: 25,
        pages: 1,
        total: data.related.items.length,
      }
      if (section === 'users') data.item.facts.memberships = 1
      else data.item.facts.image_links = 3
      await page.route(`**/api/admin/api/v1/${section}/${data.item.entity_key}**`, (route) =>
        route.fulfill({ json: data }),
      )
      await page.goto(`/${section}/${data.item.entity_key}`)
      await expect(page.getByRole('heading', { level: 2 })).toHaveText(data.item.entity_name)
      await expect(page.getByRole('region', { name: 'Technische Informationen' })).toBeVisible()
      await expect
        .poll(() =>
          page
            .locator(section === 'images' ? '[data-record-preview] img' : '[data-entity-hero] img')
            .evaluate((img: HTMLImageElement) => img.naturalWidth),
        )
        .toBeGreaterThan(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({
        path: info.outputPath(
          `${section === 'users' ? 'user' : 'image'}-${width === 1440 ? 'desktop' : 'mobile'}.png`,
        ),
        fullPage: true,
      })
    }
  })
}
