import { test, expect } from '../fixtures/authenticated'
import { findings } from '../fixtures/api'
import { diagnosticDefinition, diagnosticResult } from '../fixtures/sql-diagnostics'

test('persisted resolved finding exposes a lazy read-only diagnostic and copy action', async ({
  page,
}) => {
  let definitions = 0
  let executions = 0
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (text: string) => {
          ;(window as typeof window & { copiedSql?: string }).copiedSql = text
        },
      },
    })
  })
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/sql-diagnostic/execute')) {
      executions++
      expect(route.request().postDataJSON()).toEqual({ finding_id: findings.items[0]!.id })
      return route.fulfill({
        json: {
          ...diagnosticResult,
          rows: diagnosticResult.rows.map((row) => ({ ...row, point_missing: false })),
          evaluation: {
            ...diagnosticResult.evaluation,
            matched: false,
            message: 'Aktueller Datenstand erfüllt die Regel nicht mehr.',
            checks: [],
          },
        },
      })
    }
    if (url.pathname.endsWith('/sql-diagnostic')) {
      definitions++
      expect(url.searchParams.get('finding_id')).toBe(findings.items[0]!.id)
      return route.fulfill({ json: diagnosticDefinition })
    }
    return route.fulfill({
      json: { ...findings, items: [{ ...findings.items[0], status: 'resolved' }] },
    })
  })
  await page.goto('/findings')
  await page.getByRole('button', { name: 'Befund zu Test-Hafenbühne ansehen' }).click()
  const dialog = page.getByRole('dialog', { name: 'Test-Hafenbühne' })
  expect(definitions).toBe(0)
  expect(executions).toBe(0)
  await dialog.locator('summary').filter({ hasText: 'SQL-Diagnose' }).click()
  await expect(dialog.locator('code')).toContainText('WHERE uuid = :entity_key')
  expect(executions).toBe(0)
  await dialog.getByRole('button', { name: 'SQL kopieren', exact: true }).click()
  await expect(dialog.getByText('SQL kopiert', { exact: true })).toBeVisible()
  expect(
    await page.evaluate(() => (window as typeof window & { copiedSql?: string }).copiedSql),
  ).toBe(diagnosticDefinition.copy_sql)
  await dialog.getByRole('button', { name: 'Prüfen', exact: true }).click()
  await expect(dialog.getByText('Aktueller Datenstand erfüllt die Regel nicht mehr.')).toBeVisible()
  expect(executions).toBe(1)
  await expect(dialog.getByRole('table')).toContainText('point_missing')
  await expect(dialog.getByText('TOP-SECRET-FIXTURE')).toHaveCount(0)
})
