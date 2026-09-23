import { test, expect, logout } from '../fixtures/authenticated'
import { findings } from '../fixtures/api'
import { geocodeDetail, geocodePage } from '../fixtures/geocoding'

test('missing-location workflow, retry, global queue and session reset', async ({ page }) => {
  const item = structuredClone(geocodeDetail)
  const requests: string[] = []
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/findings'))
      return route.fulfill({
        json: {
          ...findings,
          items: [
            {
              ...findings.items[0],
              rule: 'venue_missing_location',
              message: 'Veranstaltungsort hat keine Geoposition.',
              location_suggestion_request_id: item.id,
            },
          ],
        },
      })
    if (!url.pathname.includes('/geocode/')) return route.continue()
    requests.push(url.search)
    if (url.pathname.endsWith('/retry')) {
      expect(route.request().method()).toBe('POST')
      expect(route.request().postData()).toBeNull()
      item.status = 'pending'
      item.candidates = []
      item.best_candidate = null
      item.candidate_count = 0
      return route.fulfill({ status: 202, json: { id: item.id, status: 'pending' } })
    }
    if (url.pathname.endsWith('/requests'))
      return route.fulfill({ json: { ...geocodePage, items: [item] } })
    return route.fulfill({ json: item })
  })
  await page.goto('/findings')
  await expect(page.getByRole('link', { name: 'Standortvorschlag prüfen' })).toBeVisible()
  await page
    .getByRole('combobox', { name: 'Regel', exact: true })
    .selectOption('venue_missing_location')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/rule=venue_missing_location/)
  await page.getByRole('link', { name: 'Standortvorschlag prüfen' }).click()
  await expect(page.getByText('100 % Adressübereinstimmung')).toBeVisible()
  await expect(page.getByText('Hausnummer stimmt überein')).toBeVisible()
  await expect(
    page.getByRole('link', { name: /Kandidat 1 auf OpenStreetMap öffnen/ }),
  ).toHaveAttribute('href', 'https://www.openstreetmap.org/way/123')
  await expect(page.getByRole('button', { name: /übernehmen/i })).toHaveCount(0)
  await page.getByRole('button', { name: 'Standort erneut prüfen' }).click()
  await expect(page.getByText('Neue Prüfung wurde eingeplant.')).toBeVisible()
  await expect(page.getByText('Prüfung vorgemerkt.', { exact: false })).toBeVisible()
  await page.getByRole('link', { name: 'Alle Standortvorschläge' }).click()
  await page.getByRole('combobox', { name: 'Status', exact: true }).selectOption('ambiguous')
  await page.getByRole('combobox', { name: 'Entität', exact: true }).selectOption('venue')
  await page.getByRole('button', { name: 'Filter anwenden' }).click()
  await expect(page).toHaveURL(/status=ambiguous/)
  await page.getByRole('button', { name: /Gebiet: Alle/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Gebiet auswählen', exact: true })
  await dialog.getByRole('combobox', { name: 'Administratives Gebiet suchen' }).fill('Flensburg')
  await dialog.getByRole('option').getByRole('button').click()
  await expect(page.getByRole('button', { name: /Gebiet: Flensburg/ })).toBeVisible()
  await expect(
    page.getByText(/Fehlende Positionen sind keinem Gebiet sicher zuordenbar/),
  ).toBeVisible()
  expect(new URL(page.url()).searchParams.has('geo_scope_id')).toBe(false)
  expect(requests.every((q) => !q.includes('geo_scope_id'))).toBe(true)
  await logout(page)
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByText('Test-Hafenbühne')).toHaveCount(0)
  await page.getByLabel('Benutzername', { exact: true }).fill('operator')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('button', { name: /Gebiet: Alle/ })).toBeVisible()
})

