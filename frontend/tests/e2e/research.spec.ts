import { test, expect } from '../fixtures/authenticated'
import {
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
      return route.fulfill({ json: { categories: [{ id: 2, name: 'Konzert' }] } })
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
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'CSV exportieren' }).click()
  const file = await (await download).path()
  expect(await readFile(file!, 'utf8')).toContain('Jazzabend')
  await page.getByRole('button', { name: 'Recherche-Link kopieren' }).click()
  await expect(page.getByText('Kopiert.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(page.url())
  await page.reload()
  await expect(page.getByText('3 Ergebnisse insgesamt')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Stadt: Flensburg entfernen' })).toBeVisible()
  await page.getByRole('button', { name: 'Stadt: Flensburg entfernen' }).click()
  await expect(page).not.toHaveURL(/city=/)
  await page.getByLabel('Treffer durchsuchen').fill('missing')
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
  const detail = researchDetail()
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
