import { test, expect } from '@playwright/test'

test('durable check goes from queued to running and success independently of start request', async ({
  page,
}) => {
  let started = false
  let polls = 0
  const job = {
    id: '10000000-0000-4000-8000-000000000001',
    started_at: '2026-09-16T10:00:00Z',
    finished_at: null,
    status: 'queued',
    rule_count: 0,
    finding_count: 0,
    error_message: null,
    rule_results: {},
  }
  await page.route('**/api/admin/api/v1/check-runs**', (route) => {
    if (route.request().method() === 'POST') {
      started = true
      polls = 0
      return route.fulfill({ status: 202, json: job })
    }
    const status = polls++ < 2 ? 'queued' : polls < 4 ? 'running' : 'success'
    return route.fulfill({
      json: {
        items: started ? [{ ...job, status }] : [],
        pagination: { page: 1, page_size: 50, total: started ? 1 : 0, pages: started ? 1 : 0 },
      },
    })
  })
  await page.goto('/checks')
  await expect(page.getByText('Noch keine gespeicherten Prüfläufe.')).toBeVisible()
  await page.getByRole('button', { name: 'Prüflauf starten' }).click()
  await expect(page.getByText('Wartet auf Worker', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Prüfung läuft …' })).toBeDisabled()
  await expect(page.getByText('Läuft', { exact: true })).toBeVisible()
  await expect(page.getByText('Erfolgreich', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Prüflauf starten' })).toBeEnabled()
})
