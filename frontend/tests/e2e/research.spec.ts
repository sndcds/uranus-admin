import { test, expect } from '../fixtures/authenticated'
import {
  researchCategories,
  researchDetail,
  researchEvent,
  researchOrganization,
  researchPage,
  researchVenue,
} from '../fixtures/research'
import { readFile } from 'node:fs/promises'
import { enforceProductionCsp } from '../fixtures/record-csp'

const root = '/api/admin/api/v1/research'
test.beforeEach(async ({ page, context }) => {
  const login = await context.request.post('/api/admin/auth/login', {
    headers: { Origin: 'http://127.0.0.1:3100', 'X-Admin-CSRF': '1' },
    data: { login: 'journalist', password: 'test-only-password' },
  })
  expect(login.status()).toBe(200)
  await page.route('**/api/admin/api/v1/research/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/options'))
      return route.fulfill({ json: { categories: researchCategories } })
    if (url.pathname.endsWith('/export'))
      return route.fulfill({
        json: {
          columns: ['event_uuid', 'title'],
          rows: [{ event_uuid: researchEvent.entity_key, title: researchEvent.name }],
          total: 1,
          observed_at: '2026-09-26T10:00:00Z',
        },
      })
    if (url.pathname.endsWith('/search')) {
      const kind = url.searchParams.get('entity_type')
      const items =
        kind === 'venue'
          ? [researchVenue]
          : kind === 'organization'
            ? [researchOrganization]
            : researchPage().items
      return route.fulfill({
        json: researchPage(url.searchParams.get('q') === 'missing' ? [] : items),
      })
    }
    const kind = url.pathname.includes('/venues/')
      ? 'venue'
      : url.pathname.includes('/organizations/')
        ? 'organization'
        : 'event'
    return route.fulfill({ json: researchDetail(kind) })
  })
})

test('journalist landing, isolated navigation, direct Operations redirect and API denial', async ({
  page,
  context,
}, info) => {
  await page.goto('/research')
  await expect(page.getByRole('heading', { name: 'Kulturbytes Recherche', level: 2 })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Operations', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Globale Suche öffnen' })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('research-desktop.png'), fullPage: true })
  await page.goto('/sql')
  await expect(page).toHaveURL(/\/research$/)
  // Direct requests go through the real fixture server's role boundary, not page mocks.
  const cookie = (await context.cookies()).find((item) => item.name.endsWith('admin_session'))!
  const denied = await context.request.get('/api/admin/api/v1/findings', {
    headers: { Cookie: `${cookie.name}=${cookie.value}` },
  })
  expect(denied.status()).toBe(403)
  if (info.project.name === 'mobile') {
    await page.getByRole('button', { name: 'Recherche-Menü öffnen' }).click()
    await expect(
      page.getByRole('dialog').getByRole('link', { name: 'Suche', exact: true }),
    ).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'Recherche-Menü öffnen' })).toBeFocused()
  }
})

