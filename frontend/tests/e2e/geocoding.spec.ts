import { test, expect } from '../fixtures/authenticated'
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
  await expect(page.getByText('Übereinstimmung: 100 %')).toBeVisible()
  await expect(page.getByText('Hausnummer stimmt überein')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Auf OpenStreetMap ansehen' })).toHaveAttribute(
    'href',
    'https://www.openstreetmap.org/way/123',
  )
  await expect(page.getByRole('button', { name: /übernehmen/i })).toHaveCount(0)
  await page.getByRole('button', { name: 'Standort erneut prüfen' }).click()
  await expect(page.getByText('Neue Prüfung wurde eingeplant.')).toBeVisible()
  await expect(page.getByText('Standort wird geprüft.', { exact: true })).toBeVisible()
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
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByText('Test-Hafenbühne')).toHaveCount(0)
  await page.getByLabel('Benutzername', { exact: true }).fill('operator')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('button', { name: /Gebiet: Alle/ })).toBeVisible()
})

test('real proxy enforces bodyless retry and forwards Origin/CSRF to protected backend', async ({
  page,
  request,
}) => {
  const path = `/api/admin/api/v1/geocode/requests/${geocodeDetail.id}/retry`
  const valid = { Origin: 'http://127.0.0.1:3100', 'X-Admin-CSRF': '1' }
  expect((await request.post(path, { headers: valid })).status()).toBe(401)
  expect(
    (
      await page.request.post(path, { headers: { ...valid, Origin: 'https://evil.test' } })
    ).status(),
  ).toBe(403)
  expect((await page.request.post(path, { headers: { Origin: valid.Origin } })).status()).toBe(403)
  for (const data of [{}, { address: 'override' }, { lat: 54, lon: 9 }, { provider: 'evil' }]) {
    expect((await page.request.post(path, { headers: valid, data })).status()).toBe(422)
  }
  expect((await page.request.post(`${path}?host=evil`, { headers: valid })).status()).toBe(422)
  expect(
    (await page.request.get('/api/admin/api/v1/geocode/requests?geo_scope_id=bad')).status(),
  ).toBe(422)
  const response = await page.request.post(path, { headers: valid })
  expect(response.status()).toBe(409)
  expect((await response.json()).error.code).toBe('geocode_no_longer_needed')
})
