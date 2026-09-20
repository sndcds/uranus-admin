import { test, expect } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'
import { detailFixture } from '../fixtures/entities'
import definitions from '../fixtures/sql-provenance.json' with { type: 'json' }
import { provenanceDefinitionSchema } from '../../shared/sql-provenance'

const cases = [
  { view: 'dashboard', path: '/?period=24h', expected: { period: '24h' } },
  {
    view: 'findings',
    path: '/findings?severity=error&active_only=true',
    expected: { severity: 'error', active_only: 'true' },
  },
  {
    view: 'venues.detail',
    path: `/venues/${detailFixture('venues').item.entity_key}`,
    expected: {},
  },
  {
    view: 'queues.partner_requests',
    path: '/queues/partner_requests?status=pending',
    expected: { status: 'pending' },
  },
] as const
for (const scenario of cases)
  test(`${scenario.view} provenance is lazy, filtered, read-only and keyboard accessible`, async ({
    page,
  }) => {
    let loads = 0
    const executions: string[] = []
    const definition = provenanceDefinitionSchema.parse(definitions[scenario.view])
    await page.addInitScript(() =>
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: async (text: string) => {
            ;(window as typeof window & { copiedSql?: string }).copiedSql = text
          },
        },
      }),
    )
    await page.route('**/api/admin/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.includes('/sql-provenance/')) {
        if (url.pathname.endsWith('/execute')) {
          const sourceId = url.pathname.split('/').at(-2)!
          executions.push(sourceId)
          const selected = definition.sources.find((source) => source.id === sourceId)!
          expect(route.request().postDataJSON()).toEqual(definition.parameters)
          if (executions.length === 2)
            return route.fulfill({
              status: 504,
              json: { error: { code: 'diagnostic_timeout', message: 'Safe timeout' } },
            })
          return route.fulfill({
            json: {
              source_id: sourceId,
              datasource: selected.datasource,
              columns: ['count'],
              rows: [{ count: 17 }],
              row_count: 1,
              duration_ms: 4,
              observed_at: definition.observed_at,
              truncated: false,
            },
          })
        }
        loads++
        for (const [key, value] of Object.entries(scenario.expected))
          expect(url.searchParams.get(key)).toBe(value)
        return route.fulfill({ json: definition })
      }
      if (url.pathname.endsWith('/summary')) return route.fulfill({ json: summary })
      if (url.pathname.includes('/venues/')) return route.fulfill({ json: detailFixture('venues') })
      if (url.pathname.includes('/work-queues/'))
        return route.fulfill({
          json: {
            kind: 'partner_requests',
            items: [],
            pagination: { page: 1, page_size: 50, total: 0, pages: 0 },
            observed_at: definition.observed_at,
          },
        })
      return route.fulfill({ json: findings })
    })
    await page.goto(scenario.path)
    const button = page.getByRole('button', { name: 'SQL / Datenherkunft', exact: true })
    await expect(button).toBeEnabled()
    expect(loads).toBe(0)
    expect(executions).toHaveLength(0)
    await button.focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'SQL / Datenherkunft' })
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('code')).toHaveCount(definition.sources.length)
    expect(executions).toHaveLength(0)
    const first = dialog.getByRole('region', { name: definition.sources[0]!.title, exact: true })
    await first.getByRole('button', { name: 'SQL kopieren', exact: true }).click()
    await expect(first.getByText('SQL kopiert', { exact: true })).toBeVisible()
    expect(
      await page.evaluate(() => (window as typeof window & { copiedSql?: string }).copiedSql),
    ).toBe(definition.sources[0]!.copy_sql)
    await first.getByRole('button', { name: 'Ausführen', exact: true }).click()
    await expect(first.getByRole('table')).toContainText('17')
    expect(executions).toEqual([definition.sources[0]!.id])
    const second = dialog.getByRole('region', { name: definition.sources[1]!.title, exact: true })
    await second.getByRole('button', { name: 'Ausführen', exact: true }).click()
    await expect(second.getByRole('alert')).toContainText('Zeitlimit')
    await expect(first.getByRole('table')).toContainText('17')
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
    await expect(button).toBeFocused()
    await expect(page.getByText('TOP-SECRET')).toHaveCount(0)
  })