test('search, URL filters, map, table, selected detail, export and permalink', async ({
  page,
  context,
}, info) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto(
    '/research/search?city=Flensburg&from_date=2026-01-01&to_date=2026-06-30&category=2',
  )
  await expect(page.getByText('3 Ergebnisse insgesamt')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Stadt: Flensburg entfernen' })).toBeVisible()
  await expect(page.getByRole('searchbox').filter({ visible: true })).toHaveCount(1)
  await expect(
    page.getByRole('button', {
      name: info.project.name === 'mobile' ? 'Liste' : 'Karte',
      exact: true,
    }),
  ).toHaveAttribute('aria-pressed', 'true')
  if (info.project.name === 'desktop')
    await expect(page.locator('.research-map-popup')).toBeVisible()
  await page.screenshot({
    path: info.outputPath(
      info.project.name === 'mobile' ? 'mobile-search.png' : 'search-split-view.png',
    ),
    fullPage: true,
  })
  await page.getByRole('button', { name: 'Karte', exact: true }).click()
  await expect(page.locator('.candidate-map-marker').first()).toBeVisible()
  await page.getByRole('button', { name: 'Tabelle', exact: true }).click()
  await expect(page.getByRole('table', { name: 'Recherche-Ergebnisse' })).toBeVisible()
  await page.getByRole('button', { name: 'Liste', exact: true }).click()
  await page.getByRole('button', { name: 'Vorschau: Indie Night' }).click()
  await expect(page.getByRole('heading', { name: 'Indie Night' })).toBeVisible()
  await page.getByRole('button', { name: 'Treffer-Link kopieren' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    `${new URL(page.url()).origin}/research/events/20000000-0000-4000-8000-000000000003?from_date=2026-01-01&to_date=2026-06-30`,
  )
  await page.getByRole('button', { name: 'Auf Karte anzeigen', exact: true }).click()
  await expect(page.locator('.research-map-popup')).toContainText('Indie Night')
  await expect(
    page.locator('.research-map-popup a', { hasText: 'Details anzeigen' }),
  ).toHaveAttribute('href', '/research/events/20000000-0000-4000-8000-000000000003')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'CSV exportieren' }).click()
  const file = await (await download).path()
  expect(await readFile(file!, 'utf8')).toContain('Jazzabend')
  await page.getByRole('button', { name: 'Recherche-Link kopieren' }).click()
  await expect(
    page
      .locator('span')
      .filter({ has: page.getByRole('button', { name: 'Recherche-Link kopieren' }) })
      .getByRole('status'),
  ).toHaveText('Kopiert.')
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(page.url())
  await page.reload()
  await expect(page.getByText('3 Ergebnisse insgesamt')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Stadt: Flensburg entfernen' })).toBeVisible()
  await page.getByRole('button', { name: 'Stadt: Flensburg entfernen' }).click()
  await expect(page).not.toHaveURL(/city=/)
  await page
    .getByLabel('Veranstaltungen, Orte, Organisationen suchen', { exact: true })
    .fill('missing')
  await expect(page.getByText(/Keine Treffer für diese Filter/)).toBeVisible()
})

for (const [section, kind, id, name] of [
  ['events', 'event', researchEvent.entity_key, researchEvent.name],
  ['venues', 'venue', researchVenue.entity_key, researchVenue.name],
  ['organizations', 'organization', researchOrganization.entity_key, researchOrganization.name],
] as const) {
  test(`${kind} dossier, relations and honest timeline`, async ({ page }, info) => {
    await page.goto(`/research/${section}/${id}`)
    await expect(page.getByRole('heading', { name, exact: true, level: 2 })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Datenstand / Quellen' })).toBeVisible()
    await expect(page.getByText('Welche Felder geändert wurden, ist nicht belegt.')).toBeVisible()
    await page.getByRole('button', { name: 'Graph', exact: true }).click()
    await expect(page.locator('.graph-node').first()).toBeVisible()
    await page.getByRole('button', { name: 'Liste', exact: true }).click()
    await expect(page.getByRole('link', { name: 'SQL / Datenherkunft' })).toHaveCount(0)
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    await page.evaluate(() => {
      ;(document.activeElement as HTMLElement | null)?.blur()
      window.scrollTo(0, 0)
    })
    await page.screenshot({
      path: info.outputPath(`${info.project.name}-${kind}-dossier.png`),
      fullPage: true,
    })
  })
}

test('safe error and retry, invalid URL and mobile filter dialog', async ({ page }, info) => {
  await page.route(`**${root}/search?**`, (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: 'database_unavailable', message: 'SQL secret' } },
    }),
  )
  await page.goto('/research/search?city=Flensburg')
  await expect(page.getByText('Abruf fehlgeschlagen')).toBeVisible()
  await expect(page.getByText('SQL secret')).toHaveCount(0)
  await page.goto('/research/search?status=draft')
  await expect(page.getByText(/Die Filter-URL ist ungültig/)).toBeVisible()
  if (info.project.name === 'mobile') {
    await expect(page.getByRole('button', { name: 'Recherche-Link kopieren' })).toBeEnabled()
    await page.getByRole('button', { name: 'Filter öffnen' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Stadt', { exact: true }).fill('Husum')
    await dialog.getByRole('button', { name: 'Filter anwenden' }).click()
    await expect(page).toHaveURL(/city=Husum/)
  }
})

