import { test, expect } from '../fixtures/authenticated'
import { enforceProductionCsp } from '../fixtures/record-csp'

test('approved homepage layout across desktop, tablet and mobile', async ({ page }, info) => {
  await enforceProductionCsp(page)
  for (const [name, width, height] of [
    ['desktop', 1672, 941],
    ['tablet', 834, 1194],
    ['mobile', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height })
    await page.goto('/research')
    await expect(page.getByLabel('Deine Recherchefrage')).toBeEnabled()
    await expect(page.getByText('KI-gestützte Kulturanalyse', { exact: true })).toBeVisible()
    await expect(
      page.getByRole('group', { name: 'Beispiele für Fragen' }).getByRole('button'),
    ).toHaveCount(3)
    await expect(page.getByRole('button', { name: 'Antwort anzeigen' })).toBeInViewport()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await expect(page.locator('.research-discovery-card')).toHaveCount(0)
    await expect(page.getByText('Kultur entdecken', { exact: true })).toHaveCount(0)
    if (name === 'desktop') {
      const composer = await page.locator('.research-composer').boundingBox()
      expect(composer!.width).toBe(1024)
      expect(composer!.height).toBeLessThan(125)
      expect(composer!.y).toBeGreaterThan(height * 0.75)
      expect(composer!.y + composer!.height).toBeLessThan(height)
    }
    await page.screenshot({ path: info.outputPath(`homepage-${name}.png`), fullPage: true })
  }
})
