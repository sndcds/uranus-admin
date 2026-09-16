import { test, expect } from '@playwright/test'
import { graphFixture, graphPath } from '../fixtures/graph'

test('native fullscreen reuses the graph and survives root/history navigation', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/api/admin/auth/session', (route) =>
    route.fulfill({ json: { subject: 'admin:test-only-operator', system_admin: true } }),
  )
  await page.route('**/api/admin/api/v1/graph?**', (route) => {
    const url = new URL(route.request().url())
    return route.fulfill({
      json: {
        ...graphFixture,
        root: {
          type: url.searchParams.get('root_type'),
          key: url.searchParams.get('root_key'),
        },
      },
    })
  })
  await page.goto(graphPath)
  await expect(page.locator('.graph-node')).toHaveCount(12)
  const workspace = page.locator('.graph-workspace')
  const enter = page.getByRole('button', { name: 'Graph im Vollbild anzeigen', exact: true })
  await expect(enter).toBeVisible()
  const svg = await workspace.locator('svg[role="group"]').elementHandle()
  const before = await workspace.locator('svg[role="group"]').getAttribute('viewBox')
  await page.screenshot({ path: info.outputPath('graph-normal.png'), fullPage: true })
  async function enterFullscreen() {
    await enter.click()
    // A click does not await requestFullscreen()/fullscreenchange. In mobile mode
    // that transition closes details, so finish it before selecting another node.
    await expect
      .poll(() => workspace.evaluate((element) => document.fullscreenElement === element))
      .toBe(true)
    const exit = page.getByRole('button', { name: 'Vollbild beenden', exact: true })
    await expect(exit).toBeVisible()
    await expect(exit).toHaveAttribute('aria-pressed', 'true')
  }
  await enterFullscreen()
  await expect(workspace.locator('svg[role="group"]')).not.toHaveAttribute('viewBox', before!)
  expect(await svg!.evaluate((element) => element.isConnected)).toBe(true)
  await expect(workspace.locator('svg[role="group"]')).toHaveCount(1)
  expect(
    await workspace.evaluate((element) => {
      const bounds = element.getBoundingClientRect()
      return Math.abs(bounds.width - innerWidth) < 2 && Math.abs(bounds.height - innerHeight) < 2
    }),
  ).toBe(true)
  await expect(workspace.getByLabel('Graphlegende')).toBeVisible()
  await expect(workspace.getByText('12 Knoten · 12 Beziehungen · Tiefe 2')).toBeVisible()
  const node = workspace.locator('.graph-node').filter({ hasText: 'Max Mustermann' })
  await node.focus()
  await page.keyboard.press('Enter')
  const panel = workspace.getByRole('complementary', { name: 'Knotendetails' })
  await expect(panel.getByRole('heading', { name: 'Max Mustermann' })).toBeVisible()
  await page.getByRole('button', { name: 'Details ausblenden', exact: true }).click()
  await expect(panel).toBeHidden()
  await page.getByRole('button', { name: 'Ansicht einpassen', exact: true }).click()
  await page.getByRole('button', { name: 'Details anzeigen', exact: true }).click()
  await expect(panel).toBeVisible()
  await page.getByRole('button', { name: 'Ansicht einpassen', exact: true }).click()
  await page.screenshot({ path: info.outputPath('graph-fullscreen.png') })
  await page.getByRole('button', { name: 'Vollbild beenden', exact: true }).click()
  await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true)
  await expect(enter).toBeFocused()
  await enterFullscreen()
  await workspace.locator('.graph-node').filter({ hasText: 'Max Mustermann' }).focus()
  await page.keyboard.press('Enter')
  await expect(panel.getByRole('heading', { name: 'Max Mustermann' })).toBeVisible()
  await panel.getByRole('button', { name: 'Als Ausgangspunkt verwenden', exact: true }).click()
  await expect(page).toHaveURL(/root_type=user/)
  await expect(panel.getByRole('heading', { name: 'Max Mustermann' })).toBeVisible()
  expect(
    await page.evaluate(() => document.fullscreenElement?.classList.contains('graph-workspace')),
  ).toBe(true)
  await page.goBack()
  await expect(page).toHaveURL(/root_type=organization/)
  await expect(page.locator('.graph-node')).toHaveCount(12)
  expect(
    await page.evaluate(() => document.fullscreenElement?.classList.contains('graph-workspace')),
  ).toBe(true)
  // Browser-originated exit (same fullscreenchange as Escape; no application click).
  await page.evaluate(() => document.exitFullscreen())
  await expect(enter).toHaveAttribute('aria-pressed', 'false')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await enterFullscreen()
  await workspace.locator('.graph-node').first().focus()
  await page.keyboard.press('Enter')
  await panel.getByRole('link', { name: 'Im Admin ansehen', exact: true }).click()
  await expect(page).toHaveURL(/\/activity\?/)
  await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true)
  expect(errors).toEqual([])
})
