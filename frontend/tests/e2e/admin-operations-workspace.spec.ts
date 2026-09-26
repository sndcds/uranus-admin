import { test, expect } from '../fixtures/authenticated'
import { mockLayoutApi } from '../fixtures/layout'
import { detailFixture, timelineFixture } from '../fixtures/entities'
import { activityFixture } from '../fixtures/activity'
import { geocodeDetail } from '../fixtures/geocoding'
import { entitySections } from '../../app/utils/entities'
import { inspectorHref } from '../../app/utils/inspector'

const id = activityFixture.items[0]!.entity_key
test.beforeEach(async ({ page }) => {
  await mockLayoutApi(page)
  // Match the server's requested page size, so overview screenshots show the bounded preview.
  await page.route('**/api/admin/api/v1/dashboard/activity?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    const pageSize = Number(query.get('page_size') ?? 50)
    const items = activityFixture.items.filter(
      (item) => !query.get('entity_key') || item.entity_key === query.get('entity_key'),
    )
    return route.fulfill({ json: { ...activityFixture, items: items.slice(0, pageSize) } })
  })
  // Compact review record; larger relation pagination stays covered by existing record tests.
  await page.route(`**/api/admin/api/v1/users/${id}?*`, (route) =>
    route.fulfill({ json: detailFixture('users') }),
  )
})

