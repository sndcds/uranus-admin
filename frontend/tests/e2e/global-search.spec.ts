import { inspectorHref } from '../../app/utils/inspector'
import { test, expect } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'
import { detailFixture, entityFixture, timelineFixture } from '../fixtures/entities'
import { globalSearchFixture } from '../fixtures/search'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/admin/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/search'))
      return route.fulfill({ json: globalSearchFixture(url.searchParams.get('q') || '') })
    if (url.pathname.endsWith('/summary')) return route.fulfill({ json: summary })
    if (url.pathname.endsWith('/timeline')) return route.fulfill({ json: timelineFixture('user') })
    for (const section of ['users', 'venues'] as const) {
      if (url.pathname.includes(`/${section}/`))
        return route.fulfill({ json: detailFixture(section) })
      if (url.pathname.endsWith(`/${section}`))
        return route.fulfill({ json: entityFixture(section) })
    }
    return route.fulfill({ json: findings })
  })
})

test('global keyboard navigation from Dashboard to an email user and local Arbeitsliste', async ({
  page,
}) => {
  await page.goto('/?period=24h')
  const trigger = page
    .getByRole('button', { name: 'Globale Suche öffnen' })
    .filter({ visible: true })
  await expect(trigger).toBeEnabled()
  await trigger.focus()
  await page.keyboard.press('Control+k')
  const dialog = page.getByRole('dialog', { name: 'Kulturbytes durchsuchen' })
  const input = dialog.getByRole('combobox')
  await expect(input).toBeFocused()
  await expect(dialog.getByRole('group', { name: 'Navigation', exact: true })).toBeVisible()
  // Native Tab navigation and Escape return to the original trigger.
  await page.keyboard.press('Tab')
  await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true)
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()
  await page.keyboard.press('Meta+k')
  await input.fill('person@example.org')
  const option = dialog.getByRole('option', { name: /person@example.org/ })
  await expect(option).toBeVisible()
  await expect(option).toHaveAttribute('aria-selected', 'true')
  await input.press('Enter')
  await expect(page).toHaveURL(
    inspectorHref(
      globalSearchFixture('person@example.org').groups[0]!.items[0]!.entity_type,
      globalSearchFixture('person@example.org').groups[0]!.items[0]!.entity_key,
    )!,
  )
  await expect(dialog).not.toBeVisible()
  await page.keyboard.press('Control+k')
  await input.fill('Arbeitsliste')
  await expect(dialog.getByRole('option', { name: 'Arbeitsliste', exact: true })).toBeVisible()
  await input.press('Enter')
  await expect(page).toHaveURL(/\/findings/)
})

test('visible trigger, grouped places, pointer selection and mobile geometry', async ({
  page,
}, info) => {
  await page.goto('/?period=24h')
  const trigger = page
    .getByRole('button', { name: 'Globale Suche öffnen' })
    .filter({ visible: true })
  await expect(trigger).toBeEnabled()
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: 'Kulturbytes durchsuchen' })
  await dialog.getByRole('combobox').fill('Kühlhaus')
  await expect(dialog.getByRole('group', { name: 'Organisationen', exact: true })).toBeVisible()
  await expect(dialog.getByRole('group', { name: 'Orte', exact: true })).toBeVisible()
  const venue = dialog.getByRole('option', { name: /Kühlhaus Flensburg/ })
  expect((await venue.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('global-search.png') })
  await venue.click()
  await expect(page).toHaveURL(
    inspectorHref(
      globalSearchFixture('Kühlhaus').groups[1]!.items[0]!.entity_type,
      globalSearchFixture('Kühlhaus').groups[1]!.items[0]!.entity_key,
    )!,
  )
  await expect(dialog).not.toBeVisible()
})

