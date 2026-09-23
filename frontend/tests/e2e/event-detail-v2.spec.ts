import { test, expect } from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'
import { eventDetailFixture, paginatedEventDetailFixture } from '../fixtures/event-detail'

// Match the existing production test policy, plus the already approved public image origin.
// No application/deployment CSP is changed by this response-only test hook.
async function enforceProductionCsp(page: import('@playwright/test').Page) {
  if (process.env.TEST_PRODUCTION !== '1') return
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue()
    const response = await route.fetch()
    await route.fulfill({
      response,
      headers: {
        ...response.headers(),
        'content-security-policy':
          "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://api.kulturbytes.de; connect-src 'self'; object-src 'none'; base-uri 'self'",
      },
    })
  })
}

for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
]) {
  test(`record detail v2 at ${viewport.width}px`, async ({ page }, info) => {
    await page.setViewportSize(viewport)
    const violations: string[] = []
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
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await enforceProductionCsp(page)
    await mockLayoutApi(page)
    const data = eventDetailFixture()
    const response = await page.goto(`/events/${data.item.entity_key}`)
    if (process.env.TEST_PRODUCTION === '1')
      expect(response?.headers()['content-security-policy']).toContain(
        "script-src 'self' 'unsafe-inline';",
      )
    const main = page.locator('#main-content')
    await expect(
      main.getByRole('heading', { name: data.item.entity_name, exact: true }),
    ).toHaveCount(1)
    await expect(main.getByRole('heading', { level: 2 })).toHaveText(data.item.entity_name)
    const description = main.getByRole('region', { name: 'Beschreibung', exact: true })
    await expect(description.locator('.prose-admin strong')).toHaveText('Kultur und Begegnung')
    await expect(description.locator('h4')).toHaveText('Das erwartet dich')
    const technical = main.getByRole('region', { name: 'Technische Informationen' })
    await expect(technical.getByText(data.item.entity_key, { exact: true })).toBeVisible()
    await expect(main.locator('[data-entity-hero]')).not.toContainText(data.item.entity_key)
    await expect(main.getByRole('region', { name: 'Auf einen Blick' })).not.toContainText(
      data.item.entity_key,
    )
    const relations = main.getByRole('region', { name: 'Verknüpfte Datensätze', exact: true })
    for (const item of data.related.items)
      await expect(
        relations.getByRole('heading', { name: item.entity_name, exact: true }),
      ).toBeVisible()
    await expect(relations).toContainText('keine chronologische Terminliste')
    for (const name of ['Termine', 'Veranstalter', 'Orte & Räume', 'Medien', 'Weitere Beziehungen'])
      await expect(main.getByRole('region', { name, exact: true })).toHaveCount(0)
    await expect(main.locator('[data-entity-hero]')).toContainText(
      `Veranstalter: ${data.item.organization_name}`,
    )
    await expect(main.getByRole('heading', { name: 'Verlauf', exact: true })).toBeVisible()
    const headings = await main.locator('h3').allTextContents()
    expect(headings.indexOf('Verlauf')).toBeGreaterThan(headings.indexOf('Verknüpfte Datensätze'))
    expect(headings.indexOf('Technische Informationen')).toBeGreaterThan(
      headings.indexOf('Verlauf'),
    )
    await expect(main.getByRole('link', { name: 'Befunde anzeigen', exact: true })).toHaveAttribute(
      'href',
      new RegExp(`entity_key=${data.item.entity_key}`),
    )
    const actions = main.getByRole('group', { name: 'Datensatzaktionen', exact: true })
    await expect(actions.getByRole('link', { name: 'Beziehungen', exact: true })).toHaveAttribute(
      'href',
      `/graph?root_type=event&root_key=${data.item.entity_key}&depth=2`,
    )
    await expect(
      actions.getByRole('link', {
        name: `Markierungen & Notizen zu ${data.item.entity_name}`,
        exact: true,
      }),
    ).toHaveAttribute('href', new RegExp(`entity_key=${data.item.entity_key}`))
    const publicLink = actions.getByRole('link', {
      name: `${data.item.entity_name} auf kulturbytes.de öffnen (neuer Tab)`,
      exact: true,
    })
    await expect(publicLink).toHaveAttribute('href', data.item.public_url!)
    await expect(publicLink).toHaveClass(/button-primary/)
    await expect(publicLink).toHaveAttribute('rel', 'noopener noreferrer')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const proseWidth = await description
      .locator('.prose-admin')
      .evaluate((el) => el.getBoundingClientRect().width)
    expect(proseWidth).toBeLessThanOrEqual(740)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({
      path: info.outputPath(`event-detail-v2-${viewport.width}.png`),
      fullPage: true,
    })
    expect(errors).toEqual([])
    expect(violations).toEqual([])
  })
}