for (const [section, entry] of Object.entries(entitySections)) {
  test(`inspector composes ${section} with independent findings and timeline`, async ({ page }) => {
    const record = detailFixture(section as keyof typeof entitySections)
    await page.route(`**/api/admin/api/v1/${section}/*`, (route) => route.fulfill({ json: record }))
    await page.goto(inspectorHref(entry.type, id)!)
    await expect(
      page.getByRole('heading', { name: 'Datensatz untersuchen', exact: true }),
    ).toBeVisible()
    await expect(page.locator('[data-entity-hero]')).toContainText(record.item.entity_name)
    await expect(
      page.getByRole('link', { name: 'Bestehende Detailansicht öffnen' }),
    ).toHaveAttribute('href', `/${section}/${id}`)
    await expect(page.getByRole('heading', { name: 'Aktive Befunde' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Verlauf', exact: true })).toBeVisible()
    await expect(page.locator('#activity')).toContainText('Betroffenes Feld')
    await expect(page.locator('#activity')).toContainText('description')
    await expect(page.locator('#relations')).toContainText('Verknüpfte Datensätze')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

for (const width of [1440, 1024, 390]) {
  test(`operations workspace review at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 })
    for (const [name, path, ready] of [
      ['dashboard', '/', 'Letzte Aktivitäten'],
      ['inspector', inspectorHref('user', id)!, 'Aktive Befunde'],
      ['activity', '/activity', 'Neue Datensätze'],
      ['findings', '/findings', 'Priorisierte Arbeitsliste'],
      ['social', '/social-publishing', 'Verfügbarkeit'],
      ['geocoding', `/geocoding/${geocodeDetail.id}`, 'Standortprüfung'],
    ]) {
      await page.goto(path!)
      await expect(
        page.getByRole('button', { name: 'Globale Suche öffnen' }).filter({ visible: true }),
      ).toBeEnabled()
      if (name === 'dashboard')
        await expect(page.getByText('Sichtbare Aufgaben', { exact: true })).toBeVisible()
      if (name === 'inspector') await expect(page.locator('[data-entity-hero]')).toBeVisible()
      if (name === 'activity')
        await expect(page.getByRole('link', { name: /^Öffnen:/ }).first()).toBeVisible()
      if (name === 'findings')
        await expect(
          page.getByRole('button', { name: /^Befund bearbeiten:/ }).first(),
        ).toBeVisible()
      if (name === 'geocoding') await expect(page.locator('[data-geocode-source]')).toBeVisible()
      await expect(page.getByRole('heading', { name: ready!, exact: true }).first()).toBeVisible()
      await expect(page.getByText('Daten werden geladen …', { exact: true })).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      await page.screenshot({ path: info.outputPath(`${name}-${width}.png`), fullPage: true })
    }
  })
}

test('dashboard loads independent operations in parallel and retains usable sections on failure', async ({
  page,
}) => {
  let release!: () => void
  const hold = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/admin/api/v1/geocode/requests?*', async (route) => {
    await hold
    await route.fulfill({ status: 503, json: { error: { code: 'storage_unavailable' } } })
  })
  await page.goto('/')
  await expect(page.getByText('Sichtbare Aufgaben', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Letzte Aktivitäten' })).toBeVisible()
  release()
  await expect(page.getByText('Abruf fehlgeschlagen', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Inbox öffnen', exact: true })).toBeVisible()
})

test('inspector findings error leaves the record and relations usable; source updates never invent a diff', async ({
  page,
}) => {
  const timeline = timelineFixture('user')
  timeline.items[0] = {
    ...timeline.items[0]!,
    kind: 'source_updated',
    title: 'Datensatz geändert',
    summary: null,
  }
  await page.route('**/api/admin/api/v1/**/timeline?*', (route) =>
    route.fulfill({ json: timeline }),
  )
  await page.route('**/api/admin/api/v1/findings?*', (route) =>
    route.fulfill({ status: 503, json: { error: { code: 'storage_unavailable' } } }),
  )
  await page.goto(inspectorHref('user', id)!)
  await expect(page.locator('#findings')).toContainText('Abruf fehlgeschlagen')
  await expect(page.locator('#activity')).toContainText(
    'Vorher-/Nachher-Vergleich sind nicht verfügbar',
  )
  await expect(page.locator('[data-entity-hero]')).toBeVisible()
  await expect(
    page.locator('#relations').getByRole('link', { name: 'Beziehungen', exact: true }).first(),
  ).toHaveAttribute('href', `/graph?root_type=user&root_key=${id}&depth=2`)
})

test('empty findings and timeline remain neutral; unsupported inspector types make no domain requests', async ({
  page,
}) => {
  const timeline = timelineFixture('user')
  await page.route('**/api/admin/api/v1/**/timeline?*', (route) =>
    route.fulfill({ json: { ...timeline, items: [] } }),
  )
  await page.route('**/api/admin/api/v1/findings?*', (route) =>
    route.fulfill({
      json: {
        items: [],
        pagination: { page: 1, page_size: 5, total: 0, pages: 0 },
        observed_at: timeline.observed_at,
        mode: 'persisted',
      },
    }),
  )
  await page.goto(inspectorHref('user', id)!)
  await expect(page.locator('#findings')).toContainText('Keine aktiven Befunde')
  await expect(page.locator('#activity')).toContainText('noch keine Ereignisse')
  const requests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/')) requests.push(request.url())
  })
  await page.goto(`/inspect/social_publication/${id}`)
  expect(requests).toEqual([])
})

test('social states stay unavailable and never trigger fabricated API requests', async ({
  page,
}) => {
  const requests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/')) requests.push(request.url())
  })
  await page.goto('/social-publishing')
  await expect(page.getByRole('heading', { name: 'Social Publishing', exact: true })).toBeVisible()
  for (const label of [
    'Social Posts',
    'Targets und Accounts',
    'Publication History',
    'Scheduling und Worker-Status',
  ]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible()
  }
  await expect(page.getByText('Nicht verfügbar', { exact: true })).toHaveCount(4)
  expect(requests).toEqual([])
})

for (const type of ['event_date', 'team_membership', 'partner_request'] as const) {
  test(`inspector keeps exact ${type} identity and available relationships`, async ({ page }) => {
    const item = activityFixture.items.find((entry) => entry.entity_type === type)!
    const calls: URL[] = []
    await page.route('**/api/admin/api/v1/dashboard/activity?*', (route) => {
      calls.push(new URL(route.request().url()))
      return route.fulfill({ json: { ...activityFixture, items: [item] } })
    })
    await page.goto(inspectorHref(type, item.entity_key)!)
    await expect(
      page.getByRole('heading', { name: item.entity_name, exact: true }).first(),
    ).toBeVisible()
    expect(calls[0]!.searchParams.get('entity_type')).toBe(type)
    expect(calls[0]!.searchParams.get('entity_key')).toBe(item.entity_key)
    expect(calls[0]!.searchParams.has('period')).toBe(false)
    await expect(page.locator('#activity')).toContainText(
      'zusammengeführter Verlauf ist für diese Objektart nicht verfügbar',
    )
    if (type === 'team_membership') {
      await expect(
        page.locator('#relations').getByRole('link', { name: 'Benutzer: Anna Beispiel' }),
      ).toBeVisible()
      await expect(page.locator('#relations')).toContainText(
        'ein Beitrittszeitpunkt ist nicht verfügbar',
      )
    }
  })
}

test('findings tools and geocoding share inspector and relationship navigation', async ({
  page,
}) => {
  await page.goto('/findings')
  await page
    .getByRole('button', { name: /^Befund bearbeiten:/ })
    .first()
    .click()
  const dialog = page.getByRole('dialog', { name: 'Test-Hafenbühne', exact: true })
  await expect(dialog.getByRole('link', { name: 'Datensatz untersuchen' })).toHaveAttribute(
    'href',
    /^\/inspect\//,
  )
  await expect(dialog.getByRole('link', { name: 'Aktivität zum Datensatz' })).toHaveAttribute(
    'href',
    /#activity$/,
  )
  await expect(dialog.getByRole('link', { name: 'Beziehungen', exact: true })).toHaveAttribute(
    'href',
    /^\/graph\?/,
  )
  await page.keyboard.press('Escape')
  await page.goto(`/geocoding/${geocodeDetail.id}`)
  const source = page.locator('[data-geocode-source]')
  await expect(source.getByRole('link', { name: 'Datensatz untersuchen' })).toHaveAttribute(
    'href',
    inspectorHref(geocodeDetail.entity_type, geocodeDetail.entity_key)!,
  )
  await expect(source.getByRole('link', { name: 'Beziehungen', exact: true })).toHaveAttribute(
    'href',
    `/graph?root_type=venue&root_key=${geocodeDetail.entity_key}&depth=2`,
  )
})