test('journalist signs in through the shared login and admin can switch workspaces', async ({
  page,
  context,
}) => {
  await context.clearCookies()
  await page.goto('/login')
  await page.getByLabel('Benutzername', { exact: true }).fill('journalist')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page).toHaveURL(/\/research$/)
  await page.getByRole('button', { name: 'Nutzerbereich öffnen' }).click()
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await page.getByLabel('Benutzername', { exact: true }).fill('operator')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page).toHaveURL(/\/?period=24h/)
  await page.goto('/research/search')
  await expect(page.getByText('3 Ergebnisse insgesamt')).toBeVisible()
  if ((page.viewportSize()?.width ?? 1440) < 1024)
    await page.getByRole('button', { name: 'Recherche-Menü öffnen' }).click()
  await expect(
    page.getByRole('link', { name: 'Operations', exact: true }).filter({ visible: true }),
  ).toBeVisible()
})

test('research Markdown and contracts stay inert under production CSP', async ({ page }) => {
  await enforceProductionCsp(page)
  const detail = structuredClone(researchDetail())
  detail.item.description =
    '<script>alert(1)</script>\n\n[unsafe](javascript:alert%281%29)\n\n[Operations](/sql)'
  detail.item.location = null
  for (const date of detail.dates.items) date.location = null
  await page.route(`**${root}/events/${detail.item.entity_key}**`, (route) =>
    route.fulfill({ json: detail }),
  )
  await page.route(`**${root}/options`, (route) => route.fulfill({ json: { categories: [] } }))
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto(`/research/events/${detail.item.entity_key}`)
  const overview = page.getByRole('region', { name: 'Überblick', exact: true })
  await expect(overview).toContainText('<script>alert(1)</script>')
  await expect(overview.locator('script, iframe, [onerror], a[href="/sql"]')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Datenstand / Quellen' })).toBeVisible()
  expect(errors).toEqual([])
})

test('header search preserves filters and history; secondary filters remain in their dialog', async ({
  page,
}, info) => {
  await page.goto('/research/search?city=Flensburg&from_date=2026-01-01&to_date=2026-06-30')
  await expect(page.getByText('3 Ergebnisse insgesamt')).toBeVisible()
  const search = page.getByLabel('Veranstaltungen, Orte, Organisationen suchen', { exact: true })
  await search.fill('Jazz')
  await expect(page).toHaveURL(/q=Jazz/)
  expect(new URL(page.url()).searchParams.get('city')).toBe('Flensburg')
  expect(new URL(page.url()).searchParams.get('from_date')).toBe('2026-01-01')
  expect(new URL(page.url()).searchParams.get('to_date')).toBe('2026-06-30')
  await page.goBack()
  await expect(search).toHaveValue('')
  await expect(page).not.toHaveURL(/q=/)
  await expect(page.getByRole('searchbox').filter({ visible: true })).toHaveCount(1)
  if (info.project.name === 'desktop') {
    await page.getByLabel('Status', { exact: true }).selectOption('cancelled')
    await expect(page).toHaveURL(/status=cancelled/)
    await expect(page.getByRole('button', { name: 'Status: Abgesagt entfernen' })).toBeVisible()
  }
  await page
    .getByRole('button', {
      name: info.project.name === 'mobile' ? 'Filter öffnen' : 'Weitere Filter',
      exact: true,
    })
    .click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('Organisation', { exact: true })).toBeVisible()
  await expect(dialog.getByLabel('Ort', { exact: true })).toBeVisible()
  await dialog.getByLabel('Datensatztyp', { exact: true }).selectOption('venue')
  await dialog.getByRole('button', { name: 'Filter anwenden' }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page).toHaveURL(/entity_type=venue/)
  expect(new URL(page.url()).searchParams.get('city')).toBe('Flensburg')
  await page.getByRole('button', { name: 'Karte', exact: true }).click()
  await expect(page.locator('.research-map-popup')).toContainText('3 Veranstaltungen im Filter')
  await expect(page.locator('.research-map-popup img')).toHaveCount(0)
  await page.getByRole('button', { name: 'Alle Filter zurücksetzen', exact: true }).click()
  await expect(page).not.toHaveURL(/city=|entity_type=|status=|from_date=|to_date=/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

for (const [section, title, count] of [
  ['map', 'Karte', 3],
  ['events', 'Veranstaltungen', 3],
  ['venues', 'Orte', 1],
  ['organizations', 'Organisationen', 1],
] as const) {
  test(`${section} collection keeps the research presentation and navigation`, async ({
    page,
  }, info) => {
    await page.goto(`/research/${section}`)
    await expect(page.getByRole('heading', { name: title, exact: true, level: 2 })).toBeVisible()
    await expect(page.getByText(`${count} Ergebnisse insgesamt`)).toBeVisible()
    await expect(page.getByRole('searchbox').filter({ visible: true })).toHaveCount(1)
    if (info.project.name === 'desktop' || section === 'map')
      await expect(page.locator('.research-map-popup')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({
      path: info.outputPath(`${info.project.name}-${section}.png`),
      fullPage: true,
    })
  })
}

test('public image fills preview and dossier without being reused as a venue photo', async ({
  page,
}, info) => {
  const imageUrl = 'https://assets.example.invalid/research.png'
  const item = { ...researchEvent, image_url: imageUrl }
  const detail = structuredClone(researchDetail())
  detail.item = item
  await page.route(imageUrl, (route) =>
    route.fulfill({
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><rect width="400" height="500" fill="#dbeafe"/><text x="30" y="250" fill="#1e3a8a">Synthetisches Testbild</text></svg>',
    }),
  )
  await page.route(
    (url) => url.pathname === `${root}/search`,
    (route) => route.fulfill({ json: researchPage([item]) }),
  )
  await page.route(`**${root}/events/${item.entity_key}**`, (route) =>
    route.fulfill({ json: detail }),
  )
  await page.goto('/research/search')
  const previewImage = page.getByRole('region', { name: 'Ausgewählter Treffer' }).locator('img')
  await previewImage.scrollIntoViewIfNeeded()
  await expect(previewImage).toBeVisible()
  await expect(previewImage).toHaveAttribute('referrerpolicy', 'no-referrer')
  await expect
    .poll(() => previewImage.evaluate((image: HTMLImageElement) => image.naturalWidth))
    .toBe(400)
  await page.getByRole('link', { name: 'Vollständige Details', exact: true }).click()
  const overview = page.getByRole('region', { name: 'Überblick', exact: true })
  await expect(overview.locator('img')).toHaveAttribute('src', imageUrl)
  await expect(overview.locator('img')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: info.outputPath(`${info.project.name}-event-image.png`),
    fullPage: true,
  })
  await page.getByRole('button', { name: /Treffer 1 auf der Karte:/ }).click()
  await expect(page.locator('.research-map-popup')).toBeVisible()
  await expect(page.locator('.research-map-popup img')).toHaveCount(0)
})

test('table selection updates the preview with keyboard controls and preserves the URL', async ({
  page,
}, info) => {
  await page.goto('/research/search?q=Jazz&from_date=2026-01-01&view=table')
  const table = page.getByRole('table', { name: 'Recherche-Ergebnisse' })
  await expect(table.getByRole('row')).toHaveCount(4)
  const choice = table.getByRole('button', { name: 'Vorschau: Indie Night' })
  await choice.focus()
  await page.keyboard.press('Enter')
  await expect(choice).toHaveAttribute('aria-pressed', 'true')
  await expect(table.locator('button[aria-pressed="true"]')).toHaveCount(1)
  await expect(
    page
      .getByRole('region', { name: 'Ausgewählter Treffer' })
      .getByRole('heading', { name: 'Indie Night' }),
  ).toBeVisible()
  expect(new URL(page.url()).searchParams.get('q')).toBe('Jazz')
  expect(new URL(page.url()).searchParams.get('from_date')).toBe('2026-01-01')
  expect(new URL(page.url()).searchParams.get('view')).toBe('table')
  const target = await choice.boundingBox()
  expect(target!.height).toBeGreaterThanOrEqual(44)
  expect(target!.width).toBeGreaterThanOrEqual(44)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.evaluate(() => {
    ;(document.activeElement as HTMLElement | null)?.blur()
    window.scrollTo(0, 0)
  })
  await page.screenshot({ path: info.outputPath(`${info.project.name}-table.png`), fullPage: true })
})

test('cancelled secondary filters stay unapplied and the period chip clears both dates', async ({
  page,
}, info) => {
  await page.goto('/research/search?city=Flensburg&from_date=2026-01-01&to_date=2026-06-30')
  await expect(page.getByText('3 Ergebnisse insgesamt')).toBeVisible()
  const trigger = page.getByRole('button', {
    name: info.project.name === 'mobile' ? 'Filter öffnen' : 'Weitere Filter',
    exact: true,
  })
  await trigger.click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Datensatztyp', { exact: true }).selectOption('venue')
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()
  await expect(page).not.toHaveURL(/entity_type=venue/)
  if (info.project.name === 'desktop') {
    await page.getByLabel('Stadt', { exact: true }).fill('Husum')
    await page.getByLabel('Stadt', { exact: true }).press('Tab')
  } else {
    await trigger.click()
    await dialog.getByLabel('Stadt', { exact: true }).fill('Husum')
    await dialog.getByRole('button', { name: 'Filter anwenden' }).click()
  }
  await expect(page).toHaveURL(/city=Husum/)
  await expect(page).not.toHaveURL(/entity_type=venue/)
  await page.getByRole('button', { name: /^Zeitraum:.*entfernen$/ }).click()
  await expect(page).not.toHaveURL(/from_date=|to_date=/)
  await expect(page).toHaveURL(/city=Husum/)
})

test('canonical category accents in results, preview, filters and dossiers', async ({
  page,
}, info) => {
  const colors = [
    ['Kultur', 'rgb(242, 13, 94)'],
    ['Bildung', 'rgb(255, 122, 83)'],
    ['Sport', 'rgb(243, 181, 42)'],
    ['Freizeit', 'rgb(4, 193, 141)'],
    ['Familie', 'rgb(9, 186, 236)'],
    ['Gesellschaft', 'rgb(26, 113, 228)'],
  ] as const
  await page.goto('/research/search?category=2')
  for (const [name, color] of colors) {
    const badges = page.locator('.research-category').filter({ hasText: name })
    await expect(badges.first()).toBeVisible()
    for (const badge of await badges.all())
      await expect(badge.locator('[aria-hidden="true"]')).toHaveCSS('background-color', color)
  }
  await expect(
    page.getByRole('button', { name: 'Kategorie: Bildung entfernen' }).locator('i'),
  ).toHaveCSS('background-color', 'rgb(255, 122, 83)')
  await expect(page.locator('.research-type').first()).toHaveText('Veranstaltung')
  await expect(page.locator('.research-type [aria-hidden]')).toHaveCount(0)
  await expect(page.locator('span').filter({ hasText: /^Abgesagt$/ })).toHaveClass(/text-rose-700/)

  const detail = structuredClone(researchDetail())
  detail.item.categories = [...researchCategories, { id: 772, name: 'Weitere Kategorie' }]
  await page.route(`**${root}/events/${researchEvent.entity_key}`, (route) =>
    route.fulfill({ json: detail }),
  )
  await page.goto(`/research/events/${researchEvent.entity_key}`)
  for (const [name, color] of colors)
    await expect(
      page.locator('.research-category').filter({ hasText: name }).locator('[aria-hidden="true"]'),
    ).toHaveCSS('background-color', color)
  await expect(
    page
      .locator('.research-category')
      .filter({ hasText: 'Weitere Kategorie' })
      .locator('[aria-hidden="true"]'),
  ).toHaveCSS('background-color', 'rgb(100, 116, 139)')
  await page.screenshot({ path: info.outputPath('category-colors.png'), fullPage: true })
  await page.goto(`/research/organizations/${researchOrganization.entity_key}`)
  await expect(
    page
      .locator('.research-category')
      .filter({ hasText: 'Kultur' })
      .last()
      .locator('[aria-hidden="true"]'),
  ).toHaveCSS('background-color', 'rgb(242, 13, 94)')
})
