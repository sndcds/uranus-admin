import { test, expect } from '../fixtures/authenticated'
import { entityFixture } from '../fixtures/entities'
import { venueScopeLabels } from '../../app/utils/venues'

test('venue scope survives apply, pagination, history and reload and stays out of spaces', async ({
  page,
}, info) => {
  const requests: URL[] = []
  let empty = false
  await page.route('**/api/admin/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    requests.push(url)
    const section = url.pathname.endsWith('/spaces') ? 'spaces' : 'venues'
    const fixture = entityFixture(section)
    return route.fulfill({
      json: {
        ...fixture,
        items: empty
          ? []
          : fixture.items.map((item) => ({
              ...item,
              venue_scope: section === 'venues' ? url.searchParams.get('scope') || 'shared' : null,
            })),
        pagination: {
          ...fixture.pagination,
          page: Number(url.searchParams.get('page') || 1),
          ...(empty ? { total: 0, pages: 0 } : {}),
        },
      },
    })
  })
  await page.goto('/venues')
  const scope = page.getByRole('combobox', { name: 'Ortstyp', exact: true })
  await expect(scope).toBeVisible()
  await expect(scope.locator('option')).toHaveText([
    'Alle',
    venueScopeLabels.organization,
    venueScopeLabels.shared,
  ])
  const summary = page.getByRole('region', { name: 'Ergebnisübersicht' })
  const actions = page.locator('[data-page-header-actions]')
  const venues = actions.getByRole('link', { name: 'Orte', exact: true })
  const spaces = actions.getByRole('link', { name: 'Räume', exact: true })
  const refresh = actions.getByRole('button', { name: 'Aktualisieren', exact: true })
  for (const control of [venues, spaces, refresh])
    await expect(control).toHaveClass(/button-compact/)
  await expect(venues).toHaveAttribute('aria-current', 'page')
  await expect(spaces).not.toHaveAttribute('aria-current', 'page')
  await expect(actions.getByRole('button', { name: 'SQL / Datenherkunft' })).toBeEnabled()
  for (const value of ['organization', 'shared'] as const) {
    await scope.selectOption(value)
    await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
    await expect(page).toHaveURL(
      (url) => url.searchParams.get('scope') === value && url.searchParams.get('page') === '1',
    )
    await expect(summary).toContainText(`Ortstyp: ${venueScopeLabels[value]}`)
    await expect.poll(() => requests.at(-1)?.searchParams.get('scope')).toBe(value)
  }
  await page.goBack()
  await expect(scope).toHaveValue('organization')
  await expect(summary).toContainText(venueScopeLabels.organization)
  await page.goForward()
  await expect(scope).toHaveValue('shared')
  await page.getByRole('link', { name: 'Weiter', exact: true }).click()
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('scope') === 'shared' && url.searchParams.get('page') === '2',
  )
  await page.reload()
  await expect(scope).toHaveValue('shared')
  await expect(summary).toContainText(`Ortstyp: ${venueScopeLabels.shared}`)
  const before = requests.length
  await refresh.click()
  await expect.poll(() => requests.length).toBeGreaterThan(before)
  expect(requests.at(-1)?.searchParams.get('scope')).toBe('shared')
  await spaces.click()
  await expect(page).toHaveURL('/spaces')
  await expect(scope).toHaveCount(0)
  await expect(spaces).toHaveAttribute('aria-current', 'page')
  await expect(venues).not.toHaveAttribute('aria-current', 'page')
  await expect.poll(() => requests.at(-1)?.pathname).toBe('/api/admin/api/v1/spaces')
  expect(requests.at(-1)?.searchParams.has('scope')).toBe(false)
  await venues.click()
  await expect(scope).toHaveValue('shared')
  await expect(page).toHaveURL((url) => url.searchParams.get('scope') === 'shared')
  await scope.selectOption('organization')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(summary).toContainText(venueScopeLabels.organization)
  for (const width of [1440, 1024, 390, 360]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(scope).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    for (const control of [venues, spaces, refresh, scope])
      expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    if (info.project.name === 'desktop')
      await page.screenshot({ path: info.outputPath(`venues-scope-${width}.png`), fullPage: true })
  }
  empty = true
  await refresh.click()
  await expect(page.getByText('Keine Datensätze für diese Auswahl.', { exact: true })).toBeVisible()
  const resets = page.getByRole('button', { name: 'Filter zurücksetzen', exact: true })
  await expect(resets).toHaveCount(2)
  await resets.last().click()
  await expect(page).toHaveURL(
    (url) => !url.searchParams.has('scope') && url.searchParams.get('page') === '1',
  )
  await expect(scope).toHaveValue('')
  await expect(summary).not.toContainText('Ortstyp:')
  await scope.selectOption('shared')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/scope=shared/)
  await scope.selectOption('')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL((url) => !url.searchParams.has('scope'))
})
