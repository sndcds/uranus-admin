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
    ).toHaveCount(4)
    await expect(page.getByRole('button', { name: 'Antwort anzeigen' })).toBeInViewport()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const cards = page.locator('.research-discovery-card')
    await expect(cards).toHaveCount(4)
    const boxes = await cards.evaluateAll((elements) =>
      elements.map((element) => {
        const { x, y, height } = element.getBoundingClientRect()
        return { x, y, height }
      }),
    )
    if (name === 'desktop') {
      expect(new Set(boxes.map((box) => box.y)).size).toBe(1)
      expect(boxes[0]!.height).toBeLessThanOrEqual(175)
      const composer = await page.locator('.research-composer').boundingBox()
      expect(composer!.width).toBeGreaterThan(790)
      expect(composer!.width).toBeLessThan(840)
      expect(composer!.height).toBeLessThan(125)
      expect(composer!.y).toBeGreaterThan(340)
      expect(composer!.y).toBeLessThan(380)
    } else {
      expect(new Set(boxes.map((box) => box.x)).size).toBe(name === 'tablet' ? 2 : 1)
    }
    await page.screenshot({ path: info.outputPath(`homepage-${name}.png`), fullPage: true })
  }
})
