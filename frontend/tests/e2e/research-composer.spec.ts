import type { Page } from '@playwright/test'
import { test, expect } from '../fixtures/authenticated'
import { executionResponse, countQuestion } from '../fixtures/research-execution'
import { groupedExecutionResponse } from '../fixtures/research-grouping'
import { researchSuggestions } from '../fixtures/research-suggestions'
import { enforceProductionCsp } from '../fixtures/record-csp'

const root = '/api/admin/api/v1/research'
test.beforeEach(async ({ page }) => {
  await enforceProductionCsp(page)
  await page.route(`**${root}/suggestions?**`, (route) =>
    route.fulfill({
      json: { request_id: researchSuggestions.request_id, suggestions: [] },
    }),
  )
})

async function composerBounds(page: Page) {
  const main = page.locator('main#main-content')
  const composer = main.locator('.research-composer')
  await expect(composer.locator('textarea')).toHaveCount(1)
  await expect(composer).toBeInViewport()
  await expect(page.locator('aside textarea, nav textarea, input[type="file"]')).toHaveCount(0)
  await expect(composer.getByRole('button')).toHaveCount(1)
  await expect(composer.getByRole('button', { name: 'Antwort anzeigen' })).toBeInViewport()
  await expect(composer.locator('.research-composer-count')).toBeVisible()
  const box = (await composer.boundingBox())!
  const mainBox = (await main.boundingBox())!
  expect(box.x).toBeGreaterThan(mainBox.x)
  expect(box.x + box.width).toBeLessThan(mainBox.x + mainBox.width)
  expect(Math.abs(box.x + box.width / 2 - (mainBox.x + mainBox.width / 2))).toBeLessThan(2)
  expect(box.width).toBeLessThanOrEqual(816)
  expect(box.y + box.height).toBeLessThan(page.viewportSize()!.height)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  if (page.viewportSize()!.width >= 1024) {
    const sidebar = (await page.locator('aside').boundingBox())!
    expect(sidebar.width).toBe(224)
    expect(box.x).toBeGreaterThan(sidebar.x + sidebar.width)
  } else {
    expect(box.width).toBeGreaterThan(mainBox.width - 64)
  }
  return box
}

for (const state of ['count', 'grouped', 'clarification', 'error', 'long-result'] as const) {
  test(`persistent main-column composer: empty → loading → ${state}`, async ({ page }, info) => {
    let release!: () => void
    let requests = 0
    const response =
      state === 'grouped' || state === 'long-result'
        ? groupedExecutionResponse()
        : executionResponse(state === 'clarification' ? 'needs_clarification' : 'count')
    if (state === 'long-result' && response.result.kind === 'grouped') {
      const item = response.result.items[0]!
      response.result.items = Array.from({ length: 20 }, (_, index) => ({
        ...item,
        coordinates: item.coordinates.map((coordinate) =>
          coordinate.dimension === 'event_type'
            ? { ...coordinate, key: String(index), name: `Veranstaltungstyp ${index}` }
            : coordinate,
        ),
      }))
    }
    await page.route(`**${root}/query`, async (route) => {
      requests++
      await new Promise<void>((resolve) => {
        release = resolve
      })
      await route.fulfill(
        state === 'error'
          ? {
              status: 503,
              json: { error: { code: 'research_planner_unavailable', message: 'Unavailable' } },
            }
          : { json: response },
      )
    })
    await page.goto('/research')
    const input = page.getByLabel('Deine Recherchefrage')
    await expect(input).toBeEnabled()
    const original = await input.elementHandle()
    const initial = await composerBounds(page)
    await input.fill(response.query)
    await input.press('Enter')
    await expect(page.getByText('Frage wird ausgewertet …')).toBeVisible()
    await input.press('Control+Enter')
    expect(requests).toBe(1)
    const pending = await composerBounds(page)
    expect(pending.y + pending.height).toBeCloseTo(initial.y + initial.height, 0)
    release()
    if (state === 'error')
      await expect(page.getByRole('button', { name: 'Erneut versuchen' })).toBeVisible()
    else if (state === 'clarification')
      await expect(page.getByRole('heading', { name: 'Frage präzisieren' })).toBeVisible()
    else if (state === 'count') await expect(page.getByTestId('research-count')).toBeVisible()
    else
      await expect(page.getByRole('table', { name: 'Mehrdimensionale Auswertung' })).toBeVisible()
    const final = await composerBounds(page)
    expect(final.y).toBeCloseTo(pending.y, 0)
    expect(final.width).toBeCloseTo(initial.width, 0)
    expect(await original!.evaluate((element) => element.isConnected)).toBe(true)
    await expect(input).toHaveValue(response.query)
    if (state === 'long-result') {
      const content = page.locator('.research-question-content')
      expect(await content.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(
        true,
      )
      await content.evaluate((element) => {
        element.scrollTop = element.scrollHeight
      })
      const last = await page.getByRole('table').locator('tbody tr').last().boundingBox()
      expect(last!.y + last!.height).toBeLessThan(final.y)
      expect((await composerBounds(page)).y).toBeCloseTo(final.y, 0)
    }
    await page.screenshot({ path: info.outputPath(`composer-${state}.png`), fullPage: true })
  })
}

test('bounded auto-grow, IME and suggestions above the composer', async ({ page }) => {
  await page.route(`**${root}/suggestions?**`, (route) =>
    route.fulfill({ json: researchSuggestions }),
  )
  let requests = 0
  await page.route(`**${root}/query`, (route) => {
    requests++
    return route.fulfill({ json: executionResponse() })
  })
  await page.goto('/research')
  const input = page.getByLabel('Deine Recherchefrage')
  await expect(input).toBeEnabled()
  await input.fill('Wie viele')
  await expect(page.getByRole('listbox')).toBeVisible()
  const composer = (await page.locator('.research-composer').boundingBox())!
  const list = (await page.getByRole('listbox').boundingBox())!
  expect(list.y + list.height).toBeLessThanOrEqual(composer.y)
  await input.dispatchEvent('keydown', { key: 'Enter', isComposing: true })
  expect(requests).toBe(0)
  await input.press('Escape')
  await input.fill(Array.from({ length: 30 }, () => 'Eine längere Frage').join('\n'))
  const size = await input.evaluate((element) => ({
    height: element.clientHeight,
    scroll: element.scrollHeight,
    overflow: getComputedStyle(element).overflowY,
  }))
  expect(size.height).toBeLessThanOrEqual(192)
  expect(size.scroll).toBeGreaterThan(size.height)
  expect(size.overflow).toBe('auto')
  await expect(page.getByRole('button', { name: 'Antwort anzeigen' })).toBeInViewport()
  await input.fill(countQuestion)
  expect((await input.boundingBox())!.height).toBeLessThan(size.height)
})

test('composer remains usable when the mobile content viewport shrinks', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 440 })
  await page.goto('/research')
  const input = page.getByLabel('Deine Recherchefrage')
  await expect(input).toBeEnabled()
  await input.fill('Eine Frage\nmit mehreren\nZeilen')
  await composerBounds(page)
  await expect(input).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Antwort anzeigen' })).toBeInViewport()
})