test('session loss closes the palette and clears protected results', async ({ page }) => {
  await page.goto('/?period=24h')
  await page.getByRole('button', { name: 'Globale Suche öffnen' }).filter({ visible: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Kulturbytes durchsuchen' })
  await dialog.getByRole('combobox').fill('person@example.org')
  await expect(dialog.getByRole('option')).toBeVisible()
  await page.route('**/api/admin/api/v1/search?**', (route) =>
    route.fulfill({
      status: 401,
      json: { error: { code: 'invalid_credentials', message: 'Unauthorized' } },
    }),
  )
  await dialog.getByRole('combobox').fill('expired@example.org')
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText('person@example.org')).toHaveCount(0)
})

test('shortcut from the SQL editor preserves its text and restores focus', async ({ page }) => {
  await page.unroute('**/api/admin/api/v1/**')
  await page.goto('/sql')
  const editor = page.getByRole('textbox', { name: 'SQL-Abfrage bearbeiten' })
  await expect(editor).toBeVisible()
  await editor.fill('SELECT 123; -- keep this text')
  await editor.press('Control+k')
  const dialog = page.getByRole('dialog', { name: 'Kulturbytes durchsuchen' })
  await expect(dialog.getByRole('combobox')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(editor).toBeFocused()
  await expect(editor).toHaveText('SELECT 123; -- keep this text')
})

test('palette geometry, focus and internal scroll stay stable through debounce, revalidation and errors', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      throw new Error(`CSP violation: ${event.effectiveDirective}`)
    })
  })
  if (process.env.TEST_PRODUCTION === '1') {
    await page.route('**/*', async (route) => {
      if (route.request().resourceType() !== 'document') return route.fallback()
      const response = await route.fetch()
      await route.fulfill({
        response,
        headers: {
          ...response.headers(),
          'content-security-policy':
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; worker-src 'none'; object-src 'none'; base-uri 'self'",
        },
      })
    })
  }
  const pending = new Map<string, import('@playwright/test').Route>()
  await page.route('**/api/admin/api/v1/search?**', (route) => {
    pending.set(new URL(route.request().url()).searchParams.get('q')!, route)
  })
  await page.goto('/?period=24h')
  await page.getByRole('button', { name: 'Globale Suche öffnen' }).filter({ visible: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Kulturbytes durchsuchen' })
  const input = dialog.getByRole('combobox')
  const results = dialog.locator('.search-results')
  const header = dialog.locator('.search-header')
  await expect(input).toBeFocused()
  const initial = (await dialog.boundingBox())!
  const initialHeader = (await header.boundingBox())!
  const assertStable = async () => {
    const box = (await dialog.boundingBox())!
    expect(Math.abs(box.height - initial.height)).toBeLessThanOrEqual(3)
    expect(Math.abs(box.y - initial.y)).toBeLessThanOrEqual(3)
    expect(Math.abs((await header.boundingBox())!.y - initialHeader.y)).toBeLessThanOrEqual(3)
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await expect(input).toBeFocused()
  }
  if (info.project.name === 'mobile') {
    expect(initial.height).toBeGreaterThanOrEqual(820)
    expect(initial.y).toBeGreaterThanOrEqual(0)
    expect(initial.y + initial.height).toBeLessThanOrEqual(844)
  }
  await page.screenshot({ path: info.outputPath('palette-initial.png') })
  // Freeze the browser clock so measurements really cover the debounce window.
  await page.clock.install()
  await page.clock.pauseAt(new Date(Date.now() + 1000))
  await input.fill('Kühlhaus')
  await page.clock.runFor(249)
  expect(pending.size).toBe(0)
  await assertStable()
  await page.clock.runFor(1)
  await expect.poll(() => pending.has('Kühlhaus')).toBe(true)
  await expect(dialog.getByRole('listbox')).toHaveAttribute('aria-busy', 'true')
  await assertStable()
  await pending.get('Kühlhaus')!.fulfill({ json: globalSearchFixture('Kühlhaus') })
  await expect(dialog.getByRole('option')).toHaveCount(2)
  await assertStable()
  await input.press('ArrowDown')
  await expect(dialog.getByRole('option', { selected: true })).toContainText('Kühlhaus Flensburg')

  await input.fill('Kühlhaus neu')
  await page.clock.runFor(249)
  await expect(dialog.getByRole('option')).toHaveCount(2)
  await expect(dialog.getByRole('option', { selected: true })).toContainText('Kühlhaus Flensburg')
  await assertStable()
  await page.clock.runFor(1)
  await expect.poll(() => pending.has('Kühlhaus neu')).toBe(true)
  await expect(dialog.getByText('Ergebnisse werden aktualisiert …')).toBeVisible()
  await expect(dialog.getByText('Datensätze für „Kühlhaus“')).toBeVisible()
  await assertStable()
  await page.screenshot({ path: info.outputPath('palette-loading.png'), animations: 'disabled' })
  const many = globalSearchFixture('Kühlhaus neu')
  many.groups = many.groups.map((group) => ({
    ...group,
    items: Array.from({ length: 5 }, (_, index) => ({
      ...group.items[0]!,
      entity_key: `20000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
      label: `${group.items[0]!.label} · Treffer ${index + 1}`,
      action: {
        ...group.items[0]!.action,
        entity_key: `20000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
        href: `${group.items[0]!.action.href.slice(0, -36)}20000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
      },
    })),
  }))
  await pending.get('Kühlhaus neu')!.fulfill({ json: many })
  await expect(dialog.getByRole('option')).toHaveCount(10)
  await expect(dialog.getByRole('option', { selected: true })).toContainText('Treffer 1')
  await expect(dialog.getByText('Datensätze für „Kühlhaus neu“')).toBeVisible()
  await assertStable()
  await page.screenshot({ path: info.outputPath('palette-results.png') })
  expect(await results.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
  await results.evaluate((el) => {
    el.scrollTop = 100
  })
  const scrollTop = await results.evaluate((el) => el.scrollTop)
  expect(scrollTop).toBeGreaterThan(0)
  await assertStable()
  await input.fill('Kühlhaus neuer')
  expect(await results.evaluate((el) => el.scrollTop)).toBe(scrollTop)
  await page.clock.runFor(250)
  await expect.poll(() => pending.has('Kühlhaus neuer')).toBe(true)
  await pending.get('Kühlhaus neuer')!.fulfill({
    status: 503,
    json: { error: { code: 'service_unavailable', message: 'Unavailable' } },
  })
  await expect(dialog.getByText('Neue Suche konnte nicht geladen werden.')).toBeVisible()
  await expect(dialog.getByRole('option')).toHaveCount(10)
  expect(await results.evaluate((el) => el.scrollTop)).toBe(scrollTop)
  await assertStable()
  await input.fill('missing')
  await page.clock.runFor(250)
  await expect.poll(() => pending.has('missing')).toBe(true)
  await pending.get('missing')!.fulfill({ json: globalSearchFixture('missing') })
  await expect(dialog.getByText('Keine passenden Ergebnisse gefunden.')).toBeVisible()
  await expect(input).not.toHaveAttribute('aria-activedescendant')
  await assertStable()
  await input.fill('person@example.org')
  await page.clock.runFor(250)
  await expect.poll(() => pending.has('person@example.org')).toBe(true)
  await pending
    .get('person@example.org')!
    .fulfill({ json: globalSearchFixture('person@example.org') })
  await expect(dialog.getByRole('option')).toHaveCount(1)
  await assertStable()
  await input.fill('k')
  await expect(dialog.getByRole('group', { name: 'Navigation', exact: true })).toBeVisible()
  await assertStable()
  expect(errors).toEqual([])
})

test('nine groups retain mobile geometry and large targets with long labels', async ({ page }) => {
  const { allGlobalSearchFixture } = await import('../fixtures/search')
  const data = allGlobalSearchFixture()
  for (const group of data.groups) {
    group.items[0]!.label += ' SehrLangerAnzeigename'.repeat(20)
    group.items[0]!.subtitle += ' LangerKontext'.repeat(20)
  }
  await page.route('**/api/admin/api/v1/search?**', (route) => route.fulfill({ json: data }))
  await page.goto('/?period=24h')
  // The document shortcut is registered during hydration, after SSR renders the shell.
  await expect(
    page.getByRole('button', { name: 'Globale Suche öffnen' }).filter({ visible: true }),
  ).toBeEnabled()
  await page.keyboard.press('Control+k')
  const dialog = page.getByRole('dialog', { name: 'Kulturbytes durchsuchen' })
  const input = dialog.getByRole('combobox')
  await input.fill(data.query)
  await expect(dialog.getByRole('group')).toHaveCount(9)
  for (const label of [
    'Benutzer',
    'Organisationen',
    'Orte',
    'Räume',
    'Veranstaltungen',
    'Termine',
    'Bilder',
    'Partneranfragen',
    'Teameinladungen',
  ]) {
    await expect(dialog.getByRole('group', { name: label, exact: true })).toHaveCount(1)
  }
  for (const option of await dialog.getByRole('option').all()) {
    expect((await option.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  }
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  for (let index = 0; index < 8; index++) await input.press('ArrowDown')
  await expect(dialog.getByRole('option', { selected: true })).toContainText('Beigetreten')
  await input.press('Enter')
  await expect(page).toHaveURL(
    inspectorHref(data.groups[8]!.items[0]!.entity_type, data.groups[8]!.items[0]!.entity_key)!,
  )
})
