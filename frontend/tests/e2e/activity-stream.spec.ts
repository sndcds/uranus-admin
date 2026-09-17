import { test, expect } from '../fixtures/authenticated'
import { activityFixture } from '../fixtures/activity'
const org = '10000000-0000-4000-8000-000000000010'

test('compact activity groups, visible-page summary, accessible targets and pagination', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.route('**/api/admin/api/v1/dashboard/activity**', (route) => {
    const query = new URL(route.request().url()).searchParams
    return route.fulfill({
      json: {
        ...activityFixture,
        pagination: { ...activityFixture.pagination, page: Number(query.get('page') ?? 1) },
      },
    })
  })
  await page.goto(`/activity?period=7d&organization_id=${org}&page_size=20`)
  await expect(page.getByRole('heading', { name: 'Heute', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Gestern', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '13. September 2026', exact: true })).toBeVisible()
  await expect(page.getByText('80 Datensätze insgesamt')).toBeVisible()
  await expect(page.getByText('Auf dieser Seite: 20 Einträge')).toBeVisible()
  await expect(
    page
      .getByRole('combobox', { name: 'Objektart', exact: true })
      .locator('option[value="event_date"]'),
  ).toHaveText('Termin')
  const row = page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name: 'Lesung am Hafen', exact: true }) })
  await expect(row.getByText('Termin', { exact: true })).toBeVisible()
  await expect(row.getByText('Veröffentlicht', { exact: true })).toBeVisible()
  await expect(
    row.getByRole('link', { name: 'Im Admin ansehen: Lesung am Hafen' }),
  ).toHaveAttribute('href', activityFixture.items[0]!.action!.href)
  await expect(
    row.getByRole('link', { name: 'Markierungen & Notizen zu Lesung am Hafen' }),
  ).toHaveAttribute('href', /\/marks\?.*entity_type=event_date/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await expect(page.getByText('Seite 1 von 4')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Zurück', exact: true })).toBeDisabled()
  await page.getByRole('link', { name: 'Weiter', exact: true }).click()
  await expect(page.getByText('Seite 2 von 4')).toBeVisible()
  const query = new URL(page.url()).searchParams
  expect(query.get('page_size')).toBe('20')
  expect(query.get('organization_id')).toBe(org)
  expect(query.get('period')).toBe('7d')
  await page.getByRole('link', { name: 'Zurück', exact: true }).click()
  await expect(page.getByText('Seite 1 von 4')).toBeVisible()
})

test('unknown timestamps, filter reset and browser navigation keep URL and form synchronized', async ({
  page,
}) => {
  const queries: URLSearchParams[] = []
  await page.route('**/api/admin/api/v1/dashboard/activity**', (route) => {
    const query = new URL(route.request().url()).searchParams
    queries.push(query)
    const unknown = query.get('timestamp_state') === 'unknown'
    return route.fulfill({
      json: {
        ...activityFixture,
        items: [
          {
            ...activityFixture.items[1]!,
            entity_name: 'Beispielbild',
            created_at: unknown ? null : activityFixture.items[1]!.created_at,
            action: null,
          },
        ],
        timestamp_state: unknown ? 'unknown' : 'known',
        pagination: { page: 1, page_size: 20, total: 1, pages: 1 },
      },
    })
  })
  await page.goto(`/activity?entity_type=image&organization_id=${org}&timestamp_state=unknown`)
  await expect(page.getByRole('heading', { name: 'Beispielbild' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Zeitraum', exact: true })).toHaveValue('unknown')
  await expect(
    page.getByText('Nach Objektschlüssel geordnet; eine zeitliche Reihenfolge ist nicht bekannt.'),
  ).toBeVisible()
  await expect(page.locator('h3[id^="activity-day-"]')).toHaveCount(0)
  await expect(page.locator('time')).toHaveCount(0)
  await expect(page.getByText('Keine eindeutige Organisation')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Weiter', exact: true })).toBeDisabled()
  await page.getByRole('combobox', { name: 'Zeitraum', exact: true }).selectOption('7d')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/timestamp_state=known/)
  await expect(page.getByRole('heading', { name: 'Heute', exact: true })).toBeVisible()
  expect(queries.at(-1)!.get('entity_type')).toBe('image')
  expect(queries.at(-1)!.get('organization_id')).toBe(org)
  expect(queries.at(-1)!.get('period')).toBe('7d')
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(page).toHaveURL('/activity')
  await expect(page.getByRole('combobox', { name: 'Objektart', exact: true })).toHaveValue('')
  await expect(page.getByRole('textbox', { name: 'Organisation (UUID)' })).toHaveValue('')
  await expect(page.getByRole('combobox', { name: 'Zeitraum', exact: true })).toHaveValue('24h')
  await page.goBack()
  await expect(page.getByRole('combobox', { name: 'Objektart', exact: true })).toHaveValue('image')
  await expect(page.getByRole('textbox', { name: 'Organisation (UUID)' })).toHaveValue(org)
  await expect(page.getByRole('combobox', { name: 'Zeitraum', exact: true })).toHaveValue('7d')
})

test('loading, error retry and an empty page remain usable', async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let requests = 0
  await page.route('**/api/admin/api/v1/dashboard/activity**', async (route) => {
    requests++
    if (requests === 1) {
      await gate
      return route.fulfill({
        status: 503,
        json: { error: { code: 'database_unavailable', message: 'Synthetic unavailable' } },
      })
    }
    return route.fulfill({
      json: {
        ...activityFixture,
        items: [],
        pagination: { page: 1, page_size: 20, total: 0, pages: 0 },
      },
    })
  })
  await page.goto('/activity')
  await expect(page.getByText('Daten werden geladen …', { exact: true })).toBeVisible()
  release()
  await expect(page.getByRole('alert')).toContainText('Abruf fehlgeschlagen')
  await page.getByRole('button', { name: 'Erneut versuchen', exact: true }).click()
  await expect(page.getByText('Keine Datensätze für diese Filter.')).toBeVisible()
  await expect(page.getByText('Auf dieser Seite: 0 Einträge')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Activity-Seitennavigation' })).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
})