test('detail compares candidates and presents each workflow state without mobile overflow', async ({
  page,
}, info) => {
  const item = structuredClone(geocodeDetail)
  await page.route('**/api/admin/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/admins'))
      return route.fulfill({ json: { items: [], admin_timezone: 'Europe/Berlin' } })
    if (url.pathname.endsWith('/assignments')) return route.fulfill({ json: null })
    if (url.pathname.includes('/geocode/requests/')) return route.fulfill({ json: item })
    return route.continue()
  })
  item.status = 'ambiguous'
  item.candidates.push({
    ...item.candidates[0]!,
    id: '00000000-0000-4000-8000-000000000903',
    rank: 2,
    latitude: 54.674079,
    longitude: 9.790914,
    display_name: 'Holzstraße 14, Wagersrott',
  })
  item.candidate_count = 2
  await page.goto(`/geocoding/${item.id}`)
  await expect(page.getByRole('heading', { name: item.entity_name })).toBeVisible()
  await expect(
    page.getByText('Mehrere mögliche Standorte wurden gefunden.', { exact: false }),
  ).toBeVisible()
  await expect(page.getByRole('region', { name: 'Karte der Standortkandidaten' })).toBeVisible()
  await expect(page.locator('.leaflet-container')).toBeVisible()
  await expect(page.locator('.leaflet-tile-loaded').first()).toBeVisible()
  await expect(page.locator('.candidate-map-marker')).toHaveCount(2)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('geocoding-map.png'), fullPage: true })
  const secondMarker = page.getByRole('button', { name: /Kandidat 2 auf der Karte:/ })
  await secondMarker.click()
  await expect(secondMarker).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('listitem').filter({ hasText: 'Holzstraße 14' })).toHaveAttribute(
    'aria-current',
    'true',
  )
  await expect(page.locator('li[aria-current="true"]')).toBeFocused()
  await page.getByRole('button', { name: 'Kandidat 1 auf der Karte zeigen', exact: true }).click()
  await expect(page.locator('.leaflet-container')).toBeFocused()
  await expect(page.getByRole('button', { name: /Kandidat 1 auf der Karte:/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: 'Alle Kandidaten zeigen' }).click()
  await expect(secondMarker).toBeVisible()
  await page.getByRole('button', { name: 'Vergrößern', exact: true }).click()
  await page.getByRole('button', { name: 'Verkleinern', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Ort öffnen' })).toHaveAttribute(
    'href',
    `/venues/${item.entity_key}`,
  )
  await expect(
    page.getByText('Derzeit ist kein aktiver Systemadministrator', { exact: false }),
  ).toBeVisible()

  for (const [status, message] of [
    ['not_found', 'Für diese Adresse wurde kein passender Standort gefunden.'],
    ['insufficient_input', 'Für eine zuverlässige Standortsuche fehlen ausreichende Adressdaten.'],
    ['failed', 'Standortprüfung fehlgeschlagen.'],
    ['pending', 'Prüfung vorgemerkt.'],
    ['checking', 'Prüfung läuft.'],
  ] as const) {
    item.status = status
    item.candidates = []
    item.best_candidate = null
    item.candidate_count = 0
    await page.reload()
    await expect(page.getByText(message, { exact: false }).first()).toBeVisible()
    await expect(page.getByRole('region', { name: 'Karte der Standortkandidaten' })).toHaveCount(0)
  }
  await expect(page.getByRole('button', { name: 'Prüfstand aktualisieren' })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('real proxy enforces bodyless retry and forwards Origin/CSRF to protected backend', async ({
  page,
  request,
}) => {
  const path = `/api/admin/api/v1/geocode/requests/${geocodeDetail.id}/retry`
  const origin = { Origin: 'http://127.0.0.1:3100', 'X-Admin-CSRF': '1' }
  expect((await request.post(path, { headers: origin })).status()).toBe(401)
  // APIRequestContext lacks Chromium's Secure-cookie exception for loopback HTTP.
  const cookie = (await page.context().cookies()).find((item) =>
    item.name.endsWith('admin_session'),
  )!
  const valid = { ...origin, Cookie: `${cookie.name}=${cookie.value}` }
  expect(
    (
      await page.request.post(path, { headers: { ...valid, Origin: 'https://evil.test' } })
    ).status(),
  ).toBe(403)
  expect(
    (
      await page.request.post(path, { headers: { Origin: valid.Origin, Cookie: valid.Cookie } })
    ).status(),
  ).toBe(403)
  for (const data of [{}, { address: 'override' }, { lat: 54, lon: 9 }, { provider: 'evil' }]) {
    expect((await page.request.post(path, { headers: valid, data })).status()).toBe(422)
  }
  expect((await page.request.post(`${path}?host=evil`, { headers: valid })).status()).toBe(422)
  expect(
    (
      await page.request.get('/api/admin/api/v1/geocode/requests?geo_scope_id=bad', {
        headers: valid,
      })
    ).status(),
  ).toBe(422)
  const response = await page.request.post(path, { headers: valid })
  expect(response.status()).toBe(409)
  expect((await response.json()).error.code).toBe('geocode_no_longer_needed')
})

test('tile failure leaves the complete candidate list usable', async ({ page }) => {
  await page.route('https://tile.openstreetmap.org/**', (route) => route.abort())
  await page.route('**/api/admin/api/v1/geocode/requests/*', (route) =>
    route.fulfill({ json: geocodeDetail }),
  )
  await page.goto(`/geocoding/${geocodeDetail.id}`)
  await expect(page.getByText('Karte konnte nicht geladen werden.', { exact: false })).toBeVisible()
  await expect(
    page.getByRole('heading', { name: geocodeDetail.candidates[0]!.display_name }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Kandidat 1 auf der Karte zeigen', exact: true }).click()
  await expect(page.locator('li[aria-current="true"]')).toBeVisible()
  await expect(
    page.getByRole('link', { name: /Kandidat 1 auf OpenStreetMap öffnen/ }),
  ).toBeVisible()
})

test('map loads in production CSP without workers, eval or extra inline policy', async ({
  page,
}) => {
  test.skip(process.env.TEST_PRODUCTION !== '1', 'Requires production client build')
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.addInitScript(() => {
    const state = window as typeof window & { violations: string[] }
    state.violations = []
    document.addEventListener('securitypolicyviolation', (event) =>
      state.violations.push(event.effectiveDirective),
    )
  })
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.fallback()
    const response = await route.fetch()
    return route.fulfill({
      response,
      headers: {
        ...response.headers(),
        'content-security-policy':
          "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; worker-src 'none'; object-src 'none'; base-uri 'self'",
      },
    })
  })
  await page.route('**/api/admin/api/v1/geocode/requests/*', (route) =>
    route.fulfill({ json: geocodeDetail }),
  )
  await page.goto(`/geocoding/${geocodeDetail.id}`)
  await expect(page.locator('.leaflet-tile-loaded').first()).toBeVisible()
  await expect(page.locator('.candidate-map-marker')).toHaveCount(1)
  await expect(page.locator('.leaflet-tile-loaded').first()).toHaveAttribute(
    'src',
    /^https:\/\/tile\.openstreetmap\.org\/16\/\d+\/\d+\.png$/,
  )
  const requests: string[] = []
  page.on('request', (request) => {
    if (request.url().startsWith('https://tile.openstreetmap.org/')) requests.push(request.url())
  })
  await page.getByRole('button', { name: 'Vergrößern', exact: true }).click()
  await expect.poll(() => requests.length).toBeGreaterThan(0)
  expect(errors).toEqual([])
  expect(
    await page.evaluate(() => (window as typeof window & { violations: string[] }).violations),
  ).toEqual([])
})
