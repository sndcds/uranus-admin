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
    globalSearchFixture('person@example.org').groups[0]!.items[0]!.action.href,
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
  await expect(page).toHaveURL(globalSearchFixture('Kühlhaus').groups[1]!.items[0]!.action.href)
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