test('event Markdown stays inert under production CSP and leaves source text readable', async ({
  page,
}) => {
  await enforceProductionCsp(page)
  await mockLayoutApi(page)
  const data = eventDetailFixture()
  data.item.facts.description =
    '<img src="https://evil.example/pixel" onerror="alert(1)">\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert%281%29)\n\n```html\n<img onerror=alert(1)>\n```'
  await page.route(`**/api/admin/api/v1/events/${data.item.entity_key}**`, (route) =>
    route.fulfill({ json: data }),
  )
  data.item.facts.description +=
    '\n\nZeile eins\nZeile zwei\n\nHarte Zeile  \nNeue Zeile\n\n' +
    [
      '/sql',
      '/findings',
      '/queues/team_invitations',
      '/notifications',
      '/marks',
      '/checks',
      '/inbox',
    ]
      .map((path) => `[Adminziel](${path})`)
      .join(' ')
  const requests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('evil.example')) requests.push(request.url())
  })
  await page.goto(`/events/${data.item.entity_key}`)
  const content = page.getByRole('region', { name: 'Beschreibung', exact: true })
  await expect(content).toContainText('<script>alert(1)</script>')
  await expect(content.locator('script, img, iframe, [onerror]')).toHaveCount(0)
  await expect(content.locator('a')).toHaveCount(0)
  await expect(content.locator('p').filter({ hasText: 'Zeile eins' })).toHaveText(
    'Zeile eins Zeile zwei',
  )
  await expect(content.locator('br')).toHaveCount(1)
  await content.getByRole('region', { name: 'Codeblock' }).focus()
  await expect(content.getByRole('region', { name: 'Codeblock' })).toBeFocused()
  expect(requests).toEqual([])
})

test('30 dates use general pagination without hiding the organizer or standard location context', async ({
  page,
}) => {
  await mockLayoutApi(page)
  const first = paginatedEventDetailFixture(1)
  await page.route(`**/api/admin/api/v1/events/${first.item.entity_key}**`, (route) => {
    const query = new URL(route.request().url()).searchParams
    return route.fulfill({
      json: paginatedEventDetailFixture(Number(query.get('related_page') ?? 1)),
    })
  })
  await page.goto(`/events/${first.item.entity_key}?context=retained`)
  const main = page.locator('#main-content')
  const relations = main.getByRole('region', { name: 'Verknüpfte Datensätze', exact: true })
  await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(25)
  await expect(relations).toContainText('25 auf dieser Seite von 34 insgesamt')
  await expect(relations).toContainText('keine chronologische Terminliste')
  await expect(main.locator('[data-entity-hero]')).toContainText(
    `Veranstalter: ${first.item.organization_name}`,
  )
  const facts = main.getByRole('region', { name: 'Auf einen Blick' })
  await expect(facts).toContainText('Standardort')
  await expect(facts).toContainText(first.item.facts.venue_name!)
  await expect(facts).toContainText('Standardraum')
  await expect(facts).toContainText(first.item.facts.space_name!)
  for (const name of ['Termine', 'Veranstalter', 'Orte & Räume', 'Medien', 'Weitere Beziehungen'])
    await expect(main.getByRole('region', { name, exact: true })).toHaveCount(0)
  await expect(relations.getByRole('heading', { name: 'Plakat zur Kulturnacht' })).toHaveCount(0)
  await relations.getByRole('link', { name: 'Weiter', exact: true }).click()
  await expect(page).toHaveURL(/context=retained&related_page=2/)
  await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(9)
  await expect(relations).toContainText('9 auf dieser Seite von 34 insgesamt')
  for (const item of paginatedEventDetailFixture(2).related.items)
    await expect(
      relations.getByRole('heading', { name: item.entity_name, exact: true }),
    ).toBeVisible()
  await relations.getByRole('link', { name: 'Zurück', exact: true }).click()
  await expect(relations.getByRole('heading', { level: 4 })).toHaveCount(25)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
