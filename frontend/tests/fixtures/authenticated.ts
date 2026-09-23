import { test as base, expect, type Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'

// Real HttpOnly test sessions also reach SSR. Browser-only route mocks cannot
// authorize server rendering. The independent request fixture stays anonymous.
export const test = base.extend({
  page: async ({ page, context }, use) => {
    const response = await context.request.post('/api/admin/auth/login', {
      headers: { Origin: 'http://127.0.0.1:3100', 'X-Admin-CSRF': '1' },
      data: { login: 'operator', password: 'test-only-password' },
    })
    expect(response.status()).toBe(200)
    await page.route('**/__test-tiles/**', (route) => {
      expect(new URL(route.request().url()).pathname).toMatch(
        /^\/__test-tiles\/\d+\/\d+\/\d+\.png$/,
      )
      expect(new URL(route.request().url()).search).toBe('')
      return route.fulfill({
        contentType: 'image/svg+xml',
        path: fileURLToPath(new URL('./map-tile.svg', import.meta.url)),
      })
    })
    await use(page)
  },
})

async function openAccountDrawer(page: Page) {
  const drawer = page.getByRole('dialog', { name: 'Mobile Navigation' })
  if (await drawer.isVisible()) return false
  if ((page.viewportSize()?.width ?? 1024) >= 1024) return false
  const menu = page.getByRole('button', { name: 'Navigation öffnen' })
  await expect(menu).toBeVisible()
  await expect(menu).toBeEnabled()
  await menu.focus()
  await menu.press('Enter')
  await expect(drawer).toBeVisible()
  return true
}

async function closeAccountDrawer(page: Page, opened: boolean) {
  if (!opened) return
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Navigation öffnen' })).toBeFocused()
}

export async function expectLogoutAvailable(page: Page) {
  const visibleLogout = page
    .getByRole('button', { name: 'Abmelden', exact: true })
    .filter({ visible: true })
  if (await visibleLogout.isVisible()) {
    await expect(visibleLogout).toBeEnabled()
    return
  }
  const opened = await openAccountDrawer(page)
  await expect(visibleLogout).toBeVisible()
  await closeAccountDrawer(page, opened)
}

export async function expectCreateUnavailable(page: Page) {
  const opened = await openAccountDrawer(page)
  await expect(
    page.getByRole('button', { name: /\+ Datensatz/ }).filter({ visible: true }),
  ).toBeDisabled()
  await closeAccountDrawer(page, opened)
}

export async function logout(page: Page) {
  const visibleLogout = page
    .getByRole('button', { name: 'Abmelden', exact: true })
    .filter({ visible: true })
  if (!(await visibleLogout.isVisible())) await openAccountDrawer(page)
  await visibleLogout.click()
}
export { expect }
